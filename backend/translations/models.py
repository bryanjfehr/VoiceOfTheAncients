# backend/translations/models.py
"""
Models for translation data management using Firestore and Django ORM for SQLite.

This module defines local SQLite models for storing translations during scraping,
and provides functions to sync them to Firestore with versioning. It also includes
Firestore CRUD operations for the web application with retry logic for transient failures.
"""
import logging
import os
import re
import time
from typing import List

import firebase_admin
from django.db import models
from firebase_admin import credentials, firestore
from google.api_core import retry

# Import logging setup (configured in ojibwe_scraper.py)
logger = logging.getLogger("translations.models")

# Import definition utilities
from translations.utils.definition_utils import is_valid_definition, format_definition  # noqa: E402

# Initialize Firebase lazily
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cred_path = os.path.join(BASE_DIR, "firebase_credentials.json")


def initialize_firebase():
    """
    Initialize the Firebase app if not already initialized.

    Returns:
        firestore.Client: The Firestore client.
    """
    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    return firestore.client()


# Firestore client (lazy initialization)
db = None


def get_firestore_client():
    """
    Get the Firestore client, initializing it if necessary.

    Returns:
        firestore.Client: The Firestore client.
    """
    global db
    if db is None:
        db = initialize_firebase()
    return db


# Define Firestore collections
def get_collections():
    """
    Get Firestore collections using the initialized client.

    Returns:
        dict: Dictionary mapping collection names to Firestore collections.
    """
    client = get_firestore_client()
    return {
        "english_to_ojibwe": client.collection("english_to_ojibwe"),
        "ojibwe_to_english": client.collection("ojibwe_to_english"),
        "version": client.collection("version"),
    }


# Utility function to sanitize document IDs
def sanitize_document_id(text: str) -> str:
    """
    Sanitize a string to be a valid Firestore document ID.

    Args:
        text (str): The text to sanitize.

    Returns:
        str: A sanitized string suitable for use as a Firestore document ID.
    """
    if not isinstance(text, str):
        text = str(text)
    # Replace newlines, spaces, and invalid characters with underscores
    text = re.sub(r"[\n\r\s]+", "_", text.strip())
    text = re.sub(r"[^a-zA-Z0-9_-]", "_", text)
    # Firestore document IDs must be between 1 and 1500 bytes
    if len(text.encode("utf-8")) > 1500:
        text = text[:500]  # Truncate to a safe length
    if not text:
        text = "unknown"
    return text


# Local SQLite models for translations
class EnglishToOjibweLocal(models.Model):
    """
    Model for storing English-to-Ojibwe translations locally in SQLite.
    """
    english_text = models.TextField()
    ojibwe_text = models.TextField()
    definition = models.TextField(blank=True, null=True)
    version = models.CharField(max_length=20, default="1.0")

    class Meta:
        """
        Meta options for the EnglishToOjibweLocal model.
        """
        db_table = "english_to_ojibwe_local"


class OjibweToEnglishLocal(models.Model):
    """
    Model for storing Ojibwe-to-English translations locally in SQLite.
    """
    ojibwe_text = models.TextField()
    english_text = models.JSONField()  # Store list of English translations as JSON
    version = models.CharField(max_length=20, default="1.0")

    class Meta:
        """
        Meta options for the OjibweToEnglishLocal model.
        """
        db_table = "ojibwe_to_english_local"


# Utility functions for local storage
def create_english_to_ojibwe_local(
    english_text: str, ojibwe_text: str, definition: str = "", version: str = "1.0"
) -> None:
    """
    Insert a new English-to-Ojibwe translation into SQLite.

    Validates and formats the definition before storing to ensure it is meaningful.

    Args:
        english_text (str): The English text to translate.
        ojibwe_text (str): The Ojibwe translation.
        definition (str): The definition of the translation (optional).
        version (str): The version of the data (default: "1.0").
    """
    try:
        formatted_def = format_definition(definition) if definition else ""
        if definition and not formatted_def:
            logger.warning(f"Invalid definition for English text '{english_text}': {definition}")
            return  # Skip storing if the definition is invalid

        EnglishToOjibweLocal.objects.create(
            english_text=english_text.lower()
            if isinstance(english_text, str)
            else [e.lower() for e in english_text],
            ojibwe_text=ojibwe_text.lower(),
            definition=formatted_def,
            version=version,
        )
        logger.info(f"Created English-to-Ojibwe translation in SQLite: {english_text}")
    except Exception as e:
        logger.error(f"Error creating English-to-Ojibwe translation in SQLite: {e}")


def create_ojibwe_to_english_local(
    ojibwe_text: str, english_text: list, version: str = "1.0"
) -> None:
    """
    Insert a new Ojibwe-to-English translation into SQLite.

    Args:
        ojibwe_text (str): The Ojibwe text to translate.
        english_text (list): List of English translations.
        version (str): The version of the data (default: "1.0").
    """
    try:
        OjibweToEnglishLocal.objects.create(
            ojibwe_text=ojibwe_text.lower(),
            english_text=[e.lower() for e in english_text],
            version=version,
        )
        logger.info(f"Created Ojibwe-to-English translation in SQLite: {ojibwe_text}")
    except Exception as e:
        logger.error(f"Error creating Ojibwe-to-English translation in SQLite: {e}")


def get_all_english_to_ojibwe_local(version: str = "1.0") -> list[dict]:
    """
    Retrieve all English-to-Ojibwe translations from SQLite for a given version.

    Args:
        version (str): The version of the data to retrieve (default: "1.0").

    Returns:
        list[dict]: List of translation dictionaries.
    """
    try:
        entries = EnglishToOjibweLocal.objects.filter(version=version)
        result = [
            {
                "english_text": e.english_text,
                "ojibwe_text": e.ojibwe_text,
                "definition": e.definition,
            }
            for e in entries
        ]
        logger.info(f"Retrieved {len(result)} English-to-Ojibwe translations from SQLite.")
        return result
    except Exception as e:
        logger.error(f"Error retrieving English-to-Ojibwe translations from SQLite: {e}")
        return []


def get_all_ojibwe_to_english_local(version: str = "1.0") -> list[dict]:
    """
    Retrieve all Ojibwe-to-English translations from SQLite for a given version.

    Args:
        version (str): The version of the data to retrieve (default: "1.0").

    Returns:
        list[dict]: List of translation dictionaries.
    """
    try:
        entries = OjibweToEnglishLocal.objects.filter(version=version)
        result = [
            {"ojibwe_text": e.ojibwe_text, "english_text": e.english_text}
            for e in entries
        ]
        logger.info(f"Retrieved {len(result)} Ojibwe-to-English translations from SQLite.")
        return result
    except Exception as e:
        logger.error(f"Error retrieving Ojibwe-to-English translations from SQLite: {e}")
        return []


# Firestore sync functions with retry logic
@retry.Retry(predicate=retry.if_transient_error, timeout=60, initial=1, maximum=10)
def get_firestore_version() -> str:
    """
    Retrieve the current version from Firestore with retry logic.

    Returns:
        str: The current version, or "1.0" if not set.
    """
    try:
        version_doc = get_collections()["version"].document("current_version").get()
        if version_doc.exists:
            version = version_doc.to_dict().get("version", "1.0")
            logger.info(f"Retrieved Firestore version: {version}")
            return version
        logger.info("No version found in Firestore. Defaulting to 1.0.")
        return "1.0"
    except Exception as e:
        logger.error(f"Error retrieving Firestore version: {e}")
        raise


@retry.Retry(predicate=retry.if_transient_error, timeout=60, initial=1, maximum=10)
def set_firestore_version(version: str) -> None:
    """
    Set the current version in Firestore with retry logic.

    Args:
        version (str): The version to set.
    """
    try:
        get_collections()["version"].document("current_version").set({"version": version})
        logger.info(f"Set Firestore version to {version}.")
    except Exception as e:
        logger.error(f"Error setting Firestore version: {e}")
        raise


def sync_to_firestore(version: str = "1.0") -> None:
    """
    Sync local SQLite data to Firestore if the Firestore version is older.

    Args:
        version (str): The version of the local data (default: "1.0").
    """
    try:
        firestore_version = get_firestore_version()
        if firestore_version >= version:
            logger.info(
                f"Firestore version {firestore_version} is up to date or newer than "
                f"local version {version}. Skipping sync."
            )
            return

        # Sync English-to-Ojibwe translations
        entries = get_all_english_to_ojibwe_local(version)
        for entry in entries:
            if entry["definition"] and not is_valid_definition(entry["definition"]):
                logger.warning(f"Skipping invalid definition for English text '{entry['english_text']}': {entry['definition']}")
                continue
            formatted_def = format_definition(entry["definition"]) if entry["definition"] else ""
            if entry["definition"] and not formatted_def:
                logger.warning(f"Invalid definition after formatting for English text '{entry['english_text']}': {entry['definition']}")
                continue
            doc_id = sanitize_document_id(entry["english_text"])
            doc_ref = get_collections()["english_to_ojibwe"].document(doc_id)
            @retry.Retry(predicate=retry.if_transient_error, timeout=60, initial=1, maximum=10)
            def set_doc():
                doc_ref.set(
                    {
                        "english_text": entry["english_text"],
                        "ojibwe_text": entry["ojibwe_text"],
                        "definition": formatted_def,
                    }
                )
            set_doc()

        # Sync Ojibwe-to-English translations
        entries = get_all_ojibwe_to_english_local(version)
        for entry in entries:
            doc_id = sanitize_document_id(entry["ojibwe_text"])
            doc_ref = get_collections()["ojibwe_to_english"].document(doc_id)
            @retry.Retry(predicate=retry.if_transient_error, timeout=60, initial=1, maximum=10)
            def set_doc():
                doc_ref.set(
                    {
                        "ojibwe_text": entry["ojibwe_text"],
                        "english_text": entry["english_text"],
                    }
                )
            set_doc()

        # Update Firestore version
        set_firestore_version(version)
        logger.info(f"Synced {len(entries)} entries to Firestore with version {version}.")
    except Exception as e:
        logger.error(f"Error syncing to Firestore: {e}")
        raise


# Firestore CRUD functions with retry logic
@retry.Retry(predicate=retry.if_transient_error, timeout=60, initial=1, maximum=10)
def create_english_to_ojibwe(english_text: str, ojibwe_text: str) -> None:
    """
    Insert a new English-to-Ojibwe translation into Firestore with retry logic.

    Args:
        english_text (str): The English text to translate.
        ojibwe_text (str): The Ojibwe translation.
    """
    try:
        doc_id = sanitize_document_id(english_text)
        doc = {
            "english_text": english_text.lower()
            if isinstance(english_text, str)
            else [e.lower() for e in english_text],
            "ojibwe_text": ojibwe_text.lower(),
        }
        get_collections()["english_to_ojibwe"].document(doc_id).set(doc)
        logger.info(f"Created English-to-Ojibwe translation in Firestore: {english_text}")
    except Exception as e:
        logger.error(f"Error creating English-to-Ojibwe translation in Firestore: {e}")
        raise


@retry.Retry(predicate=retry.if_transient_error, timeout=60, initial=1, maximum=10)
def create_ojibwe_to_english(ojibwe_text: str, english_text: list) -> None:
    """
    Insert a new Ojibwe-to-English translation into Firestore with retry logic.

    Args:
        ojibwe_text (str): The Ojibwe text to translate.
        english_text (list): List of English translations.
    """
    try:
        doc_id = sanitize_document_id(ojibwe_text)
        doc = {
            "ojibwe_text": ojibwe_text.lower(),
            "english_text": [e.lower() for e in english_text],
        }
        get_collections()["ojibwe_to_english"].document(doc_id).set(doc)
        logger.info(f"Created Ojibwe-to-English translation in Firestore: {ojibwe_text}")
    except Exception as e:
        logger.error(f"Error creating Ojibwe-to-English translation in Firestore: {e}")
        raise


@retry.Retry(predicate=retry.if_transient_error, timeout=60, initial=1, maximum=10)
def update_or_create_english_to_ojibwe(
    english_text: str, ojibwe_text: str, definition: str = ""
) -> None:
    """
    Update or create an English-to-Ojibwe translation entry in Firestore with retry logic.

    Args:
        english_text (str): The English text to translate.
        ojibwe_text (str): The Ojibwe translation.
        definition (str): The definition of the translation (optional).
    """
    try:
        formatted_def = format_definition(definition) if definition else ""
        if definition and not formatted_def:
            logger.warning(f"Invalid definition for English text '{english_text}': {definition}")
            return  # Skip storing if the definition is invalid

        doc_id = sanitize_document_id(english_text)
        doc_ref = get_collections()["english_to_ojibwe"].document(doc_id)
        doc = doc_ref.get()
        if doc.exists:
            doc_ref.update(
                {
                    "ojibwe_text": ojibwe_text.lower(),
                    "definition": formatted_def,
                }
            )
            logger.info(f"Updated English-to-Ojibwe translation in Firestore: {english_text}")
        else:
            doc_ref.set(
                {
                    "english_text": english_text.lower(),
                    "ojibwe_text": ojibwe_text.lower(),
                    "definition": formatted_def,
                }
            )
            logger.info(f"Created English-to-Ojibwe translation in Firestore: {english_text}")
    except Exception as e:
        logger.error(f"Error updating/creating English-to-Ojibwe translation in Firestore: {e}")
        raise


@retry.Retry(predicate=retry.if_transient_error, timeout=60, initial=1, maximum=10)
def update_or_create_ojibwe_to_english(ojibwe_text: str, english_text: list) -> None:
    """
    Update or create an Ojibwe-to-English translation entry in Firestore with retry logic.

    Args:
        ojibwe_text (str): The Ojibwe text to translate.
        english_text (list): List of English translations.
    """
    try:
        doc_id = sanitize_document_id(ojibwe_text)
        doc_ref = get_collections()["ojibwe_to_english"].document(doc_id)
        doc = doc_ref.get()
        if isinstance(english_text, str):
            english_texts = english_text.lower().split(", ")
        else:
            english_texts = [e.lower() for e in english_text]
        if doc.exists:
            current_english = doc.to_dict().get("english_text", [])
            updated_english = list(set(current_english + english_texts))
            doc_ref.update({"english_text": updated_english})
            logger.info(f"Updated Ojibwe-to-English translation in Firestore: {ojibwe_text}")
        else:
            create_ojibwe_to_english(ojibwe_text, english_texts)
    except Exception as e:
        logger.error(f"Error updating/creating Ojibwe-to-English translation in Firestore: {e}")
        raise


@retry.Retry(predicate=retry.if_transient_error, timeout=60, initial=1, maximum=10)
def get_all_english_to_ojibwe() -> list[dict]:
    """
    Retrieve all English-to-Ojibwe translations from Firestore with retry logic.

    Returns:
        list[dict]: List of translation dictionaries.
    """
    try:
        docs = get_collections()["english_to_ojibwe"].stream()
        result = [doc.to_dict() for doc in docs]
        logger.info(f"Retrieved {len(result)} English-to-Ojibwe translations from Firestore.")
        return result
    except Exception as e:
        logger.error(f"Error retrieving English-to-Ojibwe translations from Firestore: {e}")
        raise


@retry.Retry(predicate=retry.if_transient_error, timeout=60, initial=1, maximum=10)
def get_all_ojibwe_to_english() -> list[dict]:
    """
    Retrieve all Ojibwe-to-English translations from Firestore with retry logic.

    Returns:
        list[dict]: List of translation dictionaries.
    """
    try:
        docs = get_collections()["ojibwe_to_english"].stream()
        result = [doc.to_dict() for doc in docs]
        logger.info(f"Retrieved {len(result)} Ojibwe-to-English translations from Firestore.")
        return result
    except Exception as e:
        logger.error(f"Error retrieving Ojibwe-to-English translations from Firestore: {e}")
        raise


# Django ORM model for English words (stored in SQLite)
class EnglishWord(models.Model):
    """
    Model representing an English word in SQLite.
    """
    word = models.TextField(primary_key=True)

    class Meta:
        """
        Meta options for the EnglishWord model.
        """
        db_table = "english_dict"

    def __str__(self) -> str:
        """
        String representation of the EnglishWord object.

        Returns:
            str: The word.
        """
        return self.word
