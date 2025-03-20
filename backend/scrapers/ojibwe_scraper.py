"""Scrape Ojibwe translations to build English-Ojibwe dictionaries.

This module scrapes translations from online sources, stores them in MongoDB,
and tracks attempted words to avoid redundant scraping. It prioritizes untranslated
words by frequency of usage.
"""
import json
import os
import sys
import time
from typing import List, Dict, Set, Union
import sqlite3

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
    "https://glosbe.com/oj/en",    # Glosbe Ojibwe-to-English
]

# Threshold for initial full scrape
TRANSLATION_THRESHOLD = 0.2  # 20% threshold

# Custom Ojibwe alphabet set for pagination
OJIBWE_ALPHABET = {
    'a', 'aa', 'e', 'i', 'ii', 'o', 'oo', 'u',
    'b', 'd', 'g', 'h', 'j', 'k', 'm', 'n', 'p', 's', 't', 'w', 'y', 'z', 'zh',
}

# Set up retry mechanism for requests
session = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)
session.mount("http://", HTTPAdapter(max_retries=retries))
session.mount("https://", HTTPAdapter(max_retries=retries))


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


def scrape_full_dictionary(base_url: str) -> List[Dict[str, Union[str, List[str]]]]:
    """Scrape the entire dictionary from a single website, including definitions.

    Args:
        base_url (str): Base URL of the site to scrape (e.g., ojibwe.lib.umn.edu).

    Returns:
        List[Dict[str, Union[str, List[str]]]]: List of dictionaries containing
            translations and definitions.
    """
    translations: List[Dict[str, Union[str, List[str]]]] = []
    try:
        if "ojibwe.lib" in base_url:
            # Paginate through /browse/ojibwe/{letter} using Ojibwe alphabet
            for letter in OJIBWE_ALPHABET:
                url = f"{base_url}/browse/ojibwe/{letter}"
                print(f"Debug: Attempting to scrape {url}")
                response = session.get(url, timeout=10)
                response.raise_for_status()
                print(f"Debug: Received response with status {response.status_code}")
                soup = BeautifulSoup(response.text, "html.parser")
                print(f"Debug: Parsed HTML, length of content: {len(response.text)} characters")

                entries = soup.select(".search-results .main-entry-search")
                print(f"Debug: Found {len(entries)} .main-entry-search entries")
                for entry in entries:
                    english_div = entry.select_one(".english-search-main-entry")
                    if english_div:
                        # Extract Ojibwe term from lemma
                        lemma_span = english_div.select_one(".main-entry-title .lemma")
                        ojibwe_text = lemma_span.text.strip() if lemma_span else "N/A"

                        # Extract full text as potential definition
                        full_text = english_div.get_text(separator=" ").strip()

                        # Isolate English translations by removing Ojibwe term
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
                            translation = {
                                "ojibwe_text": ojibwe_text,
                                "english_text": english_texts,
                                "definition": full_text,
                            }
                            translations.append(translation)
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
                time.sleep(1)  # Delay to avoid rate limiting

        elif "glosbe.com" in base_url:
            # Fetch all English words
            english_words = get_english_words()
            for word in english_words:
                url = f"{base_url}/{word}"
                print(f"Debug: Attempting to scrape {url}")
                try:
                    response = session.get(url, timeout=10)
                    response.raise_for_status()
                    print(f"Debug: Received response with status {response.status_code}")
                    soup = BeautifulSoup(response.text, "html.parser")
                    print(
                        f"Debug: Parsed HTML, length of content: "
                        f"{len(response.text)} characters"
                    )

                    entries = soup.select(".translation")
                    print(f"Debug: Found {len(entries)} .translation entries")
                    for entry in entries:
                        ojibwe = entry.find("span", class_="translation-term")
                        english = entry.find("span", class_="translation-translation")
                        print(
                            f"Debug: Found Ojibwe: {ojibwe is not None}, "
                            f"English: {english is not None}"
                        )
                        if ojibwe and english:
                            ojibwe_text = ojibwe.text.strip()
                            english_text = english.text.strip()
                            definition = f"{ojibwe_text}: {english_text}"  # Placeholder
                            translation = {
                                "ojibwe_text": ojibwe_text,
                                "english_text": [english_text],
                                "definition": definition,
                            }
                            translations.append(translation)
                            update_or_create_ojibwe_to_english(ojibwe_text, [english_text])
                            update_or_create_english_to_ojibwe(english_text, ojibwe_text)
                            print(
                                f"Debug: Added translation - Ojibwe: {ojibwe_text}, "
                                f"English: {english_text}"
                            )
                        else:
                            print(
                                f"Debug: Failed to extract translation for entry: "
                                f"{entry.prettify()[:200]}..."
                            )
                except requests.RequestException as e:
                    print(f"Error scraping {url}: {e}")
                    continue
                time.sleep(1)  # Delay to avoid rate limiting

    except Exception as e:
        print(f"Error scraping full dictionary from {base_url}: {e}")
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


def scrape_ojibwe() -> List[Dict[str, Union[str, List[str]]]]:
    """Scrape Ojibwe translations based on coverage threshold.

    Performs a full scrape if less than 20% of words are translated, otherwise
    targets missing words. Tracks attempted words to avoid redundant scraping.

    Returns:
        List[Dict[str, Union[str, List[str]]]]: List of new translations.
    """
    translations: List[Dict[str, Union[str, List[str]]]] = []
    dict_size = get_english_dict_size()
    translation_count = get_existing_translations_count()

    # Load attempted words
    attempted_path = os.path.join(BASE_DIR, "data", "scraped_words.json")
    attempted_words = load_attempted_words(attempted_path)

    if should_perform_full_scrape():
        print(
            f"Translation coverage is below 20% ({translation_count}/{dict_size}). "
            "Performing full scrape."
        )
        for base_url in URLS:
            translations.extend(scrape_full_dictionary(base_url))
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
        else:
            print(
                f"Found {len(remaining_words)} unattempted missing words out of "
                f"{len(missing_words)} total missing words."
            )

        print(f"Attempting to find translations for {len(remaining_words)} words.")
        for word in remaining_words:
            for base_url in URLS:
                try:
                    # Construct query URL for each site
                    if "ojibwe.lib" in base_url:
                        url = f"{base_url}?utf8=%E2%9C%93&q={word}&search_field=all_fields"
                    elif "glosbe.com" in base_url:
                        url = f"{base_url}/{word}"

                    print(f"Debug: Requesting {url}")
                    response = session.get(url, timeout=10)
                    response.raise_for_status()
                    print(f"Debug: Received response with status {response.status_code}")
                    soup = BeautifulSoup(response.text, "html.parser")
                    print(
                        f"Debug: Parsed HTML, length of content: "
                        f"{len(response.text)} characters"
                    )

                    ojibwe_text = None
                    english_text = word

                    if "ojibwe.lib" in base_url:
                        entry = soup.select_one(".search-results .main-entry-search")
                        print(f"Debug: Found {entry is not None} .main-entry-search entry")
                        if entry:
                            english_div = entry.select_one(".english-search-main-entry")
                            if english_div:
                                lemma_span = english_div.select_one(
                                    ".main-entry-title .lemma"
                                )
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
                                    update_or_create_ojibwe_to_english(
                                        ojibwe_text, english_texts
                                    )
                                    for e_text in english_texts:
                                        update_or_create_english_to_ojibwe(
                                            e_text, ojibwe_text
                                        )
                            else:
                                print("Debug: No .english-search-main-entry found")

                    elif "glosbe.com" in base_url:
                        entry = soup.select_one(".translation")
                        print(f"Debug: Found {entry is not None} .translation entry")
                        if entry:
                            ojibwe = entry.find("span", class_="translation-term")
                            english = entry.find("span", class_="translation-translation")
                            print(
                                f"Debug: Found Ojibwe: {ojibwe is not None}, "
                                f"English: {english is not None}"
                            )
                            if ojibwe and english:
                                ojibwe_text = ojibwe.text.strip()
                                english_text = english.text.strip()
                                definition = f"{ojibwe_text}: {english_text}"
                                translations.append({
                                    "ojibwe_text": ojibwe_text,
                                    "english_text": [english_text],
                                    "definition": definition,
                                })
                                update_or_create_ojibwe_to_english(
                                    ojibwe_text, [english_text]
                                )
                                update_or_create_english_to_ojibwe(
                                    english_text, ojibwe_text
                                )

                    if ojibwe_text:
                        print(f"Found translation for '{word}': {ojibwe_text}")
                    attempted_words.add(word)
                    save_attempted_words(attempted_words, attempted_path)
                    time.sleep(1)  # Delay to avoid rate limiting
                except Exception as e:
                    print(f"Error scraping {url} for word '{word}': {e}")

    print(f"Scraped and stored {len(translations)} new Ojibwe translations.")

    # Perform semantic analysis after scraping
    print("Performing semantic analysis on translations...")
    from translations.utils.analysis import print_semantic_matches
    print_semantic_matches()

    return translations


if __name__ == "__main__":
    scrape_ojibwe()
