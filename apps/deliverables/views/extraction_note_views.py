# apps/deliverables/views/extraction_note_views.py
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from apps.deliverables.models import ExtractionNote, ExtractedData
from apps.deliverables.serializers.extraction_note import (
    ExtractionNoteSerializer,
    ExtractionNoteCreateUpdateSerializer
)
from apps.deliverables.permissions import ExtractionNoteAccessPermissions


class ExtractionNoteViewSet(viewsets.ModelViewSet):
    """ViewSet for ExtractionNote CRUD operations"""
    permission_classes = [IsAuthenticated, ExtractionNoteAccessPermissions]

    def get_queryset(self):
        """Filter by extracted_data and project, optimize queries"""
        project_id = self.kwargs.get('project_pk')
        extracted_data_id = self.kwargs.get('extracteddata_pk')

        return ExtractionNote.objects.filter(
            extracted_data_id=extracted_data_id,
            extracted_data__project_id=project_id
        ).select_related('created_by', 'extracted_data').order_by('created_at')

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ExtractionNoteCreateUpdateSerializer
        return ExtractionNoteSerializer

    def perform_create(self, serializer):
        """Set created_by and extracted_data from context"""
        project_id = self.kwargs.get('project_pk')
        extracted_data_id = self.kwargs.get('extracteddata_pk')

        # Verify ExtractedData exists and belongs to project
        extracted_data = get_object_or_404(
            ExtractedData,
            id=extracted_data_id,
            project_id=project_id
        )

        serializer.save(
            created_by=self.request.user,
            extracted_data=extracted_data
        )

    def check_object_permissions(self, request, obj):
        """Only note author can edit/delete"""
        super().check_object_permissions(request, obj)

        if self.action in ['update', 'partial_update', 'destroy']:
            if obj.created_by and obj.created_by != request.user:
                raise PermissionDenied("You can only modify notes you created.")
