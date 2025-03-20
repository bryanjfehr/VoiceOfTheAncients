"""Compile a list of common English words missing Ojibwe translations."""
import os
import json
import sys
from typing import List, Dict, Set

# Add the base directory to the system path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

# Configure Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vota_backend.settings")
import django
django.setup()

from translations.models import get_all_ojibwe_to_english
from translations.utils.frequencies import WORD_FREQUENCIES


def compile_missing_translations(output_path: str, top_n: int = 1000) -> None:
    """Compile a list of common English words missing Ojibwe translations.

    Args:
        output_path (str): Path to save the list of missing translations.
        top_n (int): Number of top common words to consider. Defaults to 1000.
    """
    # Get all Ojibwe-to-English translations from MongoDB
    ojibwe_translations = get_all_ojibwe_to_english()
    translated_english = {t["english_text"][0].lower() for t in ojibwe_translations if t.get("english_text")}

    # Get the top N most common English words
    sorted_words = sorted(WORD_FREQUENCIES.items(), key=lambda x: x[1], reverse=True)[:top_n]
    common_words = {word.lower() for word, _ in sorted_words}

    # Identify missing translations
    missing_words = common_words - translated_english
    missing_words = sorted(missing_words, key=lambda x: WORD_FREQUENCIES.get(x, 0), reverse=True)

    # Save the list to a JSON file
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(list(missing_words), f, indent=2)
    print(f"Saved {len(missing_words)} missing common English words to {output_path}")


if __name__ == "__main__":
    output_path = os.path.join(BASE_DIR, "data", "missing_common_translations.json")
    compile_missing_translations(output_path, top_n=1000)
