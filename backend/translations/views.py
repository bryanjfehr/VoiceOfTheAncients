# backend/translations/views.py
"""
API views for translation gap analysis, dictionary updates, and data access.
"""
import sqlite3
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import EnglishWord, get_all_english_to_ojibwe, get_all_ojibwe_to_english
from .utils.fetch_dictionary import update_dictionary
from .serializers import (
    EnglishToOjibweSerializer,
    OjibweToEnglishSerializer,
    SemanticMatchSerializer,
    MissingTranslationSerializer,
)
from translations.utils.frequencies import WORD_FREQUENCIES
import json
import os

# Base directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class UpdateDictionaryView(APIView):
    def get(self, request):
        """API endpoint to check for and apply updates to the English dictionary.
        Fetches a new version from a remote source and updates the SQLite database.
        """
        try:
            # Use the fetch_dictionary module to update the dictionary
            new_words_count = update_dictionary()

            if new_words_count > 0:
                return Response({"status": "success", "new_words_added": new_words_count})
            return Response({"status": "no update needed", "new_words_added": 0})
        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=500)

class EnglishToOjibweListView(APIView):
    def get(self, request):
        translations = get_all_english_to_ojibwe()
        serializer = EnglishToOjibweSerializer(translations, many=True)
        return Response(serializer.data)

class OjibweToEnglishListView(APIView):
    def get(self, request):
        translations = get_all_ojibwe_to_english()
        serializer = OjibweToEnglishSerializer(translations, many=True)
        return Response(serializer.data)

class SemanticMatchesView(APIView):
    def get(self, request):
        # Load semantic matches from the last analysis
        matches_path = os.path.join(BASE_DIR, "data", "semantic_matches.json")
        try:
            with open(matches_path, "r", encoding="utf-8") as f:
                matches = json.load(f)
        except FileNotFoundError:
            matches = []
        serializer = SemanticMatchSerializer(matches, many=True)
        return Response(serializer.data)

class MissingCommonTranslationsView(APIView):
    def get(self, request):
        """Fetch all English words missing Ojibwe translations, sorted by frequency."""
        # Get all English words from SQLite
        conn = sqlite3.connect("translations.db")
        cursor = conn.cursor()
        cursor.execute("SELECT word FROM english_dict")
        english_words = {row[0].lower() for row in cursor.fetchall()}
        conn.close()

        # Get existing translations
        translations = get_all_english_to_ojibwe()
        translated_english = {
            t["english_text"].lower() if isinstance(t["english_text"], str) else t["english_text"][0].lower()
            for t in translations
        }

        # Identify missing words
        missing_words = english_words - translated_english

        # Sort by frequency
        missing_words = sorted(
            missing_words,
            key=lambda x: WORD_FREQUENCIES.get(x, 0),
            reverse=True
        )

        # Convert to the expected format
        missing_data = [{"english_text": word} for word in missing_words]
        serializer = MissingTranslationSerializer(missing_data, many=True)
        return Response(serializer.data)
