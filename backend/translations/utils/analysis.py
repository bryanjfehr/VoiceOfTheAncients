"""Utility functions for analyzing translations using semantic matching."""
import spacy
import numpy as np
from translations.models import get_all_ojibwe_to_english, get_all_english_to_ojibwe

# Load the English language model for spacy
nlp = spacy.load("en_core_web_sm")

def match_semantic_translations(similarity_threshold: float = 0.7) -> dict:
    """Match Ojibwe-to-English translations with English-to-Ojibwe translations using semantic similarity.
    Args:
        similarity_threshold (float): Minimum similarity score to consider a match (default: 0.7).
    Returns:
        dict: Dictionary mapping Ojibwe terms to (English term, similarity score) pairs.
    """
    # Fetch translations from MongoDB
    ojibwe_translations = get_all_ojibwe_to_english()
    english_translations = get_all_english_to_ojibwe()

    # Dictionary to store matches
    matches = {}

    # Process each Ojibwe-to-English translation
    for ojibwe_entry in ojibwe_translations:
        ojibwe_text = ojibwe_entry["ojibwe_text"]
        # Join English translations into a single string for embedding
        english_texts = ojibwe_entry.get("english_text", [])
        if not english_texts:
            continue
        ojibwe_english = " ".join(english_texts)
        
        # Create embedding for the Ojibwe entry's English translation
        ojibwe_doc = nlp(ojibwe_english)
        
        # Compare with each English-to-Ojibwe translation
        for english_entry in english_translations:
            english_text = " ".join(english_entry["english_text"])
            english_doc = nlp(english_text)
            
            # Compute cosine similarity between embeddings
            similarity = ojibwe_doc.similarity(english_doc)
            
            # Store the match if similarity exceeds the threshold
            if similarity > similarity_threshold:
                if ojibwe_text not in matches or matches[ojibwe_text][1] < similarity:
                    matches[ojibwe_text] = (english_text, similarity)

    return matches

def print_semantic_matches():
    """Print the semantic matches between Ojibwe and English translations."""
    matches = match_semantic_translations()
    for ojibwe, (english, similarity) in matches.items():
        print(f"Ojibwe: {ojibwe} -> English: {english} (Similarity: {similarity:.2f})")

if __name__ == "__main__":
    print_semantic_matches()
