"""API views for translation gap analysis and dictionary updates."""
from django.http import JsonResponse
from .models import Translation, EnglishWord
import requests
import json
import sqlite3


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
    # Hypothetical URL for dictionary updates (e.g., a GitHub repo or API)
    update_url = "https://example.com/websters-dictionary.json"
    try:
        response = requests.get(update_url, timeout=10)
        response.raise_for_status()
        new_dict_data = response.json()

        # Assuming new_dict_data has a version and words list
        current_version = "1.0"  # Placeholder—store in a config or database
        new_version = new_dict_data.get("version", "1.0")
        new_words = new_dict_data.get("words", [])

        if new_version > current_version:
            # Update SQLite database
            conn = sqlite3.connect("translations.db")
            cursor = conn.cursor()
            for word in new_words:
                cursor.execute(
                    "INSERT OR IGNORE INTO english_dict (word) VALUES (?)", (word,)
                )
            conn.commit()
            conn.close()

            # Update version (in a real app, store this in a config or DB)
            print(f"Updated dictionary to version {new_version}")
            return JsonResponse({"status": "success", "version": new_version})
        return JsonResponse({"status": "no update needed", "version": current_version})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
