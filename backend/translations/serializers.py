# translations/serializers.py
from rest_framework import serializers


class EnglishToOjibweSerializer(serializers.Serializer):
    english_text = serializers.CharField()
    ojibwe_text = serializers.CharField()
    definition = serializers.CharField(required=False, allow_null=True)


class OjibweToEnglishSerializer(serializers.Serializer):
    ojibwe_text = serializers.CharField()
    english_text = serializers.ListField(child=serializers.CharField())
    definition = serializers.CharField(required=False, allow_null=True)


class SemanticMatchSerializer(serializers.Serializer):
    english_text = serializers.CharField()
    ojibwe_text = serializers.CharField()
    similarity = serializers.FloatField()


class MissingTranslationSerializer(serializers.Serializer):
    english_text = serializers.CharField()
