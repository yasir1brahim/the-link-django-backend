from django.core.validators import RegexValidator
from rest_framework import serializers

from apps.deliverables.models import UserHighlightPreference, CustomItemType


class UserHighlightPreferenceSerializer(serializers.ModelSerializer):
    """
    Serializer for reading and writing user's last used highlight type preference.
    """

    class Meta:
        model = UserHighlightPreference
        fields = [
            "id",
            "is_custom_type",
            "custom_item_type",
            "standard_item_type",
            "extraction_type",
            "type_display_name",
            "type_color",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_type_color(self, value):
        """Validate that type_color is in HEX format (#RRGGBB)."""
        validator = RegexValidator(
            regex=r"^#[0-9A-Fa-f]{6}$",
            message="Color must be in HEX format (#RRGGBB).",
        )
        validator(value)
        return value.upper()

    def validate(self, data):
        """
        Validate that either custom_item_type or standard_item_type is set based on is_custom_type.
        Also validates that custom_item_type belongs to the correct project and is active.
        """
        is_custom = data.get("is_custom_type", False)

        if is_custom:
            custom_item_type = data.get("custom_item_type")
            if not custom_item_type:
                raise serializers.ValidationError(
                    "custom_item_type is required when is_custom_type is True."
                )
            # Validate custom_item_type belongs to the correct project
            project = self.context.get("project")
            if project and custom_item_type.project_id != project.id:
                raise serializers.ValidationError(
                    "custom_item_type must belong to the same project."
                )
            # Validate custom_item_type is active
            if not custom_item_type.is_active:
                raise serializers.ValidationError(
                    "custom_item_type must be active."
                )
        else:
            if not data.get("standard_item_type"):
                raise serializers.ValidationError(
                    "standard_item_type is required when is_custom_type is False."
                )

        return data

    def create(self, validated_data):
        """
        Create or update the user's highlight preference (upsert behavior).
        Only one preference per user per project should exist.
        """
        request = self.context["request"]
        project = self.context["project"]

        # Use update_or_create to implement upsert behavior
        preference, created = UserHighlightPreference.objects.update_or_create(
            user=request.user,
            project=project,
            defaults=validated_data
        )

        return preference

    def update(self, instance, validated_data):
        """
        Update the existing preference.
        """
        return super().update(instance, validated_data)
