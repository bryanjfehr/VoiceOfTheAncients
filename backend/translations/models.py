# backend/translations/models.py
"""
Models for translation data management using Firestore and Django ORM for SQLite.

Manages local SQLite storage and Firestore syncing with versioning.
Ensures all validated entries are synced without version skipping.
"""
import logging
import os
import re
from typing import List

from django.db import models

# Try to import Firebase dependencies, handle if not available
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except ImportError as e:
    FIREBASE_AVAILABLE = False
    print(f"Firebase dependencies not available: {e}. Firestore operations will be skipped.")

from translations.utils.definition_utils import is_valid_definition, format_definition

logger = logging.getLogger("translations.models")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cred_path = os.path.join(BASE_DIR, "firebase_credentials.json")

def initialize_firebase():
    """Initialize Firebase app if not already done."""
    if not FIREBASE_AVAILABLE:
        logger.error("Firebase is not available. Cannot initialize.")
        return None
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            return None
    return firestore.client()

db = None

def get_firestore_client():
    """Get Firestore client, initializing if necessary."""
    global db
    if not FIREBASE_AVAILABLE:
        logger.warning("Firestore client unavailable due to missing dependencies.")
        return None
    if db is None:
        db = initialize_firebase()
    return db

def get_collections():
    """Get Firestore collections."""
    client = get_firestore_client()
    if client is None:
        logger.warning("Cannot access Firestore collections: client is None.")
        return {
            "english_to_ojibwe": None,
            "ojibwe_to_english": None,
            "version": None,
        }
    return {
        "english_to_ojibwe": client.collection("english_to_ojibwe"),
        "ojibwe_to_english": client.collection("ojibwe_to_english"),
        "version": client.collection("version"),
    }

def sanitize_document_id(text: str) -> str:
    """Sanitize text for Firestore document IDs."""
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r"[\n\r\s]+", "_", text.strip())
    text = re.sub(r"[^a-zA-Z0-9_-]", "_", text)
    if len(text.encode("utf-8")) > 1500:
        text = text[:500]
    return text or "unknown"

class EnglishToOjibweLocal(models.Model):
    """Local SQLite model for English-to-Ojibwe translations."""
    english_text = models.TextField()
    ojibwe_text = models.TextField()
    definition = models.TextField(blank=True, null=True)
    version = models.CharField(max_length=20, default="1.0")

    class Meta:
        db_table = "english_to_ojibwe_local"

class OjibweToEnglishLocal(models.Model):
    """Local SQLite model for Ojibwe-to-English translations."""
    ojibwe_text = models.TextField()
    english_text = models.JSONField()
    version = models.CharField(max_length=20, default="1.0")

    class Meta:
        db_table = "ojibwe_to_english_local"

def create_english_to_ojibwe_local(
    english_text: str, ojibwe_text: str, definition: str = "", version: str = "1.0"
) -> None:
    """Insert English-to-Ojibwe translation into SQLite."""
    try:
        formatted_def = format_definition(definition) if definition else ""
        if definition and not formatted_def:
            logger.warning(f"Invalid definition for '{english_text}': {definition}")
            return
        EnglishToOjibweLocal.objects.create(
            english_text=english_text.lower(),
            ojibwe_text=ojibwe_text.lower(),
            definition=formatted_def,
            version=version,
        )
        logger.info(f"Created English-to-Ojibwe in SQLite: {english_text}")
    except Exception as e:
        logger.error(f"Error creating English-to-Ojibwe in SQLite: {e}")

def create_ojibwe_to_english_local(
    ojibwe_text: str, english_text: list, version: str = "1.0"
) -> None:
    """Insert Ojibwe-to-English translation into SQLite."""
    try:
        OjibweToEnglishLocal.objects.create(
            ojibwe_text=ojibwe_text.lower(),
            english_text=[e.lower() for e in english_text],
            version=version,
        )
        logger.info(f"Created Ojibwe-to-English in SQLite: {ojibwe_text}")
    except Exception as e:
        logger.error(f"Error creating Ojibwe-to-English in SQLite: {e}")

def get_all_english_to_ojibwe_local(version: str = "1.0") -> list[dict]:
    """Retrieve all English-to-Ojibwe translations from SQLite."""
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
        logger.info(f"Retrieved {len(result)} English-to-Ojibwe from SQLite.")
        return result
    except Exception as e:
        logger.error(f"Error retrieving English-to-Ojibwe from SQLite: {e}")
        return []

def get_all_ojibwe_to_english_local(version: str = "1.0") -> list[dict]:
    """Retrieve all Ojibwe-to-English translations from SQLite."""
    try:
        entries = OjibweToEnglishLocal.objects.filter(version=version)
        result = [
            {"ojibwe_text": e.ojibwe_text, "english_text": e.english_text}
            for e in entries
        ]
        logger.info(f"Retrieved {len(result)} Ojibwe-to-English from SQLite.")
        return result
    except Exception as e:
        logger.error(f"Error retrieving Ojibwe-to-English from SQLite: {e}")
        return []

def get_firestore_version() -> str:
    """Retrieve current Firestore version."""
    if not FIREBASE_AVAILABLE:
        logger.warning("Firestore unavailable. Returning default version.")
        return "1.0"
    try:
        version_doc = get_collections()["version"].document("current_version").get()
        version = version_doc.to_dict().get("version", "1.0") if version_doc.exists else "1.0"
        logger.info(f"Firestore version: {version}")
        return version
    except Exception as e:
        logger.error(f"Error retrieving Firestore version: {e}")
        return "1.0"

def set_firestore_version(version: str) -> None:
    """Set Firestore version."""
    if not FIREBASE_AVAILABLE:
        logger.warning("Firestore unavailable. Skipping version set.")
        return
    try:
        get_collections()["version"].document("current_version").set({"version": version})
        logger.info(f"Set Firestore version to {version}.")
    except Exception as e:
        logger.error(f"Error setting Firestore version: {e}")

def sync_to_firestore(version: str = "1.0") -> None:
    """
    Sync SQLite data to Firestore, always syncing all entries.
    """
    if not FIREBASE_AVAILABLE:
        logger.warning("Firestore unavailable. Skipping sync.")
        return
    try:
        # Sync English-to-Ojibwe
        entries = get_all_english_to_ojibwe_local(version)
        logger.info(f"Syncing {len(entries)} English-to-Ojibwe entries to Firestore.")
        for entry in entries:
            if entry["definition"] and not is_valid_definition(entry["definition"]):
                logger.warning(f"Skipping invalid definition for '{entry['english_text']}': {entry['definition']}")
                continue
            formatted_def = format_definition(entry["definition"]) if entry["definition"] else ""
            doc_id = sanitize_document_id(entry["english_text"])
            doc_ref = get_collections()["english_to_ojibwe"].document(doc_id)

            def set_doc():
                doc_ref.set({
                    "english_text": entry["english_text"],
                    "ojibwe_text": entry["ojibwe_text"],
                    "definition": formatted_def,
                })
            set_doc()
            logger.debug(f"Synced English-to-Ojibwe: {entry['english_text']}")

        # Sync Ojibwe-to-English
        entries = get_all_ojibwe_to_english_local(version)
        logger.info(f"Syncing {len(entries)} Ojibwe-to-English entries to Firestore.")
        for entry in entries:
            doc_id = sanitize_document_id(entry["ojibwe_text"])
            doc_ref = get_collections()["ojibwe_to_english"].document(doc_id)

            def set_doc():
                doc_ref.set({
                    "ojibwe_text": entry["ojibwe_text"],
                    "english_text": entry["english_text"],
                })
            set_doc()
            logger.debug(f"Synced Ojibwe-to-English: {entry['ojibwe_text']}")

        set_firestore_version(version)
    except Exception as e:
        logger.error(f"Error syncing to Firestore: {e}")
        raise

def create_english_to_ojibwe(english_text: str, ojibwe_text: str) -> None:
    """Insert English-to-Ojibwe translation into Firestore."""
    if not FIREBASE_AVAILABLE:
        logger.warning("Firestore unavailable. Skipping create.")
        return
    try:
        doc_id = sanitize_document_id(english_text)
        get_collections()["english_to_ojibwe"].document(doc_id).set({
            "english_text": english_text.lower(),
            "ojibwe_text": ojibwe_text.lower(),
        })
        logger.info(f"Created English-to-Ojibwe in Firestore: {english_text}")
    except Exception as e:
        logger.error(f"Error creating English-to-Ojibwe in Firestore: {e}")

def create_ojibwe_to_english(ojibwe_text: str, english_text: list) -> None:
    """Insert Ojibwe-to-English translation into Firestore."""
    if not FIREBASE_AVAILABLE:
        logger.warning("Firestore unavailable. Skipping create.")
        return
    try:
        doc_id = sanitize_document_id(ojibwe_text)
        get_collections()["ojibwe_to_english"].document(doc_id).set({
            "ojibwe_text": ojibwe_text.lower(),
            "english_text": [e.lower() for e in english_text],
        })
        logger.info(f"Created Ojibwe-to-English in Firestore: {ojibwe_text}")
    except Exception as e:
        logger.error(f"Error creating Ojibwe-to-English in Firestore: {e}")

def update_or_create_english_to_ojibwe(
    english_text: str, ojibwe_text: str, definition: str = ""
) -> None:
    """Update or create English-to-Ojibwe in Firestore."""
    if not FIREBASE_AVAILABLE:
        logger.warning("Firestore unavailable. Skipping update/create.")
        return
    try:
        formatted_def = format_definition(definition) if definition else ""
        if definition and not formatted_def:
            logger.warning(f"Invalid definition for '{english_text}': {definition}")
            return
        doc_id = sanitize_document_id(english_text)
        doc_ref = get_collections()["english_to_ojibwe"].document(doc_id)
        doc = doc_ref.get()
        if doc.exists:
            doc_ref.update({"ojibwe_text": ojibwe_text.lower(), "definition": formatted_def})
            logger.info(f"Updated English-to-Ojibwe in Firestore: {english_text}")
        else:
            doc_ref.set({
                "english_text": english_text.lower(),
                "ojibwe_text": ojibwe_text.lower(),
                "definition": formatted_def,
            })
            logger.info(f"Created English-to-Ojibwe in Firestore: {english_text}")
    except Exception as e:
        logger.error(f"Error updating/creating English-to-Ojibwe in Firestore: {e}")

def update_or_create_ojibwe_to_english(ojibwe_text: str, english_text: list) -> None:
    """Update or create Ojibwe-to-English in Firestore."""
    if not FIREBASE_AVAILABLE:
        logger.warning("Firestore unavailable. Skipping update/create.")
        return
    try:
        doc_id = sanitize_document_id(ojibwe_text)
        doc_ref = get_collections()["ojibwe_to_english"].document(doc_id)
        doc = doc_ref.get()
        english_texts = [e.lower() for e in ([english_text] if isinstance(english_text, str) else english_text)]
        if doc.exists:
            current_english = doc.to_dict().get("english_text", [])
            updated_english = list(set(current_english + english_texts))
            doc_ref.update({"english_text": updated_english})
            logger.info(f"Updated Ojibwe-to-English in Firestore: {ojibwe_text}")
        else:
            create_ojibwe_to_english(ojibwe_text, english_texts)
    except Exception as e:
        logger.error(f"Error updating/creating Ojibwe-to-English in Firestore: {e}")

def get_all_english_to_ojibwe() -> list[dict]:
    """Retrieve all English-to-Ojibwe translations from Firestore, fall back to SQLite if Firestore is unavailable."""
    if FIREBASE_AVAILABLE:
        try:
            docs = get_collections()["english_to_ojibwe"].stream()
            result = [doc.to_dict() for doc in docs]
            logger.info(f"Retrieved {len(result)} English-to-Ojibwe from Firestore.")
            return result
        except Exception as e:
            logger.error(f"Error retrieving English-to-Ojibwe from Firestore: {e}")
    logger.warning("Falling back to SQLite for English-to-Ojibwe translations.")
    return get_all_english_to_ojibwe_local()

def get_all_ojibwe_to_english() -> list[dict]:
    """Retrieve all Ojibwe-to-English translations from Firestore, fall back to SQLite if Firestore is unavailable."""
    if FIREBASE_AVAILABLE:
        try:
            docs = get_collections()["ojibwe_to_english"].stream()
            result = [doc.to_dict() for doc in docs]
            logger.info(f"Retrieved {len(result)} Ojibwe-to-English from Firestore.")
            return result
        except Exception as e:
            logger.error(f"Error retrieving Ojibwe-to-English from Firestore: {e}")
    logger.warning("Falling back to SQLite for Ojibwe-to-English translations.")
    return get_all_ojibwe_to_english_local()

class EnglishWord(models.Model):
    """SQLite model for English words."""
    word = models.TextField(primary_key=True)

    class Meta:
        db_table = "english_dict"

    def __str__(self) -> str:
        return self.word
