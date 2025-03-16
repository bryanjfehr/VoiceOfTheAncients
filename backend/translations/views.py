"""API views for translation gap analysis and dictionary updates."""
from django.http import JsonResponse
import requests
import sqlite3
from .models import Translation, EnglishWord
from .utils.fetch_dictionary import update_dictionary

from .models import get_all_english_to_ojibwe

def get_gaps(request):
    english_words = {word.word for word in EnglishWord.objects.all()}
    translations = get_all_english_to_ojibwe()
    translated_english = {t["english_text"] if isinstance(t["english_text"], str) else t["english_text"][0] for t in translations}
    gaps = english_words - translated_english
    return JsonResponse({"gaps": list(gaps)})

def update_dictionary(request):
    """API endpoint to check for and apply updates to the English dictionary.
    Fetches a new version from a remote source and updates the SQLite database.
    """
    try:
        # Use the fetch_dictionary module to update the dictionary
        new_words_count = update_dictionary()

        if new_words_count > 0:
            return JsonResponse({"status": "success", "new_words_added": new_words_count})
        return JsonResponse({"status": "no update needed", "new_words_added": 0})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
