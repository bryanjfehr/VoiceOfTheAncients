"""Unit tests for the translations backend functionality."""
from django.test import TestCase
from unittest.mock import patch
from translations.models import (
    update_or_create_english_to_ojibwe,
    update_or_create_ojibwe_to_english,
    get_all_english_to_ojibwe,
    EnglishWord,
)
from translations.utils.dict_converter import populate_english_dict, clear_english_dict


class TranslationTests(TestCase):
    """Test suite for translation-related functionality."""

    def setUp(self) -> None:
        """Set up test data before each test."""
        # Create a sample English-to-Ojibwe translation
        update_or_create_english_to_ojibwe("water", "nibi")
        # Create the corresponding Ojibwe-to-English translation
        update_or_create_ojibwe_to_english("nibi", ["water"])
        # Populate the English dictionary with a small test file
        # Assuming a test JSON file exists or mocking could be added
        populate_english_dict("translations/tests/test_english_dict.json")

    def tearDown(self) -> None:
        """Clean up test data after each test."""
        clear_english_dict()
        # Clear MongoDB collections for isolation (optional, depending on setup)
        from translations.models import english_to_ojibwe, ojibwe_to_english
        english_to_ojibwe.delete_many({})
        ojibwe_to_english.delete_many({})

    def test_gaps(self) -> None:
        """Test the get_gaps API endpoint for correct gap identification."""
        # Add an untranslated English word
        EnglishWord.objects.create(word="fire")
        response = self.client.get("/api/gaps/")
        self.assertEqual(response.status_code, 200)
        gaps = response.json()["gaps"]
        self.assertIn("fire", gaps)  # 'fire' should be untranslated
        self.assertNotIn("water", gaps)  # 'water' should be translated

    @patch("translations.views.update_dictionary")
    def test_update_dictionary(self, mock_update) -> None:
        """Test the update_dictionary API endpoint for dictionary updates."""
        mock_update.return_value = 2  # Simulate adding 2 new words
        response = self.client.get("/api/update-dictionary/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["new_words_added"], 2)

    def test_translation_creation(self) -> None:
        """Test creation and retrieval of translations."""
        # Add a new translation
        update_or_create_english_to_ojibwe("sky", "giizhig")
        translations = get_all_english_to_ojibwe()
        self.assertTrue(any(t["english_text"] == "sky" and t["ojibwe_text"] == "giizhig"
                            for t in translations))