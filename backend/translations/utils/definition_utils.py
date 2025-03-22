# backend/translations/utils/definition_utils.py
"""
Utility module for analyzing, formatting, and validating definitions in the Voice of the Ancients project.

This module provides functions to ensure that definitions scraped from the web are meaningful,
properly formatted, and suitable for storage in the translation dictionaries. It includes validation
checks to prevent placeholder or invalid definitions from being used in semantic analysis.
"""
import logging
import re
from typing import Optional, List, Dict, Union

# Import logger (configured in ojibwe_scraper.py)
logger = logging.getLogger("translations.utils.definition_utils")


def clean_definition(definition: str) -> str:
    """
    Clean a definition by removing unwanted characters, extra whitespace, and standardizing format.

    Args:
        definition (str): The raw definition text to clean.

    Returns:
        str: The cleaned definition text.
    """
    if not definition:
        return ""

    # Remove HTML tags if any
    definition = re.sub(r"<[^>]+>", "", definition)
    # Replace multiple spaces, newlines, and tabs with a single space
    definition = re.sub(r"\s+", " ", definition)
    # Remove leading/trailing whitespace
    definition = definition.strip()
    # Remove any leading/trailing punctuation that might not be meaningful
    definition = definition.strip(".,;:!?()[]{}")
    return definition


def is_valid_definition(definition: str, min_length: int = 5) -> bool:
    """
    Validate a definition to ensure it is meaningful and not a placeholder.

    A valid definition must:
    - Be non-empty after cleaning.
    - Meet a minimum length requirement (default: 5 characters).
    - Not be a placeholder (e.g., "word: translation").
    - Contain at least some meaningful content (not just punctuation or numbers).

    Args:
        definition (str): The definition to validate.
        min_length (int): Minimum length for a valid definition. Defaults to 5.

    Returns:
        bool: True if the definition is valid, False otherwise.
    """
    if not definition:
        logger.debug("Definition is empty.")
        return False

    cleaned_def = clean_definition(definition)
    if not cleaned_def:
        logger.debug("Definition is empty after cleaning.")
        return False

    # Check minimum length
    if len(cleaned_def) < min_length:
        logger.debug(f"Definition too short: '{cleaned_def}' (length: {len(cleaned_def)} < {min_length})")
        return False

    # Check if the definition is a placeholder (e.g., "word: translation")
    if ": " in cleaned_def:
        parts = cleaned_def.split(": ", 1)
        if len(parts) == 2 and len(parts[1].strip()) < min_length:
            logger.debug(f"Definition is a placeholder: '{cleaned_def}'")
            return False

    # Check if the definition contains meaningful content (not just numbers/punctuation)
    if re.match(r"^[0-9.,;:!?()[\]{}\- ]+$", cleaned_def):
        logger.debug(f"Definition contains no meaningful content: '{cleaned_def}'")
        return False

    return True


def format_definition(definition: str) -> str:
    """
    Format a definition for storage by cleaning and standardizing it.

    Args:
        definition (str): The raw definition text to format.

    Returns:
        str: The formatted definition, or an empty string if invalid.
    """
    cleaned_def = clean_definition(definition)
    if not is_valid_definition(cleaned_def):
        logger.warning(f"Invalid definition after cleaning: '{definition}'")
        return ""
    # Capitalize the first letter and ensure it ends with a period
    formatted_def = cleaned_def[0].upper() + cleaned_def[1:]
    if not formatted_def.endswith("."):
        formatted_def += "."
    return formatted_def


def validate_translation_entry(
    entry: Dict[str, Union[str, List[str]]], min_length: int = 5
) -> Optional[Dict[str, Union[str, List[str]]]]:
    """
    Validate a translation entry to ensure it has a meaningful definition and valid text fields.

    Args:
        entry (Dict[str, Union[str, List[str]]]): The translation entry to validate.
            Expected keys: "ojibwe_text", "english_text", "definition".
        min_length (int): Minimum length for the definition. Defaults to 5.

    Returns:
        Optional[Dict[str, Union[str, List[str]]]]: The validated entry with a formatted definition,
            or None if the entry is invalid.
    """
    # Check required fields
    required_fields = ["ojibwe_text", "english_text", "definition"]
    for field in required_fields:
        if field not in entry:
            logger.warning(f"Missing required field '{field}' in translation entry: {entry}")
            return None

    # Validate Ojibwe text
    ojibwe_text = entry["ojibwe_text"]
    if not isinstance(ojibwe_text, str) or not ojibwe_text.strip() or len(ojibwe_text.strip()) < 2:
        logger.warning(f"Invalid Ojibwe text: '{ojibwe_text}'")
        return None

    # Validate English text
    english_text = entry["english_text"]
    if not isinstance(english_text, list) or not english_text:
        logger.warning(f"Invalid English text: '{english_text}'")
        return None
    if not all(isinstance(e, str) and e.strip() and len(e.strip()) >= 2 for e in english_text):
        logger.warning(f"Invalid English text entries: {english_text}")
        return None

    # Validate and format definition
    definition = entry["definition"]
    if not isinstance(definition, str):
        logger.warning(f"Definition must be a string: '{definition}'")
        return None
    formatted_def = format_definition(definition)
    if not formatted_def:
        logger.warning(f"Invalid definition after formatting: '{definition}'")
        return None

    # Create validated entry
    validated_entry = {
        "ojibwe_text": ojibwe_text,
        "english_text": english_text,
        "definition": formatted_def,
    }
    return validated_entry
