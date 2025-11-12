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


class CustomItemTypeAccessPermissions(ProjectAccessPermissions):
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, "project"):
            obj = obj.project
        return super().has_object_permission(request, view, obj)


class CustomItemTypeViewSet(viewsets.ModelViewSet):
    """
    Manage project-scoped custom item types.
    """

    permission_classes = [IsAuthenticated, CustomItemTypeAccessPermissions]

    def _get_project_id(self):
        return self.kwargs.get("project_pk") or self.kwargs.get("project_id")

    def get_queryset(self):
        project_id = self._get_project_id()
        queryset = CustomItemType.objects.filter(project_id=project_id, is_active=True)

        if self.action == "list":
            queryset = queryset.annotate(
                extracted_data_count=Count(
                    "extracted_data_items",
                    filter=Q(extracted_data_items__project_id=project_id),
                )
            ).select_related("created_by")
        elif self.action in {"retrieve", "update", "partial_update"}:
            queryset = queryset.select_related("project", "created_by")

        return queryset.order_by("name")

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
        project_id = self._get_project_id()
        if project_id:
            context["project"] = get_object_or_404(Project, pk=project_id)
        return context

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    @action(detail=True, methods=["post"], url_path="assign-to-extracted-data")
    def assign_to_extracted_data(self, request, *args, **kwargs):
        extracted_ids = request.data.get("extracted_data_ids")
        if not extracted_ids:
            return Response(
                {"detail": "extracted_data_ids is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        project_id = self._get_project_id()
        queryset = ExtractedData.objects.filter(
            id__in=extracted_ids,
            project_id=project_id,
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
    def extracted_data(self, request, *args, **kwargs):
        custom_type = self.get_object()
        project_id = self._get_project_id()
        queryset = ExtractedData.objects.filter(
            custom_item_type=custom_type,
            project_id=project_id,
        ).select_related("created_by")

        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(requirement_text__icontains=search)

        page = self.paginate_queryset(queryset)
        results = []

        def serialize_item(item):
            return {
                "id": item.id,
                "spec_section_number": item.spec_section_number,
                "requirement_text": item.requirement_text,
                "created_by": item.created_by.get_full_name() if item.created_by else None,
                "created_at": item.created_at,
            }

        if page is not None:
            results = [serialize_item(item) for item in page]
            return self.get_paginated_response(results)

        results = [serialize_item(item) for item in queryset]
        return Response({"results": results, "count": len(results)})

    @action(detail=False, methods=["get"], url_path="color-palette")
    def color_palette(self, request, *args, **kwargs):
        project_id = self._get_project_id()
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
        used_colors = set(CustomItemType.objects.filter(project_id=project_id, is_active=True).values_list("color", flat=True))
        available = [color for color in palette if color not in used_colors] or palette
        return Response({"available_colors": available, "used_colors": sorted(used_colors)})

