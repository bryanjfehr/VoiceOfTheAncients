"""Module to dynamically determine the number of words in the English dictionary database."""
import sqlite3
from typing import Optional

def get_english_dict_size(db_path: str = "translations.db") -> int:
    """Retrieve the number of words in the English dictionary SQLite table.
    Args:
        db_path (str): Path to the SQLite database file.
    Returns:
        int: Number of words in the english_dict table.
    Raises:
        sqlite3.Error: If the database query fails.
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM english_dict")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except sqlite3.Error as e:
        print(f"Error fetching dictionary size: {e}")
        return 0
