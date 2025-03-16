"""Semantic analysis using Transformers to match English and Ojibwe definitions."""
import json
from typing import Dict, List
import torch
from transformers import AutoTokenizer, AutoModel
import numpy as np
from translations.models import get_all_english_to_ojibwe, get_all_ojibwe_to_english


def load_english_definitions(json_path: str) -> Dict[str, str]:
    """Load English words and definitions from a JSON file."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading English definitions: {e}")
        return {}


def get_semantic_similarity(text1: str, text2: str,
                           tokenizer: AutoTokenizer, model: AutoModel) -> float:
    """Calculate semantic similarity between two texts using BERT."""
    try:
        # Tokenize inputs
        inputs1 = tokenizer(text1, return_tensors="pt", padding=True, truncation=True, max_length=512)
        inputs2 = tokenizer(text2, return_tensors="pt", padding=True, truncation=True, max_length=512)

        # Get embeddings
        with torch.no_grad():
            outputs1 = model(**inputs1).last_hidden_state.mean(dim=1).squeeze().numpy()
            outputs2 = model(**inputs2).last_hidden_state.mean(dim=1).squeeze().numpy()

        # Cosine similarity
        return float(np.dot(outputs1, outputs2) /
                     (np.linalg.norm(outputs1) * np.linalg.norm(outputs2)))
    except Exception as e:
        print(f"Error calculating similarity: {e}")
        return 0.0


def print_semantic_matches(threshold: float = 0.8) -> None:
    """Analyze scraped translations and print semantic matches to fill gaps."""
    # Initialize BERT model and tokenizer
    tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
    model = AutoModel.from_pretrained("bert-base-uncased")

    # Load English dictionary
    english_dict = load_english_definitions("../data/english_dict.json")  # Adjusted path
    if not english_dict:
        print("Failed to load English dictionary. Skipping semantic analysis.")
        return

    # Get all scraped translations from MongoDB
    ojibwe_translations = get_all_ojibwe_to_english()
    if not ojibwe_translations:
        print("No Ojibwe translations found in database.")
        return

    # Track untranslated English words
    translated_english = {t["english_text"][0] for t in ojibwe_translations
                          if t.get("english_text")}
    untranslated_words = {word for word in english_dict.keys()
                          if word not in translated_english}

    print(f"Found {len(untranslated_words)} untranslated English words.")

    # Analyze semantic matches (limit to 100 for testing)
    matches = []
    for eng_word in list(untranslated_words)[:100]:  # Limit for speed
        eng_def = english_dict.get(eng_word, "")
        if not eng_def:
            continue
        for trans in ojibwe_translations:
            ojibwe_def = trans.get("definition", "")
            if not ojibwe_def:
                continue
            similarity = get_semantic_similarity(eng_def, ojibwe_def, tokenizer, model)
            if similarity >= threshold:
                matches.append({
                    "english_text": eng_word,
                    "ojibwe_text": trans["ojibwe_text"],
                    "similarity": similarity
                })

    # Print results
    if matches:
        print(f"Found {len(matches)} potential semantic matches:")
        for match in matches:
            print(f"  {match['english_text']} -> {match['ojibwe_text']} "
                  f"(Similarity: {match['similarity']:.2f})")
    else:
        print("No semantic matches found above threshold.")


if __name__ == "__main__":
    print_semantic_matches()