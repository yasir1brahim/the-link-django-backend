from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch, Q, Max
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.utils.feature_flags import is_spec_centered_view_feature_flag_active
from apps.deliverables.permissions import SpecCentricViewAccessPermissions
from apps.deliverables.models import (
    Project,
    SpecSection,
    SubmittalItem,
    ProjectVersion,
    AiGeneratedLog
)
from apps.deliverables.serializers.spec_centric_serializers import (
    SpecSectionSerializer,
    SubmittalHighlightSerializer,
    SpecSectionContentSerializer,
    SpecCentricViewSerializer
)


class SpecCentricViewSet(viewsets.ViewSet):
    """
    ViewSet for spec centric view functionality.
    Provides endpoints for spec sections, content, and submittal highlights.
    """
    permission_classes = [IsAuthenticated, SpecCentricViewAccessPermissions]

    def get_queryset(self):
        """Get queryset with proper filtering and prefetching."""
        project_id = self.kwargs.get('project_id')
        project = get_object_or_404(Project, id=project_id)
        
        # Check feature flag
        if not is_spec_centered_view_feature_flag_active(
            self.request.user, 
            getattr(self.request, 'team', None), 
            project
        ):
            return SpecSection.objects.none()
        
        return SpecSection.objects.filter(
            document__project=project
        ).select_related(
            'masterformat_section',
            'document'
        )

    @extend_schema(
        summary="Get all spec sections for a project",
        description="Retrieve all spec sections for a project with basic information.",
        parameters=[
            OpenApiParameter(
                name='project_version_id',
                description='ID of the project version to filter sections',
                required=False,
                type=OpenApiTypes.INT
            )
        ],
        responses={
            200: SpecSectionSerializer(many=True),
            403: {'description': 'Feature flag not enabled'}
        }
    )
    def list(self, request, project_id=None):
        """Get all spec sections for a project."""
        project = get_object_or_404(Project, id=project_id)
        
        
        # Filter by project version if provided
        project_version_id = request.query_params.get('project_version_id')
        queryset = self.get_queryset()
        
        if project_version_id:
            queryset = queryset.filter(
                document__project_version_id=project_version_id
            )
        
        serializer = SpecSectionSerializer(queryset, many=True, context={'request': request})
        
        return Response({
            'spec_sections': serializer.data,
            'total_sections': queryset.count(),
            'project_id': project.id,
            'project_version_id': project_version_id
        })

    @extend_schema(
        summary="Get spec section content with submittal highlights",
        description="Retrieve detailed content for a specific spec section including submittal highlights.",
        parameters=[
            OpenApiParameter(
                name='project_version_id',
                description='ID of the project version to filter submittals',
                required=False,
                type=OpenApiTypes.INT
            )
        ],
        responses={
            200: SpecSectionContentSerializer,
            404: {'description': 'Spec section not found'},
            403: {'description': 'Feature flag not enabled'}
        }
    )
    def retrieve(self, request, pk=None, project_id=None):
        """Get detailed content for a specific spec section."""
        project = get_object_or_404(Project, id=project_id)
        
        spec_section = get_object_or_404(
            self.get_queryset().prefetch_related(
                Prefetch(
                    'submittalitem_set',
                    queryset=SubmittalItem.objects.select_related(
                        'masterformat_section',
                        'document'
                    )
                )
            ),
            id=pk
        )
        
        # Filter submittals by project version if provided
        project_version_id = request.query_params.get('project_version_id')
        submittals = spec_section.submittalitem_set.exclude(parsing_method='PLACEHOLDER')

        if project_version_id:
            submittals = submittals.filter(project_version_id=project_version_id)
        
        # Fetch AI generated log data for this project/version
        ai_logs = []
        if project_version_id:
            try:
                # Get the latest log ID for each distinct log_type
                latest_by_type = AiGeneratedLog.objects.filter(
                    project=project,
                    project_version_id=project_version_id,
                    log_status='SUCCESS',
                    log_data__isnull=False
                ).values('log_type').annotate(
                    latest_id=Max('id')
                ).values_list('latest_id', flat=True)
                
                # Get the actual log objects for the latest logs
                ai_logs = AiGeneratedLog.objects.filter(id__in=latest_by_type).order_by('log_type')
                
            except Exception as e:
                # Log error but don't fail the request
                print(f"Error fetching AI log data: {str(e)}")
                ai_logs = []
        
        # Create a data structure for the serializer
        data = {
            'spec_section': spec_section,
            'content': f"Content for {spec_section.document.name if spec_section.document else 'Unknown Document'} - Section {spec_section.masterformat_section.masterformat_number if spec_section.masterformat_section else 'Unknown'}"
        }
        
        # Pass the filtered submittals and AI log data to the serializer context
        serializer = SpecSectionContentSerializer(data, context={
            'request': request,
            'filtered_submittals': submittals,
            'ai_log_data': ai_logs
        })
        
        return Response(serializer.data)

    @extend_schema(
        summary="Get submittal highlights for a spec section",
        description="Retrieve submittal highlights with positioning data for a specific spec section.",
        parameters=[
            OpenApiParameter(
                name='project_version_id',
                description='ID of the project version to filter submittals',
                required=False,
                type=OpenApiTypes.INT
            )
        ],
        responses={
            200: SubmittalHighlightSerializer(many=True),
            404: {'description': 'Spec section not found'},
            403: {'description': 'Feature flag not enabled'}
        }
    )
    @action(detail=True, methods=['get'], url_path='submittal-highlights')
    def get_submittal_highlights(self, request, pk=None, project_id=None):
        """Get submittal highlights for a specific spec section."""
        project = get_object_or_404(Project, id=project_id)
        
        spec_section = get_object_or_404(self.get_queryset(), id=pk)
        
        # Get submittals for this spec section
        project_version_id = request.query_params.get('project_version_id')
        submittals = SubmittalItem.objects.filter(
            spec_section=spec_section
        ).exclude(
            parsing_method='PLACEHOLDER'
        ).select_related(
            'masterformat_section',
            'document'
        )
        
        if project_version_id:
            submittals = submittals.filter(project_version_id=project_version_id)
        
        serializer = SubmittalHighlightSerializer(submittals, many=True, context={'request': request})
        
        return Response(serializer.data)

    @extend_schema(
        summary="Get spec centric view data",
        description="Get comprehensive spec centric view data including all sections and highlights.",
        parameters=[
            OpenApiParameter(
                name='project_version_id',
                description='ID of the project version to filter data',
                required=False,
                type=OpenApiTypes.INT
            )
        ],
        responses={
            200: SpecCentricViewSerializer,
            403: {'description': 'Feature flag not enabled'}
        }
    )
    @action(detail=False, methods=['get'], url_path='spec-centric-data')
    def get_spec_centric_data(self, request, project_id=None):
        """Get comprehensive spec centric view data."""
        project = get_object_or_404(Project, id=project_id)
        
        project_version_id = request.query_params.get('project_version_id')
        queryset = self.get_queryset()
        
        if project_version_id:
            queryset = queryset.filter(
                document__project_version_id=project_version_id
            )
        
        serializer = SpecCentricViewSerializer({
            'spec_sections': queryset,
            'total_sections': queryset.count(),
            'project_id': project.id,
            'project_version_id': project_version_id,
            'project': project
        }, context={'request': request})
        
        return Response(serializer.data)
