"""Scrape Ojibwe translations from top websites."""
import requests
import time
from bs4 import BeautifulSoup
from translations.models import create_translation, update_or_create_translation

# List of URLs to scrape (adjust selectors based on site structure)
URLS = [
    "https://ojibwe.lib.umn.edu",  # Ojibwe People's Dictionary
    "https://glosbe.com/oj/en",     # Glosbe Ojibwe-English
    "http://www.native-languages.org/ojibwe_words.htm",  # Native Languages
]

def scrape_ojibwe() -> list[dict]:
    """Scrape Ojibwe translations and store them in MongoDB.
    Returns a list of dictionaries containing scraped translations.
    """
    translations = []

    for url in URLS:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()  # Raise exception for bad status codes
            soup = BeautifulSoup(response.text, "html.parser")

            if "ojibwe.lib" in url:
                entries = soup.select(".entry")  # Hypothetical selector
                for entry in entries:
                    ojibwe = entry.find(class_="ojibwe")
                    english = entry.find(class_="english")
                    if ojibwe and english:
                        ojibwe_text = ojibwe.text.strip()
                        english_text = english.text.strip()
                        translations.append(
                            {"ojibwe_text": ojibwe_text, "english_text": english_text}
                        )
                        update_or_create_translation(ojibwe_text, {"english_text": english_text})
            # Add parsing for Glosbe, Native Languages similarly (adjust selectors)

            time.sleep(2)  # Respect site rate limits
        except Exception as e:
            print(f"Error scraping {url}: {e}")

    return translations


if __name__ == "__main__":
    scrape_ojibwe()
