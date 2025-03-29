# backend/translations/utils/analysis.py
"""
Perform semantic analysis on English and Ojibwe translations using sentence transformers.

Compares definitions to find semantic matches above a threshold, storing them in SQLite.
"""
import json
import logging
import os
from typing import Dict, List, Optional

from sentence_transformers import SentenceTransformer, util

from translations.models import (
    SemanticMatchLocal,
    create_semantic_match_local,
    get_all_english_to_ojibwe,
    get_all_semantic_matches_local,
    sync_to_firestore,
    get_firestore_version,
)
from translations.utils.definition_utils import is_valid_definition

logger = logging.getLogger("translations.utils.analysis")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENGLISH_DICT_PATH = os.path.join(BASE_DIR, "data", "english_dict.json")
SEMANTIC_MATCHES_PATH = os.path.join(BASE_DIR, "data", "semantic_matches.json")
PROCESSED_WORDS_PATH = os.path.join(BASE_DIR, "data", "processed_words.json")
BATCH_SIZE = 10000


def load_english_dict() -> Dict[str, str]:
    """Load English dictionary from JSON file."""
    try:
        with open(ENGLISH_DICT_PATH, "r", encoding="utf-8") as f:
            english_dict = json.load(f)
        logger.info(f"Loaded {len(english_dict)} entries from {ENGLISH_DICT_PATH}")
        return english_dict
    except Exception as e:
        logger.error(f"Error loading English dictionary: {e}")
        return {}


def load_processed_words() -> List[str]:
    """Load processed words for semantic analysis."""
    try:
        with open(PROCESSED_WORDS_PATH, "r", encoding="utf-8") as f:
            processed = json.load(f)
        logger.info(f"Loaded {len(processed)} processed words from {PROCESSED_WORDS_PATH}")
        return processed
    except FileNotFoundError:
        logger.info(f"No processed words file at {PROCESSED_WORDS_PATH}. Starting fresh.")
        return []
    except Exception as e:
        logger.error(f"Error loading processed words: {e}")
        return []


def save_processed_words(processed_words: List[str]) -> None:
    """Save processed words to JSON file."""
    try:
        with open(PROCESSED_WORDS_PATH, "w", encoding="utf-8") as f:
            json.dump(processed_words, f)
        logger.info(f"Saved {len(processed_words)} processed words to {PROCESSED_WORDS_PATH}")
    except Exception as e:
        logger.error(f"Error saving processed words: {e}")


def save_semantic_matches(matches: List[Dict]) -> None:
    """Save semantic matches to JSON for frontend access."""
    try:
        with open(SEMANTIC_MATCHES_PATH, "w", encoding="utf-8") as f:
            json.dump(matches, f, indent=2)
        logger.info(f"Saved {len(matches)} matches to {SEMANTIC_MATCHES_PATH}")
    except Exception as e:
        logger.error(f"Error saving semantic matches: {e}")


def check_existing_semantic_matches(version: str = "1.0") -> bool:
    """Check if semantic matches exist in SQLite."""
    try:
        existing_matches = get_all_semantic_matches_local()
        if existing_matches:
            logger.info(f"Found {len(existing_matches)} existing semantic matches in SQLite.")
            return True
        logger.info("No existing semantic matches in SQLite.")
        return False
    except Exception as e:
        logger.error(f"Error checking existing semantic matches: {e}")
        return False


def print_semantic_matches(threshold: float = 0.7, version: str = "1.0") -> Optional[List[Dict]]:
    """
    Perform semantic analysis to find matches between English and Ojibwe definitions.

    Args:
        threshold (float): Similarity threshold (default: 0.7).
        version (str): Version for storing matches (default: "1.0").

    Returns:
        Optional[List[Dict]]: List of matches if found, None otherwise.
    """
    logger.info(f"Starting semantic analysis with model 'all-MiniLM-L6-v2', threshold: {threshold}, version: {version}")

    if check_existing_semantic_matches(version):
        logger.info("Existing matches found. Overwriting with new analysis.")
        SemanticMatchLocal.objects.filter(version=version).delete()
        logger.info(f"Cleared existing semantic matches for version {version}.")

    try:
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        logger.info("Loaded sentence transformer model successfully.")
    except Exception as e:
        logger.error(f"Failed to load sentence transformer model: {e}")
        return None

    english_dict = load_english_dict()
    if not english_dict:
        logger.error("Failed to load English dictionary. Aborting.")
        return None

    ojibwe_translations = get_all_english_to_ojibwe()
    logger.info(f"Loaded {len(ojibwe_translations)} Ojibwe translations.")

    ojibwe_with_definitions = [
        trans for trans in ojibwe_translations
        if trans.get("definition") and is_valid_definition(trans["definition"])
    ]
    logger.info(f"Found {len(ojibwe_with_definitions)} translations with valid definitions.")

    if not ojibwe_with_definitions:
        logger.warning("No valid Ojibwe definitions found. Aborting.")
        return None

    translated_english = {trans["english_text"].lower() for trans in ojibwe_translations}
    untranslated_english = {
        word.lower() for word in english_dict.keys()
        if word.lower() not in translated_english and english_dict[word]
    }
    logger.info(f"Found {len(untranslated_english)} untranslated English words.")

    from translations.utils.frequencies import WORD_FREQUENCIES
    word_freqs = [(word, WORD_FREQUENCIES.get(word.lower(), 0)) for word in untranslated_english]
    word_freqs.sort(key=lambda x: x[1], reverse=True)
    untranslated_english_sorted = [word for word, _ in word_freqs]

    processed_words = set(load_processed_words())
    remaining_words = [word for word in untranslated_english_sorted if word not in processed_words]
    logger.info(f"Found {len(remaining_words)} untranslated words to process.")

    if not remaining_words:
        logger.info("No more words to process.")
        return None

    ojibwe_definitions = [trans["definition"] for trans in ojibwe_with_definitions]
    logger.info(f"Computing embeddings for {len(ojibwe_definitions)} Ojibwe definitions.")
    try:
        ojibwe_embeddings = model.encode(ojibwe_definitions, convert_to_tensor=True, show_progress_bar=True)
        logger.info("Computed Ojibwe embeddings successfully.")
    except Exception as e:
        logger.error(f"Error computing Ojibwe embeddings: {e}")
        return None

    matches = []
    batch_index = 0
    total_processed = len(processed_words)

    while remaining_words:
        batch_words = remaining_words[:BATCH_SIZE]
        remaining_words = remaining_words[BATCH_SIZE:]
        batch_index += 1

        logger.info(f"Processing batch {batch_index} with {len(batch_words)} words (Total: {total_processed})")

        english_definitions = [english_dict[word] for word in batch_words if english_dict.get(word)]
        if not english_definitions:
            logger.warning(f"No valid definitions for batch {batch_index}. Skipping.")
            processed_words.update(batch_words)
            total_processed += len(batch_words)
            save_processed_words(list(processed_words))
            continue

        try:
            english_embeddings = model.encode(english_definitions, convert_to_tensor=True, show_progress_bar=True)
            logger.info(f"Computed English embeddings for batch {batch_index}")
        except Exception as e:
            logger.error(f"Error computing English embeddings for batch {batch_index}: {e}")
            processed_words.update(batch_words)
            total_processed += len(batch_words)
            save_processed_words(list(processed_words))
            continue

        try:
            cosine_scores = util.cos_sim(english_embeddings, ojibwe_embeddings)
            logger.info(f"Computed cosine similarities for batch {batch_index}")
        except Exception as e:
            logger.error(f"Error computing cosine similarities for batch {batch_index}: {e}")
            processed_words.update(batch_words)
            total_processed += len(batch_words)
            save_processed_words(list(processed_words))
            continue

        batch_matches = []
        for i, word in enumerate(batch_words):
            for j, ojibwe_trans in enumerate(ojibwe_with_definitions):
                similarity = cosine_scores[i][j].item()
                if similarity >= threshold:
                    match = {
                        "index": len(matches) + len(batch_matches),
                        "english_text": word,
                        "ojibwe_text": ojibwe_trans["ojibwe_text"],
                        "similarity": similarity,
                        "english_definition": english_dict[word],
                        "ojibwe_definition": ojibwe_trans["definition"],
                    }
                    batch_matches.append(match)

        logger.info(f"Batch {batch_index} generated {len(batch_matches)} matches")
        matches.extend(batch_matches)

        for match in batch_matches:
            try:
                create_semantic_match_local(
                    english_text=match["english_text"],
                    ojibwe_text=match["ojibwe_text"],
                    similarity=match["similarity"],
                    english_definition=match["english_definition"],
                    ojibwe_definition=match["ojibwe_definition"],
                    version=version,
                )
            except Exception as e:
                logger.error(f"Error storing match {match['english_text']} => {match['ojibwe_text']}: {e}")

        logger.info(f"Stored {len(batch_matches)} matches in SQLite for version {version}")
        processed_words.update(batch_words)
        total_processed += len(batch_words)
        save_processed_words(list(processed_words))

    logger.info(f"Generated and stored {len(matches)} matches with threshold {threshold}")
    save_semantic_matches(matches)

    if matches:
        try:
            current_version = get_firestore_version()
            version_parts = current_version.split(".")
            new_version = f"{version_parts[0]}.{int(version_parts[1]) + 1}"
            logger.info(f"Syncing {len(matches)} new matches to Firestore with version {new_version}")
            sync_to_firestore(version=new_version)
            logger.info(f"Synced matches to Firestore with version {new_version}.")
        except Exception as e:
            logger.error(f"Error syncing matches to Firestore: {e}")

    return matches if matches else None


if __name__ == "__main__":
    print_semantic_matches()
