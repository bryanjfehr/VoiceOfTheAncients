"""Django ORM models for translation data management using MongoDB via djongo."""
from djongo import models


class Translation(models.Model):
    """Model representing a translation entry in MongoDB."""
    ojibwe_text = models.TextField()
    english_text = models.TextField(null=True, blank=True)
    audio_url = models.TextField(null=True, blank=True)
    syllabary_text = models.TextField(null=True, blank=True)
    other_lang_text = models.TextField(null=True, blank=True)

    class Meta:
        """Meta options for the Translation model."""
        db_table = "translations"

    def __str__(self) -> str:
        """String representation of the Translation object."""
        return self.ojibwe_text


class EnglishWord(models.Model):
    """Model representing an English word in SQLite."""
    word = models.TextField(primary_key=True)

    class Meta:
        """Meta options for the EnglishWord model."""
        db_table = "english_dict"

    def __str__(self) -> str:
        """String representation of the EnglishWord object."""
        return self.word
