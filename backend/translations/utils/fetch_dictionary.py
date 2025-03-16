"""Module to fetch and update the English dictionary from a remote JSON source."""
import requests
import sqlite3
import json
import os
from typing import Set, Dict, Any


DICTIONARY_URL = "https://raw.githubusercontent.com/matthewreagan/WebstersEnglishDictionary/master/dictionary.json"

# Base directory for the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JSON_PATH = os.path.join(BASE_DIR, "data", "english_dict.json")


def fetch_dictionary() -> Dict[str, Any]:
    """Fetch the English dictionary from a remote JSON source."""
    response = requests.get(DICTIONARY_URL, timeout=10)
    response.raise_for_status()
    return response.json()


def get_existing_words(db_path: str = "translations.db") -> Set[str]:
    """Retrieve all existing words from the SQLite english_dict table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS english_dict (word TEXT PRIMARY KEY)")
    conn.commit()
    cursor.execute("SELECT word FROM english_dict")
    existing_words = {row[0] for row in cursor.fetchall()}
    conn.close()
    return existing_words


def update_dictionary(db_path: str = "translations.db", json_path: str = JSON_PATH) -> int:
    """Fetch the latest dictionary, update SQLite, and save to JSON."""
    try:
        dictionary_data = fetch_dictionary()
        new_words = set(dictionary_data.keys())

        # Ensure the data directory exists
        os.makedirs(os.path.dirname(json_path), exist_ok=True)

        # Save to JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(dictionary_data, f)
        print(f"Saved dictionary to {json_path}")

        # Update SQLite (adjust db_path if needed)
        db_full_path = os.path.join(BASE_DIR, db_path)
        existing_words = get_existing_words(db_full_path)
        words_to_add = new_words - existing_words
        if not words_to_add:
            print("No new words to add to SQLite.")
            return 0

        conn = sqlite3.connect(db_full_path)
        cursor = conn.cursor()
        for word in words_to_add:
            cursor.execute("INSERT OR IGNORE INTO english_dict (word) VALUES (?)", (word,))
        conn.commit()
        conn.close()

        print(f"Added {len(words_to_add)} new words to SQLite.")
        return len(words_to_add)
    except requests.RequestException as e:
        print(f"Failed to fetch dictionary: {e}")
        return 0


if __name__ == "__main__":
    update_dictionary()