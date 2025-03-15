"""Scrape Ojibwe translations for missing English words to build the English-Ojibwe dictionary."""
import requests
import time
from bs4 import BeautifulSoup
from translations.models import update_or_create_translation, get_all_translations

# Base URLs for scraping (query strings will be appended)
URLS = [
    "https://ojibwe.lib.umn.edu/search",  # Ojibwe People's Dictionary
    "https://glosbe.com/oj/en",           # Glosbe Ojibwe-English
    "http://www.native-languages.org",    # Native Languages
]

def get_missing_words() -> set:
    """Fetch the list of English words missing Ojibwe translations.
    Returns:
        set: Set of English words without translations.
    """
    # Simulate the get_gaps endpoint logic
    try:
        # Load English dictionary from SQLite
        conn = sqlite3.connect("translations.db")
        cursor = conn.cursor()
        cursor.execute("SELECT word FROM english_dict")
        english_words = {row[0] for row in cursor.fetchall()}
        conn.close()

        # Get existing translations from MongoDB
        translations = get_all_translations()
        translated_english = {t["english_text"] for t in translations if t.get("english_text")}

        # Identify gaps
        return english_words - translated_english
    except Exception as e:
        print(f"Error fetching missing words: {e}")
        return set()

def scrape_ojibwe() -> list[dict]:
    """Scrape Ojibwe translations for missing English words from multiple websites.
    Returns a list of dictionaries containing new translations.
    """
    translations = []
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
                elif "native-languages.org" in base_url:
                    url = f"{base_url}/search.php?query={word}"  # Hypothetical query string

                response = requests.get(url, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")

                ojibwe_text = None
                english_text = word  # The word we’re searching for

                if "ojibwe.lib" in base_url:
                    # Scrape Ojibwe People's Dictionary
                    entry = soup.select_one(".search-result")
                    if entry:
                        ojibwe = entry.find("span", class_="ojibwe-word")
                        if ojibwe:
                            ojibwe_text = ojibwe.text.strip()

                elif "glosbe.com" in base_url:
                    # Scrape Glosbe Ojibwe-English
                    entry = soup.select_one(".phrase__translation")
                    if entry:
                        ojibwe = entry.find("span", class_="phrase__text")
                        if ojibwe:
                            ojibwe_text = ojibwe.text.strip()

                elif "native-languages.org" in base_url:
                    # Scrape Native Languages
                    entry = soup.select_one(".wordlist tr td")
                    if entry:
                        ojibwe_text = entry.text.strip()

                if ojibwe_text:
                    translations.append({"ojibwe_text": ojibwe_text, "english_text": english_text})
                    update_or_create_translation(ojibwe_text, {"english_text": english_text})
                    print(f"Found translation for '{word}': {ojibwe_text}")

                time.sleep(2)  # Respect rate limits
            except Exception as e:
                print(f"Error scraping {url} for word '{word}': {e}")

    print(f"Scraped and stored {len(translations)} new Ojibwe translations.")
    return translations

if __name__ == "__main__":
    scrape_ojibwe()
