"""
Scrape Ojibwe translations to build English-Ojibwe dictionaries.

This module scrapes translations from online sources, stores raw data in JSON,
processes it into validated entries, performs optional semantic analysis,
and syncs all data to Firestore with proper versioning.
"""
import asyncio
import json
import os
import sqlite3
import sys
import time
from typing import Dict, List, Set, Union

import aiohttp
from asgiref.sync import sync_to_async
from bs4 import BeautifulSoup
from tqdm import tqdm

# Add base directory to system path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# Configure Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vota_backend.settings")
import django

django.setup()

from translations.utils.logging_config import setup_logging

setup_logging()
import logging

logger = logging.getLogger("translations.utils.ojibwe_scraper")

from translations.models import (
    create_english_to_ojibwe_local,
    create_ojibwe_to_english_local,
    create_semantic_match_local,
    get_all_english_to_ojibwe,
    get_all_ojibwe_to_english,
    get_all_semantic_matches,
    sync_english_dict_to_firestore,
    sync_to_firestore,
    get_firestore_version,
    set_firestore_version,
    create_missing_translation_local,
)
from translations.utils.frequencies import WORD_FREQUENCIES
from translations.utils.get_dict_size import get_english_dict_size
from translations.utils.process_raw_data import load_raw_data, save_raw_data, process_raw_data

# Scraping configuration
URLS = [
    "https://ojibwe.lib.umn.edu",
    "https://glosbe.com/en/oj",
]
TRANSLATION_THRESHOLD = 0.2  # 20% threshold
SCRAPE_LIMIT = 1000
OJIBWE_ALPHABET = {
    "a", "aa", "b", "d", "e", "g", "h", "i", "ii", "j", "k", "m", "n",
    "o", "oo", "p", "s", "t", "u", "w", "y", "z", "zh",
}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    ),
}
RAW_DATA_PATH = os.path.join(BASE_DIR, "data", "raw_ojibwe_english_dict.json")
TIMESTAMP_PATH = os.path.join(BASE_DIR, "data", "timestamps.json")
ONE_MONTH_SECONDS = 30 * 24 * 60 * 60
SEMANTIC_THRESHOLD = 0.7


def load_timestamps() -> Dict[str, float]:
    """Load timestamps from JSON file."""
    try:
        with open(TIMESTAMP_PATH, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return {"last_scrape": 0, "last_sync": 0}


def save_timestamps(timestamps: Dict[str, float]) -> None:
    """Save timestamps to JSON file."""
    with open(TIMESTAMP_PATH, "w", encoding="utf-8") as file:
        json.dump(timestamps, file)
    logger.info("Updated timestamps in timestamps.json")


async def get_existing_translations_count() -> int:
    """Count existing English-to-Ojibwe translations in Firestore."""
    translations = await sync_to_async(get_all_english_to_ojibwe)()
    count = len(translations)
    logger.info(f"Found {count} existing English-to-Ojibwe translations in Firestore.")
    return count


async def check_databases_populated() -> bool:
    """Check if translation databases are populated."""
    try:
        english_to_ojibwe = await sync_to_async(get_all_english_to_ojibwe)()
        ojibwe_to_english = await sync_to_async(get_all_ojibwe_to_english)()
        populated = bool(english_to_ojibwe or ojibwe_to_english)
        logger.info(f"Databases populated: {populated}")
        return populated
    except Exception as e:
        logger.error(f"Error checking database population: {e}")
        return False


async def prompt_to_scrape() -> bool:
    """Prompt user to scrape if databases are populated."""
    if await check_databases_populated():
        print("\nDatabases are already populated with translation entries.")
        print("Do you want to proceed with scraping? (Y/n): ", end="")
        response = input().strip().lower()
        return response in ("", "y", "yes")
    logger.info("Databases are empty, proceeding with scraping.")
    return True


async def fetch_url(
    session: aiohttp.ClientSession,
    url: str,
    semaphore: asyncio.Semaphore,
    retries: int = 3,
) -> str:
    """Fetch a URL with rate limiting and retries."""
    async with semaphore:
        for attempt in range(retries):
            try:
                async with session.get(url, headers=HEADERS, timeout=10) as response:
                    if response.status == 429:
                        retry_after = int(response.headers.get("Retry-After", 60))
                        logger.warning(f"Rate limited on {url}. Waiting {retry_after}s.")
                        await asyncio.sleep(retry_after)
                        continue
                    response.raise_for_status()
                    return await response.text()
            except aiohttp.ClientError as e:
                if attempt == retries - 1:
                    logger.error(f"Failed to fetch {url} after {retries} attempts: {e}")
                    return ""
                logger.warning(f"Attempt {attempt + 1}/{retries} failed for {url}: {e}")
                await asyncio.sleep(2**attempt)
        return ""


async def scrape_ojibwe_page(
    session: aiohttp.ClientSession,
    base_url: str,
    word: str,
    semaphore: asyncio.Semaphore,
) -> List[Dict[str, Union[str, List[str]]]]:
    """Scrape a single page for Ojibwe translations."""
    translations = []
    url = (
        f"{base_url}?utf8=%E2%9C%93&q={word}&search_field=all_fields"
        if "ojibwe.lib" in base_url
        else f"{base_url}/{word}"
    )

    html = await fetch_url(session, url, semaphore)
    if not html:
        return translations

    soup = BeautifulSoup(html, "html.parser")
    ojibwe_text = None
    english_text = word

    if "ojibwe.lib" in base_url:
        entry = soup.select_one(".search-results .main-entry-search")
        if entry:
            english_div = entry.select_one(".english-search-main-entry")
            if english_div:
                lemma_span = english_div.select_one(".main-entry-title .lemma")
                ojibwe_text = lemma_span.text.strip() if lemma_span else None
                definition_div = entry.select_one(".definition")
                definition = (
                    definition_div.get_text(separator=" ").strip()
                    if definition_div
                    else english_div.get_text(separator=" ").strip()
                )
                english_texts = [english_text]
                if ojibwe_text:
                    translations.append({
                        "ojibwe_text": ojibwe_text,
                        "english_text": english_texts,
                        "definition": definition
                    })
    elif "glosbe.com" in base_url:
        for item in soup.select("div.translation__item"):
            ojibwe_span = item.find("span", attrs={"lang": "oj"})
            if ojibwe_span and (ojibwe_text := ojibwe_span.text.strip()):
                definition = item.get_text(separator=" ").strip()
                translations.append({
                    "ojibwe_text": ojibwe_text,
                    "english_text": [english_text],
                    "definition": definition
                })

    if translations:
        logger.info(f"Scraped translation for '{word}' from {base_url}")
    return translations


async def scrape_full_dictionary(base_url: str) -> List[Dict[str, Union[str, List[str]]]]:
    """Scrape translations from a single website."""
    translations = []
    semaphore = asyncio.Semaphore(10)
    async with aiohttp.ClientSession() as session:
        if "ojibwe.lib" in base_url:
            for letter in OJIBWE_ALPHABET:
                url = f"{base_url}/browse/ojibwe/{letter}"
                html = await fetch_url(session, url, semaphore)
                if not html:
                    continue
                soup = BeautifulSoup(html, "html.parser")
                for entry in soup.select(".search-results .main-entry-search"):
                    english_div = entry.select_one(".english-search-main-entry")
                    if english_div:
                        lemma_span = english_div.select_one(".main-entry-title .lemma")
                        ojibwe_text = lemma_span.text.strip() if lemma_span else None
                        if not ojibwe_text:
                            continue
                        definition = (
                            entry.select_one(".definition").get_text(separator=" ").strip()
                            if entry.select_one(".definition")
                            else english_div.get_text(separator=" ").strip()
                        )
                        translations.append({
                            "ojibwe_text": ojibwe_text,
                            "english_text": [definition.split(",")[0].strip()],
                            "definition": definition
                        })
                await asyncio.sleep(0.1)
        else:
            english_words = await get_english_words()
            tasks = [
                scrape_ojibwe_page(session, base_url, word, semaphore)
                for word in english_words[:SCRAPE_LIMIT]
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    translations.extend(result)
    return translations


async def get_english_words() -> List[str]:
    """Fetch English words from SQLite."""
    try:
        conn = await sync_to_async(sqlite3.connect)("translations.db")
        cursor = await sync_to_async(conn.cursor)()
        await sync_to_async(cursor.execute)("SELECT word FROM english_dict")
        words = [row[0] for row in await sync_to_async(cursor.fetchall)()]
        await sync_to_async(conn.close)()
        return words
    except sqlite3.Error as e:
        logger.error(f"Error fetching English words: {e}")
        return []


def is_valid_translation(ojibwe_text: str, english_texts: List[str]) -> bool:
    """Validate a translation."""
    if not ojibwe_text or not english_texts:
        return False
    if ojibwe_text.lower() in [e.lower() for e in english_texts]:
        return False
    return True


def check_duplicates(new_translations: List[Dict], existing_translations: List[Dict]) -> List[Dict]:
    """Remove duplicate translations."""
    existing_set = {(t["english_text"], t["ojibwe_text"]) for t in existing_translations}
    unique_new = [
        t for t in new_translations
        if (t["english_text"][0], t["ojibwe_text"]) not in existing_set
    ]
    logger.info(f"Filtered {len(new_translations) - len(unique_new)} duplicates, {len(unique_new)} new translations.")
    return unique_new


def check_semantic_duplicates(new_matches: List[Dict], existing_matches: List[Dict]) -> List[Dict]:
    """Remove duplicate semantic matches."""
    existing_set = {(m["english_text"], m["ojibwe_text"]) for m in existing_matches}
    unique_new = [
        m for m in new_matches
        if (m["english_text"], m["ojibwe_text"]) not in existing_set
    ]
    return unique_new


async def scrape_ojibwe_async() -> List[Dict[str, Union[str, List[str]]]]:
    """
    Scrape translations, process data, and sync to Firestore with conditional versioning.

    Ensures semantic analysis is performed if new translations are added or if no semantic
    matches exist in Firestore, guaranteeing frontend data availability.
    Versioning logic:
    - If no semantic matches exist in Firestore, sync without incrementing the version.
    - If semantic analysis yields new matches, increment the version.
    - Otherwise, use the current version.
    """
    timestamps = load_timestamps()
    current_time = time.time()

    # Load existing raw data as a starting point
    raw_translations = load_raw_data(RAW_DATA_PATH)
    if not raw_translations:
        logger.info("No existing raw data found, initializing empty list.")
        raw_translations = []

    # Determine if scraping should occur
    should_scrape = await prompt_to_scrape()
    if should_scrape:
        # Check if scraping is needed based on time and coverage
        dict_size = await sync_to_async(get_english_dict_size)()
        translation_count = await get_existing_translations_count()
        coverage = translation_count / dict_size if dict_size > 0 else 0
        time_since_last_scrape = current_time - timestamps.get("last_scrape", 0)

        if time_since_last_scrape >= ONE_MONTH_SECONDS or coverage < TRANSLATION_THRESHOLD:
            logger.info("Performing scrape due to time elapsed or insufficient coverage.")
            new_translations = []
            for url in URLS:
                scraped = await scrape_full_dictionary(url)
                new_translations.extend(scraped)
            if new_translations:
                raw_translations.extend(new_translations)
                save_raw_data(raw_translations, RAW_DATA_PATH)
                timestamps["last_scrape"] = current_time
                save_timestamps(timestamps)
                logger.info(f"Scraped {len(new_translations)} new translations.")
            else:
                logger.warning("No new translations scraped.")
        else:
            logger.info("Skipping scrape: Recent scrape and sufficient coverage.")
    else:
        logger.info("User opted not to scrape. Proceeding with existing data.")

    # Process raw data into validated translations
    validated_translations = process_raw_data(raw_translations)
    if not validated_translations:
        logger.warning("No validated translations available after processing.")
        return []

    # Sync english_dict to Firestore (optimized to skip if already present)
    await sync_to_async(sync_english_dict_to_firestore)()
    logger.info("Synced english_dict to Firestore (or skipped if already present).")

    # Pull existing translations from Firestore
    existing_translations = await sync_to_async(get_all_english_to_ojibwe)()
    logger.info(f"Pulled {len(existing_translations)} existing translations.")

    # Store new translations in SQLite
    unique_new_translations = check_duplicates(validated_translations, existing_translations)
    cleaned_translations = [
        t for t in unique_new_translations
        if is_valid_translation(t["ojibwe_text"], t["english_text"])
    ]
    current_version = await sync_to_async(get_firestore_version)()
    for entry in cleaned_translations:
        await sync_to_async(create_ojibwe_to_english_local)(
            entry["ojibwe_text"], entry["english_text"], version=current_version
        )
        for e_text in entry["english_text"]:
            await sync_to_async(create_english_to_ojibwe_local)(
                e_text, entry["ojibwe_text"], entry["definition"], version=current_version
            )
    logger.info(f"Stored {len(cleaned_translations)} translations in SQLite.")

    # Compute and store missing common translations
    top_n = 1000
    sorted_words = sorted(WORD_FREQUENCIES.items(), key=lambda x: x[1], reverse=True)[:top_n]
    common_words = {word.lower() for word, _ in sorted_words if len(word) >= 2}
    translated_english = {t["english_text"].lower() for t in existing_translations}
    missing_common_words = common_words - translated_english
    missing_common_words = sorted(
        missing_common_words, key=lambda x: WORD_FREQUENCIES.get(x, 0), reverse=True
    )
    for word in missing_common_words:
        frequency = WORD_FREQUENCIES.get(word, 0)
        await sync_to_async(create_missing_translation_local)(
            english_text=word, frequency=frequency, version=current_version
        )
    logger.info(f"Stored {len(missing_common_words)} missing translations.")

    # Check if semantic matches exist in Firestore
    existing_semantic_matches = await sync_to_async(get_all_semantic_matches)()
    has_existing_semantic_matches = bool(existing_semantic_matches)
    logger.info(
        f"Firestore has {'some' if has_existing_semantic_matches else 'no'} existing semantic matches."
    )

    # Perform semantic analysis if new translations or no existing matches
    semantic_matches = []
    perform_analysis = (
        cleaned_translations or not has_existing_semantic_matches
    )
    if perform_analysis:
        print("\nPerforming semantic analysis due to new translations or missing matches...")
        try:
            from translations.utils.analysis import print_semantic_matches
            matches = await sync_to_async(print_semantic_matches)(
                threshold=SEMANTIC_THRESHOLD, version=current_version
            )
            if matches:
                semantic_matches.extend(matches)
                for match in semantic_matches:
                    await sync_to_async(create_semantic_match_local)(
                        english_text=match["english_text"],
                        ojibwe_text=match["ojibwe_text"],
                        similarity=match["similarity"],
                        english_definition=match["english_definition"],
                        ojibwe_definition=match["ojibwe_definition"],
                        version=current_version,
                    )
                logger.info(f"Stored {len(semantic_matches)} semantic matches.")
        except Exception as e:
            logger.error(f"Semantic analysis failed: {e}")
    else:
        print("\nNo new translations or existing matches found. Skipping semantic analysis.")
        logger.info("Skipping semantic analysis.")

    # Determine the version for syncing
    sync_version = current_version  # Default to current version
    new_semantic_matches = check_semantic_duplicates(semantic_matches, existing_semantic_matches)

    if not has_existing_semantic_matches:
        logger.info(
            "No semantic matches in Firestore. Syncing local database without version increment."
        )
    elif perform_analysis and new_semantic_matches:
        major, minor = map(int, current_version.split("."))
        sync_version = f"{major}.{minor + 1}"
        logger.info(
            f"New semantic matches found. Incrementing version to {sync_version} for sync."
        )
    else:
        logger.info(
            "No new semantic matches or analysis skipped. Using current version for sync."
        )

    # Sync to Firestore if there are new translations, new semantic matches, or no existing data
    if (
        cleaned_translations
        or new_semantic_matches
        or not (existing_translations and has_existing_semantic_matches)
    ):
        try:
            await sync_to_async(sync_to_firestore)(version=sync_version)
            timestamps["last_sync"] = current_time
            save_timestamps(timestamps)
            logger.info(f"Synced to Firestore with version {sync_version}.")
        except Exception as e:
            logger.error(f"Sync to Firestore failed: {e}")
            return cleaned_translations

    return validated_translations


def reset_processed_words() -> None:
    """Reset processed words file."""
    processed_path = os.path.join(BASE_DIR, "data", "processed_words.json")
    with open(processed_path, "w", encoding="utf-8") as f:
        json.dump([], f)
    logger.info("Reset processed_words.json")


def scrape_ojibwe() -> None:
    """Main function to run the scraper."""
    # Use asyncio.run to avoid DeprecationWarning about event loop
    translations = asyncio.run(scrape_ojibwe_async())
    if translations:
        reset_processed_words()


if __name__ == "__main__":
    scrape_ojibwe()
