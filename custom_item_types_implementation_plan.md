# Custom Item Types Implementation Plan (Deliverables App Alignment)

## Overview
This plan introduces project-scoped, color-coded custom item types that can be associated with `ExtractedData` records managed by the Deliverables app. The work stays consistent with the existing Django module layout under `apps/deliverables`, reuses the current permission model, and keeps the saved data model (`requirement_text`, spec metadata, etc.) intact. When an `ExtractedData` row is attached to a custom item type, its `extraction_type` must become `custom_highlights`, and cross-project contamination must be prevented.

## Current Architecture Snapshot
- Models live in `apps/deliverables/models.py` and already import `settings` plus `BaseModel`.
- REST serializers for these models are in `apps/deliverables/serializers/`.
- API viewsets are registered in `apps/deliverables/views/` and routed through `apps/deliverables/urls.py`, which is mounted at `/api/deliverables/…` from the project-level `the_link/urls.py`.
- `ExtractedData` requires `project`, `project_version`, `spec_section_number`, `spec_section_name`, and `requirement_text`. It currently overrides `save` only to populate `created_by` for AI-sourced entries.
- `Project` exposes `name` and `project_number` (not `project_code`/`project_name`), so serializers/docstrings must reference the real fields.

## High-Level Steps
1. Extend the Deliverables model layer with `CustomItemType`.
2. Add optional `custom_item_type` foreign keys and validation hooks to `ExtractedData`.
3. Provide serializers dedicated to listing/managing custom item types.
4. Add a project-scoped `CustomItemTypeViewSet`, bulk assign helpers, and a palette endpoint.
5. Surface custom type metadata through existing `ExtractedData` serializers.
6. Register URLs within the Deliverables routers.
7. Generate and apply migrations (`deliverables` app label).
8. Ship model, API, and integration tests under `apps/deliverables/tests/`.
9. Publish developer-facing API docs that reference `/api/deliverables/projects/{project_id}/…`.
10. Run verification steps (migrations, tests, smoke checks).

Each task below details file locations, code snippets, and validation notes that match the actual codebase.

---

## Task 1 · Model: `CustomItemType`

**File:** `/Users/averypawelek/the-link/the_link_django/apps/deliverables/models.py`

1. Add missing import(s) near the top if they are not already present:
   ```python
   from django.core.validators import RegexValidator
   from django.core.exceptions import ValidationError  # Needed in later tasks
   ```

2. Append the `CustomItemType` definition immediately after `ExtractedData` (before the PDF annotation region) so it shares the deliverables namespace:
   ```python
   class CustomItemType(models.Model):
       """
       Project-scoped, user-created tags for grouping ExtractedData entries.
       """
       id = models.BigAutoField(primary_key=True)
       name = models.CharField(
           max_length=100,
           help_text="Readable label (e.g. 'Safety Requirements')."
       )
       color = models.CharField(
           max_length=7,
           default="#3B82F6",
           validators=[
               RegexValidator(
                   regex=r"^#[0-9A-Fa-f]{6}$",
                   message="Color must be in HEX format (#RRGGBB)."
               )
           ],
           help_text="HEX code used by the frontend for highlight color."
       )
       description = models.TextField(
           blank=True,
           default="",
           help_text="Optional explanation of how this tag should be used."
       )
       project = models.ForeignKey(
           "Project",
           on_delete=models.CASCADE,
           related_name="custom_item_types",
           help_text="Owning project."
       )
       created_by = models.ForeignKey(
           settings.AUTH_USER_MODEL,
           on_delete=models.SET_NULL,
           null=True,
           related_name="created_custom_item_types",
           help_text="User who defined this custom type."
       )
       is_active = models.BooleanField(
           default=True,
           help_text="Soft-delete flag so we can hide a type without losing history."
       )
       created_at = models.DateTimeField(auto_now_add=True)
       updated_at = models.DateTimeField(auto_now=True)

       class Meta:
           db_table = "deliverables_custom_item_type"
           ordering = ["name"]
           constraints = [
               models.UniqueConstraint(
                   fields=["project", "name"],
                   name="unique_custom_item_type_per_project"
               )
           ]
           indexes = [
               models.Index(fields=["project", "is_active"]),
               models.Index(fields=["created_by"]),
           ]

       def __str__(self) -> str:
           project_label = self.project.project_number or self.project.name
           return f"{self.name} ({project_label})"
   ```

3. Add `CustomItemType` to `apps/deliverables/__init__.py` and `apps/deliverables/admin.py` if you want admin visibility (optional but recommended; note in later section).

---

## Task 2 · Model Changes: `ExtractedData`

**File:** `/Users/averypawelek/the-link/the_link_django/apps/deliverables/models.py`

1. Add the `custom_item_type` FK near other relational fields:
   ```python
       custom_item_type = models.ForeignKey(
           "CustomItemType",
           on_delete=models.SET_NULL,
           null=True,
           blank=True,
           related_name="extracted_data_items",
           help_text="User-defined grouping (only valid for custom highlights)."
       )
   ```
   Place it after `project_version`/`spec_section` for readability.

2. Add a helper to ensure cross-project consistency:
   ```python
       def validate_custom_highlight_consistency(self):
           """
           Ensure custom tags belong to the same project as the extraction.
           """
           if self.custom_item_type and self.custom_item_type.project_id != self.project_id:
               raise ValidationError(
                   {"custom_item_type": "Custom item type must belong to the same project."}
               )
   ```

3. Override `clean` to enforce the coupling between `custom_item_type` and `extraction_type`:
   ```python
       def clean(self):
           super().clean()

           if self.custom_item_type and self.extraction_type != "custom_highlights":
               raise ValidationError({
                   "custom_item_type": 'When custom_item_type is set, extraction_type must be "custom_highlights".'
               })

           if self.extraction_type == "custom_highlights" and not self.custom_item_type:
               raise ValidationError({
                   "custom_item_type": 'Extraction type "custom_highlights" requires a custom_item_type.'
               })
   ```

4. Expand the existing `save` override while keeping the AI logic:
   ```python
       def save(self, *args, **kwargs):
           if self.custom_item_type:
               self.extraction_type = "custom_highlights"

           self.validate_custom_highlight_consistency()

           if self.source == ExtractionSource.AI and not self.created_by_id:
               if self.ai_generated_log and hasattr(self.ai_generated_log, "created_by"):
                   self.created_by = self.ai_generated_log.created_by

           super().save(*args, **kwargs)
   ```
   *Note:* We deliberately avoid calling `full_clean()` on every save to preserve existing behaviour; cross-field rules are enforced via `clean()`/assignment endpoints/tests.

5. Update `__all__` or import exports if `CustomItemType` should be re-exported elsewhere (e.g. `apps/deliverables/__init__.py`).

---

## Task 3 · Serializer Module for Custom Item Types

**File (new):** `/Users/averypawelek/the-link/the_link_django/apps/deliverables/serializers/custom_item_types.py`

```python
from rest_framework import serializers

from apps.deliverables.models import CustomItemType, ExtractedData


class CustomItemTypeListSerializer(serializers.ModelSerializer):
    extracted_data_count = serializers.IntegerField(read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.get_full_name",
        read_only=True,
        allow_null=True
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
        data = []
        for item in recent_items:
            snippet = item["requirement_text"]
            if snippet and len(snippet) > 120:
                snippet = f"{snippet[:117]}..."
            data.append(
                {
                    "id": item["id"],
                    "spec_section_number": item["spec_section_number"],
                    "requirement_text": snippet,
                    "created_at": item["created_at"],
                }
            )
        return data


class CustomItemTypeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomItemType
        fields = ["name", "color", "description", "is_active"]
        read_only_fields = ["is_active"]  # toggled via DELETE soft-delete

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
        normalized = value.upper()
        RegexValidator(
            regex=r"^#[0-9A-F]{6}$",
            message="Color must be in HEX format (#RRGGBB).",
        )(normalized)
        return normalized

    def create(self, validated_data):
        request = self.context["request"]
        project = self.context["project"]
        validated_data["project"] = project
        validated_data["created_by"] = request.user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Prevent accidental reactivation via PATCH; require dedicated endpoint if needed.
        validated_data.pop("is_active", None)
        return super().update(instance, validated_data)
```

Add the module to `apps/deliverables/serializers/__init__.py` so it can be imported via package shortcuts.

---

## Task 4 · Expose Custom Types Through ExtractedData Serializers

**File:** `/Users/averypawelek/the-link/the_link_django/apps/deliverables/serializers/extracted_data.py`

1. Update imports:
   ```python
   from apps.deliverables.models import ExtractedData, ExtractionItemType, ExtractionSource, CustomItemType
   ```

2. `ExtractedDataListSerializer` additions:
   ```python
   class ExtractedDataListSerializer(serializers.ModelSerializer):
       custom_item_type = serializers.SerializerMethodField()
       ...
       class Meta:
           fields = [
               "id",
               "spec_section_number",
               "spec_section_name",
               "extraction_type",
               "item_type",
               "requirement_text",
               "responsible_party",
               "metadata",
               "custom_item_type",
               "source",
               "source_display",
               "created_by_name",
               "created_at",
           ]

       def get_custom_item_type(self, obj):
           if not obj.custom_item_type:
               return None
           return {
               "id": obj.custom_item_type_id,
               "name": obj.custom_item_type.name,
               "color": obj.custom_item_type.color,
           }
   ```

3. `ExtractedDataSerializer` updates (detail view):
   ```python
   class ExtractedDataSerializer(serializers.ModelSerializer):
       custom_item_type = serializers.SerializerMethodField()
       custom_item_type_id = serializers.PrimaryKeyRelatedField(
           source="custom_item_type",
           queryset=CustomItemType.objects.filter(is_active=True),
           write_only=True,
           required=False,
           allow_null=True,
       )
       ...
       class Meta:
           fields = [
               "id",
               "ai_generated_log",
               "spec_section_number",
               "spec_section_name",
               "extraction_type",
               "item_type",
               "requirement_text",
               "responsible_party",
               "metadata",
               "pdf_locations",
               "paragraph_number",
               "custom_item_type",
               "custom_item_type_id",
               "source",
               "source_display",
               "created_by",
               "created_at",
               "updated_at",
           ]
           read_only_fields = [
               "id",
               "ai_generated_log",
               "spec_section_number",
               "spec_section_name",
               "requirement_text",
               "responsible_party",
               "metadata",
               "pdf_locations",
               "paragraph_number",
               "custom_item_type",
               "source",
               "source_display",
               "created_by",
               "created_at",
               "updated_at",
           ]

       def get_custom_item_type(self, obj):
           if not obj.custom_item_type:
               return None
           return {
               "id": obj.custom_item_type_id,
               "name": obj.custom_item_type.name,
               "color": obj.custom_item_type.color,
               "description": obj.custom_item_type.description,
           }

       def validate(self, attrs):
           custom_type = attrs.get("custom_item_type")
           extraction_type = attrs.get("extraction_type")
           if custom_type:
               attrs["extraction_type"] = "custom_highlights"
           elif extraction_type == "custom_highlights":
               raise serializers.ValidationError(
                   {"custom_item_type_id": "Custom item type is required when extraction_type is custom_highlights."}
               )
           return super().validate(attrs)
   ```

4. `ExtractedDataCreateSerializer` (manual highlights):
   ```python
   class ExtractedDataCreateSerializer(serializers.ModelSerializer):
       custom_item_type_id = serializers.PrimaryKeyRelatedField(
           source="custom_item_type",
           queryset=CustomItemType.objects.filter(is_active=True),
           required=False,
           allow_null=True,
       )
       class Meta:
           fields = [
               "project",
               "project_version",
               "spec_section",
               "spec_section_number",
               "spec_section_name",
               "extraction_type",
               "item_type",
               "paragraph_number",
               "requirement_text",
               "responsible_party",
               "metadata",
               "pdf_locations",
               "custom_item_type_id",
           ]

       def validate(self, attrs):
           if attrs.get("custom_item_type"):
               attrs["extraction_type"] = "custom_highlights"
           return super().validate(attrs)
   ```

---

## Task 5 · ViewSet & API

**File (new):** `/Users/averypawelek/the-link/the_link_django/apps/deliverables/views/custom_item_type_views.py`

```python
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.deliverables.models import CustomItemType, ExtractedData, Project
from apps.deliverables.permissions import ProjectAccessPermissions
from apps.deliverables.serializers.custom_item_types import (
    CustomItemTypeCreateSerializer,
    CustomItemTypeDetailSerializer,
    CustomItemTypeListSerializer,
)


class CustomItemTypeViewSet(viewsets.ModelViewSet):
    """
    Nested under /api/deliverables/projects/<project_id>/custom-item-types/.
    Provides list/create/detail/update (soft-delete on destroy) plus custom actions.
    """

    permission_classes = [IsAuthenticated, ProjectAccessPermissions]

    def get_queryset(self):
        project_id = self.kwargs["project_pk"]
        qs = CustomItemType.objects.filter(project_id=project_id, is_active=True)
        if self.action == "list":
            qs = qs.annotate(
                extracted_data_count=Count(
                    "extracted_data_items",
                    filter=Q(extracted_data_items__project_id=project_id),
                )
            ).select_related("created_by")
        elif self.action in {"retrieve", "update", "partial_update"}:
            qs = qs.select_related("project", "created_by")
        return qs.order_by("name")

    def get_serializer_class(self):
        if self.action == "list":
            return CustomItemTypeListSerializer
        if self.action == "retrieve":
            return CustomItemTypeDetailSerializer
        if self.action in {"create", "update", "partial_update"}:
            return CustomItemTypeCreateSerializer
        return CustomItemTypeDetailSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        project_id = self.kwargs.get("project_pk")
        if project_id:
            context["project"] = get_object_or_404(Project, pk=project_id)
        return context

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    @action(detail=True, methods=["post"])
    def assign_to_extracted_data(self, request, project_pk=None, pk=None):
        extracted_ids = request.data.get("extracted_data_ids")
        if not extracted_ids:
            return Response(
                {"detail": "extracted_data_ids is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = ExtractedData.objects.filter(
            id__in=extracted_ids,
            project_id=project_pk,
        )
        if queryset.count() != len(extracted_ids):
            return Response(
                {"detail": "One or more ExtractedData ids are invalid for this project."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        custom_type = self.get_object()
        with transaction.atomic():
            updated = queryset.update(
                custom_item_type=custom_type,
                extraction_type="custom_highlights",
            )

        return Response(
            {
                "message": f"Assigned custom type to {updated} items.",
                "updated_count": updated,
            }
        )

    @action(detail=True, methods=["get"])
    def extracted_data(self, request, project_pk=None, pk=None):
        custom_type = self.get_object()
        queryset = (
            ExtractedData.objects.filter(custom_item_type=custom_type, project_id=project_pk)
            .select_related("created_by")
            .order_by("-created_at")
        )

        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(requirement_text__icontains=search)

        page = self.paginate_queryset(queryset)
        if page is not None:
            return self.get_paginated_response(
                [
                    {
                        "id": item.id,
                        "spec_section_number": item.spec_section_number,
                        "requirement_text": item.requirement_text,
                        "created_by": item.created_by.get_full_name() if item.created_by else None,
                        "created_at": item.created_at,
                    }
                    for item in page
                ]
            )

        data = [
            {
                "id": item.id,
                "spec_section_number": item.spec_section_number,
                "requirement_text": item.requirement_text,
                "created_by": item.created_by.get_full_name() if item.created_by else None,
                "created_at": item.created_at,
            }
            for item in queryset
        ]
        return Response({"results": data, "count": len(data)})

    @action(detail=False, methods=["get"])
    def color_palette(self, request, project_pk=None):
        palette = [
            "#EF4444",
            "#F97316",
            "#F59E0B",
            "#EAB308",
            "#84CC16",
            "#22C55E",
            "#10B981",
            "#14B8A6",
            "#06B6D4",
            "#0EA5E9",
            "#3B82F6",
            "#6366F1",
            "#8B5CF6",
            "#A855F7",
            "#D946EF",
            "#EC4899",
            "#F43F5E",
        ]
        used_colors = set(
            CustomItemType.objects.filter(project_id=project_pk, is_active=True).values_list("color", flat=True)
        )
        available = [color for color in palette if color not in used_colors] or palette
        return Response({"available_colors": available, "used_colors": sorted(used_colors)})
```

Add the import/export for this viewset in `apps/deliverables/views/__init__.py` if the project uses aggregated exports.

---

## Task 6 · URLs

**File:** `/Users/averypawelek/the-link/the_link_django/apps/deliverables/urls.py`

1. Import the new viewset:
   ```python
   from .views.custom_item_type_views import CustomItemTypeViewSet
   ```

2. Register it on the `single_project_router` just after the existing `extracted-data` route to keep related endpoints grouped:
   ```python
   single_project_router.register(
       "custom-item-types",
       CustomItemTypeViewSet,
       basename="custom-item-type",
   )
   ```

No changes needed in `the_link/urls.py` because the Deliverables routes are already included under `/api/deliverables/…`.

---

## Task 7 · Admin Exposure (Optional but Helpful)

**File:** `/Users/averypawelek/the-link/the_link_django/apps/deliverables/admin.py`

Register the new model so the support team can inspect custom types:
```python
@admin.register(CustomItemType)
class CustomItemTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "created_by", "is_active", "color", "created_at")
    list_filter = ("project", "is_active")
    search_fields = ("name", "project__name", "project__project_number")
```

---

## Task 8 · Migrations

From the repository root, using the mandated Docker entrypoint:
```bash
cd /Users/averypawelek/the-link/the_link_django
docker-compose exec web python manage.py makemigrations deliverables --name custom_item_types
docker-compose exec web python manage.py migrate
```

Inspect the generated migration in `apps/deliverables/migrations/` to confirm:
- `CreateModel` for `CustomItemType` with indexes/constraints.
- `AddField` for `ExtractedData.custom_item_type`.

---

## Task 9 · Tests

**File (new):** `/Users/averypawelek/the-link/the_link_django/apps/deliverables/tests/test_custom_item_types.py`

Key considerations:
- Use `Project` + `project.versions.first()` to satisfy the `project_version` FK.
- Provide `spec_section_number`, `spec_section_name`, and `requirement_text` when creating `ExtractedData`.
- Hit the real API base: `/api/deliverables/projects/<id>/custom-item-types/`.

Example skeleton:
```python
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.test import TestCase

from apps.deliverables.models import (
    CustomItemType,
    ExtractedData,
    ExtractionSource,
    Project,
    ProjectVersion,
)

User = get_user_model()


class CustomItemTypeModelTests(TestCase):
    ...


class ExtractedDataCustomTypeTests(TestCase):
    ...


class CustomItemTypeAPITests(APITestCase):
    ...
```

Ensure API routes use:
```python
base_url = f"/api/deliverables/projects/{self.project.id}/custom-item-types/"
```

Run the suite:
```bash
docker-compose exec web python manage.py test apps.deliverables.tests.test_custom_item_types -v 2
```

---

## Task 10 · Documentation

**File (new):** `/Users/averypawelek/the-link/the_link_django/docs/custom_item_types_api.md`

Include:
- Base URL: `/api/deliverables/projects/{project_id}/custom-item-types/`.
- Request/response examples using `requirement_text` and `spec_section_number`.
- Mention bulk assignment endpoint and color palette.
- Document automatic `extraction_type` coercion.
- Highlight soft-delete behaviour via `is_active`.

---

## Verification Checklist
1. `docker-compose exec web python manage.py makemigrations deliverables --check` shows clean state.
2. `docker-compose exec web python manage.py showmigrations deliverables` marks the new migration.
3. `docker-compose exec web python manage.py test apps.deliverables.tests.test_custom_item_types`.
4. Manual API smoke test (e.g. via `curl` or Postman) against:
   - `GET /api/deliverables/projects/<id>/custom-item-types/`
   - `POST /api/deliverables/projects/<id>/custom-item-types/`
   - `POST /api/deliverables/projects/<id>/custom-item-types/<id>/assign-to-extracted-data/`
5. Frontend smoke (optional): ensure the response shape matches future UI expectations (id/name/color/description).

---

## Performance & Security Notes
- Two indexes on the new model (`project + is_active`, `created_by`) keep common lookups fast.
- `select_related`/`annotate` calls avoid N+1 queries in list/detail endpoints.
- The viewset reuses `ProjectAccessPermissions`; no new permission logic required.
- Validation ensures custom types cannot be reused across projects, stopping data leakage.
- Soft deletes preserve historical associations; consider cron cleanup if types become unused.

---

## Future Enhancements (Out of Scope)
1. Frontend controls for managing custom color palettes.
2. API filters to retrieve `ExtractedData` by custom item type via query params (server-side filtering extension).
3. Analytics for usage frequency of each custom type.
4. Optional ordering field to prioritise certain custom types.
5. Bulk creation/import/export tooling for project templates.

With the above adjustments, the implementation plan now mirrors the actual Deliverables app structure and avoids the mismatches identified in the code review.

