# backend/scrapers/ojibwe_scraper.py
"""
Scrape Ojibwe translations to build English-Ojibwe dictionaries.

This module scrapes translations from online sources, stores raw data in a JSON file,
processes it into validated entries, stores them in SQLite, and syncs to Firestore.
It includes timestamp-based scraping, duplicate checking, version incrementation,
and a user prompt for sentiment analysis on sync failure.
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

# Add base directory to system path (two levels up to backend/)
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
    get_all_english_to_ojibwe,
    sync_to_firestore,
    get_firestore_version,
    set_firestore_version,
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

# Path to raw data file
RAW_DATA_PATH = os.path.join(BASE_DIR, "data", "raw_ojibwe_english_dict.json")

# Path to timestamp file
TIMESTAMP_PATH = os.path.join(BASE_DIR, "data", "timestamps.json")

# One month in seconds (30 days)
ONE_MONTH_SECONDS = 30 * 24 * 60 * 60

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

def check_duplicates(new_translations: List[Dict], existing_translations: List[Dict]) -> List[Dict]:
    """Check for duplicates and return only new translations."""
    existing_set = {(t["english_text"], t["ojibwe_text"]) for t in existing_translations}
    unique_new = []
    duplicates_found = 0
    for trans in new_translations:
        key = (trans["english_text"][0] if isinstance(trans["english_text"], list) else trans["english_text"], trans["ojibwe_text"])
        if key in existing_set:
            duplicates_found += 1
        else:
            unique_new.append(trans)
    logger.info(f"Duplicate check: Found {duplicates_found} duplicates, {len(unique_new)} new translations.")
    return unique_new

async def scrape_ojibwe_async() -> List[Dict[str, Union[str, List[str]]]]:
    """
    Scrape Ojibwe translations asynchronously with timestamp checks and duplicate handling.
    """
    timestamps = load_timestamps()
    current_time = time.time()

    # Check if scraping is needed (more than a month since last scrape)
    if current_time - timestamps.get("last_scrape", 0) < ONE_MONTH_SECONDS:
        logger.info("Last scrape was less than a month ago. Skipping scrape.")
        validated_translations = process_raw_data(load_raw_data(RAW_DATA_PATH))
    else:
        # Load and process existing raw data
        raw_translations = load_raw_data(RAW_DATA_PATH)
        validated_translations = process_raw_data(raw_translations)
        firestore_count = len(await sync_to_async(get_all_english_to_ojibwe)())

        # Pre-sync if more validated entries than in Firestore
        if len(validated_translations) > firestore_count:
            logger.info(f"Local entries ({len(validated_translations)}) exceed Firestore ({firestore_count}). Pre-syncing.")
            for entry in validated_translations:
                await sync_to_async(create_ojibwe_to_english_local)(
                    entry["ojibwe_text"], entry["english_text"], version=await sync_to_async(get_firestore_version)()
                )
                for e_text in entry["english_text"]:
                    await sync_to_async(create_english_to_ojibwe_local)(
                        e_text, entry["ojibwe_text"], entry["definition"], version=await sync_to_async(get_firestore_version)()
                    )
            await sync_to_async(sync_to_firestore)(version=await sync_to_async(get_firestore_version)())

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

                    logger.setLevel(logging.WARNING)
                    with tqdm(total=len(tasks), desc="Scraping translations", unit="task") as pbar:
                        for future in asyncio.as_completed(tasks):
                            result = await future
                            if isinstance(result, list):
                                new_raw_translations.extend(result)
                            pbar.update(1)
                    logger.setLevel(logging.INFO)

        # Combine and save new raw translations
        raw_translations.extend(new_raw_translations)
        logger.info(f"Scraped {len(new_raw_translations)} new raw translations.")
        save_raw_data(raw_translations, RAW_DATA_PATH)
        timestamps["last_scrape"] = current_time
        save_timestamps(timestamps)

        # Process into validated entries
        validated_translations = process_raw_data(raw_translations)

    # Fetch existing Firestore data for duplicate check
    existing_translations = await sync_to_async(get_all_english_to_ojibwe)()
    unique_new_translations = check_duplicates(validated_translations, existing_translations)

    # Clean up data (remove invalid entries)
    cleaned_translations = [t for t in unique_new_translations if is_valid_translation(t["ojibwe_text"], t["english_text"])]
    logger.info(f"After cleanup: {len(cleaned_translations)} valid translations remain.")

    # Store in SQLite
    current_version = await sync_to_async(get_firestore_version)()
    for entry in cleaned_translations:
        await sync_to_async(create_ojibwe_to_english_local)(
            entry["ojibwe_text"], entry["english_text"], version=current_version
        )
        for e_text in entry["english_text"]:
            await sync_to_async(create_english_to_ojibwe_local)(
                e_text, entry["ojibwe_text"], entry["definition"], version=current_version
            )
    logger.info(f"Stored {len(cleaned_translations)} validated translations in SQLite.")

    # Sync to Firestore if new translations exist
    if cleaned_translations:
        try:
            # Increment version
            version_parts = current_version.split(".")
            new_version = f"{version_parts[0]}.{int(version_parts[1]) + 1}"
            await sync_to_async(sync_to_firestore)(version=new_version)
            firestore_entries = len(await sync_to_async(get_all_english_to_ojibwe)())
            if firestore_entries >= len(cleaned_translations) + len(existing_translations):
                logger.info(f"Sync successful: {firestore_entries} entries in Firestore.")
                timestamps["last_sync"] = current_time
                save_timestamps(timestamps)
            else:
                logger.warning(f"Sync incomplete: {firestore_entries} in Firestore, expected {len(cleaned_translations) + len(existing_translations)}.")
        except Exception as e:
            logger.error(f"Error syncing to Firestore: {e}. Data stored locally in SQLite.")
            if prompt_to_continue_on_sync_failure():
                return cleaned_translations
            else:
                return []
    else:
        logger.info("No new unique translations to sync.")

    return cleaned_translations

def reset_processed_words() -> None:
    """Reset the processed_words.json file."""
    processed_path = os.path.join(BASE_DIR, "data", "processed_words.json")
    with open(processed_path, "w", encoding="utf-8") as f:
        json.dump([], f)
    logger.info(f"Reset processed_words.json at {processed_path}")

def prompt_to_continue_on_sync_failure() -> bool:
    """Prompt user to continue with sentiment analysis if sync fails."""
    print("\nSyncing to Firestore failed. Data is stored locally in SQLite.")
    print("Continue with sentiment analysis? (Y/n): ", end="")
    return input().strip().lower() in ("", "y", "yes")

def prompt_to_continue() -> bool:
    """Prompt user to continue with sentiment analysis."""
    print(f"\nScraping completed! Raw data saved to {RAW_DATA_PATH}.")
    print("Continue with sentiment analysis? (Y/n): ", end="")
    return input().strip().lower() in ("", "y", "yes")

def scrape_ojibwe() -> None:
    """Main function to run the scraper and optional sentiment analysis."""
    loop = asyncio.get_event_loop()
    translations = loop.run_until_complete(scrape_ojibwe_async())
    if translations:
        reset_processed_words()
    if prompt_to_continue():
        from translations.utils.analysis import print_semantic_matches
        while print_semantic_matches(threshold=0.85):
            pass
    else:
        logger.info("User opted not to perform sentiment analysis.")

if __name__ == "__main__":
    scrape_ojibwe()
