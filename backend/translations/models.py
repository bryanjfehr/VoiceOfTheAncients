"""MongoDB models using pymongo for translation data management."""
from typing import Optional
from pymongo import MongoClient
from decouple import config

# MongoDB connection setup
client = MongoClient(config("MONGO_URI"))
db = client["vota_db"]
translations_collection = db["translations"]

# Utility functions for translation operations
def create_translation(
    ojibwe_text: str,
    english_text: Optional[str] = None,
    audio_url: Optional[str] = None,
    syllabary_text: Optional[str] = None,
    other_lang_text: Optional[str] = None,
) -> None:
    """Insert a new translation into MongoDB."""
    doc = {
        "ojibwe_text": ojibwe_text,
        "english_text": english_text,
        "audio_url": audio_url,
        "syllabary_text": syllabary_text,
        "other_lang_text": other_lang_text,
    }
    translations_collection.insert_one(doc)


def update_or_create_translation(ojibwe_text: str, defaults: dict) -> None:
    """Update or create a translation entry in MongoDB."""
    existing = translations_collection.find_one({"ojibwe_text": ojibwe_text})
    if existing:
        translations_collection.update_one({"ojibwe_text": ojibwe_text}, {"$set": defaults})
    else:
        create_translation(ojibwe_text, **defaults)


def get_all_translations() -> list[dict]:
    """Retrieve all translations from MongoDB."""
    return list(translations_collection.find())
