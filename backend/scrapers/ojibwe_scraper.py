# backend/scrapers/ojibwe_scraper.py
"""
Scrape Ojibwe translations to build English-Ojibwe dictionaries.

This module scrapes translations from online sources, stores them in SQLite,
and syncs them to Firestore with versioning. It prioritizes untranslated words
by frequency of usage using asynchronous requests for efficiency.
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

# Add the base directory to the system path
# Since this file is in scrapers/, we need to go up two levels to reach backend/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# Configure Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vota_backend.settings")
import django  # noqa: E402

django.setup()

# Import logging setup and initialize it at the application level
from translations.utils.logging_config import setup_logging  # noqa: E402
setup_logging()  # Configure logging for all modules

# Now import the logger
import logging  # noqa: E402
logger = logging.getLogger("translations.utils.ojibwe_scraper")

from translations.models import (  # noqa: E402
    create_english_to_ojibwe_local,
    create_ojibwe_to_english_local,
    get_all_english_to_ojibwe,
    get_all_ojibwe_to_english,
    sync_to_firestore,
)
from translations.utils.frequencies import WORD_FREQUENCIES  # noqa: E402
from translations.utils.get_dict_size import get_english_dict_size  # noqa: E402
from translations.utils.definition_utils import validate_translation_entry  # noqa: E402

# Base URLs for scraping
URLS = [
    "https://ojibwe.lib.umn.edu",  # Ojibwe People's Dictionary
    "https://glosbe.com/en/oj",  # Glosbe English-to-Ojibwe
]

# Threshold for initial full scrape
TRANSLATION_THRESHOLD = 0.2  # 20% threshold

# Limit the number of words to scrape per run
SCRAPE_LIMIT = 1000  # Process only 1000 words per run

# Custom Ojibwe alphabet set for pagination
OJIBWE_ALPHABET = {
    "a",
    "aa",
    "b",
    "d",
    "e",
    "g",
    "h",
    "i",
    "ii",
    "j",
    "k",
    "m",
    "n",
    "o",
    "oo",
    "p",
    "s",
    "t",
    "u",
    "w",
    "y",
    "z",
    "zh",
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


async def get_existing_translations_count() -> int:
    """
    Count the number of existing Ojibwe-to-English translations in Firestore.

    Returns:
        int: Number of translations with English text.
    """
    translations = await sync_to_async(get_all_ojibwe_to_english)()
    count = sum(1 for t in translations if t.get("english_text"))
    logger.info(f"Found {count} existing Ojibwe-to-English translations in Firestore.")
    return count


async def should_perform_full_scrape() -> bool:
    """
    Determine if a full scrape is needed based on translation coverage.

    Returns:
        bool: True if less than 20% of words are translated, False otherwise.
    """
    dict_size = await sync_to_async(get_english_dict_size)()
    if dict_size == 0:
        logger.warning("English dictionary size is 0. Performing full scrape.")
        return True
    translation_count = await get_existing_translations_count()
    logger.debug(f"Dictionary size: {dict_size}, Translation count: {translation_count}")
    coverage = translation_count / dict_size
    logger.info(f"Translation coverage: {coverage:.2%}")
    return coverage < TRANSLATION_THRESHOLD


async def get_english_words() -> List[str]:
    """
    Fetch all English words from the SQLite dictionary for Glosbe scraping.

    Returns:
        List[str]: List of English words.

    Raises:
        sqlite3.Error: If there's an error accessing the SQLite database.
    """
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
    """
    Load the set of words the scraper has already attempted.

    Args:
        attempted_path (str): Path to the JSON file storing attempted words.

    Returns:
        Set[str]: Set of English words that have been attempted.
    """
    try:
        with open(attempted_path, "r", encoding="utf-8") as file:
            attempted = set(json.load(file))
        logger.info(f"Loaded {len(attempted)} attempted words from {attempted_path}.")
        return attempted
    except FileNotFoundError:
        logger.info(f"No attempted words file found at {attempted_path}. Starting fresh.")
        return set()


def save_attempted_words(attempted_words: Set[str], attempted_path: str) -> None:
    """
    Save the set of attempted words to a JSON file.

    Args:
        attempted_words (Set[str]): Set of English words that have been attempted.
        attempted_path (str): Path to the JSON file to store attempted words.
    """
    with open(attempted_path, "w", encoding="utf-8") as file:
        json.dump(list(attempted_words), file)
    logger.info(f"Saved {len(attempted_words)} attempted words to {attempted_path}.")


def load_progress(progress_path: str) -> Dict[str, str]:
    """
    Load the scraping progress from a JSON file.

    Args:
        progress_path (str): Path to the JSON file storing progress.

    Returns:
        Dict[str, str]: Dictionary mapping URLs to the last word scraped.
    """
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
    """
    Save the scraping progress to a JSON file.

    Args:
        progress (Dict[str, str]): Dictionary mapping URLs to the last word scraped.
        progress_path (str): Path to the JSON file to store progress.
    """
    with open(progress_path, "w", encoding="utf-8") as file:
        json.dump(progress, file)
    logger.info(f"Saved scraping progress to {progress_path}.")


async def fetch_url(
    session: aiohttp.ClientSession,
    url: str,
    semaphore: asyncio.Semaphore,
    retries: int = 3,
) -> str:
    """
    Fetch a URL asynchronously using aiohttp with a semaphore for rate limiting.

    Args:
        session (aiohttp.ClientSession): The aiohttp session to use for the request.
        url (str): The URL to fetch.
        semaphore (asyncio.Semaphore): Semaphore to limit concurrent requests.
        retries (int): Number of retries for failed requests. Defaults to 3.

    Returns:
        str: The HTML content of the page.

    Raises:
        aiohttp.ClientError: If the request fails after all retries.
    """
    async with semaphore:
        for attempt in range(retries):
            try:
                async with session.get(url, headers=HEADERS, timeout=10) as response:
                    if response.status == 429:  # Too Many Requests
                        retry_after = int(response.headers.get("Retry-After", 60))
                        logger.warning(
                            f"Rate limited on {url}. Waiting {retry_after} seconds..."
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    response.raise_for_status()
                    return await response.text()
            except aiohttp.ClientError as e:
                if attempt == retries - 1:
                    logger.error(f"Failed to fetch {url} after {retries} attempts: {e}")
                    return ""
                logger.warning(
                    f"Error fetching {url} (attempt {attempt + 1}/{retries}): {e}. Retrying..."
                )
                await asyncio.sleep(2**attempt)  # Exponential backoff
        return ""


def is_valid_translation(ojibwe_text: str, english_texts: List[str]) -> bool:
    """
    Validate a translation to ensure it is meaningful.

    Args:
        ojibwe_text (str): The Ojibwe text.
        english_texts (List[str]): List of English translations.

    Returns:
        bool: True if the translation is valid, False otherwise.
    """
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
    """
    Scrape a single Ojibwe translation page for a given word.

    Improved definition extraction to ensure meaningful definitions are captured
    from both the Ojibwe People's Dictionary and Glosbe. Uses validate_translation_entry
    to ensure only valid entries are stored.

    Args:
        session (aiohttp.ClientSession): The aiohttp session for making requests.
        base_url (str): Base URL of the site to scrape.
        word (str): The English word to look up.
        semaphore (asyncio.Semaphore): Semaphore to limit concurrent requests.

    Returns:
        List[Dict[str, Union[str, List[str]]]]: List of validated translation dictionaries.
    """
    translations: List[Dict[str, Union[str, List[str]]]] = []
    if "ojibwe.lib" in base_url:
        url = f"{base_url}?utf8=%E2%9C%93&q={word}&search_field=all_fields"
    else:  # Glosbe
        url = f"{base_url}/{word}"

    logger.debug(f"Requesting {url}")
    html = await fetch_url(session, url, semaphore)
    if not html:
        logger.warning(f"No HTML content retrieved from {url}")
        return translations

    logger.debug(f"Parsed HTML, length of content: {len(html)} characters")
    soup = BeautifulSoup(html, "html.parser")

    ojibwe_text = None
    english_text = word

    if "ojibwe.lib" in base_url:
        entry = soup.select_one(".search-results .main-entry-search")
        logger.debug(f"Found main-entry-search entry: {entry is not None}")
        if entry:
            english_div = entry.select_one(".english-search-main-entry")
            if english_div:
                # Extract Ojibwe text
                lemma_span = english_div.select_one(".main-entry-title .lemma")
                ojibwe_text = lemma_span.text.strip() if lemma_span else "N/A"
                if ojibwe_text == "N/A":
                    logger.warning(f"No Ojibwe text found for word '{word}' on {base_url}")
                    return translations

                # Improved definition extraction
                definition = None
                # Try to find a detailed definition in the entry
                definition_div = entry.select_one(".definition")
                if definition_div:
                    definition = definition_div.get_text(separator=" ").strip()
                else:
                    # Fallback to the full text of the entry, excluding the lemma
                    full_text = english_div.get_text(separator=" ").strip()
                    definition = full_text.replace(ojibwe_text, "").strip()

                # Extract English translations
                english_texts = [
                    e.strip()
                    for e in definition.split(",")
                    if e.strip() and e.lower() != ojibwe_text.lower()
                ]
                if not english_texts:
                    english_texts = [word]  # Fallback to the input word if no translations found

                # Create translation entry and validate
                translation_entry = {
                    "ojibwe_text": ojibwe_text,
                    "english_text": english_texts,
                    "definition": definition,
                }
                validated_entry = validate_translation_entry(translation_entry)
                if not validated_entry:
                    logger.warning(f"Invalid translation entry for '{word}' on {base_url}: {translation_entry}")
                    return translations

                translations.append(validated_entry)
                # Store in SQLite
                await sync_to_async(create_ojibwe_to_english_local)(
                    validated_entry["ojibwe_text"],
                    validated_entry["english_text"],
                    version=CURRENT_VERSION
                )
                for e_text in validated_entry["english_text"]:
                    await sync_to_async(create_english_to_ojibwe_local)(
                        e_text,
                        validated_entry["ojibwe_text"],
                        validated_entry["definition"],
                        version=CURRENT_VERSION
                    )
                logger.debug(
                    f"Stored translation - Ojibwe: {validated_entry['ojibwe_text']}, "
                    f"English: {validated_entry['english_text']}, "
                    f"Definition: {validated_entry['definition']}"
                )

    elif "glosbe.com" in base_url:
        translation_items = soup.select("div.translation__item")
        logger.debug(f"Found {len(translation_items)} translation__item entries")
        for item in translation_items:
            ojibwe_span = item.find("span", attrs={"lang": "oj"})
            if ojibwe_span:
                ojibwe_text = ojibwe_span.text.strip()
                if not ojibwe_text:
                    logger.warning(f"No Ojibwe text found in translation item for '{word}' on {base_url}")
                    continue

                # Improved definition extraction
                definition = None
                # Try primary definition
                english_def_span = item.find("span", class_="py-1")
                if english_def_span:
                    definition = english_def_span.text.strip()
                # Fallback to example sentence
                if not definition:
                    example_span = item.find("span", class_="text-gray-500")
                    if example_span:
                        definition = example_span.text.strip()
                # Fallback to parent container text
                if not definition:
                    parent_text = item.get_text(separator=" ").strip()
                    definition = parent_text.replace(ojibwe_text, "").strip()

                # Create translation entry and validate
                translation_entry = {
                    "ojibwe_text": ojibwe_text,
                    "english_text": [english_text],
                    "definition": definition if definition else f"{word}: {ojibwe_text}",
                }
                validated_entry = validate_translation_entry(translation_entry)
                if not validated_entry:
                    logger.warning(f"Invalid translation entry for '{word}' on {base_url}: {translation_entry}")
                    continue

                translations.append(validated_entry)
                # Store in SQLite
                await sync_to_async(create_ojibwe_to_english_local)(
                    validated_entry["ojibwe_text"],
                    validated_entry["english_text"],
                    version=CURRENT_VERSION
                )
                await sync_to_async(create_english_to_ojibwe_local)(
                    validated_entry["english_text"][0],
                    validated_entry["ojibwe_text"],
                    validated_entry["definition"],
                    version=CURRENT_VERSION
                )
                logger.debug(
                    f"Stored translation - Ojibwe: {validated_entry['ojibwe_text']}, "
                    f"English: {validated_entry['english_text']}, "
                    f"Definition: {validated_entry['definition']}"
                )

    if ojibwe_text:
        logger.info(f"Found translation for '{word}': {ojibwe_text}")
    else:
        logger.warning(f"No valid translation found for '{word}' on {base_url}")
    return translations


async def scrape_full_dictionary(
    base_url: str,
) -> List[Dict[str, Union[str, List[str]]]]:
    """
    Scrape the entire dictionary from a single website asynchronously.

    Args:
        base_url (str): Base URL of the site to scrape (e.g., ojibwe.lib.umn.edu).

    Returns:
        List[Dict[str, Union[str, List[str]]]]: List of validated translation dictionaries.
    """
    translations: List[Dict[str, Union[str, List[str]]]] = []
    semaphore = asyncio.Semaphore(10)  # Limit to 10 concurrent requests
    async with aiohttp.ClientSession() as session:
        if "ojibwe.lib" in base_url:
            for letter in OJIBWE_ALPHABET:
                url = f"{base_url}/browse/ojibwe/{letter}"
                logger.debug(f"Attempting to scrape {url}")
                html = await fetch_url(session, url, semaphore)
                if not html:
                    continue

                logger.debug(f"Parsed HTML, length of content: {len(html)} characters")
                soup = BeautifulSoup(html, "html.parser")

                entries = soup.select(".search-results .main-entry-search")
                logger.debug(f"Found {len(entries)} main-entry-search entries")
                for entry in entries:
                    english_div = entry.select_one(".english-search-main-entry")
                    if english_div:
                        lemma_span = english_div.select_one(".main-entry-title .lemma")
                        ojibwe_text = lemma_span.text.strip() if lemma_span else "N/A"
                        if ojibwe_text == "N/A":
                            logger.warning(f"No Ojibwe text found in entry on {base_url}")
                            continue

                        # Improved definition extraction
                        definition = None
                        definition_div = entry.select_one(".definition")
                        if definition_div:
                            definition = definition_div.get_text(separator=" ").strip()
                        else:
                            full_text = english_div.get_text(separator=" ").strip()
                            definition = full_text.replace(ojibwe_text, "").strip()

                        # Extract English translations
                        english_texts = [
                            e.strip()
                            for e in definition.split(",")
                            if e.strip() and e.lower() != ojibwe_text.lower()
                        ]
                        if not english_texts:
                            logger.warning(f"No English translations extracted from definition: {definition}")
                            continue

                        # Create translation entry and validate
                        translation_entry = {
                            "ojibwe_text": ojibwe_text,
                            "english_text": english_texts,
                            "definition": definition,
                        }
                        validated_entry = validate_translation_entry(translation_entry)
                        if not validated_entry:
                            logger.warning(f"Invalid translation entry on {base_url}: {translation_entry}")
                            continue

                        translations.append(validated_entry)
                        # Store in SQLite
                        await sync_to_async(create_ojibwe_to_english_local)(
                            validated_entry["ojibwe_text"],
                            validated_entry["english_text"],
                            version=CURRENT_VERSION
                        )
                        for e_text in validated_entry["english_text"]:
                            await sync_to_async(create_english_to_ojibwe_local)(
                                e_text,
                                validated_entry["ojibwe_text"],
                                validated_entry["definition"],
                                version=CURRENT_VERSION
                            )
                        logger.debug(
                            f"Stored translation - Ojibwe: {validated_entry['ojibwe_text']}, "
                            f"English: {validated_entry['english_text']}, "
                            f"Definition: {validated_entry['definition']}"
                        )
                    else:
                        logger.debug("No .english-search-main-entry found in this entry")
                await asyncio.sleep(0.1)  # Small delay to avoid rate limiting

        elif "glosbe.com" in base_url:
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


async def get_missing_words() -> List[str]:
    """
    Fetch the list of English words missing Ojibwe translations, sorted by frequency.

    Returns:
        List[str]: List of English words without translations, sorted by usage frequency.

    Raises:
        Exception: If there's an error accessing the database.
    """
    try:
        conn = await sync_to_async(sqlite3.connect)("translations.db")
        cursor = await sync_to_async(conn.cursor)()
        await sync_to_async(cursor.execute)("SELECT word FROM english_dict")
        english_words = {row[0] for row in await sync_to_async(cursor.fetchall)()}
        await sync_to_async(conn.close)()

        translations = await sync_to_async(get_all_english_to_ojibwe)()
        translated_english = {
            t["english_text"][0] for t in translations if t.get("english_text")
        }

        missing = english_words - translated_english
        word_freqs = [
            (word, WORD_FREQUENCIES.get(word.lower(), 0)) for word in missing
        ]
        word_freqs.sort(key=lambda x: x[1], reverse=True)
        missing_words = [word for word, _ in word_freqs]
        logger.info(f"Found {len(missing_words)} missing English words.")
        return missing_words
    except Exception as e:
        logger.error(f"Error fetching missing words: {e}")
        return []


async def scrape_ojibwe_async() -> List[Dict[str, Union[str, List[str]]]]:
    """
    Scrape Ojibwe translations asynchronously based on coverage threshold.

    Performs a full scrape if less than 20% of words are translated, otherwise
    targets missing words. Tracks attempted words to avoid redundant scraping.

    Returns:
        List[Dict[str, Union[str, List[str]]]]: List of validated translation dictionaries.
    """
    translations: List[Dict[str, Union[str, List[str]]]] = []
    dict_size = await sync_to_async(get_english_dict_size)()
    translation_count = await get_existing_translations_count()

    attempted_path = os.path.join(BASE_DIR, "data", "scraped_words.json")
    progress_path = os.path.join(BASE_DIR, "data", "scrape_progress.json")
    attempted_words = load_attempted_words(attempted_path)
    progress = load_progress(progress_path)

    if await should_perform_full_scrape():
        logger.info(
            f"Translation coverage is below 20% ({translation_count}/{dict_size}). "
            "Performing full scrape."
        )
        for base_url in URLS:
            translations.extend(await scrape_full_dictionary(base_url))
    else:
        missing_words = await get_missing_words()
        if not missing_words:
            logger.info("No missing words to scrape.")
            return translations

        remaining_words = [word for word in missing_words if word not in attempted_words]
        if not remaining_words:
            logger.info("All missing words have been attempted. Resetting attempted list.")
            attempted_words.clear()
            remaining_words = missing_words
            progress = {url: "" for url in URLS}
            save_progress(progress, progress_path)
        else:
            logger.info(
                f"Found {len(remaining_words)} unattempted missing words out of "
                f"{len(missing_words)} total missing words."
            )

        words_to_scrape = remaining_words[:SCRAPE_LIMIT]
        logger.info(
            f"Attempting to find translations for {len(words_to_scrape)} words "
            f"(limited to {SCRAPE_LIMIT})."
        )
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
                # Batch writes to reduce I/O
                if len(tasks) % 100 == 0:
                    save_attempted_words(attempted_words, attempted_path)
                    save_progress(progress, progress_path)

            # Final write for any remaining updates
            save_attempted_words(attempted_words, attempted_path)
            save_progress(progress, progress_path)

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    translations.extend(result)

    logger.info(f"Scraped and stored {len(translations)} new Ojibwe translations in SQLite.")
    # Sync to Firestore
    try:
        await sync_to_async(sync_to_firestore)(version=CURRENT_VERSION)
    except Exception as e:
        logger.error(
            f"Error syncing to Firestore: {e}. Data is still stored locally in SQLite."
        )
    return translations


def reset_processed_words() -> None:
    """
    Reset the processed_words.json file to an empty list.
    """
    processed_path = os.path.join(BASE_DIR, "data", "processed_words.json")
    with open(processed_path, "w", encoding="utf-8") as f:
        json.dump([], f)
    logger.info(f"Reset processed_words.json at {processed_path}")


def scrape_ojibwe() -> None:
    """
    Main function to run the scraper and semantic analysis in a loop.

    Scrapes translations, then runs semantic analysis, prompting the user to
    continue if desired.
    """
    loop = asyncio.get_event_loop()
    translations = loop.run_until_complete(scrape_ojibwe_async())

    if translations:
        logger.info(
            "New translations added. Resetting processed_words.json to allow reprocessing."
        )
        reset_processed_words()

    logger.info("Performing semantic analysis on translations...")
    from translations.utils.analysis import print_semantic_matches  # noqa: E402

    while True:
        if not print_semantic_matches(threshold=0.85):
            break


if __name__ == "__main__":
    scrape_ojibwe()
