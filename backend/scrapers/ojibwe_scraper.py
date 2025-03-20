"""Scrape Ojibwe translations to build English-Ojibwe dictionaries.

This module scrapes translations from online sources, stores them in MongoDB,
and tracks attempted words to avoid redundant scraping. It prioritizes untranslated
words by frequency of usage using asynchronous requests for efficiency.
"""
import os
import sys
import time
from typing import List, Dict, Set, Union
import sqlite3
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json

# Add the base directory to the system path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# Configure Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vota_backend.settings")
import django
django.setup()

from translations.models import (
    update_or_create_english_to_ojibwe,
    update_or_create_ojibwe_to_english,
    get_all_english_to_ojibwe,
    get_all_ojibwe_to_english,
)
from translations.utils.frequencies import WORD_FREQUENCIES
from translations.utils.get_dict_size import get_english_dict_size

# Base URLs for scraping
URLS = [
    "https://ojibwe.lib.umn.edu",  # Ojibwe People's Dictionary
    "https://glosbe.com/en/oj",    # Glosbe English-to-Ojibwe
]

# Threshold for initial full scrape
TRANSLATION_THRESHOLD = 0.2  # 20% threshold

# Limit the number of words to scrape per run
SCRAPE_LIMIT = 1000  # Process only 1000 words per run

# Custom Ojibwe alphabet set for pagination
OJIBWE_ALPHABET = {
    'a', 'aa', 'e', 'i', 'ii', 'o', 'oo', 'u',
    'b', 'd', 'g', 'h', 'j', 'k', 'm', 'n', 'p', 's', 't', 'w', 'y', 'z', 'zh',
}

# HTTP headers to avoid being blocked
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    ),
}


def get_existing_translations_count() -> int:
    """Count the number of existing Ojibwe-to-English translations in MongoDB.

    Returns:
        int: Number of translations with English text.
    """
    translations = get_all_ojibwe_to_english()
    return sum(1 for t in translations if t.get("english_text"))


def should_perform_full_scrape() -> bool:
    """Determine if a full scrape is needed based on translation coverage.

    Returns:
        bool: True if less than 20% of words are translated, False otherwise.
    """
    dict_size = get_english_dict_size()
    if dict_size == 0:
        print("Warning: English dictionary size is 0. Performing full scrape.")
        return True
    translation_count = get_existing_translations_count()
    print(f"Debug: Dictionary size = {dict_size}, Translation count = {translation_count}")
    return (translation_count / dict_size) < TRANSLATION_THRESHOLD


def get_english_words() -> List[str]:
    """Fetch all English words from the SQLite dictionary for Glosbe scraping.

    Returns:
        List[str]: List of English words.

    Raises:
        sqlite3.Error: If there’s an error accessing the SQLite database.
    """
    try:
        conn = sqlite3.connect("translations.db")
        cursor = conn.cursor()
        cursor.execute("SELECT word FROM english_dict")
        words = [row[0] for row in cursor.fetchall()]
        conn.close()
        return words
    except sqlite3.Error as e:
        print(f"Error fetching English words: {e}")
        return []


def load_attempted_words(attempted_path: str) -> Set[str]:
    """Load the set of words the scraper has already attempted.

    Args:
        attempted_path (str): Path to the JSON file storing attempted words.

    Returns:
        Set[str]: Set of English words that have been attempted.
    """
    try:
        with open(attempted_path, "r", encoding="utf-8") as file:
            return set(json.load(file))
    except FileNotFoundError:
        return set()


def save_attempted_words(attempted_words: Set[str], attempted_path: str) -> None:
    """Save the set of attempted words to a JSON file.

    Args:
        attempted_words (Set[str]): Set of English words that have been attempted.
        attempted_path (str): Path to the JSON file to store attempted words.
    """
    with open(attempted_path, "w", encoding="utf-8") as file:
        json.dump(list(attempted_words), file)


def load_progress(progress_path: str) -> Dict[str, str]:
    """Load the scraping progress from a JSON file.

    Args:
        progress_path (str): Path to the JSON file storing progress.

    Returns:
        Dict[str, str]: Dictionary mapping URLs to the last word scraped.
    """
    try:
        with open(progress_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return {url: "" for url in URLS}


def save_progress(progress: Dict[str, str], progress_path: str) -> None:
    """Save the scraping progress to a JSON file.

    Args:
        progress (Dict[str, str]): Dictionary mapping URLs to the last word scraped.
        progress_path (str): Path to the JSON file to store progress.
    """
    with open(progress_path, "w", encoding="utf-8") as file:
        json.dump(progress, file)


async def fetch_url(session: aiohttp.ClientSession, url: str, semaphore: asyncio.Semaphore) -> str:
    """Fetch a URL asynchronously using aiohttp with a semaphore for rate limiting.

    Args:
        session (aiohttp.ClientSession): The aiohttp session to use for the request.
        url (str): The URL to fetch.
        semaphore (asyncio.Semaphore): Semaphore to limit concurrent requests.

    Returns:
        str: The HTML content of the page.

    Raises:
        aiohttp.ClientError: If the request fails.
    """
    async with semaphore:
        try:
            async with session.get(url, headers=HEADERS, timeout=10) as response:
                response.raise_for_status()
                return await response.text()
        except aiohttp.ClientError as e:
            print(f"Error fetching {url}: {e}")
            return ""


async def scrape_ojibwe_page(
    session: aiohttp.ClientSession,
    base_url: str,
    word: str,
    semaphore: asyncio.Semaphore,
) -> List[Dict[str, Union[str, List[str]]]]:
    """Scrape a single Ojibwe translation page for a given word.

    Args:
        session (aiohttp.ClientSession): The aiohttp session for making requests.
        base_url (str): Base URL of the site to scrape.
        word (str): The English word to look up.
        semaphore (asyncio.Semaphore): Semaphore to limit concurrent requests.

    Returns:
        List[Dict[str, Union[str, List[str]]]]: List of translation dictionaries.
    """
    translations: List[Dict[str, Union[str, List[str]]]] = []
    if "ojibwe.lib" in base_url:
        url = f"{base_url}?utf8=%E2%9C%93&q={word}&search_field=all_fields"
    else:  # Glosbe
        url = f"{base_url}/{word}"

    print(f"Debug: Requesting {url}")
    html = await fetch_url(session, url, semaphore)
    if not html:
        return translations

    print(f"Debug: Parsed HTML, length of content: {len(html)} characters")
    soup = BeautifulSoup(html, "html.parser")

    ojibwe_text = None
    english_text = word

    if "ojibwe.lib" in base_url:
        entry = soup.select_one(".search-results .main-entry-search")
        print(f"Debug: Found {entry is not None} .main-entry-search entry")
        if entry:
            english_div = entry.select_one(".english-search-main-entry")
            if english_div:
                lemma_span = english_div.select_one(".main-entry-title .lemma")
                ojibwe_text = lemma_span.text.strip() if lemma_span else "N/A"
                full_text = english_div.get_text(separator=" ").strip()
                english = full_text.replace(ojibwe_text, "").strip()
                english_texts = [
                    e.strip() for e in english.split(",")
                    if e.strip() and e.lower() != ojibwe_text.lower()
                ]
                print(
                    f"Debug: Found Ojibwe: {ojibwe_text is not None}, "
                    f"English: {bool(english_texts)}"
                )
                if ojibwe_text and english_texts:
                    translations.append({
                        "ojibwe_text": ojibwe_text,
                        "english_text": english_texts,
                        "definition": full_text,
                    })
                    update_or_create_ojibwe_to_english(ojibwe_text, english_texts)
                    for e_text in english_texts:
                        update_or_create_english_to_ojibwe(e_text, ojibwe_text)

    elif "glosbe.com" in base_url:
        # Find all translation items
        translation_items = soup.select("div.translation__item")
        print(f"Debug: Found {len(translation_items)} .translation__item entries")
        for item in translation_items:
            # Look for the Ojibwe translation using lang="oj"
            ojibwe_span = item.find("span", attrs={"lang": "oj"})
            # Look for the English definition using class="py-1"
            english_def_span = item.find("span", class_="py-1")
            if ojibwe_span:
                ojibwe_text = ojibwe_span.text.strip()
                # Try to find a more detailed definition if py-1 is empty
                definition = None
                if english_def_span:
                    definition = english_def_span.text.strip()
                else:
                    # Look for alternative definition elements (e.g., examples or additional info)
                    example_span = item.find("span", class_="text-gray-500")
                    if example_span:
                        definition = example_span.text.strip()
                    else:
                        # Fallback to a simple definition
                        definition = f"{word}: {ojibwe_text}"
                print(f"Debug: Found Ojibwe: {ojibwe_text}, English: {english_text}, Definition: {definition}")
                translations.append({
                    "ojibwe_text": ojibwe_text,
                    "english_text": [english_text],
                    "definition": definition,
                })
                update_or_create_ojibwe_to_english(ojibwe_text, [english_text])
                update_or_create_english_to_ojibwe(english_text, ojibwe_text)

    if ojibwe_text:
        print(f"Found translation for '{word}': {ojibwe_text}")
    return translations


async def scrape_full_dictionary(base_url: str) -> List[Dict[str, Union[str, List[str]]]]:
    """Scrape the entire dictionary from a single website asynchronously.

    Args:
        base_url (str): Base URL of the site to scrape (e.g., ojibwe.lib.umn.edu).

    Returns:
        List[Dict[str, Union[str, List[str]]]]: List of translation dictionaries.
    """
    translations: List[Dict[str, Union[str, List[str]]]] = []
    semaphore = asyncio.Semaphore(10)  # Limit to 10 concurrent requests
    async with aiohttp.ClientSession() as session:
        if "ojibwe.lib" in base_url:
            # Paginate through /browse/ojibwe/{letter} using Ojibwe alphabet
            for letter in OJIBWE_ALPHABET:
                url = f"{base_url}/browse/ojibwe/{letter}"
                print(f"Debug: Attempting to scrape {url}")
                html = await fetch_url(session, url, semaphore)
                if not html:
                    continue

                print(f"Debug: Parsed HTML, length of content: {len(html)} characters")
                soup = BeautifulSoup(html, "html.parser")

                entries = soup.select(".search-results .main-entry-search")
                print(f"Debug: Found {len(entries)} .main-entry-search entries")
                for entry in entries:
                    english_div = entry.select_one(".english-search-main-entry")
                    if english_div:
                        lemma_span = english_div.select_one(".main-entry-title .lemma")
                        ojibwe_text = lemma_span.text.strip() if lemma_span else "N/A"
                        full_text = english_div.get_text(separator=" ").strip()
                        english = full_text.replace(ojibwe_text, "").strip()
                        english_texts = [
                            e.strip() for e in english.split(",")
                            if e.strip() and e.lower() != ojibwe_text.lower()
                        ]
                        print(
                            f"Debug: Found Ojibwe: {ojibwe_text is not None}, "
                            f"English: {bool(english_texts)}"
                        )
                        if ojibwe_text and english_texts:
                            translations.append({
                                "ojibwe_text": ojibwe_text,
                                "english_text": english_texts,
                                "definition": full_text,
                            })
                            update_or_create_ojibwe_to_english(ojibwe_text, english_texts)
                            for e_text in english_texts:
                                update_or_create_english_to_ojibwe(e_text, ojibwe_text)
                            print(
                                f"Debug: Added translation - Ojibwe: {ojibwe_text}, "
                                f"English: {english_texts}"
                            )
                        else:
                            print(
                                f"Debug: Failed to extract translation for entry: "
                                f"{entry.prettify()[:200]}..."
                            )
                    else:
                        print("Debug: No .english-search-main-entry found in this entry")
                await asyncio.sleep(0.1)  # Small delay to avoid rate limiting

        elif "glosbe.com" in base_url:
            english_words = get_english_words()
            tasks = [
                scrape_ojibwe_page(session, base_url, word, semaphore)
                for word in english_words[:SCRAPE_LIMIT]  # Apply limit here
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    translations.extend(result)

    return translations


def get_missing_words() -> List[str]:
    """Fetch the list of English words missing Ojibwe translations, sorted by frequency.

    Returns:
        List[str]: List of English words without translations, sorted by usage frequency.

    Raises:
        Exception: If there’s an error accessing the database.
    """
    try:
        # Load English dictionary from SQLite
        conn = sqlite3.connect("translations.db")
        cursor = conn.cursor()
        cursor.execute("SELECT word FROM english_dict")
        english_words = {row[0] for row in cursor.fetchall()}
        conn.close()

        # Get existing translations from MongoDB
        translations = get_all_english_to_ojibwe()
        translated_english = {
            t["english_text"][0] for t in translations if t.get("english_text")
        }

        # Identify untranslated words
        missing = english_words - translated_english

        # Sort by frequency (default to 0 if not in frequency list)
        word_freqs = [
            (word, WORD_FREQUENCIES.get(word.lower(), 0)) for word in missing
        ]
        word_freqs.sort(key=lambda x: x[1], reverse=True)  # Highest frequency first
        return [word for word, _ in word_freqs]
    except Exception as e:
        print(f"Error fetching missing words: {e}")
        return []


async def scrape_ojibwe_async() -> List[Dict[str, Union[str, List[str]]]]:
    """Scrape Ojibwe translations asynchronously based on coverage threshold.

    Performs a full scrape if less than 20% of words are translated, otherwise
    targets missing words. Tracks attempted words to avoid redundant scraping.

    Returns:
        List[Dict[str, Union[str, List[str]]]]: List of new translations.
    """
    translations: List[Dict[str, Union[str, List[str]]]] = []
    dict_size = get_english_dict_size()
    translation_count = get_existing_translations_count()

    # Load attempted words and progress
    attempted_path = os.path.join(BASE_DIR, "data", "scraped_words.json")
    progress_path = os.path.join(BASE_DIR, "data", "scrape_progress.json")
    attempted_words = load_attempted_words(attempted_path)
    progress = load_progress(progress_path)

    if should_perform_full_scrape():
        print(
            f"Translation coverage is below 20% ({translation_count}/{dict_size}). "
            "Performing full scrape."
        )
        for base_url in URLS:
            translations.extend(await scrape_full_dictionary(base_url))
    else:
        missing_words = get_missing_words()
        if not missing_words:
            print("No missing words to scrape.")
            return translations

        # Filter out already attempted words
        remaining_words = [word for word in missing_words if word not in attempted_words]
        if not remaining_words:
            print("All missing words have been attempted. Resetting attempted list.")
            attempted_words.clear()
            remaining_words = missing_words
            progress = {url: "" for url in URLS}  # Reset progress
            save_progress(progress, progress_path)
        else:
            print(
                f"Found {len(remaining_words)} unattempted missing words out of "
                f"{len(missing_words)} total missing words."
            )

        # Apply the scrape limit
        words_to_scrape = remaining_words[:SCRAPE_LIMIT]
        print(f"Attempting to find translations for {len(words_to_scrape)} words (limited to {SCRAPE_LIMIT}).")
        semaphore = asyncio.Semaphore(10)  # Limit to 10 concurrent requests
        async with aiohttp.ClientSession() as session:
            tasks = []
            for word in words_to_scrape:
                for base_url in URLS:
                    # Skip words before the last scraped word for this URL
                    last_word = progress.get(base_url, "")
                    if last_word and word < last_word:
                        continue
                    tasks.append(scrape_ojibwe_page(session, base_url, word, semaphore))
                attempted_words.add(word)
                # Update progress for each URL
                for url in URLS:
                    if word > progress.get(url, ""):
                        progress[url] = word
                save_attempted_words(attempted_words, attempted_path)
                save_progress(progress, progress_path)

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    translations.extend(result)

    print(f"Scraped and stored {len(translations)} new Ojibwe translations.")
    return translations


def reset_processed_words() -> None:
    """Reset the processed_words.json file to an empty list."""
    processed_path = os.path.join(BASE_DIR, "data", "processed_words.json")
    with open(processed_path, "w", encoding="utf-8") as f:
        json.dump([], f)
    print(f"Reset processed_words.json at {processed_path}")


def scrape_ojibwe() -> None:
    """Main function to run the scraper and semantic analysis in a loop.

    Scrapes translations, then runs semantic analysis, prompting the user to
    continue if desired.
    """
    loop = asyncio.get_event_loop()
    translations = loop.run_until_complete(scrape_ojibwe_async())

    # Reset processed_words.json if new translations were added
    if translations:
        print(f"New translations added. Resetting processed_words.json to allow reprocessing.")
        reset_processed_words()

    # Perform semantic analysis after scraping
    print("Performing semantic analysis on translations...")
    from translations.utils.analysis import print_semantic_matches
    while True:
        if not print_semantic_matches(threshold=0.84):  # Set threshold to 0.84
            break


if __name__ == "__main__":
    scrape_ojibwe()