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

    def validate(self, data):
        """
        Validate that either custom_item_type or standard_item_type is set based on is_custom_type.
        """
        is_custom = data.get("is_custom_type", False)

        if is_custom:
            if not data.get("custom_item_type"):
                raise serializers.ValidationError(
                    "custom_item_type is required when is_custom_type is True."
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
