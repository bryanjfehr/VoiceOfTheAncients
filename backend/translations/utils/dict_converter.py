"""Utility script to convert a JSON English dictionary to SQLite."""
import json
import sqlite3

def json_to_sqlite(json_path: str, db_path: str = "translations.db") -> None:
    """Convert a JSON file of English words to an SQLite database.
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

if __name__ == "__main__":
    json_to_sqlite("../data/english_dict.json")
