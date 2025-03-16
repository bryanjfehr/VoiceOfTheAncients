"""Semantic analysis using Transformers to match English and Ojibwe definitions."""
import json
import os
from typing import Dict, List, Union
import torch
import warnings
from transformers import AutoTokenizer, AutoModel
import numpy as np
from translations.models import get_all_english_to_ojibwe, get_all_ojibwe_to_english

# Suppress FutureWarning from transformers
warnings.filterwarnings("ignore", category=FutureWarning)

# Base directory (three levels up from analysis.py to backend/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_english_definitions(json_path: str) -> Union[Dict[str, str], List[str]]:
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
        inputs1 = tokenizer(text1, return_tensors="pt", padding=True, truncation=True, max_length=128)  # Reduced max_length
        inputs2 = tokenizer(text2, return_tensors="pt", padding=True, truncation=True, max_length=128)
        with torch.no_grad():
            outputs1 = model(**inputs1).last_hidden_state.mean(dim=1).squeeze().numpy()
            outputs2 = model(**inputs2).last_hidden_state.mean(dim=1).squeeze().numpy()
        return float(np.dot(outputs1, outputs2) /
                     (np.linalg.norm(outputs1) * np.linalg.norm(outputs2)))
    except Exception as e:
        print(f"Error calculating similarity: {e}")
        return 0.0


def print_semantic_matches(threshold: float = 0.8, max_words: int = 1000) -> None:
    """Analyze scraped translations and print semantic matches to fill gaps."""
    tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
    model = AutoModel.from_pretrained("bert-base-uncased")

    # Load English dictionary with absolute path
    json_path = os.path.join(BASE_DIR, "data", "english_dict.json")
    print(f"Loading dictionary from: {json_path}")
    english_dict = load_english_definitions(json_path)
    if not english_dict:
        print("Failed to load English dictionary. Skipping semantic analysis.")
        return

    print(f"English dict type: {type(english_dict)}")

    # Handle different JSON formats
    if isinstance(english_dict, dict):
        pass
    elif isinstance(english_dict, list):
        if all(isinstance(item, str) for item in english_dict):
            english_dict = {word: word for word in english_dict}
        elif all(isinstance(item, dict) and "word" in item for item in english_dict):
            english_dict = {item["word"]: item.get("definition", item["word"])
                           for item in english_dict}
        else:
            print("Unknown list format in english_dict.json. Skipping analysis.")
            return
    else:
        print("Unsupported format in english_dict.json. Skipping analysis.")
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

    # Limit to max_words for performance
    untranslated_words = list(untranslated_words)[:max_words]
    print(f"Processing {len(untranslated_words)} words for analysis.")

    # Analyze semantic matches
    matches = []
    for eng_word in untranslated_words:
        eng_def = english_dict.get(eng_word, eng_word)
        for trans in ojibwe_translations:
            ojibwe_def = trans.get("definition", trans["ojibwe_text"])
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