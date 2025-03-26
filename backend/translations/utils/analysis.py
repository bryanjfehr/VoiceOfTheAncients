# backend/translations/utils/analysis.py
"""
Perform semantic analysis on English and Ojibwe translations using sentence transformers.

Compares English definitions with Ojibwe definitions to find semantic matches above a threshold.
Stores matches in SQLite and saves them to a JSON file for frontend access.
"""
import json
import logging
import os
import time
from typing import Dict, List, Optional

import numpy as np
import torch
from sentence_transformers import SentenceTransformer, util

from translations.models import create_semantic_match_local, get_all_english_to_ojibwe
from translations.utils.definition_utils import is_valid_definition

logger = logging.getLogger("translations.utils.analysis")

# Base directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENGLISH_DICT_PATH = os.path.join(BASE_DIR, "data", "english_dict.json")
SEMANTIC_MATCHES_PATH = os.path.join(BASE_DIR, "data", "semantic_matches.json")
PROCESSED_WORDS_PATH = os.path.join(BASE_DIR, "data", "processed_words.json")

# Batch size for processing
BATCH_SIZE = 500

def load_english_dict() -> Dict[str, str]:
    """Load English dictionary from JSON file."""
    try:
        with open(ENGLISH_DICT_PATH, "r", encoding="utf-8") as f:
            english_dict = json.load(f)
        logger.info(f"Loaded {len(english_dict)} entries from {ENGLISH_DICT_PATH}")
        logger.debug(f"English dict type: {type(english_dict)}")
        return english_dict
    except Exception as e:
        logger.error(f"Error loading English dictionary: {e}")
        return {}

def load_processed_words() -> List[str]:
    """Load the list of words already processed for semantic analysis."""
    try:
        with open(PROCESSED_WORDS_PATH, "r", encoding="utf-8") as f:
            processed = json.load(f)
        logger.info(f"Loaded {len(processed)} processed words from {PROCESSED_WORDS_PATH}")
        return processed
    except FileNotFoundError:
        logger.info(f"No processed words file found at {PROCESSED_WORDS_PATH}. Starting fresh.")
        return []
    except Exception as e:
        logger.error(f"Error loading processed words: {e}")
        return []

def save_processed_words(processed_words: List[str]) -> None:
    """Save the list of processed words to a JSON file."""
    try:
        with open(PROCESSED_WORDS_PATH, "w", encoding="utf-8") as f:
            json.dump(processed_words, f)
        logger.info(f"Saved {len(processed_words)} processed words to {PROCESSED_WORDS_PATH}")
    except Exception as e:
        logger.error(f"Error saving processed words: {e}")

def save_semantic_matches(matches: List[Dict]) -> None:
    """Save semantic matches to a JSON file for frontend access."""
    try:
        with open(SEMANTIC_MATCHES_PATH, "w", encoding="utf-8") as f:
            json.dump(matches, f, indent=2)
        logger.info(f"Saved {len(matches)} matches to {SEMANTIC_MATCHES_PATH}")
    except Exception as e:
        logger.error(f"Error saving semantic matches: {e}")

def print_semantic_matches(threshold: float = 0.7) -> Optional[List[Dict]]:
    """
    Perform semantic analysis to find matches between English and Ojibwe definitions.

    Args:
        threshold (float): Similarity threshold for matches (default: 0.7).

    Returns:
        List[Dict]: List of semantic matches, or None if no more words to process.
    """
    logger.info(f"Using model: sentence-transformers/all-MiniLM-L6-v2")
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    # Load English dictionary
    english_dict = load_english_dict()
    if not english_dict:
        logger.error("Failed to load English dictionary. Aborting semantic analysis.")
        return None

    # Load Ojibwe translations from Firestore
    ojibwe_translations = get_all_english_to_ojibwe()
    logger.info(f"Loaded {len(ojibwe_translations)} Ojibwe translations from Firestore")

    # Filter translations with valid definitions
    ojibwe_with_definitions = [
        trans for trans in ojibwe_translations
        if trans.get("definition") and is_valid_definition(trans["definition"])
    ]
    logger.info(f"Found {len(ojibwe_with_definitions)} Ojibwe translations with valid definitions.")

    # Identify untranslated English words
    translated_english = {trans["english_text"].lower() for trans in ojibwe_translations}
    untranslated_english = {
        word.lower() for word in english_dict.keys()
        if word.lower() not in translated_english and english_dict[word]
    }
    logger.info(f"Found {len(untranslated_english)} untranslated English words.")

    # Sort untranslated words by frequency
    from translations.utils.frequencies import WORD_FREQUENCIES
    word_freqs = [(word, WORD_FREQUENCIES.get(word.lower(), 0)) for word in untranslated_english]
    word_freqs.sort(key=lambda x: x[1], reverse=True)
    untranslated_english_sorted = [word for word, _ in word_freqs]

    # Load processed words
    processed_words = set(load_processed_words())
    remaining_words = [word for word in untranslated_english_sorted if word not in processed_words]
    logger.info(f"Found {len(remaining_words)} untranslated words to process.")

    if not remaining_words:
        logger.info("No more untranslated words to process.")
        return None

    # Compute embeddings for Ojibwe definitions
    ojibwe_definitions = [trans["definition"] for trans in ojibwe_with_definitions]
    logger.info(f"Computing embeddings for {len(ojibwe_definitions)} Ojibwe definitions.")
    ojibwe_embeddings = model.encode(ojibwe_definitions, convert_to_tensor=True, show_progress_bar=True)
    logger.info(f"Computed embeddings for {len(ojibwe_definitions)} Ojibwe definitions.")

    # Process in batches
    total_processed = len(processed_words)
    matches = []
    batch_index = 0

    while remaining_words:
        batch_words = remaining_words[:BATCH_SIZE]
        remaining_words = remaining_words[BATCH_SIZE:]
        batch_index += 1

        logger.info(f"Processing batch {batch_index} with {len(batch_words)} words (Total processed: {total_processed})")

        # Compute embeddings for English definitions in the batch
        english_definitions = [english_dict[word] for word in batch_words if english_dict.get(word)]
        if not english_definitions:
            logger.warning(f"No valid definitions found for batch {batch_index}. Skipping.")
            processed_words.update(batch_words)
            total_processed += len(batch_words)
            save_processed_words(list(processed_words))
            continue

        logger.info(f"Computed embeddings for {len(english_definitions)} English definitions in batch {batch_index}.")
        english_embeddings = model.encode(english_definitions, convert_to_tensor=True, show_progress_bar=True)

        # Compute cosine similarities
        cosine_scores = util.cos_sim(english_embeddings, ojibwe_embeddings)

        # Find matches above threshold
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

        logger.info(f"Batch {batch_index} generated {len(batch_matches)} matches. Total matches so far: {len(matches) + len(batch_matches)}")
        matches.extend(batch_matches)

        # Update processed words
        processed_words.update(batch_words)
        total_processed += len(batch_words)
        save_processed_words(list(processed_words))

        # Store matches in SQLite
        for match in batch_matches:
            create_semantic_match_local(
                english_text=match["english_text"],
                ojibwe_text=match["ojibwe_text"],
                similarity=match["similarity"],
                english_definition=match["english_definition"],
                ojibwe_definition=match["ojibwe_definition"],
                version="1.0",  # Use current version
            )

        logger.info(f"{total_processed} words processed successfully. Processing another batch in 10 seconds. Press any key to cancel...")
        for remaining in range(10, 0, -1):
            logger.info(f"{remaining} seconds remaining...")
            time.sleep(1)

    # Save all matches
    logger.info(f"Generated {len(matches)} semantic matches with threshold {threshold}")
    save_semantic_matches(matches)

    if not matches:
        logger.info("No semantic matches found above threshold.")
        return None

    return matches