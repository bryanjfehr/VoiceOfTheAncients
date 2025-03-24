# backend/translations/utils/definition_utils.py
"""
Utility module for analyzing, formatting, and validating definitions.

Ensures definitions are meaningful and suitable for storage, with detailed logging.
"""
import logging
import re
from typing import Optional, List, Dict, Union

logger = logging.getLogger("translations.utils.definition_utils")

def clean_definition(definition: str) -> str:
    """Clean definition by removing unwanted characters and standardizing format."""
    if not definition:
        return ""
    definition = re.sub(r"<[^>]+>", "", definition)  # Remove HTML tags
    definition = re.sub(r"\s+", " ", definition)    # Normalize whitespace
    definition = definition.strip()                 # Remove leading/trailing whitespace
    definition = definition.strip(".,;:!?()[]{}")   # Remove edge punctuation
    return definition

def is_valid_definition(definition: str, min_length: int = 5) -> bool:
    """
    Validate a definition for meaningful content.

    Ensures non-empty, sufficient length, not a placeholder, and contains letters.
    """
    if not definition:
        logger.debug("Definition is empty.")
        return False

    cleaned_def = clean_definition(definition)
    if not cleaned_def:
        logger.debug("Definition empty after cleaning.")
        return False

    if len(cleaned_def) < min_length:
        logger.debug(f"Definition too short: '{cleaned_def}' (len: {len(cleaned_def)} < {min_length})")
        return False

    if ": " in cleaned_def and len(cleaned_def.split(": ", 1)[1].strip()) < min_length:
        logger.debug(f"Placeholder definition: '{cleaned_def}'")
        return False

    if re.match(r"^[0-9.,;:!?()[\]{}\- ]+$", cleaned_def):
        logger.debug(f"No meaningful content: '{cleaned_def}'")
        return False

    return True

def format_definition(definition: str) -> str:
    """Format definition for storage, capitalizing and adding a period."""
    cleaned_def = clean_definition(definition)
    if not is_valid_definition(cleaned_def):
        logger.warning(f"Invalid definition: '{definition}'")
        return ""
    formatted_def = cleaned_def[0].upper() + cleaned_def[1:]
    if not formatted_def.endswith("."):
        formatted_def += "."
    return formatted_def

def validate_translation_entry(
    entry: Dict[str, Union[str, List[str]]], min_length: int = 5
) -> Optional[Dict[str, Union[str, List[str]]]]:
    """Validate a translation entry, ensuring all fields are valid."""
    required_fields = ["ojibwe_text", "english_text", "definition"]
    for field in required_fields:
        if field not in entry:
            logger.warning(f"Missing field '{field}': {entry}")
            return None

    ojibwe_text = entry["ojibwe_text"]
    if not isinstance(ojibwe_text, str) or not ojibwe_text.strip() or len(ojibwe_text.strip()) < 2:
        logger.warning(f"Invalid Ojibwe text: '{ojibwe_text}'")
        return None

    english_text = entry["english_text"]
    if not isinstance(english_text, list) or not english_text or not all(
        isinstance(e, str) and e.strip() and len(e.strip()) >= 2 for e in english_text
    ):
        logger.warning(f"Invalid English text: {english_text}")
        return None

    definition = entry["definition"]
    if not isinstance(definition, str):
        logger.warning(f"Definition not a string: '{definition}'")
        return None
    formatted_def = format_definition(definition)
    if not formatted_def:
        logger.warning(f"Invalid definition: '{definition}'")
        return None

    return {
        "ojibwe_text": ojibwe_text,
        "english_text": english_text,
        "definition": formatted_def,
    }
