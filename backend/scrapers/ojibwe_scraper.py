"""Scrape Ojibwe translations to build the English-Ojibwe and Ojibwe-to-English dictionaries."""
import os
import sys
import requests
import time
import sqlite3
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Set the base directory to the backend folder
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
    get_english_dict_size,
)

# Base URLs for scraping
URLS = [
    "https://ojibwe.lib.umn.edu/search",  # Ojibwe People's Dictionary
    "https://glosbe.com/oj/en",           # Glosbe Ojibwe-English
]

# Threshold for initial full scrape (0.01% as adjusted)
TRANSLATION_THRESHOLD = 0.0001  # 0.01% threshold

# Set up retry mechanism for requests
session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
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
        bool: True if less than 0.01% of words are translated, False otherwise.
    """
    dict_size = get_english_dict_size()
    if dict_size == 0:
        print("Warning: English dictionary size is 0. Performing full scrape.")
        return True
    translation_count = get_existing_translations_count()
    print(f"Debug: Dictionary size = {dict_size}, Translation count = {translation_count}")
    return (translation_count / dict_size) < TRANSLATION_THRESHOLD

def scrape_full_dictionary(base_url: str) -> list[dict]:
    """Scrape the entire dictionary from a single website, populating both translation collections.
    Args:
        base_url (str): Base URL of the site to scrape.
    Returns:
        list[dict]: List of dictionaries containing translations.
    """
    translations = []
    try:
        if "ojibwe.lib" in base_url:
            url = f"{base_url}?utf8=%E2%9C%93&q=*&search_field=all_fields"  # Search all entries
        elif "glosbe.com" in base_url:
            url = base_url  # Default page, may need pagination

        print(f"Debug: Attempting to scrape {url}")
        response = session.get(url, timeout=10)
        response.raise_for_status()
        print(f"Debug: Received response with status {response.status_code}")
        soup = BeautifulSoup(response.text, "html.parser")
        print(f"Debug: Parsed HTML, length of content: {len(response.text)} characters")

        if "ojibwe.lib" in base_url:
            # Scrape all entries from Ojibwe People's Dictionary
            entries = soup.select(".col-sm-9")
            print(f"Debug: Found {len(entries)} .col-sm-9 entries")
            for entry in entries:
                ojibwe = entry.find("span", class_="lemma")
                glosses = entry.find("p", class_="glosses")
                print(f"Debug: Found Ojibwe: {ojibwe is not None}, Glosses: {glosses is not None}")
                if ojibwe and glosses:
                    ojibwe_text = ojibwe.text.strip()
                    english_texts = [g.strip() for g in glosses.text.split(",") if g.strip()]
                    translations.append({"ojibwe_text": ojibwe_text, "english_text": english_texts})
                    update_or_create_ojibwe_to_english(ojibwe_text, english_texts)
                    for english_text in english_texts:
                        update_or_create_english_to_ojibwe(english_text, ojibwe_text)
                    print(f"Debug: Added translation - Ojibwe: {ojibwe_text}, English: {english_texts}")
                else:
                    print(f"Debug: Failed to extract translation for entry: {entry.prettify()[:200]}...")

        elif "glosbe.com" in base_url:
            # Scrape all entries from Glosbe (may need pagination)
            entries = soup.select(".translation")
            print(f"Debug: Found {len(entries)} .translation entries")
            for entry in entries:
                ojibwe = entry.find("span", class_="translation-term")
                english = entry.find("span", class_="translation-translation")
                print(f"Debug: Found Ojibwe: {ojibwe is not None}, English: {english is not None}")
                if ojibwe and english:
                    ojibwe_text = ojibwe.text.strip()
                    english_text = english.text.strip()
                    translations.append({"ojibwe_text": ojibwe_text, "english_text": [english_text]})
                    update_or_create_ojibwe_to_english(ojibwe_text, [english_text])
                    update_or_create_english_to_ojibwe(english_text, ojibwe_text)
                    print(f"Debug: Added translation - Ojibwe: {ojibwe_text}, English: {english_text}")
                else:
                    print(f"Debug: Failed to extract translation for entry: {entry.prettify()[:200]}...")

        time.sleep(1)  # Reduced delay to 1 second for faster scraping
    except Exception as e:
        print(f"Error scraping full dictionary from {base_url}: {e}")
    return translations

def get_missing_words() -> set:
    """Fetch the list of English words missing Ojibwe translations.
    Returns:
        set: Set of English words without translations.
    """
    try:
        # Load English dictionary from SQLite
        conn = sqlite3.connect("translations.db")
        cursor = conn.cursor()
        cursor.execute("SELECT word FROM english_dict")
        english_words = {row[0] for row in cursor.fetchall()}
        conn.close()

        # Get existing translations from MongoDB (English-to-Ojibwe)
        translations = get_all_english_to_ojibwe()
        translated_english = {t["english_text"][0] for t in translations if t.get("english_text")}  # Take first English word

        # Identify gaps
        return english_words - translated_english
    except Exception as e:
        print(f"Error fetching missing words: {e}")
        return set()

def scrape_ojibwe() -> list[dict]:
    """Scrape Ojibwe translations based on coverage threshold.
    Performs a full scrape if less than 0.01% of words are translated, otherwise targets missing words.
    Returns a list of dictionaries containing new translations.
    """
    translations = []
    dict_size = get_english_dict_size()
    translation_count = get_existing_translations_count()

    if should_perform_full_scrape():
        print(
            f"Translation coverage is below 0.01% ({translation_count}/{dict_size}). "
            "Performing full scrape."
        )
        for base_url in URLS:
            translations.extend(scrape_full_dictionary(base_url))
    else:
        missing_words = get_missing_words()
        if not missing_words:
            print("No missing words to scrape.")
            return translations

        print(f"Attempting to find translations for {len(missing_words)} missing words.")
        for word in missing_words:
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
                    print(f"Debug: Parsed HTML, length of content: {len(response.text)} characters")

                    ojibwe_text = None
                    english_text = word  # The word we’re searching for

                    if "ojibwe.lib" in base_url:
                        # Scrape Ojibwe People's Dictionary
                        entry = soup.select_one(".col-sm-9")
                        print(f"Debug: Found {entry is not None} .col-sm-9 entry")
                        if entry:
                            ojibwe = entry.find("span", class_="lemma")
                            glosses = entry.find("p", class_="glosses")
                            print(f"Debug: Found Ojibwe: {ojibwe is not None}, Glosses: {glosses is not None}")
                            if ojibwe and glosses:
                                ojibwe_text = ojibwe.text.strip()
                                english_texts = [g.strip() for g in glosses.text.split(",") if g.strip()]
                                translations.append({"ojibwe_text": ojibwe_text, "english_text": english_texts})
                                update_or_create_ojibwe_to_english(ojibwe_text, english_texts)
                                for e_text in english_texts:
                                    update_or_create_english_to_ojibwe(e_text, ojibwe_text)

                    elif "glosbe.com" in base_url:
                        # Scrape Glosbe Ojibwe-English
                        entry = soup.select_one(".translation")
                        print(f"Debug: Found {entry is not None} .translation entry")
                        if entry:
                            ojibwe = entry.find("span", class_="translation-term")
                            english = entry.find("span", class_="translation-translation")
                            print(f"Debug: Found Ojibwe: {ojibwe is not None}, English: {english is not None}")
                            if ojibwe and english:
                                ojibwe_text = ojibwe.text.strip()
                                english_text = english.text.strip()
                                translations.append({"ojibwe_text": ojibwe_text, "english_text": [english_text]})
                                update_or_create_ojibwe_to_english(ojibwe_text, [english_text])
                                update_or_create_english_to_ojibwe(english_text, ojibwe_text)

                    if ojibwe_text:
                        print(f"Found translation for '{word}': {ojibwe_text}")

                    time.sleep(1)  # Reduced delay to 1 second for faster scraping
                except Exception as e:
                    print(f"Error scraping {url} for word '{word}': {e}")

    print(f"Scraped and stored {len(translations)} new Ojibwe translations.")
    return translations

if __name__ == "__main__":
    scrape_ojibwe()
