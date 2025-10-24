# apps/specs/serializers.py
from rest_framework import serializers
from apps.deliverables.models import PDFAnnotation

class PDFAnnotationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PDFAnnotation
        fields = [
            "id",
            "annotation_id",
            "project",
            "project_version",
            "spec_section",
            "user",
            "page_number",
            "color",
            "quads",
            "xfdf_data",
            "tag",
            "created_at",
            "updated_at",

        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            validated_data["user"] = request.user
        return super().create(validated_data)
