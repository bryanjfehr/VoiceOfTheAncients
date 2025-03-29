# backend/translations/views.py
"""
API views for translation gap analysis, dictionary updates, and data access.

Fetches data directly from Firestore for all endpoints to ensure consistency
when deployed online (e.g., on GKE).
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import (
    EnglishWord,
    get_all_english_to_ojibwe,
    get_all_ojibwe_to_english,
    get_all_semantic_matches,
    get_all_missing_translations,
)
from .utils.fetch_dictionary import update_dictionary
from .serializers import (
    EnglishToOjibweSerializer,
    OjibweToEnglishSerializer,
    SemanticMatchSerializer,
    MissingTranslationSerializer,
)
from translations.utils.frequencies import WORD_FREQUENCIES

class UpdateDictionaryView(APIView):
    def get(self, request):
        """
        API endpoint to check for and apply updates to the English dictionary.
        Fetches a new version from a remote source and updates the SQLite database,
        which is then synced to Firestore.
        """
        try:
            new_words_count = update_dictionary()
            if new_words_count > 0:
                return Response({"status": "success", "new_words_added": new_words_count})
            return Response({"status": "no update needed", "new_words_added": 0})
        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=500)

class EnglishToOjibweListView(APIView):
    def get(self, request):
        """
        Fetch all English-to-Ojibwe translations directly from Firestore.
        """
        translations = get_all_english_to_ojibwe()
        serializer = EnglishToOjibweSerializer(translations, many=True)
        return Response(serializer.data)

class OjibweToEnglishListView(APIView):
    def get(self, request):
        """
        Fetch all Ojibwe-to-English translations directly from Firestore.
        """
        translations = get_all_ojibwe_to_english()
        serializer = OjibweToEnglishSerializer(translations, many=True)
        return Response(serializer.data)

class SemanticMatchesView(APIView):
    def get(self, request):
        """
        Fetch all semantic matches directly from Firestore.
        """
        matches = get_all_semantic_matches()
        # Pass the list of matches to the serializer context for index generation
        serializer = SemanticMatchSerializer(
            matches,
            many=True,
            context={'instance_list': matches}
        )
        return Response(serializer.data)

class MissingCommonTranslationsView(APIView):
    def get(self, request):
        """
        Fetch all English words missing Ojibwe translations from Firestore,
        sorted by frequency, and include their usage frequency.
        """
        try:
            # Fetch missing translations from Firestore
            missing = get_all_missing_translations()
            if not missing:
                return Response([])  # Return empty list if no missing translations

            # Prepare data with frequency
            missing_data = [
                {
                    "english_text": m["english_text"],
                    "frequency": m.get("frequency", 0.0)  # Ensure frequency is included
                }
                for m in missing
            ]

            # Sort by frequency (descending)
            missing_data.sort(key=lambda x: x["frequency"], reverse=True)

            serializer = MissingTranslationSerializer(missing_data, many=True)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {"status": "error", "message": f"Error fetching missing translations: {str(e)}"},
                status=500
            )
