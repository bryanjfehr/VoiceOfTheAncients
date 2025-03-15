"""Unit tests for the translations backend functionality."""
from django.test import TestCase
from .models import Translation, EnglishWord
from .utils.dict_converter import populate_english_dict, clear_english_dict


class TranslationTests(TestCase):
    """Test suite for translation-related functionality."""

    def setUp(self):
        """Set up test data before each test."""
        Translation.objects.create(ojibwe_text="nibi", english_text="water")
        populate_english_dict("../data/english_dict.json")

    def tearDown(self):
        """Clean up test data after each test."""
        clear_english_dict()

    def test_gaps(self):
        """Test the get_gaps API endpoint for correct gap identification."""
        EnglishWord.objects.create(word="fire")
        response = self.client.get("/api/gaps/")
        self.assertEqual(response.status_code, 200)
        gaps = response.json()["gaps"]
        self.assertIn("fire", gaps)  # 'fire' untranslated
        self.assertNotIn("water", gaps)  # 'water' translated

    def test_update_dictionary(self):
        """Test the update_dictionary API endpoint for dictionary updates."""
        response = self.client.get("/api/update-dictionary/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)