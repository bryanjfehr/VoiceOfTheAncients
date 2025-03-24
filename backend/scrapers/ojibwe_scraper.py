# backend/scrapers/ojibwe_scraper.py
"""
Scrape Ojibwe translations to build English-Ojibwe dictionaries.

This module scrapes translations from online sources, stores raw data in a JSON file,
processes it into validated entries, stores them in SQLite, and syncs to Firestore.
It includes pre-syncing local entries, a progress bar for scraping, and sync verification.
"""
import asyncio
import json
import os
import sqlite3
import sys
from typing import Dict, List, Set, Union

import aiohttp
from asgiref.sync import sync_to_async
from bs4 import BeautifulSoup
from tqdm import tqdm  # Added for progress bar

# Add base directory to system path (two levels up to backend/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# Configure Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vota_backend.settings")
import django

django.setup()

from translations.utils.logging_config import setup_logging

setup_logging()  # Configure logging for all modules
import logging

logger = logging.getLogger("translations.utils.ojibwe_scraper")

from translations.models import (
    create_english_to_ojibwe_local,
    create_ojibwe_to_english_local,
    get_all_english_to_ojibwe,
    sync_to_firestore,
)
from translations.utils.frequencies import WORD_FREQUENCIES
from translations.utils.get_dict_size import get_english_dict_size
from translations.utils.process_raw_data import load_raw_data, save_raw_data, process_raw_data

# Base URLs for scraping
URLS = [
    "https://ojibwe.lib.umn.edu",  # Ojibwe People's Dictionary
    "https://glosbe.com/en/oj",   # Glosbe English-to-Ojibwe
]

# Threshold for initial full scrape
TRANSLATION_THRESHOLD = 0.2  # 20% threshold

# Limit the number of words to scrape per run
SCRAPE_LIMIT = 1000

# Custom Ojibwe alphabet set for pagination
OJIBWE_ALPHABET = {
    "a", "aa", "b", "d", "e", "g", "h", "i", "ii", "j", "k", "m", "n",
    "o", "oo", "p", "s", "t", "u", "w", "y", "z", "zh",
}

# HTTP headers to avoid being blocked
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    ),
}

# Version for this scrape
CURRENT_VERSION = "1.0"

# Path to raw data file
RAW_DATA_PATH = os.path.join(BASE_DIR, "data", "raw_ojibwe_english_dict.json")


async def get_existing_translations_count() -> int:
    """Count existing Ojibwe-to-English translations in Firestore."""
    translations = await sync_to_async(get_all_english_to_ojibwe)()
    count = sum(1 for t in translations if t.get("english_text"))
    logger.info(f"Found {count} existing English-to-Ojibwe translations in Firestore.")
    return count


async def should_perform_full_scrape() -> bool:
    """Determine if a full scrape is needed based on translation coverage."""
    dict_size = await sync_to_async(get_english_dict_size)()
    if dict_size == 0:
        logger.warning("English dictionary size is 0. Performing full scrape.")
        return True
    translation_count = await get_existing_translations_count()
    coverage = translation_count / dict_size
    logger.info(f"Translation coverage: {coverage:.2%}")
    return coverage < TRANSLATION_THRESHOLD


async def get_english_words() -> List[str]:
    """Fetch all English words from SQLite for Glosbe scraping."""
    try:
        conn = await sync_to_async(sqlite3.connect)("translations.db")
        cursor = await sync_to_async(conn.cursor)()
        await sync_to_async(cursor.execute)("SELECT word FROM english_dict")
        words = [row[0] for row in await sync_to_async(cursor.fetchall)()]
        await sync_to_async(conn.close)()
        logger.info(f"Fetched {len(words)} English words from SQLite.")
        return words
    except sqlite3.Error as e:
        logger.error(f"Error fetching English words from SQLite: {e}")
        return []


def load_attempted_words(attempted_path: str) -> Set[str]:
    """Load the set of words already attempted."""
    try:
        with open(attempted_path, "r", encoding="utf-8") as file:
            attempted = set(json.load(file))
        logger.info(f"Loaded {len(attempted)} attempted words from {attempted_path}.")
        return attempted
    except FileNotFoundError:
        logger.info(f"No attempted words file found at {attempted_path}. Starting fresh.")
        return set()


def save_attempted_words(attempted_words: Set[str], attempted_path: str) -> None:
    """Save the set of attempted words to a JSON file."""
    with open(attempted_path, "w", encoding="utf-8") as file:
        json.dump(list(attempted_words), file)
    logger.info(f"Saved {len(attempted_words)} attempted words to {attempted_path}.")


def load_progress(progress_path: str) -> Dict[str, str]:
    """Load scraping progress from a JSON file."""
    try:
        with open(progress_path, "r", encoding="utf-8") as file:
            progress = json.load(file)
        logger.info(f"Loaded scraping progress from {progress_path}.")
        return progress
    except FileNotFoundError:
        progress = {url: "" for url in URLS}
        logger.info(f"No progress file found at {progress_path}. Starting fresh.")
        return progress


def save_progress(progress: Dict[str, str], progress_path: str) -> None:
    """Save scraping progress to a JSON file."""
    with open(progress_path, "w", encoding="utf-8") as file:
        json.dump(progress, file)
    logger.info(f"Saved scraping progress to {progress_path}.")


async def fetch_url(
    session: aiohttp.ClientSession,
    url: str,
    semaphore: asyncio.Semaphore,
    retries: int = 3,
) -> str:
    """Fetch a URL asynchronously with rate limiting and retries."""
    async with semaphore:
        for attempt in range(retries):
            try:
                async with session.get(url, headers=HEADERS, timeout=10) as response:
                    if response.status == 429:  # Too Many Requests
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
                logger.warning(f"Error fetching {url} (attempt {attempt + 1}/{retries}): {e}")
                await asyncio.sleep(2**attempt)  # Exponential backoff
        return ""


def is_valid_translation(ojibwe_text: str, english_texts: List[str]) -> bool:
    """Validate a translation to ensure it’s meaningful."""
    if not ojibwe_text or not english_texts:
        return False
    if len(ojibwe_text.strip()) < 2 or all(len(e.strip()) < 2 for e in english_texts):
        return False
    if ojibwe_text.lower() in [e.lower() for e in english_texts]:
        return False
    return True


async def scrape_ojibwe_page(
    session: aiohttp.ClientSession,
    base_url: str,
    word: str,
    semaphore: asyncio.Semaphore,
) -> List[Dict[str, Union[str, List[str]]]]:
    """Scrape a single Ojibwe translation page for a given word."""
    translations: List[Dict[str, Union[str, List[str]]]] = []
    url = f"{base_url}?utf8=%E2%9C%93&q={word}&search_field=all_fields" if "ojibwe.lib" in base_url else f"{base_url}/{word}"
    
    html = await fetch_url(session, url, semaphore)
    if not html:
        logger.warning(f"No HTML content retrieved from {url}")
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
                ojibwe_text = lemma_span.text.strip() if lemma_span else "N/A"
                if ojibwe_text == "N/A":
                    logger.warning(f"No Ojibwe text found for '{word}' on {base_url}")
                    return translations

                definition_div = entry.select_one(".definition")
                definition = definition_div.get_text(separator=" ").strip() if definition_div else english_div.get_text(separator=" ").strip().replace(ojibwe_text, "").strip()
                english_texts = [e.strip() for e in definition.split(",") if e.strip() and e.lower() != ojibwe_text.lower()] or [word]

                logger.debug(f"Raw data for '{word}': Ojibwe: {ojibwe_text}, English: {english_texts}, Def: {definition}")
                translations.append({"ojibwe_text": ojibwe_text, "english_text": english_texts, "definition": definition})

    elif "glosbe.com" in base_url:
        for item in soup.select("div.translation__item"):
            ojibwe_span = item.find("span", attrs={"lang": "oj"})
            if ojibwe_span and (ojibwe_text := ojibwe_span.text.strip()):
                definition = None
                for cls in ["py-1", "text-gray-500"]:
                    if span := item.find("span", class_=cls):
                        definition = span.text.strip()
                        break
                definition = definition or item.get_text(separator=" ").strip().replace(ojibwe_text, "").strip() or f"{word}: {ojibwe_text}"
                
                logger.debug(f"Raw data for '{word}': Ojibwe: {ojibwe_text}, English: {english_text}, Def: {definition}")
                translations.append({"ojibwe_text": ojibwe_text, "english_text": [english_text], "definition": definition})

    if ojibwe_text:
        logger.info(f"Found translation for '{word}': {ojibwe_text}")
    else:
        logger.warning(f"No valid translation for '{word}' on {base_url}")
    return translations


async def scrape_full_dictionary(base_url: str) -> List[Dict[str, Union[str, List[str]]]]:
    """Scrape the entire dictionary from a single website."""
    translations: List[Dict[str, Union[str, List[str]]]] = []
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
                        ojibwe_text = lemma_span.text.strip() if lemma_span else "N/A"
                        if ojibwe_text == "N/A":
                            continue

                        definition_div = entry.select_one(".definition")
                        definition = definition_div.get_text(separator=" ").strip() if definition_div else english_div.get_text(separator=" ").strip().replace(ojibwe_text, "").strip()
                        english_texts = [e.strip() for e in definition.split(",") if e.strip() and e.lower() != ojibwe_text.lower()]
                        if not english_texts:
                            continue

                        translations.append({"ojibwe_text": ojibwe_text, "english_text": english_texts, "definition": definition})
                await asyncio.sleep(0.1)
        else:
            english_words = await get_english_words()
            tasks = [scrape_ojibwe_page(session, base_url, word, semaphore) for word in english_words[:SCRAPE_LIMIT]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    translations.extend(result)
    return translations


async def get_missing_words() -> List[str]:
    """Fetch English words missing Ojibwe translations, sorted by frequency."""
    try:
        conn = await sync_to_async(sqlite3.connect)("translations.db")
        cursor = await sync_to_async(conn.cursor)()
        await sync_to_async(cursor.execute)("SELECT word FROM english_dict")
        english_words = {row[0] for row in await sync_to_async(cursor.fetchall)()}
        await sync_to_async(conn.close)()

        translations = await sync_to_async(get_all_english_to_ojibwe)()
        translated_english = {t["english_text"] for t in translations if t.get("english_text")}
        missing = english_words - translated_english
        word_freqs = [(word, WORD_FREQUENCIES.get(word.lower(), 0)) for word in missing]
        word_freqs.sort(key=lambda x: x[1], reverse=True)
        missing_words = [word for word, _ in word_freqs]
        logger.info(f"Found {len(missing_words)} missing English words.")
        return missing_words
    except Exception as e:
        logger.error(f"Error fetching missing words: {e}")
        return []


async def scrape_ojibwe_async() -> List[Dict[str, Union[str, List[str]]]]:
    """
    Scrape Ojibwe translations asynchronously with pre-sync and progress bar.

    Checks local JSON against Firestore, syncs if more entries exist locally,
    then scrapes with a progress bar, and verifies sync success.
    """
    # Load and process existing raw data
    raw_translations = load_raw_data(RAW_DATA_PATH)
    validated_translations = process_raw_data(raw_translations)
    firestore_count = len(await sync_to_async(get_all_english_to_ojibwe)())

    # Pre-sync if more validated entries than in Firestore
    if len(validated_translations) > firestore_count:
        logger.info(
            f"Local entries ({len(validated_translations)}) exceed Firestore "
            f"({firestore_count}). Pre-syncing to Firestore."
        )
        for entry in validated_translations:
            await sync_to_async(create_ojibwe_to_english_local)(
                entry["ojibwe_text"], entry["english_text"], version=CURRENT_VERSION
            )
            for e_text in entry["english_text"]:
                await sync_to_async(create_english_to_ojibwe_local)(
                    e_text, entry["ojibwe_text"], entry["definition"], version=CURRENT_VERSION
                )
        await sync_to_async(sync_to_firestore)(version=CURRENT_VERSION)

    # Scrape new data
    dict_size = await sync_to_async(get_english_dict_size)()
    translation_count = await get_existing_translations_count()
    attempted_path = os.path.join(BASE_DIR, "data", "scraped_words.json")
    progress_path = os.path.join(BASE_DIR, "data", "scrape_progress.json")
    attempted_words = load_attempted_words(attempted_path)
    progress = load_progress(progress_path)
    new_raw_translations: List[Dict[str, Union[str, List[str]]]] = []

    if await should_perform_full_scrape():
        logger.info(f"Coverage below 20% ({translation_count}/{dict_size}). Full scrape.")
        for base_url in URLS:
            new_raw_translations.extend(await scrape_full_dictionary(base_url))
    else:
        missing_words = await get_missing_words()
        if not missing_words:
            logger.info("No missing words to scrape.")
        else:
            remaining_words = [word for word in missing_words if word not in attempted_words]
            if not remaining_words:
                logger.info("All missing words attempted. Resetting list.")
                attempted_words.clear()
                remaining_words = missing_words
                progress = {url: "" for url in URLS}
                save_progress(progress, progress_path)
            else:
                logger.info(f"Found {len(remaining_words)} unattempted missing words.")

            words_to_scrape = remaining_words[:SCRAPE_LIMIT]
            logger.info(f"Scraping {len(words_to_scrape)} words (limit: {SCRAPE_LIMIT}).")
            semaphore = asyncio.Semaphore(10)
            async with aiohttp.ClientSession() as session:
                tasks = []
                for word in words_to_scrape:
                    for base_url in URLS:
                        last_word = progress.get(base_url, "")
                        if last_word and word < last_word:
                            continue
                        tasks.append(scrape_ojibwe_page(session, base_url, word, semaphore))
                    attempted_words.add(word)
                    for url in URLS:
                        if word > progress.get(url, ""):
                            progress[url] = word
                    if len(tasks) % 100 == 0:
                        save_attempted_words(attempted_words, attempted_path)
                        save_progress(progress, progress_path)

                save_attempted_words(attempted_words, attempted_path)
                save_progress(progress, progress_path)

                # Scrape with progress bar
                logger.setLevel(logging.WARNING)  # Reduce verbosity during scraping
                with tqdm(total=len(tasks), desc="Scraping translations", unit="task") as pbar:
                    for future in asyncio.as_completed(tasks):
                        result = await future
                        if isinstance(result, list):
                            new_raw_translations.extend(result)
                        pbar.update(1)
                logger.setLevel(logging.INFO)  # Restore logging level

    # Combine and save new raw translations
    raw_translations.extend(new_raw_translations)
    logger.info(f"Scraped {len(new_raw_translations)} new raw translations.")
    save_raw_data(raw_translations, RAW_DATA_PATH)

    # Process into validated entries
    validated_translations = process_raw_data(raw_translations)

    # Store in SQLite
    for entry in validated_translations:
        await sync_to_async(create_ojibwe_to_english_local)(
            entry["ojibwe_text"], entry["english_text"], version=CURRENT_VERSION
        )
        for e_text in entry["english_text"]:
            await sync_to_async(create_english_to_ojibwe_local)(
                e_text, entry["ojibwe_text"], entry["definition"], version=CURRENT_VERSION
            )
    logger.info(f"Stored {len(validated_translations)} validated translations in SQLite.")

    # Sync to Firestore and verify
    try:
        await sync_to_async(sync_to_firestore)(version=CURRENT_VERSION)
        firestore_entries = len(await sync_to_async(get_all_english_to_ojibwe)())
        if firestore_entries >= len(validated_translations):
            logger.info(f"Sync successful: {firestore_entries} entries in Firestore.")
        else:
            logger.warning(
                f"Sync incomplete: {firestore_entries} in Firestore, "
                f"expected {len(validated_translations)}."
            )
    except Exception as e:
        logger.error(f"Error syncing to Firestore: {e}. Data stored locally in SQLite.")

    return validated_translations


def reset_processed_words() -> None:
    """Reset the processed_words.json file."""
    processed_path = os.path.join(BASE_DIR, "data", "processed_words.json")
    with open(processed_path, "w", encoding="utf-8") as f:
        json.dump([], f)
    logger.info(f"Reset processed_words.json at {processed_path}")


def prompt_to_continue() -> bool:
    """Prompt user to continue with semantic analysis."""
    print(f"\nScraping completed! Raw data saved to {RAW_DATA_PATH}.")
    print("Continue with semantic analysis? (Y/n): ", end="")
    return input().strip().lower() in ("", "y", "yes")


def scrape_ojibwe() -> None:
    """Main function to run the scraper and optional semantic analysis."""
    loop = asyncio.get_event_loop()
    translations = loop.run_until_complete(scrape_ojibwe_async())
    if translations:
        reset_processed_words()
    if prompt_to_continue():
        from translations.utils.analysis import print_semantic_matches
        while print_semantic_matches(threshold=0.85):
            pass
    else:
        logger.info("User opted not to perform semantic analysis.")


if __name__ == "__main__":
    scrape_ojibwe()
