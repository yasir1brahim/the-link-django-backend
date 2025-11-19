# apps/deliverables/serializers/extraction_note.py
from rest_framework import serializers
from apps.deliverables.models import ExtractionNote
from django.contrib.auth import get_user_model

User = get_user_model()


class ExtractionNoteSerializer(serializers.ModelSerializer):
    """Full serializer for note CRUD"""
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True,
        allow_null=True
    )
    created_by_id = serializers.IntegerField(
        source='created_by.id',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = ExtractionNote
        fields = [
            'id', 'text', 'created_by_id', 'created_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_by_id', 'created_by_name', 'created_at', 'updated_at']


class ExtractionNoteCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating notes"""
    class Meta:
        model = ExtractionNote
        fields = ['text']

    def validate_text(self, value):
        """Ensure text is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Text cannot be empty.")
        return value.strip()
