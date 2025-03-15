"""Unit tests for the translations backend functionality."""
from django.test import TestCase
from .models import create_translation, get_all_translations
import sqlite3

class TranslationTests(TestCase):
    """Test suite for translation-related functionality."""

    def setUp(self):
        """Set up test data before each test."""
        create_translation(ojibwe_text="nibi", english_text="water")
        conn = sqlite3.connect("translations.db")
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO english_dict (word) VALUES (?)", ("water",))
        cursor.execute("INSERT OR IGNORE INTO english_dict (word) VALUES (?)", ("fire",))
        conn.commit()
        conn.close()

    def test_gaps(self):
        """Test the get_gaps API endpoint for correct gap identification."""
        response = self.client.get("/api/gaps/")
        self.assertEqual(response.status_code, 200)
        gaps = response.json()["gaps"]
        self.assertIn("fire", gaps)  # 'fire' should be in gaps (untranslated)
        self.assertNotIn("water", gaps)  # 'water' should not be in gaps (translated)
