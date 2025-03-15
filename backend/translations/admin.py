"""Admin interface configuration for managing English words."""
from django.contrib import admin
from .models import EnglishWord

@admin.register(EnglishWord)
class EnglishWordAdmin(admin.ModelAdmin):
    """Admin class for managing EnglishWord entries."""
    list_display = ("word",)
