from rest_framework import viewsets, status, filters, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Count

from apps.deliverables.models import ExtractedData, Project, ExtractionSource
from apps.deliverables.serializers.extracted_data import (
    ExtractedDataSerializer,
    ExtractedDataListSerializer,
    ExtractedDataCreateSerializer
)
from apps.deliverables.permissions import ProjectAccessPermissions


class ExtractedDataViewSet(viewsets.ModelViewSet):
    """ViewSet for ExtractedData CRUD operations"""
    permission_classes = [IsAuthenticated, ProjectAccessPermissions]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]

    # Search
    search_fields = [
        'spec_section_number', 'spec_section_name',
        'requirement_text'
    ]

    # Ordering
    ordering_fields = [
        'spec_section_number', 'created_at', 'updated_at',
        'extraction_type', 'source'
    ]
    ordering = ['spec_section_number', 'id']

    def get_queryset(self):
        """Filter by project and optimize queries"""
        project_id = self.kwargs.get('project_pk') or self.kwargs.get('project_id')
        queryset = ExtractedData.objects.filter(project_id=project_id)

        # Optimize based on action
        if self.action == 'list':
            queryset = queryset.select_related('created_by', 'ai_generated_log')
            queryset = queryset.prefetch_related('notes__created_by')
        elif self.action in ['retrieve', 'update', 'partial_update']:
            queryset = queryset.select_related(
                'created_by', 'ai_generated_log',
                'project', 'project_version', 'spec_section'
            )
            queryset = queryset.prefetch_related('notes__created_by')

        return queryset

    def get_serializer_class(self):
        """Use different serializers for different actions"""
        if self.action == 'list':
            return ExtractedDataListSerializer
        elif self.action == 'create':
            return ExtractedDataCreateSerializer
        return ExtractedDataSerializer

    def perform_create(self, serializer):
        """Ensure created_by is set for human-sourced entries"""
        serializer.save(
            created_by=self.request.user,
            source=ExtractionSource.HUMAN
        )

    @action(detail=False, methods=['get'])
    def summary(self, request, project_pk=None):
        """Get summary of extractions for the project"""
        queryset = self.get_queryset()

        # Group by source
        source_stats = queryset.values('source').annotate(
            total=Count('id')
        )

        # Group by extraction type
        type_stats = queryset.values('extraction_type', 'item_type').annotate(
            count=Count('id')
        ).order_by('extraction_type', 'item_type')

        total = queryset.count()

        return Response({
            'total_items': total,
            'by_source': {
                item['source']: item['total']
                for item in source_stats
            },
            'by_type': [
                {
                    'extraction_type': item['extraction_type'],
                    'item_type': item['item_type'],
                    'count': item['count']
                }
                for item in type_stats
            ]
        })

    @action(detail=False, methods=['get'])
    def by_spec_section(self, request, project_pk=None):
        """Get extractions grouped by spec section"""
        queryset = self.get_queryset()
        spec_number = request.query_params.get('spec_section_number')

        if spec_number:
            queryset = queryset.filter(spec_section_number=spec_number)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
