"""Admin interface configuration for managing translations and English words."""
from django.contrib import admin
from .models import Translation, EnglishWord


@admin.register(Translation)
class TranslationAdmin(admin.ModelAdmin):
    """Admin class for managing Translation entries."""
    list_display = ("ojibwe_text", "english_text", "audio_url")


@admin.register(EnglishWord)
class EnglishWordAdmin(admin.ModelAdmin):
    """Admin class for managing EnglishWord entries."""
    list_display = ("word",)
