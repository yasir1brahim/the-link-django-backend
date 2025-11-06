from rest_framework import serializers
from apps.deliverables.models import ExtractedData, ExtractionItemType, ExtractionSource
from apps.users.serializers import CustomUserSerializer
from django.contrib.auth import get_user_model

User = get_user_model()

class ExtractedDataListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views"""
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True,
        allow_null=True
    )
    source_display = serializers.CharField(
        source='get_source_display',
        read_only=True
    )

    class Meta:
        model = ExtractedData
        fields = [
            'id', 'spec_section_number', 'spec_section_name',
            'extraction_type', 'item_type', 'requirement_text',
            'responsible_party', 'metadata',
            'source', 'source_display', 'created_by_name', 'created_at'
        ]
        read_only_fields = fields


class ExtractedDataSerializer(serializers.ModelSerializer):
    """Full serializer for detail views and updates"""
    created_by = CustomUserSerializer(read_only=True)
    source_display = serializers.CharField(
        source='get_source_display',
        read_only=True
    )

    class Meta:
        model = ExtractedData
        fields = [
            'id', 'ai_generated_log', 'spec_section_number',
            'spec_section_name', 'extraction_type', 'item_type',
            'requirement_text', 'responsible_party', 'metadata',
            'pdf_locations', 'paragraph_number',
            'source', 'source_display', 'created_by',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'ai_generated_log', 'spec_section_number',
            'spec_section_name', 'extraction_type', 'item_type',
            'requirement_text', 'responsible_party', 'metadata',
            'pdf_locations', 'paragraph_number',
            'source', 'created_by', 'created_at', 'updated_at'
        ]


class ExtractedDataCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new ExtractedData (human-sourced via Apryse highlights)"""

    class Meta:
        model = ExtractedData
        fields = [
            'project', 'project_version', 'spec_section',
            'spec_section_number', 'spec_section_name',
            'extraction_type', 'item_type', 'paragraph_number',
            'requirement_text', 'responsible_party', 'metadata',
            'pdf_locations'
        ]

    def create(self, validated_data):
        """Set created_by and source from request context"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user

        # Always HUMAN source for manual creation
        validated_data['source'] = ExtractionSource.HUMAN

        return super().create(validated_data)
