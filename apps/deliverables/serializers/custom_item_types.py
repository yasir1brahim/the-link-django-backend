from django.core.validators import RegexValidator
from rest_framework import serializers

from apps.deliverables.models import CustomItemType, ExtractedData


class CustomItemTypeListSerializer(serializers.ModelSerializer):
    extracted_data_count = serializers.IntegerField(read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.get_full_name",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = CustomItemType
        fields = [
            "id",
            "name",
            "color",
            "description",
            "extracted_data_count",
            "created_by_name",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class CustomItemTypeDetailSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    project = serializers.SerializerMethodField()
    extracted_data_count = serializers.SerializerMethodField()
    recent_extracted_data = serializers.SerializerMethodField()

    class Meta:
        model = CustomItemType
        fields = [
            "id",
            "name",
            "color",
            "description",
            "project",
            "created_by",
            "created_at",
            "updated_at",
            "is_active",
            "extracted_data_count",
            "recent_extracted_data",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "project", "created_by"]

    def get_created_by(self, obj):
        if not obj.created_by:
            return None
        return {
            "id": obj.created_by.id,
            "name": obj.created_by.get_full_name(),
            "email": obj.created_by.email,
        }

    def get_project(self, obj):
        return {
            "id": obj.project_id,
            "project_number": obj.project.project_number,
            "name": obj.project.name,
        }

    def get_extracted_data_count(self, obj):
        return obj.extracted_data_items.count()

    def get_recent_extracted_data(self, obj):
        recent_items = (
            obj.extracted_data_items.order_by("-created_at")
            .values("id", "spec_section_number", "requirement_text", "created_at")[:5]
        )
        results = []
        for item in recent_items:
            snippet = item["requirement_text"]
            if snippet and len(snippet) > 120:
                snippet = f"{snippet[:117]}..."
            results.append(
                {
                    "id": item["id"],
                    "spec_section_number": item["spec_section_number"],
                    "requirement_text": snippet,
                    "created_at": item["created_at"],
                }
            )
        return results


class CustomItemTypeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomItemType
        fields = ["name", "color", "description", "is_active"]
        read_only_fields = ["is_active"]

    def validate_name(self, value):
        project = self.context.get("project")
        if not project:
            raise serializers.ValidationError("Project context is required.")

        queryset = CustomItemType.objects.filter(
            project=project,
            name__iexact=value.strip(),
        )
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError(
                f"A custom item type named '{value}' already exists for this project."
            )
        return value

    def validate_color(self, value):
        validator = RegexValidator(
            regex=r"^#[0-9A-Fa-f]{6}$",
            message="Color must be in HEX format (#RRGGBB).",
        )
        validator(value)
        return value.upper()

    def create(self, validated_data):
        request = self.context["request"]
        project = self.context["project"]
        validated_data["project"] = project
        validated_data["created_by"] = request.user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("is_active", None)
        color = validated_data.get("color")
        if color:
            validated_data["color"] = color.upper()
        return super().update(instance, validated_data)

