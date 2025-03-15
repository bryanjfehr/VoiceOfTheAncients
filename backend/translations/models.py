"""Models for translation data management using pymongo for MongoDB and Django ORM for SQLite."""
from django.db import models
from pymongo import MongoClient
from decouple import config

# MongoDB connection setup (direct pymongo access)
client = MongoClient(config("MONGO_URI"))
db = client["vota_db"]
translations_collection = db["translations"]

# Utility functions for translation operations with pymongo
def create_translation(
    ojibwe_text,
    english_text=None,
    audio_url=None,
    syllabary_text=None,
    other_lang_text=None,
):
    """Insert a new translation into MongoDB."""
    doc = {
        "ojibwe_text": ojibwe_text,
        "english_text": english_text,
        "audio_url": audio_url,
        "syllabary_text": syllabary_text,
        "other_lang_text": other_lang_text,
    }
    return translations_collection.insert_one(doc)

def update_or_create_translation(ojibwe_text, defaults):
    """Update or create a translation entry in MongoDB."""
    existing = translations_collection.find_one({"ojibwe_text": ojibwe_text})
    if existing:
        translations_collection.update_one({"ojibwe_text": ojibwe_text}, {"$set": defaults})
    else:
        create_translation(ojibwe_text, **defaults)

def get_all_translations():
    """Retrieve all translations from MongoDB."""
    return list(translations_collection.find())

# Django ORM model for English words (stored in SQLite)
class EnglishWord(models.Model):
    """Model representing an English word in SQLite."""
    word = models.TextField(primary_key=True)

    class Meta:
        """Meta options for the EnglishWord model."""
        db_table = "english_dict"

    def __str__(self) -> str:
        """String representation of the EnglishWord object."""
        return self.word
