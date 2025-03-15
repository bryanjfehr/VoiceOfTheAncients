"""Module to fetch and update the English dictionary from a remote JSON source."""
import requests
import sqlite3
from typing import Set, Dict, Any

DICTIONARY_URL = "https://raw.githubusercontent.com/matthewreagan/WebstersEnglishDictionary/master/dictionary.json"

def fetch_dictionary() -> Dict[str, Any]:
    """Fetch the English dictionary from a remote JSON source.
    Returns:
        Dict[str, Any]: Dictionary with words as keys and definitions as values.
    Raises:
        requests.RequestException: If the fetch fails.
    """
    response = requests.get(DICTIONARY_URL, timeout=10)
    response.raise_for_status()  # Raise exception for bad status codes
    return response.json()

def get_existing_words(db_path: str = "translations.db") -> Set[str]:
    """Retrieve all existing words from the SQLite english_dict table.
    Creates the table if it doesn't exist.
    Args:
        db_path (str): Path to the SQLite database file.
    Returns:
        Set[str]: Set of existing English words.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Ensure the table exists
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS english_dict (
            word TEXT PRIMARY KEY
        )
        """
    )
    conn.commit()
    # Fetch existing words
    cursor.execute("SELECT word FROM english_dict")
    existing_words = {row[0] for row in cursor.fetchall()}
    conn.close()
    return existing_words

def update_dictionary(db_path: str = "translations.db") -> int:
    """Fetch the latest dictionary and update the SQLite database with new words.
    Args:
        db_path (str): Path to the SQLite database file.
    Returns:
        int: Number of new words added.
    """
    try:
        # Fetch the dictionary
        dictionary_data = fetch_dictionary()
        new_words = set(dictionary_data.keys())

        # Get existing words
        existing_words = get_existing_words(db_path)

        # Determine new words to add
        words_to_add = new_words - existing_words
        if not words_to_add:
            print("No new words to add.")
            return 0

        # Update the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        for word in words_to_add:
            cursor.execute(
                "INSERT OR IGNORE INTO english_dict (word) VALUES (?)", (word,)
            )
        conn.commit()
        conn.close()

        print(f"Added {len(words_to_add)} new words to the dictionary.")
        return len(words_to_add)

    except requests.RequestException as e:
        print(f"Failed to fetch dictionary: {e}")
        return 0

if __name__ == "__main__":
    update_dictionary()