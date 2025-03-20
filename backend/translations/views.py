"""API views for translation gap analysis, dictionary updates, and data access."""
import requests
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
        # Get the top 1000 most common English words
        top_n = 1000
        sorted_words = sorted(WORD_FREQUENCIES.items(), key=lambda x: x[1], reverse=True)[:top_n]
        common_words = {word.lower() for word, _ in sorted_words if len(word) >= 2}  # Filter out words shorter than 2 characters

        # Get existing translations
        translations = get_all_english_to_ojibwe()
        translated_english = {t["english_text"].lower() if isinstance(t["english_text"], str) else t["english_text"][0].lower() for t in translations}

        # Identify missing common words
        missing_words = common_words - translated_english
        missing_words = sorted(missing_words, key=lambda x: WORD_FREQUENCIES.get(x, 0), reverse=True)

        # Convert to the expected format
        missing_data = [{"english_text": word} for word in missing_words]
        serializer = MissingTranslationSerializer(missing_data, many=True)
        return Response(serializer.data)
