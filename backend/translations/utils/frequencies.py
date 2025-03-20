"""Shared word frequency data for ranking English words by usage."""
import os
import json
import time
from typing import Dict
import requests

# Base directory (three levels up from frequencies.py to backend/)
BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# Path to the word frequency JSON file
FREQUENCY_PATH = os.path.join(BASE_DIR, "data", "word_frequency.json")

# URL for a public word frequency list (simplified for demonstration)
# Replace with a more comprehensive source like norvig.com/ngrams/count_1w.txt
FREQUENCY_URL = "https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt"

# Update threshold (e.g., update if file is older than 7 days)
UPDATE_THRESHOLD_SECONDS = 7 * 24 * 60 * 60  # 7 days in seconds


def fetch_word_frequencies() -> Dict[str, int]:
    """Fetch word frequencies from a public source.

    For demonstration, this uses a simple word list and assigns frequencies.
    In practice, use a real frequency list like norvig.com/ngrams/count_1w.txt.

    Returns:
        Dict[str, int]: Dictionary mapping words to their frequencies.
    """
    try:
        response = requests.get(FREQUENCY_URL, timeout=10)
        response.raise_for_status()
        words = response.text.splitlines()
        # Assign decreasing frequencies (simplified for demo)
        # In a real scenario, parse a frequency list with actual counts
        freqs = {}
        for i, word in enumerate(words[:10000]):  # Limit to top 10,000 words
            freqs[word.lower()] = 1000000 - i  # Decreasing frequency
        return freqs
    except requests.RequestException as e:
        print(f"Error fetching word frequencies: {e}")
        return {}


def load_word_frequencies() -> Dict[str, int]:
    """Load word frequencies from a JSON file, updating if necessary.

    Checks if word_frequency.json exists and is up-to-date. If not, fetches
    a new list and saves it.

    Returns:
        Dict[str, int]: Dictionary mapping words to their frequencies.
    """
    # Check if the file exists and its age
    should_update = False
    if not os.path.exists(FREQUENCY_PATH):
        print(f"Word frequency file not found at {FREQUENCY_PATH}. Creating new file.")
        should_update = True
    else:
        file_age = time.time() - os.path.getmtime(FREQUENCY_PATH)
        if file_age > UPDATE_THRESHOLD_SECONDS:
            print(f"Word frequency file is outdated (age: {file_age} seconds). Updating.")
            should_update = True

    if should_update:
        freqs = fetch_word_frequencies()
        if freqs:
            with open(FREQUENCY_PATH, "w", encoding="utf-8") as f:
                json.dump(freqs, f)
            print(f"Saved updated frequencies to {FREQUENCY_PATH}")
        else:
            print("Failed to fetch frequencies. Using empty dictionary.")
            freqs = {}
    else:
        try:
            with open(FREQUENCY_PATH, "r", encoding="utf-8") as f:
                freqs = json.load(f)
            print(f"Loaded frequencies from {FREQUENCY_PATH}")
        except Exception as e:
            print(f"Error loading frequencies: {e}. Fetching new list.")
            freqs = fetch_word_frequencies()
            if freqs:
                with open(FREQUENCY_PATH, "w", encoding="utf-8") as f:
                    json.dump(freqs, f)

    return freqs


# Load frequencies at module level
WORD_FREQUENCIES = load_word_frequencies()
