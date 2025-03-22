# backend/translations/utils/logging_config.py
"""
Logging configuration for the Voice of the Ancients project.

This module sets up separate loggers for the scraper, analysis, and models components,
ensuring that logs are written to their respective files (scraper.log, analysis.log, models.log)
and also output to the console for debugging.
"""
import logging
import os

# Define the base directory for log file paths
# This points to backend/ (three levels up from translations/utils/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def setup_logging():
    """
    Configure logging for the application with separate loggers for each module.

    - Scraper logs go to scraper.log and stdout.
    - Analysis logs go to analysis.log and stdout.
    - Models logs go to models.log and stdout.
    All loggers are set to INFO level with a consistent format.
    """
    # Configure logger for scraper
    scraper_logger = logging.getLogger("translations.utils.ojibwe_scraper")
    scraper_handler = logging.FileHandler(os.path.join(BASE_DIR, "scraper.log"))
    scraper_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    scraper_logger.addHandler(scraper_handler)
    scraper_logger.addHandler(logging.StreamHandler())
    scraper_logger.setLevel(logging.INFO)

    # Configure logger for analysis
    analysis_logger = logging.getLogger("translations.utils.analysis")
    analysis_handler = logging.FileHandler(os.path.join(BASE_DIR, "analysis.log"))
    analysis_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    analysis_logger.addHandler(analysis_handler)
    analysis_logger.addHandler(logging.StreamHandler())
    analysis_logger.setLevel(logging.INFO)

    # Configure logger for models
    models_logger = logging.getLogger("translations.models")
    models_handler = logging.FileHandler(os.path.join(BASE_DIR, "models.log"))
    models_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    models_logger.addHandler(models_handler)
    models_logger.addHandler(logging.StreamHandler())
    models_logger.setLevel(logging.INFO)
