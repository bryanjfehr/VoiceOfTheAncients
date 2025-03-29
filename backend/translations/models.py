"""
Models for translation data management using Firestore and Django ORM for SQLite.

This module manages local SQLite storage and Firestore syncing, ensuring all entries
are pushed to Firestore with a consistent version, suitable for online deployment (e.g., GKE).
"""
import logging
import os
import re
from typing import List

from django.db import models
from tqdm import tqdm

# Attempt Firebase import with fallback for local development
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

# Global Firestore client
db = None


def initialize_firebase():
    """Initialize Firebase app if not already initialized."""
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


def get_firestore_client():
    """Get or initialize Firestore client."""
    global db
    if not FIREBASE_AVAILABLE:
        logger.warning("Firestore client unavailable due to missing dependencies.")
        return None
    if db is None:
        db = initialize_firebase()
    return db


def get_collections():
    """Retrieve Firestore collection references."""
    client = get_firestore_client()
    if client is None:
        logger.warning("Cannot access Firestore collections: client is None.")
        return {
            "english_to_ojibwe": None,
            "ojibwe_to_english": None,
            "version": None,
            "english_dict": None,
            "semantic_matches": None,
            "missing_translations": None,
        }
    return {
        "english_to_ojibwe": client.collection("english_to_ojibwe"),
        "ojibwe_to_english": client.collection("ojibwe_to_english"),
        "version": client.collection("version"),
        "english_dict": client.collection("english_dict"),
        "semantic_matches": client.collection("semantic_matches"),
        "missing_translations": client.collection("missing_translations"),
    }


def sanitize_document_id(text: str) -> str:
    """Sanitize text for use as Firestore document IDs."""
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r"[\n\r\s]+", "_", text.strip())
    text = re.sub(r"[^a-zA-Z0-9_-]", "_", text)
    if len(text.encode("utf-8")) > 1500:
        text = text[:500]
    return text or "unknown"


# Django models for local SQLite storage

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


class SemanticMatchLocal(models.Model):
    """Local SQLite model for semantic matches."""
    english_text = models.TextField()
    ojibwe_text = models.TextField()
    similarity = models.FloatField()
    english_definition = models.TextField(blank=True, null=True)
    ojibwe_definition = models.TextField(blank=True, null=True)
    version = models.CharField(max_length=20, default="1.0")

    class Meta:
        db_table = "semantic_matches_local"


class MissingTranslationLocal(models.Model):
    """Local SQLite model for missing translations."""
    english_text = models.TextField()
    frequency = models.FloatField(default=0.0)
    version = models.CharField(max_length=20, default="1.0")

    class Meta:
        db_table = "missing_translations_local"


class EnglishWord(models.Model):
    """SQLite model for English dictionary words."""
    word = models.TextField(primary_key=True)

    class Meta:
        db_table = "english_dict"

    def __str__(self) -> str:
        return self.word


# SQLite creation functions

def create_english_to_ojibwe_local(
    english_text: str, ojibwe_text: str, definition: str = "", version: str = "1.0"
) -> None:
    """Insert an English-to-Ojibwe translation into SQLite."""
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
    """Insert an Ojibwe-to-English translation into SQLite."""
    try:
        OjibweToEnglishLocal.objects.create(
            ojibwe_text=ojibwe_text.lower(),
            english_text=[e.lower() for e in english_text],
            version=version,
        )
        logger.info(f"Created Ojibwe-to-English in SQLite: {ojibwe_text}")
    except Exception as e:
        logger.error(f"Error creating Ojibwe-to-English in SQLite: {e}")


def create_semantic_match_local(
    english_text: str,
    ojibwe_text: str,
    similarity: float,
    english_definition: str = "",
    ojibwe_definition: str = "",
    version: str = "1.0",
) -> None:
    """Insert a semantic match into SQLite."""
    try:
        SemanticMatchLocal.objects.create(
            english_text=english_text.lower(),
            ojibwe_text=ojibwe_text.lower(),
            similarity=similarity,
            english_definition=english_definition,
            ojibwe_definition=ojibwe_definition,
            version=version,
        )
        logger.info(f"Created semantic match in SQLite: {english_text} => {ojibwe_text}")
    except Exception as e:
        logger.error(f"Error creating semantic match in SQLite: {e}")


def create_missing_translation_local(
    english_text: str, frequency: float = 0.0, version: str = "1.0"
) -> None:
    """Insert a missing translation into SQLite."""
    try:
        MissingTranslationLocal.objects.create(
            english_text=english_text.lower(),
            frequency=frequency,
            version=version,
        )
        logger.info(f"Created missing translation in SQLite: {english_text}")
    except Exception as e:
        logger.error(f"Error creating missing translation in SQLite: {e}")


# SQLite retrieval functions (fetch all entries, ignoring version)

def get_all_english_to_ojibwe_local() -> List[dict]:
    """Retrieve all English-to-Ojibwe translations from SQLite, regardless of version."""
    try:
        entries = EnglishToOjibweLocal.objects.all()
        result = [
            {
                "english_text": e.english_text,
                "ojibwe_text": e.ojibwe_text,
                "definition": e.definition,
            }
            for e in entries
        ]
        logger.info(f"Retrieved {len(result)} English-to-Ojibwe entries from SQLite.")
        return result
    except Exception as e:
        logger.error(f"Error retrieving English-to-Ojibwe from SQLite: {e}")
        return []


def get_all_ojibwe_to_english_local() -> List[dict]:
    """Retrieve all Ojibwe-to-English translations from SQLite, regardless of version."""
    try:
        entries = OjibweToEnglishLocal.objects.all()
        result = [
            {"ojibwe_text": e.ojibwe_text, "english_text": e.english_text}
            for e in entries
        ]
        logger.info(f"Retrieved {len(result)} Ojibwe-to-English entries from SQLite.")
        return result
    except Exception as e:
        logger.error(f"Error retrieving Ojibwe-to-English from SQLite: {e}")
        return []


def get_all_semantic_matches_local() -> List[dict]:
    """Retrieve all semantic matches from SQLite, regardless of version."""
    try:
        entries = SemanticMatchLocal.objects.all()
        result = [
            {
                "english_text": e.english_text,
                "ojibwe_text": e.ojibwe_text,
                "similarity": e.similarity,
                "english_definition": e.english_definition,
                "ojibwe_definition": e.ojibwe_definition,
            }
            for e in entries
        ]
        logger.info(f"Retrieved {len(result)} semantic matches from SQLite.")
        return result
    except Exception as e:
        logger.error(f"Error retrieving semantic matches from SQLite: {e}")
        return []


def get_all_missing_translations_local() -> List[dict]:
    """Retrieve all missing translations from SQLite, regardless of version."""
    try:
        entries = MissingTranslationLocal.objects.all()
        result = [
            {"english_text": e.english_text, "frequency": e.frequency}
            for e in entries
        ]
        logger.info(f"Retrieved {len(result)} missing translations from SQLite.")
        return result
    except Exception as e:
        logger.error(f"Error retrieving missing translations from SQLite: {e}")
        return []


# Firestore utility functions

def get_firestore_version() -> str:
    """Retrieve the current version from Firestore."""
    if not FIREBASE_AVAILABLE:
        logger.warning("Firestore unavailable. Returning default version '1.0'.")
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
    """Set the Firestore version."""
    if not FIREBASE_AVAILABLE:
        logger.warning("Firestore unavailable. Skipping version set.")
        return
    try:
        get_collections()["version"].document("current_version").set({"version": version})
        logger.info(f"Set Firestore version to {version}.")
    except Exception as e:
        logger.error(f"Error setting Firestore version: {e}")


def check_english_dict_in_firestore() -> int:
    """
    Check the number of documents in the Firestore english_dict collection using metadata.

    Uses a metadata document to store the count, avoiding slow streaming of all documents.
    Returns:
        int: Number of documents in the Firestore english_dict collection, or 0 if unavailable.
    """
    if not FIREBASE_AVAILABLE:
        logger.warning("Firestore unavailable. Assuming english_dict is not present.")
        return 0
    try:
        # Use a metadata document to store the count of english_dict entries
        metadata_ref = get_collections()["english_dict"].document("_metadata")
        metadata_doc = metadata_ref.get()
        if metadata_doc.exists:
            count = metadata_doc.to_dict().get("count", 0)
            logger.info(f"Found {count} documents in Firestore english_dict per metadata.")
            return count
        # If metadata doesn't exist, check if the collection has any documents
        docs = get_collections()["english_dict"].limit(1).stream()
        has_documents = any(docs)
        count = -1 if has_documents else 0  # -1 indicates unknown count but populated
        logger.info(f"Metadata not found. Collection {'has' if has_documents else 'has no'} documents.")
        return count
    except Exception as e:
        logger.error(f"Error checking Firestore english_dict: {e}")
        return 0


def sync_english_dict_to_firestore() -> None:
    """
    Sync English dictionary from SQLite to Firestore efficiently with batched writes.

    Only syncs if Firestore's english_dict collection is empty or has significantly fewer
    entries than SQLite, based on metadata. Updates metadata count after syncing.
    """
    if not FIREBASE_AVAILABLE:
        logger.warning("Firestore unavailable. Skipping English dict sync.")
        return

    try:
        # Count local English words in SQLite
        local_words = EnglishWord.objects.all()
        local_count = len(local_words)
        logger.info(f"Found {local_count} English words in SQLite.")

        # Check Firestore for existing english_dict count via metadata
        firestore_count = check_english_dict_in_firestore()
        threshold = int(local_count * 0.9)  # 90% threshold

        if firestore_count == -1:
            logger.info("Firestore english_dict is populated but count unknown. Skipping sync.")
            return
        elif firestore_count >= threshold:
            logger.info(
                f"Firestore has {firestore_count} English words, sufficient "
                f"(threshold: {threshold}). Skipping sync."
            )
            return

        logger.info(
            f"Firestore has {firestore_count} English words, below threshold "
            f"({threshold}). Syncing {local_count} words to Firestore."
        )

        # Use batched writes for efficiency (max 500 operations per batch)
        batch = get_firestore_client().batch()
        batch_count = 0
        total_synced = 0

        for word in tqdm(local_words, desc="Syncing English dictionary", unit="word"):
            doc_id = sanitize_document_id(word.word)
            doc_ref = get_collections()["english_dict"].document(doc_id)
            batch.set(doc_ref, {"word": word.word.lower()})
            batch_count += 1
            total_synced += 1

            if batch_count >= 500:
                batch.commit()
                logger.debug(f"Committed batch of {batch_count} English words.")
                batch = get_firestore_client().batch()
                batch_count = 0

        # Commit any remaining operations
        if batch_count > 0:
            batch.commit()
            logger.debug(f"Committed final batch of {batch_count} English words.")

        # Update metadata with the new count
        metadata_ref = get_collections()["english_dict"].document("_metadata")
        metadata_ref.set({"count": local_count})
        logger.info(f"Synced {total_synced} English words to Firestore and updated metadata.")
    except Exception as e:
        logger.error(f"Error syncing English dict to Firestore: {e}")
        raise


def sync_to_firestore(version: str = "1.0") -> None:
    """
    Sync all SQLite data to Firestore efficiently with batched writes.

    Pushes all entries regardless of version, updating Firestore with the specified version.
    Args:
        version (str): Version to set in Firestore after syncing (default: "1.0").
    Raises:
        RuntimeError: If Firestore is unavailable or sync fails critically.
    """
    if not FIREBASE_AVAILABLE:
        logger.error("Firestore unavailable. Cannot sync data.")
        raise RuntimeError("Firestore is unavailable. Cannot sync data.")

    client = get_firestore_client()
    try:
        # Sync English-to-Ojibwe
        entries = get_all_english_to_ojibwe_local()
        logger.info(f"Syncing {len(entries)} English-to-Ojibwe entries to Firestore.")
        batch = client.batch()
        batch_count = 0
        for entry in tqdm(entries, desc="Syncing English-to-Ojibwe", unit="entry"):
            if entry["definition"] and not is_valid_definition(entry["definition"]):
                logger.warning(f"Skipping invalid definition for '{entry['english_text']}': {entry['definition']}")
                continue
            formatted_def = format_definition(entry["definition"]) if entry["definition"] else ""
            doc_id = sanitize_document_id(entry["english_text"])
            doc_ref = get_collections()["english_to_ojibwe"].document(doc_id)
            batch.set(doc_ref, {
                "english_text": entry["english_text"],
                "ojibwe_text": entry["ojibwe_text"],
                "definition": formatted_def,
            })
            batch_count += 1
            if batch_count >= 500:
                batch.commit()
                batch = client.batch()
                batch_count = 0
        if batch_count > 0:
            batch.commit()

        # Sync Ojibwe-to-English
        entries = get_all_ojibwe_to_english_local()
        logger.info(f"Syncing {len(entries)} Ojibwe-to-English entries to Firestore.")
        batch = client.batch()
        batch_count = 0
        for entry in tqdm(entries, desc="Syncing Ojibwe-to-English", unit="entry"):
            doc_id = sanitize_document_id(entry["ojibwe_text"])
            doc_ref = get_collections()["ojibwe_to_english"].document(doc_id)
            batch.set(doc_ref, {
                "ojibwe_text": entry["ojibwe_text"],
                "english_text": entry["english_text"],
            })
            batch_count += 1
            if batch_count >= 500:
                batch.commit()
                batch = client.batch()
                batch_count = 0
        if batch_count > 0:
            batch.commit()

        # Sync semantic matches
        entries = get_all_semantic_matches_local()
        if not entries:
            logger.warning("No semantic matches found in SQLite. Ensure semantic analysis has been run.")
        else:
            logger.info(f"Syncing {len(entries)} semantic matches to Firestore.")
            batch = client.batch()
            batch_count = 0
            for entry in tqdm(entries, desc="Syncing semantic matches", unit="match"):
                doc_id = sanitize_document_id(f"{entry['english_text']}_{entry['ojibwe_text']}")
                doc_ref = get_collections()["semantic_matches"].document(doc_id)
                batch.set(doc_ref, {
                    "english_text": entry["english_text"],
                    "ojibwe_text": entry["ojibwe_text"],
                    "similarity": entry["similarity"],
                    "english_definition": entry["english_definition"] or "",
                    "ojibwe_definition": entry["ojibwe_definition"] or "",
                })
                batch_count += 1
                if batch_count >= 500:
                    batch.commit()
                    batch = client.batch()
                    batch_count = 0
            if batch_count > 0:
                batch.commit()

        # Sync missing translations
        entries = get_all_missing_translations_local()
        logger.info(f"Syncing {len(entries)} missing translations to Firestore.")
        batch = client.batch()
        batch_count = 0
        for entry in tqdm(entries, desc="Syncing missing translations", unit="entry"):
            doc_id = sanitize_document_id(entry["english_text"])
            doc_ref = get_collections()["missing_translations"].document(doc_id)
            batch.set(doc_ref, {
                "english_text": entry["english_text"],
                "frequency": entry["frequency"],
            })
            batch_count += 1
            if batch_count >= 500:
                batch.commit()
                batch = client.batch()
                batch_count = 0
        if batch_count > 0:
            batch.commit()

        # Set the specified version in Firestore
        set_firestore_version(version)
        logger.info(f"Sync completed successfully with version {version}.")
    except Exception as e:
        logger.error(f"Error syncing to Firestore: {e}")
        raise RuntimeError(f"Error syncing to Firestore: {e}")


# Firestore direct interaction functions (unchanged)

def create_english_to_ojibwe(english_text: str, ojibwe_text: str) -> None:
    """Insert English-to-Ojibwe translation directly into Firestore."""
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
    """Insert Ojibwe-to-English translation directly into Firestore."""
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
    """Update or create English-to-Ojibwe translation in Firestore."""
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
    """Update or create Ojibwe-to-English translation in Firestore."""
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


# Firestore retrieval functions with SQLite fallback

def get_all_english_to_ojibwe() -> List[dict]:
    """Retrieve all English-to-Ojibwe translations from Firestore, falling back to SQLite."""
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


def get_all_ojibwe_to_english() -> List[dict]:
    """Retrieve all Ojibwe-to-English translations from Firestore, falling back to SQLite."""
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


def get_all_semantic_matches() -> List[dict]:
    """Retrieve all semantic matches from Firestore, falling back to SQLite."""
    if FIREBASE_AVAILABLE:
        try:
            docs = get_collections()["semantic_matches"].stream()
            result = [doc.to_dict() for doc in docs]
            logger.info(f"Retrieved {len(result)} semantic matches from Firestore.")
            return result
        except Exception as e:
            logger.error(f"Error retrieving semantic matches from Firestore: {e}")
    logger.warning("Falling back to SQLite for semantic matches.")
    return get_all_semantic_matches_local()


def get_all_missing_translations() -> List[dict]:
    """Retrieve all missing translations from Firestore, falling back to SQLite."""
    if FIREBASE_AVAILABLE:
        try:
            docs = get_collections()["missing_translations"].stream()
            result = [doc.to_dict() for doc in docs]
            logger.info(f"Retrieved {len(result)} missing translations from Firestore.")
            return result
        except Exception as e:
            logger.error(f"Error retrieving missing translations from Firestore: {e}")
    logger.warning("Falling back to SQLite for missing translations.")
    return get_all_missing_translations_local()
