# backend/translations/serializers.py
from rest_framework import serializers

class EnglishToOjibweSerializer(serializers.Serializer):
    english_text = serializers.CharField()
    ojibwe_text = serializers.CharField()
    definition = serializers.CharField(allow_blank=True, required=False)

class OjibweToEnglishSerializer(serializers.Serializer):
    ojibwe_text = serializers.CharField()
    english_text = serializers.ListField(child=serializers.CharField())

class SemanticMatchSerializer(serializers.Serializer):
    index = serializers.IntegerField()
    english_text = serializers.CharField()
    ojibwe_text = serializers.CharField()
    similarity = serializers.FloatField()
    english_definition = serializers.CharField(allow_blank=True)
    ojibwe_definition = serializers.CharField(allow_blank=True)

class MissingTranslationSerializer(serializers.Serializer):
    english_text = serializers.CharField()