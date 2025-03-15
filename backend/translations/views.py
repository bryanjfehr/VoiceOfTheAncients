"""API views for translation gap analysis and dictionary updates."""
from django.http import JsonResponse
import requests
import sqlite3
from .models import Translation, EnglishWord
from .utils.fetch_dictionary import update_dictionary

def get_gaps(request):
    """API endpoint to identify translation gaps between English and Ojibwe.
    Returns a JSON response with a list of English words not translated.
    """
    # Load English dictionary from SQLite
    english_words = {word.word for word in EnglishWord.objects.all()}

    # Get Ojibwe translations from MongoDB
    translations = Translation.objects.all()
    translated_english = {t.english_text for t in translations if t.english_text}

    # Identify and return gaps
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
