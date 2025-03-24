# backend/translations/utils/process_raw_data.py
"""
Process raw scraped data into validated translation entries.

Loads, validates, and saves raw data, with detailed logging for debugging.
"""
import json
import logging
from typing import Dict, List, Union

from translations.utils.definition_utils import validate_translation_entry

logger = logging.getLogger("translations.utils.process_raw_data")

def load_raw_data(raw_data_path: str) -> List[Dict[str, Union[str, List[str]]]]:
    """Load raw scraped data from JSON."""
    try:
        with open(raw_data_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        logger.info(f"Loaded {len(data)} raw entries from {raw_data_path}")
        return data
    except FileNotFoundError:
        logger.warning(f"No raw data at {raw_data_path}. Starting fresh.")
        return []
    except Exception as e:
        logger.error(f"Error loading raw data: {e}")
        return []

def save_raw_data(data: List[Dict[str, Union[str, List[str]]]], raw_data_path: str) -> None:
    """Save raw scraped data to JSON."""
    try:
        with open(raw_data_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)
        logger.info(f"Saved {len(data)} raw entries to {raw_data_path}")
    except Exception as e:
        logger.error(f"Error saving raw data: {e}")

def process_raw_data(raw_data: List[Dict[str, Union[str, List[str]]]]) -> List[Dict[str, Union[str, List[str]]]]:
    """Process raw data into validated entries."""
    validated_entries = []
    for entry in raw_data:
        validated_entry = validate_translation_entry(entry)
        if validated_entry:
            validated_entries.append(validated_entry)
            logger.debug(f"Validated entry: {validated_entry}")
        else:
            logger.debug(f"Skipped invalid entry: {entry}")
    logger.info(f"Processed {len(raw_data)} raw entries into {len(validated_entries)} validated entries.")
    return validated_entries
