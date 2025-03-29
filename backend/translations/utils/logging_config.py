# backend/translations/utils/logging_config.py
"""
Configure logging for the translations application.
"""
import logging
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def setup_logging():
    """Set up logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(os.path.join(LOG_DIR, "app.log")),
            logging.StreamHandler(),  # Single console handler
        ],
    )
    # Prevent duplicate logging
    logging.getLogger().propagate = False