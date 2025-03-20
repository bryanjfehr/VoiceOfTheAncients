"""Semantic analysis using Transformers to match English and Ojibwe definitions.

This module performs semantic matching between English and Ojibwe definitions
using a Transformer model (DistilBERT) to fill translation gaps. It ranks words
by frequency, persists matches in MongoDB, and prompts the user to continue
processing batches of words.
"""
import json
import os
from typing import Dict, List, Union, Set
import warnings

import torch
import numpy as np
from transformers import AutoTokenizer, AutoModel

from translations.models import (
    get_all_english_to_ojibwe,
    get_all_ojibwe_to_english,
    update_or_create_english_to_ojibwe,
    update_or_create_ojibwe_to_english,
)
from translations.utils.frequencies import WORD_FREQUENCIES

# Suppress FutureWarning from transformers
warnings.filterwarnings("ignore", category=FutureWarning)

# Base directory (three levels up from analysis.py to backend/)
BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def load_english_definitions(json_path: str) -> Union[Dict[str, str], List[str]]:
    """Load English words and definitions from a JSON file.

    Args:
        json_path (str): Path to the JSON file containing English words and
            definitions.

    Returns:
        Union[Dict[str, str], List[str]]: Dictionary of words and definitions,
            or a list if the JSON format is different.

    Raises:
        FileNotFoundError: If the JSON file does not exist.
        json.JSONDecodeError: If the JSON file is malformed.
    """
    try:
        with open(json_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        print(f"Error loading English definitions: {e}")
        return {}


def load_processed_words(processed_path: str) -> Set[str]:
    """Load the set of already processed English words from a JSON file.

    Args:
        processed_path (str): Path to the JSON file storing processed words.

    Returns:
        Set[str]: Set of English words that have been processed.
    """
    try:
        with open(processed_path, "r", encoding="utf-8") as file:
            return set(json.load(file))
    except FileNotFoundError:
        return set()


def save_processed_words(processed_words: Set[str], processed_path: str) -> None:
    """Save the set of processed English words to a JSON file.

    Args:
        processed_words (Set[str]): Set of English words that have been processed.
        processed_path (str): Path to the JSON file to store processed words.
    """
    with open(processed_path, "w", encoding="utf-8") as file:
        json.dump(list(processed_words), file)


def batch_get_embeddings(
    texts: List[str],
    tokenizer: AutoTokenizer,
    model: AutoModel,
    batch_size: int = 32,
) -> np.ndarray:
    """Get embeddings for a batch of texts using a Transformer model.

    Args:
        texts (List[str]): List of texts to embed.
        tokenizer (AutoTokenizer): Tokenizer for the Transformer model.
        model (AutoModel): Transformer model to generate embeddings.
        batch_size (int): Number of texts to process in each batch. Defaults to 32.

    Returns:
        np.ndarray: Array of embeddings for the input texts.
    """
    embeddings: List[np.ndarray] = []
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        inputs = tokenizer(
            batch_texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=128,
        )
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = model(**inputs).last_hidden_state.mean(dim=1).cpu().numpy()
        embeddings.append(outputs)
        # Clear memory
        torch.cuda.empty_cache() if torch.cuda.is_available() else None
    return np.vstack(embeddings)


def print_semantic_matches(threshold: float = 0.8) -> bool:
    """Analyze translations and print semantic matches to fill gaps.

    This function loads English and Ojibwe definitions, computes their embeddings
    using a Transformer model, and finds semantic matches based on cosine similarity.
    Matches are persisted to MongoDB, and the user is prompted to continue with the
    next batch.

    Args:
        threshold (float): Minimum similarity score for a match. Defaults to 0.8.

    Returns:
        bool: True if the user wants to continue with the next batch, False otherwise.
    """
    # Initialize the Transformer model and tokenizer
    model_name = "distilbert-base-uncased"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    print(f"Using device: {device}")

    # Load English dictionary
    json_path = os.path.join(BASE_DIR, "data", "english_dict.json")
    print(f"Loading dictionary from: {json_path}")
    english_dict = load_english_definitions(json_path)
    if not english_dict:
        print("Failed to load English dictionary. Skipping semantic analysis.")
        return False

    print(f"English dict type: {type(english_dict)}")

    # Handle different JSON formats for english_dict
    if isinstance(english_dict, dict):
        pass
    elif isinstance(english_dict, list):
        if all(isinstance(item, str) for item in english_dict):
            english_dict = {word: word for word in english_dict}
        elif all(isinstance(item, dict) and "word" in item for item in english_dict):
            english_dict = {
                item["word"]: item.get("definition", item["word"])
                for item in english_dict
            }
        else:
            print("Unknown list format in english_dict.json. Skipping analysis.")
            return False
    else:
        print("Unsupported format in english_dict.json. Skipping analysis.")
        return False

    # Load Ojibwe translations from MongoDB
    ojibwe_translations = get_all_ojibwe_to_english()
    if not ojibwe_translations:
        print("No Ojibwe translations found in database.")
        return False

    # Identify untranslated English words
    translated_english = {
        t["english_text"][0] for t in ojibwe_translations if t.get("english_text")
    }
    untranslated_words = [
        word for word in english_dict.keys() if word not in translated_english
    ]

    print(f"Found {len(untranslated_words)} untranslated English words.")

    # Load previously processed words
    processed_path = os.path.join(BASE_DIR, "data", "processed_words.json")
    processed_words = load_processed_words(processed_path)

    # Sort untranslated words by frequency
    word_freqs = [
        (word, WORD_FREQUENCIES.get(word.lower(), 0))
        for word in untranslated_words
        if word not in processed_words
    ]
    word_freqs.sort(key=lambda x: x[1], reverse=True)  # Highest frequency first
    remaining_words = [word for word, _ in word_freqs]

    if not remaining_words:
        print("No more untranslated words to process.")
        return False

    # Process all remaining words
    batch_words = remaining_words
    print(f"Processing {len(batch_words)} words for analysis.")

    # Precompute embeddings for Ojibwe definitions
    ojibwe_defs = [
        trans.get("definition", trans["ojibwe_text"])
        for trans in ojibwe_translations
    ]
    ojibwe_defs = [d for d in ojibwe_defs if d]
    ojibwe_embeds = batch_get_embeddings(ojibwe_defs, tokenizer, model)
    print(f"Computed embeddings for {len(ojibwe_defs)} Ojibwe definitions.")

    # Process English definitions in batches
    matches: List[Dict[str, Union[str, float]]] = []
    eng_words: List[str] = []
    eng_defs: List[str] = []
    for eng_word in batch_words:
        eng_def = english_dict.get(eng_word, eng_word)
        eng_words.append(eng_word)
        eng_defs.append(eng_def)

    eng_embeds = batch_get_embeddings(eng_defs, tokenizer, model)
    print(f"Computed embeddings for {len(eng_defs)} English definitions.")

    # Compute similarities and store matches
    for i, eng_word in enumerate(eng_words):
        eng_embed = eng_embeds[i]
        for j, trans in enumerate(ojibwe_translations):
            if not ojibwe_defs[j]:
                continue
            ojibwe_embed = ojibwe_embeds[j]
            similarity = float(
                np.dot(eng_embed, ojibwe_embed) /
                (np.linalg.norm(eng_embed) * np.linalg.norm(ojibwe_embed))
            )
            if similarity >= threshold:
                match = {
                    "english_text": eng_word,
                    "ojibwe_text": trans["ojibwe_text"],
                    "similarity": similarity,
                }
                matches.append(match)
                # Persist to MongoDB
                update_or_create_english_to_ojibwe(eng_word, trans["ojibwe_text"])
                update_or_create_ojibwe_to_english(trans["ojibwe_text"], [eng_word])

    # Update processed words
    processed_words.update(batch_words)
    save_processed_words(processed_words, processed_path)

    # Sort matches by similarity (ascending order, highest scores at the bottom)
    matches.sort(key=lambda x: x["similarity"])  # Ascending order
    
    # Save matches to a JSON file
    matches_path = os.path.join(BASE_DIR, "data", "semantic_matches.json")
    with open(matches_path, "w", encoding="utf-8") as f:
        json.dump(matches, f, indent=2)
    print(f"Saved {len(matches)} matches to {matches_path}")

    # Print results
    if matches:
        print(f"Found {len(matches)} potential semantic matches:")
        for match in matches:
            print(
                f"  {match['english_text']} -> {match['ojibwe_text']} "
                f"(Similarity: {match['similarity']:.2f})"
            )
        # Print a summary of similarity scores
        similarities = [match["similarity"] for match in matches]
        print("\nSimilarity Score Summary:")
        print(f"  Minimum Similarity: {min(similarities):.2f}")
        print(f"  Maximum Similarity: {max(similarities):.2f}")
        print(f"  Average Similarity: {np.mean(similarities):.2f}")
    else:
        print("No semantic matches found above threshold.")
    # Print results
    if matches:
        print(f"Found {len(matches)} potential semantic matches:")
        for match in matches:
            print(
                f"  {match['english_text']} -> {match['ojibwe_text']} "
                f"(Similarity: {match['similarity']:.2f})"
            )
        # Print a summary of similarity scores
        similarities = [match["similarity"] for match in matches]
        print("\nSimilarity Score Summary:")
        print(f"  Minimum Similarity: {min(similarities):.2f}")
        print(f"  Maximum Similarity: {max(similarities):.2f}")
        print(f"  Average Similarity: {np.mean(similarities):.2f}")
    else:
        print("No semantic matches found above threshold.")

    # Prompt to continue
    response = input("\nRun semantic analysis again? (Y/n): ").strip().lower()
    return response in ("", "y", "yes")


if __name__ == "__main__":
    print_semantic_matches()
