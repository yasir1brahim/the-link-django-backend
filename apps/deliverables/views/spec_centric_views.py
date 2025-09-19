from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch, Q
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.utils.feature_flags import is_spec_centered_view_feature_flag_active
from apps.deliverables.permissions import SpecCentricViewAccessPermissions
from apps.deliverables.models import (
    Project,
    SpecSection,
    SubmittalItem,
    ProjectVersion
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
        project_id = self.kwargs.get('project_pk')
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
        ).prefetch_related(
            'submittalitem_set'
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
    def list(self, request, project_pk=None):
        """Get all spec sections for a project."""
        project = get_object_or_404(Project, id=project_pk)
        
        # Check feature flag
        if not is_spec_centered_view_feature_flag_active(
            request.user, 
            getattr(request, 'team', None), 
            project
        ):
            return Response(
                {'error': 'Spec centered view feature is not enabled'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
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
    def retrieve(self, request, pk=None, project_pk=None):
        """Get detailed content for a specific spec section."""
        project = get_object_or_404(Project, id=project_pk)
        
        # Check feature flag
        if not is_spec_centered_view_feature_flag_active(
            request.user, 
            getattr(request, 'team', None), 
            project
        ):
            return Response(
                {'error': 'Spec centered view feature is not enabled'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
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
        submittals = spec_section.submittalitem_set.all()
        
        if project_version_id:
            submittals = submittals.filter(project_version_id=project_version_id)
        
        # Create a modified spec section with filtered submittals
        spec_section.submittalitem_set = submittals
        
        serializer = SpecSectionContentSerializer(spec_section, context={'request': request})
        
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
    def get_submittal_highlights(self, request, pk=None, project_pk=None):
        """Get submittal highlights for a specific spec section."""
        project = get_object_or_404(Project, id=project_pk)
        
        # Check feature flag
        if not is_spec_centered_view_feature_flag_active(
            request.user, 
            getattr(request, 'team', None), 
            project
        ):
            return Response(
                {'error': 'Spec centered view feature is not enabled'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        spec_section = get_object_or_404(self.get_queryset(), id=pk)
        
        # Get submittals for this spec section
        project_version_id = request.query_params.get('project_version_id')
        submittals = SubmittalItem.objects.filter(
            spec_section=spec_section
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
    def get_spec_centric_data(self, request, project_pk=None):
        """Get comprehensive spec centric view data."""
        project = get_object_or_404(Project, id=project_pk)
        
        # Check feature flag
        if not is_spec_centered_view_feature_flag_active(
            request.user, 
            getattr(request, 'team', None), 
            project
        ):
            return Response(
                {'error': 'Spec centered view feature is not enabled'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
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
