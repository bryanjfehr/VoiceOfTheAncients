"""Utility script to populate the English dictionary table from a JSON file."""
import json
import sqlite3


def populate_english_dict(json_path: str, db_path: str = "translations.db") -> None:
    """Populate the english_dict table in SQLite from a JSON file.
    Args:
        json_path (str): Path to the JSON file containing English words.
        db_path (str): Path to the SQLite database file (default: translations.db).
    """
    with open(json_path, "r", encoding="utf-8") as f:
        english_dict = json.load(f)  # Assuming a list of words

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS english_dict (
            word TEXT PRIMARY KEY
        )
        """
    )

    # Insert words, avoiding duplicates
    for word in english_dict:
        cursor.execute("INSERT OR IGNORE INTO english_dict (word) VALUES (?)", (word,))

    conn.commit()
    conn.close()
    print(f"Populated {len(english_dict)} words into english_dict table")


def clear_english_dict(db_path: str = "translations.db") -> None:
    """Clear all entries from the english_dict table for testing.
    Args:
        db_path (str): Path to the SQLite database file (default: translations.db).
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM english_dict")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    populate_english_dict("../data/english_dict.json")
