# backend/translations/utils/process_raw_data.py
"""
Utility module for processing raw scraped data into validated translation entries.

This module reads raw data from raw_ojibwe_english_dict.json, validates and formats the entries,
and prepares them for storage in SQLite and Firestore. It ensures that only valid translations
with meaningful definitions are stored.
"""
import json
import logging
from typing import Dict, List, Union

# Import definition utilities
from translations.utils.definition_utils import validate_translation_entry  # noqa: E402

# Import logger (configured in ojibwe_scraper.py)
logger = logging.getLogger("translations.utils.process_raw_data")


def load_raw_data(raw_data_path: str) -> List[Dict[str, Union[str, List[str]]]]:
    """
    Load raw scraped data from a JSON file.

    Args:
        raw_data_path (str): Path to the raw data JSON file.

    Returns:
        List[Dict[str, Union[str, List[str]]]]: List of raw translation entries.
    """
    try:
        with open(raw_data_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        logger.info(f"Loaded {len(data)} raw entries from {raw_data_path}")
        return data
    except FileNotFoundError:
        logger.warning(f"Raw data file not found at {raw_data_path}. Starting fresh.")
        return []
    except Exception as e:
        logger.error(f"Error loading raw data from {raw_data_path}: {e}")
        return []


def save_raw_data(data: List[Dict[str, Union[str, List[str]]]], raw_data_path: str) -> None:
    """
    Save raw scraped data to a JSON file.

    Args:
        data (List[Dict[str, Union[str, List[str]]]]): List of raw translation entries.
        raw_data_path (str): Path to the raw data JSON file.
    """
    try:
        with open(raw_data_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)
        logger.info(f"Saved {len(data)} raw entries to {raw_data_path}")
    except Exception as e:
        logger.error(f"Error saving raw data to {raw_data_path}: {e}")


def process_raw_data(raw_data: List[Dict[str, Union[str, List[str]]]]) -> List[Dict[str, Union[str, List[str]]]]:
    """
    Process raw scraped data to validate and format translation entries.

    Args:
        raw_data (List[Dict[str, Union[str, List[str]]]]): List of raw translation entries.

    Returns:
        List[Dict[str, Union[str, List[str]]]]: List of validated and formatted translation entries.
    """
    validated_entries = []
    for entry in raw_data:
        validated_entry = validate_translation_entry(entry)
        if validated_entry:
            validated_entries.append(validated_entry)
        else:
            logger.warning(f"Skipping invalid raw entry: {entry}")
    logger.info(f"Processed {len(raw_data)} raw entries into {len(validated_entries)} validated entries.")
    return validated_entries
