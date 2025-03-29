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
    # Add index field dynamically based on the list position
    index = serializers.SerializerMethodField()
    english_text = serializers.CharField()
    ojibwe_text = serializers.CharField()
    similarity = serializers.FloatField()
    english_definition = serializers.CharField(allow_blank=True)
    ojibwe_definition = serializers.CharField(allow_blank=True)

    def get_index(self, obj):
        """
        Generate an index for each semantic match based on its position in the list.
        This ensures compatibility with the frontend, which expects an 'index' field.
        """
        # Access the list of objects from the context
        instance_list = self.context.get('instance_list', [])
        try:
            return instance_list.index(obj)
        except ValueError:
            return 0  # Fallback in case the object isn't found

class MissingTranslationSerializer(serializers.Serializer):
    english_text = serializers.CharField()
    frequency = serializers.FloatField()  # Added frequency field
