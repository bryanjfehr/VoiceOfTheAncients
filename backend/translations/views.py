"""API views for translation gap analysis."""
from django.http import JsonResponse
import sqlite3
from .models import get_all_translations

def get_gaps(request):
    """API endpoint to identify translation gaps between English and Ojibwe.
    Returns a JSON response with a list of English words not translated.
    """
    # Load English dictionary from SQLite
    conn = sqlite3.connect("translations.db")
    cursor = conn.cursor()
    cursor.execute("SELECT word FROM english_dict")
    english_words = {row[0] for row in cursor.fetchall()}
    conn.close()

    # Get Ojibwe translations from MongoDB
    translations = get_all_translations()
    translated_english = {t["english_text"] for t in translations if t.get("english_text")}

    # Identify and return gaps
    gaps = english_words - translated_english
    return JsonResponse({"gaps": list(gaps)})
