# backend/translations/utils/analysis.py
"""
Semantic analysis using Transformers to match English and Ojibwe definitions.

This module performs semantic matching between English and Ojibwe definitions
using the sentence-transformers/all-MiniLM-L6-v2 model to fill translation gaps.
It ranks words by frequency, persists matches in Firestore, and processes words in batches.
Embedding computation for English definitions is parallelized using concurrent.futures.
"""
import json
import os
import sys
import threading
import time
from typing import Dict, List, Union, Set

import concurrent.futures
import keyboard
import numpy as np
import torch
import warnings
from sentence_transformers import SentenceTransformer

from translations.models import (
    get_all_english_to_ojibwe,
    get_all_ojibwe_to_english,
    update_or_create_english_to_ojibwe,
    update_or_create_ojibwe_to_english,
)
from translations.utils.frequencies import WORD_FREQUENCIES
from translations.utils.definition_utils import is_valid_definition  # noqa: E402

# Import logging setup (configured in ojibwe_scraper.py)
import logging
logger = logging.getLogger("translations.utils.analysis")

# Suppress FutureWarning from transformers
warnings.filterwarnings("ignore", category=FutureWarning)

# Base directory (three levels up from analysis.py to backend/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_english_definitions(json_path: str) -> Union[Dict[str, str], List[str]]:
    """
    Load English words and definitions from a JSON file.

    Args:
        json_path (str): Path to the JSON file containing English words and definitions.

    Returns:
        Union[Dict[str, str], List[str]]: Dictionary of words and definitions,
            or a list if the JSON format is different.

    Raises:
        FileNotFoundError: If the JSON file does not exist.
        json.JSONDecodeError: If the JSON file is malformed.
    """
    try:
        with open(json_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        logger.info(f"Loaded {len(data)} entries from {json_path}")
        return data
    except Exception as e:
        logger.error(f"Error loading English definitions: {e}")
        return {}


def load_processed_words(processed_path: str) -> Set[str]:
    """
    Load the set of already processed English words from a JSON file.

    Args:
        processed_path (str): Path to the JSON file storing processed words.

    Returns:
        Set[str]: Set of English words that have been processed.
    """
    try:
        with open(processed_path, "r", encoding="utf-8") as file:
            processed = set(json.load(file))
        logger.info(f"Loaded {len(processed)} processed words from {processed_path}")
        return processed
    except FileNotFoundError:
        logger.info(f"No processed words file found at {processed_path}. Starting fresh.")
        return set()


def save_processed_words(processed_words: Set[str], processed_path: str) -> None:
    """
    Save the set of processed English words to a JSON file.

    Args:
        processed_words (Set[str]): Set of English words that have been processed.
        processed_path (str): Path to the JSON file to store processed words.
    """
    with open(processed_path, "w", encoding="utf-8") as file:
        json.dump(list(processed_words), file, indent=2)
    logger.info(f"Saved {len(processed_words)} processed words to {processed_path}")


def batch_get_embeddings(
    texts: List[str],
    model: SentenceTransformer,
    batch_size: int = 32,
    max_workers: int = 4,
) -> np.ndarray:
    """
    Get embeddings for a batch of texts using a SentenceTransformer model.

    Uses concurrent.futures to parallelize embedding computation across multiple threads.

    Args:
        texts (List[str]): List of texts to embed.
        model (SentenceTransformer): SentenceTransformer model to generate embeddings.
        batch_size (int): Number of texts to process in each batch. Defaults to 32.
        max_workers (int): Number of threads for parallel processing. Defaults to 4.

    Returns:
        np.ndarray: Array of embeddings for the input texts.
    """
    embeddings = []

    def compute_embeddings(batch_texts):
        """
        Helper function to compute embeddings for a batch of texts.
        """
        return model.encode(batch_texts, batch_size=batch_size, show_progress_bar=False)

    # Split texts into batches and process in parallel
    batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_batch = {executor.submit(compute_embeddings, batch): batch for batch in batches}
        for future in concurrent.futures.as_completed(future_to_batch):
            try:
                batch_embeddings = future.result()
                embeddings.append(batch_embeddings)
            except Exception as e:
                logger.error(f"Error computing embeddings for batch: {e}")

    return np.vstack(embeddings)


def countdown_prompt(total_processed: int, delay: int = 10) -> bool:
    """
    Display a countdown prompt and return whether to continue.

    Args:
        total_processed (int): Total number of words processed so far.
        delay (int): Number of seconds to wait before continuing. Defaults to 10.

    Returns:
        bool: True if the user wants to continue, False if interrupted.
    """
    logger.info(
        f"{total_processed} words processed successfully. Processing another batch in {delay} seconds. Press any key to cancel..."
    )

    # Use a flag to track if a key is pressed
    stop_event = threading.Event()

    def check_keypress():
        keyboard.read_event()
        stop_event.set()

    # Start a thread to listen for keypress
    keypress_thread = threading.Thread(target=check_keypress)
    keypress_thread.daemon = True
    keypress_thread.start()

    # Countdown
    for i in range(delay, 0, -1):
        if stop_event.is_set():
            logger.info("Cancelled by user. Exiting script.")
            sys.exit(0)  # Exit the script immediately
        time.sleep(1)
        logger.info(f"{i} seconds remaining...", extra={"end": "\r"})
    logger.info("Continuing with next batch...")
    return True


def print_semantic_matches(
    threshold: float = 0.85,  # Increased threshold for stricter matching
    batch_size: int = 500,
    min_frequency: int = 100
) -> bool:
    """
    Analyze translations and print semantic matches to fill gaps in batches.

    This function loads English and Ojibwe definitions, computes their embeddings
    using the sentence-transformers/all-MiniLM-L6-v2 model, and finds semantic matches
    based on cosine similarity. Matches are persisted to Firestore and saved to a JSON file.
    Only translations with valid definitions are used for matching.

    Args:
        threshold (float): Minimum similarity score for a match. Defaults to 0.85.
        batch_size (int): Number of words to process in each batch. Defaults to 500.
        min_frequency (int): Minimum frequency for English words to be considered. Defaults to 100.

    Returns:
        bool: True if the analysis completed, False if interrupted.
    """
    # Initialize the SentenceTransformer model
    model_name = "sentence-transformers/all-MiniLM-L6-v2"
    model = SentenceTransformer(model_name)
    logger.info(f"Using model: {model_name}")

    # Load English dictionary
    json_path = os.path.join(BASE_DIR, "data", "english_dict.json")
    logger.info(f"Loading dictionary from: {json_path}")
    english_dict = load_english_definitions(json_path)
    if not english_dict:
        logger.error("Failed to load English dictionary. Skipping semantic analysis.")
        return False

    logger.info(f"English dict type: {type(english_dict)}")

    # Handle different JSON formats for english_dict
    if isinstance(english_dict, dict):
        pass
    elif isinstance(english_dict, list):
        if all(isinstance(item, str) for item in english_dict):
            english_dict = {word: f"{word} (definition unavailable)" for word in english_dict}
        elif all(isinstance(item, dict) and "word" in item for item in english_dict):
            english_dict = {
                item["word"]: item.get(
                    "definition", f"{item['word']} (definition unavailable)"
                )
                for item in english_dict
            }
        else:
            logger.error("Unknown list format in english_dict.json. Skipping analysis.")
            return False
    else:
        logger.error("Unsupported format in english_dict.json. Skipping analysis.")
        return False

    # Load Ojibwe translations from Firestore
    ojibwe_translations = get_all_ojibwe_to_english()
    if not ojibwe_translations:
        logger.error("No Ojibwe translations found in Firestore.")
        return False
    logger.info(f"Loaded {len(ojibwe_translations)} Ojibwe translations from Firestore")

    # Filter Ojibwe translations to only those with valid definitions
    ojibwe_translations_with_defs = [
        trans for trans in ojibwe_translations
        if "definition" in trans and trans["definition"] and is_valid_definition(trans["definition"])
    ]
    if not ojibwe_translations_with_defs:
        logger.error("No Ojibwe translations with valid definitions available for semantic analysis.")
        return False
    logger.info(f"Found {len(ojibwe_translations_with_defs)} Ojibwe translations with valid definitions.")

    # Identify untranslated English words
    translated_english = {
        t["english_text"][0].lower()
        for t in ojibwe_translations
        if t.get("english_text")
    }
    untranslated_words = [
        word for word in english_dict.keys() if word.lower() not in translated_english
    ]
    logger.info(f"Found {len(untranslated_words)} untranslated English words.")

    # Load previously processed words
    processed_path = os.path.join(BASE_DIR, "data", "processed_words.json")
    processed_words = load_processed_words(processed_path)

    # Sort untranslated words by frequency and filter by minimum frequency
    word_freqs = [
        (word, WORD_FREQUENCIES.get(word.lower(), 0))
        for word in untranslated_words
        if word not in processed_words
    ]
    word_freqs = [(word, freq) for word, freq in word_freqs if freq >= min_frequency]
    word_freqs.sort(key=lambda x: x[1], reverse=True)  # Highest frequency first
    remaining_words = [word for word, _ in word_freqs]

    if not remaining_words:
        logger.info("No more untranslated words to process (after frequency filter).")
        return False

    logger.info(f"Total words to process (after frequency filter): {len(remaining_words)}")

    # Precompute embeddings for Ojibwe definitions
    ojibwe_defs = [trans["definition"] for trans in ojibwe_translations_with_defs]
    ojibwe_embeds = batch_get_embeddings(ojibwe_defs, model)
    logger.info(f"Computed embeddings for {len(ojibwe_defs)} Ojibwe definitions.")

    # Process words in batches
    total_processed = 0
    all_matches: List[Dict[str, Union[str, float]]] = []
    batch_number = 1

    for batch_start in range(0, len(remaining_words), batch_size):
        batch_words = remaining_words[batch_start : batch_start + batch_size]
        logger.info(
            f"Processing batch {batch_number} with {len(batch_words)} words "
            f"(Total processed: {total_processed})"
        )

        # Process English definitions for this batch
        eng_words: List[str] = []
        eng_defs: List[str] = []
        for eng_word in batch_words:
            eng_def = english_dict.get(eng_word, f"{eng_word} (definition unavailable)")
            if not is_valid_definition(eng_def):
                logger.debug(f"Skipping English word '{eng_word}' due to invalid definition: {eng_def}")
                continue  # Skip words with no usable definition
            eng_words.append(eng_word)
            eng_defs.append(eng_def)

        if not eng_defs:
            logger.info("No valid English definitions in this batch. Skipping.")
            total_processed += len(batch_words)
            batch_number += 1
            continue

        eng_embeds = batch_get_embeddings(eng_defs, model)
        logger.info(
            f"Computed embeddings for {len(eng_defs)} English definitions in batch {batch_number}."
        )

        # Compute similarities and store matches
        batch_matches: List[Dict[str, Union[str, float]]] = []
        seen_matches = set()  # Track unique matches to avoid duplicates
        for i, eng_word in enumerate(eng_words):
            eng_embed = eng_embeds[i]
            eng_def = eng_defs[i]
            for j, trans in enumerate(ojibwe_translations_with_defs):
                ojibwe_embed = ojibwe_embeds[j]
                ojibwe_def = trans["definition"]
                similarity = float(
                    np.dot(eng_embed, ojibwe_embed)
                    / (np.linalg.norm(eng_embed) * np.linalg.norm(ojibwe_embed))
                )
                match_key = (eng_word, trans["ojibwe_text"])
                if similarity >= threshold and match_key not in seen_matches:
                    seen_matches.add(match_key)
                    match = {
                        "english_text": eng_word,
                        "english_definition": eng_def,
                        "ojibwe_text": trans["ojibwe_text"],
                        "ojibwe_definition": ojibwe_def,
                        "similarity": similarity,
                    }
                    batch_matches.append(match)
                    logger.info(
                        f"Match found: {eng_word} (definition: {eng_def}) -> {trans['ojibwe_text']} "
                        f"(definition: {ojibwe_def}) (Similarity: {similarity:.2f})"
                    )
                    # Update Firestore
                    update_or_create_english_to_ojibwe(
                        eng_word, trans["ojibwe_text"], eng_def
                    )
                    update_or_create_ojibwe_to_english(
                        trans["ojibwe_text"], [eng_word]
                    )
                else:
                    logger.debug(
                        f"No match: {eng_word} (definition: {eng_def}) -> {trans['ojibwe_text']} "
                        f"(definition: {ojibwe_def}) (Similarity: {similarity:.2f}, below threshold {threshold})"
                    )

        # Add batch matches to all matches
        all_matches.extend(batch_matches)
        logger.info(
            f"Batch {batch_number} generated {len(batch_matches)} matches. "
            f"Total matches so far: {len(all_matches)}"
        )

        # Update processed words
        processed_words.update(batch_words)
        save_processed_words(processed_words, processed_path)

        total_processed += len(batch_words)
        batch_number += 1

        # Check if there are more words to process
        if batch_start + batch_size >= len(remaining_words):
            break

        # Prompt to continue with countdown
        if not countdown_prompt(total_processed):
            break

    # Sort matches by similarity (descending) and assign indices
    all_matches.sort(key=lambda x: x["similarity"], reverse=True)
    indexed_matches = [{**match, "index": idx} for idx, match in enumerate(all_matches)]

    # Log the number of matches found
    logger.info(f"Generated {len(indexed_matches)} semantic matches with threshold {threshold}")

    # Save matches to a JSON file
    matches_path = os.path.join(BASE_DIR, "data", "semantic_matches.json")
    with open(matches_path, "w", encoding="utf-8") as f:
        json.dump(indexed_matches, f, indent=2)
    logger.info(f"Saved {len(indexed_matches)} matches to {matches_path}")

    # Print results
    if indexed_matches:
        logger.info(f"Found {len(indexed_matches)} potential semantic matches:")
        for match in indexed_matches:
            logger.info(
                f"  Index: {match['index']}, "
                f"{match['english_text']} (definition: {match['english_definition']}) -> "
                f"{match['ojibwe_text']} (definition: {match['ojibwe_definition']}) "
                f"(Similarity: {match['similarity']:.2f})"
            )
        # Print a summary of similarity scores
        similarities = [match["similarity"] for match in indexed_matches]
        logger.info("Similarity Score Summary:")
        logger.info(f"  Minimum Similarity: {min(similarities):.2f}")
        logger.info(f"  Maximum Similarity: {max(similarities):.2f}")
        logger.info(f"  Average Similarity: {np.mean(similarities):.2f}")
    else:
        logger.info("No semantic matches found above threshold.")

    return True


if __name__ == "__main__":
    print_semantic_matches()
