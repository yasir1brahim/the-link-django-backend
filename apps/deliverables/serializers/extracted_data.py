from rest_framework import serializers
from apps.deliverables.models import (
    CustomItemType,
    ExtractedData,
    ExtractionItemType,
    ExtractionSource,
)
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
    custom_item_type = serializers.SerializerMethodField()

    class Meta:
        model = ExtractedData
        fields = [
            'id', 'spec_section_number', 'spec_section_name',
            'extraction_type', 'item_type', 'requirement_text',
            'responsible_party', 'metadata', 'custom_item_type',
            'source', 'source_display', 'created_by_name', 'created_at'
        ]
        read_only_fields = fields

    def get_custom_item_type(self, obj):
        if not obj.custom_item_type:
            return None
        return {
            'id': obj.custom_item_type_id,
            'name': obj.custom_item_type.name,
            'color': obj.custom_item_type.color,
        }


class ExtractedDataSerializer(serializers.ModelSerializer):
    """Full serializer for detail views and updates"""
    created_by = CustomUserSerializer(read_only=True)
    source_display = serializers.CharField(
        source='get_source_display',
        read_only=True
    )
    custom_item_type = serializers.SerializerMethodField()
    custom_item_type_id = serializers.PrimaryKeyRelatedField(
        source='custom_item_type',
        queryset=CustomItemType.objects.filter(is_active=True),
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = ExtractedData
        fields = [
            'id', 'ai_generated_log', 'spec_section_number',
            'spec_section_name', 'extraction_type', 'item_type',
            'requirement_text', 'responsible_party', 'metadata',
            'pdf_locations', 'paragraph_number',
            'custom_item_type', 'custom_item_type_id',
            'source', 'source_display', 'created_by',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'ai_generated_log', 'spec_section_number',
            'spec_section_name', 'extraction_type', 'item_type',
            'requirement_text', 'responsible_party', 'metadata',
            'pdf_locations', 'paragraph_number',
            'custom_item_type',
            'source', 'created_by', 'created_at', 'updated_at'
        ]

    def get_custom_item_type(self, obj):
        if not obj.custom_item_type:
            return None
        return {
            'id': obj.custom_item_type_id,
            'name': obj.custom_item_type.name,
            'color': obj.custom_item_type.color,
            'description': obj.custom_item_type.description,
        }

    def validate(self, attrs):
        custom_type = attrs.get('custom_item_type')
        extraction_type = attrs.get('extraction_type')

        if custom_type:
            attrs['extraction_type'] = 'custom_highlights'
        elif extraction_type == 'custom_highlights':
            raise serializers.ValidationError({
                'custom_item_type_id': 'Custom item type is required when extraction_type is "custom_highlights".'
            })

        return super().validate(attrs)


class ExtractedDataCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new ExtractedData (human-sourced via Apryse highlights)"""
    custom_item_type_id = serializers.PrimaryKeyRelatedField(
        source='custom_item_type',
        queryset=CustomItemType.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = ExtractedData
        fields = [
            'project', 'project_version', 'spec_section',
            'spec_section_number', 'spec_section_name',
            'extraction_type', 'item_type', 'paragraph_number',
            'requirement_text', 'responsible_party', 'metadata',
            'pdf_locations', 'custom_item_type_id'
        ]

    def create(self, validated_data):
        """Set created_by and source from request context"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user

        # Always HUMAN source for manual creation
        validated_data['source'] = ExtractionSource.HUMAN

        return super().create(validated_data)

    def validate(self, attrs):
        if attrs.get('custom_item_type'):
            attrs['extraction_type'] = 'custom_highlights'
        return super().validate(attrs)
