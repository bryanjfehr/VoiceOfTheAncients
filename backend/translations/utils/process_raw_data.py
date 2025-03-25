# backend/translations/utils/process_raw_data.py
"""
Utilities for processing raw scraped data into validated translation entries.
"""
import json
import os
from typing import Dict, List, Union

import logging
logger = logging.getLogger(__name__)

def load_raw_data(file_path: str) -> List[Dict[str, Union[str, List[str]]]]:
    """Load raw translation data from a JSON file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            logger.error(f"Raw data in {file_path} is not a list.")
            return []
        return data
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to load raw data from {file_path}: {e}. Starting fresh.")
        return []

def save_raw_data(data: List[Dict[str, Union[str, List[str]]]], file_path: str) -> None:
    """Save raw translation data to a JSON file."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {len(data)} raw entries to {file_path}.")

def check_for_duplicates(raw_data: List[Dict[str, Union[str, List[str]]]]) -> List[Dict[str, Union[str, List[str]]]]:
    """
    Remove duplicate entries from raw data based on ojibwe_text and english_text.

    Duplicates are defined as entries with the same ojibwe_text and identical english_text sets.
    """
    seen = set()
    unique_entries = []
    for entry in raw_data:
        key = (entry["ojibwe_text"], frozenset(entry["english_text"]))
        if key not in seen:
            seen.add(key)
            unique_entries.append(entry)
        else:
            logger.warning(f"Duplicate entry found and removed: {entry}")
    logger.info(f"Removed {len(raw_data) - len(unique_entries)} duplicates.")
    return unique_entries

def process_raw_data(raw_data: List[Dict[str, Union[str, List[str]]]]) -> List[Dict[str, Union[str, List[str]]]]:
    """Process raw data into validated translation entries."""
    validated = []
    for entry in raw_data:
        if not isinstance(entry, dict):
            logger.warning(f"Invalid entry format: {entry}")
            continue
        ojibwe_text = entry.get("ojibwe_text", "").strip()
        english_text = entry.get("english_text", [])
        definition = entry.get("definition", "").strip()
        if not ojibwe_text or not english_text or not isinstance(english_text, list):
            logger.warning(f"Missing or invalid fields in entry: {entry}")
            continue
        validated.append({
            "ojibwe_text": ojibwe_text,
            "english_text": [e.strip() for e in english_text if e.strip()],
            "definition": definition,
        })
    logger.info(f"Processed {len(validated)} validated entries from {len(raw_data)} raw entries.")
    return validated
