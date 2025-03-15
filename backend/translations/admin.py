"""Admin interface configuration for managing translations."""
from django.contrib import admin
from .models import get_all_translations  # No ORM, so we use utility

# Custom admin view to display translations
@admin.register(lambda: None)  # Placeholder due to no ORM model
class TranslationAdmin(admin.ModelAdmin):
    """Custom admin class to manage translations manually."""

    def get_queryset(self, request):
        """Return a queryset of all translations."""
        return get_all_translations()

    list_display = ("ojibwe_text", "english_text", "audio_url")  # Columns to display
