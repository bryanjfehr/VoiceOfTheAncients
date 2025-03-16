"""Models for translation data management using pymongo for MongoDB and Django ORM for SQLite."""
from django.db import models
from pymongo import MongoClient
from pymongo.errors import CollectionInvalid, PyMongoError
from decouple import config

# MongoDB connection setup
client = MongoClient(config("MONGO_URI"))

# Check if database exists, create if not
try:
    db = client["vota_db"]
    # Create collections if they don't exist
    try:
        db.create_collection("english_to_ojibwe")
        print("Created 'english_to_ojibwe' collection.")
    except CollectionInvalid:
        print("Collection 'english_to_ojibwe' already exists.")
    try:
        db.create_collection("ojibwe_to_english")
        print("Created 'ojibwe_to_english' collection.")
    except CollectionInvalid:
        print("Collection 'ojibwe_to_english' already exists.")
except PyMongoError as e:
    print(f"Error accessing or creating database 'vota_db': {e}. Creating new database.")
    db = client["vota_db"]  # Force creation

# Define collections
english_to_ojibwe = db["english_to_ojibwe"]
ojibwe_to_english = db["ojibwe_to_english"]

# Utility functions for translation operations with pymongo
def create_english_to_ojibwe(english_text: str, ojibwe_text: str) -> None:
    """Insert a new English-to-Ojibwe translation into MongoDB."""
    doc = {
        "english_text": english_text.lower() if isinstance(english_text, str) else [e.lower() for e in english_text],  # Handle list or string
        "ojibwe_text": ojibwe_text.lower(),
    }
    english_to_ojibwe.insert_one(doc)

def create_ojibwe_to_english(ojibwe_text: str, english_text: list) -> None:
    """Insert a new Ojibwe-to-English translation into MongoDB."""
    doc = {
        "ojibwe_text": ojibwe_text.lower(),
        "english_text": [e.lower() for e in english_text],  # Store as list for multiple translations
    }
    ojibwe_to_english.insert_one(doc)

def update_or_create_english_to_ojibwe(english_text: str, ojibwe_text: str) -> None:
    """Update or create an English-to-Ojibwe translation entry in MongoDB."""
    existing = english_to_ojibwe.find_one({"english_text": {"$in": [english_text.lower()] if isinstance(english_text, str) else [e.lower() for e in english_text]}})
    if existing:
        english_to_ojibwe.update_one(
            {"english_text": {"$in": [english_text.lower()] if isinstance(english_text, str) else [e.lower() for e in english_text]}},
            {"$set": {"ojibwe_text": ojibwe_text.lower()}},
        )
    else:
        create_english_to_ojibwe(english_text, ojibwe_text)

def update_or_create_ojibwe_to_english(ojibwe_text: str, english_text: list) -> None:
    """Update or create an Ojibwe-to-English translation entry in MongoDB."""
    existing = ojibwe_to_english.find_one({"ojibwe_text": ojibwe_text.lower()})
    if isinstance(english_text, str):
        english_texts = english_text.lower().split(", ")
    else:
        english_texts = [e.lower() for e in english_text]
    if existing:
        current_english = existing.get("english_text", [])
        updated_english = list(set(current_english + english_texts))  # Avoid duplicates
        ojibwe_to_english.update_one(
            {"ojibwe_text": ojibwe_text.lower()},
            {"$set": {"english_text": updated_english}},
        )
    else:
        create_ojibwe_to_english(ojibwe_text, english_texts)

def get_all_english_to_ojibwe() -> list[dict]:
    """Retrieve all English-to-Ojibwe translations from MongoDB."""
    return list(english_to_ojibwe.find())

def get_all_ojibwe_to_english() -> list[dict]:
    """Retrieve all Ojibwe-to-English translations from MongoDB."""
    return list(ojibwe_to_english.find())

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
