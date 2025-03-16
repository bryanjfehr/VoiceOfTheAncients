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
)
from translations.utils.get_dict_size import get_english_dict_size

# Base URLs for scraping
URLS = [
    "https://ojibwe.lib.umn.edu",  # Ojibwe People's Dictionary
    "https://glosbe.com/oj/en",    # Glosbe Ojibwe-to-English
]

# Threshold for initial full scrape (20% as adjusted)
TRANSLATION_THRESHOLD = 0.2  # 20% threshold

# Custom Ojibwe alphabet set
ojibwe_alphabet = {
    'a', 'aa', 'e', 'i', 'ii', 'o', 'oo', 'u',
    'b', 'd', 'g', 'h', 'j', 'k', 'm', 'n', 'p', 's', 't', 'w', 'y', 'z', 'zh'
}

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
        bool: True if less than 20% of words are translated, False otherwise.
    """
    dict_size = get_english_dict_size()
    if dict_size == 0:
        print("Warning: English dictionary size is 0. Performing full scrape.")
        return True
    translation_count = get_existing_translations_count()
    print(f"Debug: Dictionary size = {dict_size}, Translation count = {translation_count}")
    return (translation_count / dict_size) < TRANSLATION_THRESHOLD

def get_english_words(limit: int = 100) -> list[str]:
    """Fetch a limited number of English words from the SQLite dictionary for Glosbe scraping.
    Args:
        limit (int): Maximum number of words to fetch.
    Returns:
        list[str]: List of English words.
    """
    try:
        conn = sqlite3.connect("translations.db")
        cursor = conn.cursor()
        cursor.execute("SELECT word FROM english_dict LIMIT ?", (limit,))
        words = [row[0] for row in cursor.fetchall()]
        conn.close()
        return words
    except sqlite3.Error as e:
        print(f"Error fetching English words: {e}")
        return []

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
            # Paginate through /browse/ojibwe/{letter} using Ojibwe alphabet
            for letter in ojibwe_alphabet:
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
                    # Target the english-search-main-entry div
                    english_div = entry.select_one(".english-search-main-entry")
                    if english_div:
                        # Extract Ojibwe term from lemma
                        lemma_span = english_div.select_one(".main-entry-title .lemma")
                        ojibwe_text = lemma_span.text.strip() if lemma_span else "N/A"
                        
                        # Extract full text from english-search-main-entry
                        full_text = english_div.get_text(separator=" ").strip()
                        
                        # Isolate English translation by removing the Ojibwe term
                        english = full_text.replace(ojibwe_text, "").strip()
                        english_texts = [e.strip() for e in english.split(",") if e.strip() and e.lower() != ojibwe_text.lower()]
                        
                        # Debug output
                        print(f"Debug: Found Ojibwe: {ojibwe_text is not None}, English: {bool(english_texts)}")
                        if ojibwe_text and english_texts:
                            translations.append({"ojibwe_text": ojibwe_text, "english_text": english_texts})
                            update_or_create_ojibwe_to_english(ojibwe_text, english_texts)
                            for e_text in english_texts:
                                update_or_create_english_to_ojibwe(e_text, ojibwe_text)
                            print(f"Debug: Added translation - Ojibwe: {ojibwe_text}, English: {english_texts}")
                        else:
                            print(f"Debug: Failed to extract translation for entry: {entry.prettify()[:200]}...")
                    else:
                        print("Debug: No .english-search-main-entry found in this entry")

                time.sleep(1)  # Reduced delay to 1 second for faster scraping

        elif "glosbe.com" in base_url:
            # Iterate over English words
            english_words = get_english_words(limit=100)  # Limit to 100 words for testing
            for word in english_words:
                url = f"{base_url}/{word}"  # Corrected to Ojibwe-to-English direction
                print(f"Debug: Attempting to scrape {url}")
                try:
                    response = session.get(url, timeout=10)
                    response.raise_for_status()
                    print(f"Debug: Received response with status {response.status_code}")
                    soup = BeautifulSoup(response.text, "html.parser")
                    print(f"Debug: Parsed HTML, length of content: {len(response.text)} characters")

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
                except requests.RequestException as e:
                    print(f"Error scraping {url}: {e}")
                    continue  # Skip to the next word on error

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
    Performs a full scrape if less than 20% of words are translated, otherwise targets missing words.
    Returns a list of dictionaries containing new translations.
    """
    translations = []
    dict_size = get_english_dict_size()
    translation_count = get_existing_translations_count()

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
                        entry = soup.select_one(".search-results .main-entry-search")
                        print(f"Debug: Found {entry is not None} .main-entry-search entry")
                        if entry:
                            # Target the english-search-main-entry div
                            english_div = entry.select_one(".english-search-main-entry")
                            if english_div:
                                # Extract Ojibwe term from lemma
                                lemma_span = english_div.select_one(".main-entry-title .lemma")
                                ojibwe_text = lemma_span.text.strip() if lemma_span else "N/A"
                                
                                # Extract full text from english-search-main-entry
                                full_text = english_div.get_text(separator=" ").strip()
                                
                                # Isolate English translation by removing the Ojibwe term
                                english = full_text.replace(ojibwe_text, "").strip()
                                english_texts = [e.strip() for e in english.split(",") if e.strip() and e.lower() != ojibwe_text.lower()]
                                
                                # Debug output
                                print(f"Debug: Found Ojibwe: {ojibwe_text is not None}, English: {bool(english_texts)}")
                                if ojibwe_text and english_texts:
                                    translations.append({"ojibwe_text": ojibwe_text, "english_text": english_texts})
                                    update_or_create_ojibwe_to_english(ojibwe_text, english_texts)
                                    for e_text in english_texts:
                                        update_or_create_english_to_ojibwe(e_text, ojibwe_text)
                            else:
                                print("Debug: No .english-search-main-entry found in this entry")

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

    # Perform semantic analysis after scraping
    print("Performing semantic analysis on translations...")
    from translations.utils.analysis import print_semantic_matches
    print_semantic_matches()

    return translations
    """Scrape Ojibwe translations based on coverage threshold.
    Performs a full scrape if less than 20% of words are translated, otherwise targets missing words.
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
                        entry = soup.select_one(".search-results .main-entry-search")
                        print(f"Debug: Found {entry is not None} .main-entry-search entry")
                        if entry:
                            # Target the english-search-main-entry div
                            english_div = entry.select_one(".english-search-main-entry")
                            if english_div:
                                # Extract Ojibwe term from lemma
                                lemma_span = english_div.select_one(".main-entry-title .lemma")
                                ojibwe_text = lemma_span.text.strip() if lemma_span else "N/A"
                                
                                # Extract full text from english-search-main-entry
                                full_text = english_div.get_text(separator=" ").strip()
                                
                                # Isolate English translation by removing the Ojibwe term
                                english = full_text.replace(ojibwe_text, "").strip()
                                english_texts = [e.strip() for e in english.split(",") if e.strip() and e.lower() != ojibwe_text.lower()]
                                
                                # Debug output
                                print(f"Debug: Found Ojibwe: {ojibwe_text is not None}, English: {bool(english_texts)}")
                                if ojibwe_text and english_texts:
                                    translations.append({"ojibwe_text": ojibwe_text, "english_text": english_texts})
                                    update_or_create_ojibwe_to_english(ojibwe_text, english_texts)
                                    for e_text in english_texts:
                                        update_or_create_english_to_ojibwe(e_text, ojibwe_text)
                            else:
                                print("Debug: No .english-search-main-entry found in this entry")

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
