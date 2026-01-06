from typing import TypedDict, List
from concurrent.futures import ThreadPoolExecutor
import csv
import logging
import time
import hashlib
import boto3
import requests
import re
from enum import Enum
from datetime import datetime
from datetime import timezone
from typing import TypedDict, List
import ast
import json

import openpyxl
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side


def clean_excel_content(content):
    """
    Clean content for safe Excel/XML export by removing:
    1. Illegal XML characters (control chars)
    2. Zero-width characters
    3. Special Unicode characters that cause XML parsing issues
    4. All high Unicode characters that might not be XML-safe
    
    Uses regex for performance - much faster than looping over every character.
    """
    if not content:
        return ''
    
    # Convert to string first
    content = str(content)
    
    # Use regex to keep ONLY XML-safe characters
    # This pattern matches the INVERSE of what we want to keep, then we remove those characters
    # 
    # Pattern explanation:
    # [^\x09\x0A\x0D\x20-\x7E\xA0-\xFF\u0100-\u024F\u0370-\u03FF\u0400-\u04FF]
    # ^ = NOT (inverse match)
    # \x09\x0A\x0D = tab, newline, carriage return
    # \x20-\x7E = standard ASCII printable (space through tilde)
    # \xA0-\xFF = extended Latin (Western European)
    # \u0100-\u024F = Latin Extended-A and Extended-B
    # \u0370-\u03FF = Greek and Coptic
    # \u0400-\u04FF = Cyrillic
    #
    # So we remove everything that's NOT in these ranges
    unsafe_pattern = re.compile(r'[^\x09\x0A\x0D\x20-\x7E\xA0-\xFF\u0100-\u024F\u0370-\u03FF\u0400-\u04FF]')
    content = unsafe_pattern.sub('', content)
    
    # Truncate to safe length
    max_length = 30000
    if len(content) > max_length:
        content = content[:max_length]
    
    return content

from django.http import Http404, HttpResponse
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.db.models import Q, Case, When, IntegerField, Count, Prefetch
from django.db import connection, transaction, IntegrityError
from django.core.exceptions import TooManyFilesSent
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import CreateAPIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import generics, status, mixins
from rest_framework.exceptions import (
    PermissionDenied,
    ValidationError as DRFValidationError,
)
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework import viewsets

from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
    OpenApiResponse,
)
from drf_spectacular.types import OpenApiTypes
from waffle import flag_is_active

from rest_framework import viewsets

from apps.teams.models import Team, Flag
from apps.users.models import CustomUser
from ..serializers import (
    ProjectDetailsSerializer,
    ProjectVersionSerializer,
    ProjectMembershipAddSerializer,
    ProjectListSerializer,
    ProjectOverviewSerializer,
    ProjectWriteSerializer,
    FileUploadSerializer,
    SubmittalItemReadSerializer,
    SubmittalItemWriteSerializer,
    SubmittalItemListSerializer,
    ExcelExportHeaderSerializer,
    CombineSubmittalItemsSerializer,
    VersionComparisonSerializer,
    FilteredVersionComparisonSerializer,
    SemanticallyProcessedSpecItemSerializer
)
from ..models import (
    Project,
    ProjectVersion,
    ProjectMembership,
    UploadedFile,
    SubmittalItem,
    SubmittalItemList,
    SemanticallyProcessedSpecItem,
    MasterFormatSection,
    SpecSection,
    DocProcessingStatus,
    ExcelExportHeader,
    NoticeMatch,
    ProcoreToken,
    ProcoreSubmittalTypeMapping,
    ROLE_PROJECT_MEMBER,
    NoticeExcerpt,
    DrawingFile,
    DrawingExtraction,
    DrawingExtractionStatus,
)
from ..permissions import (
    ProjectAccessPermissions,
    SubmittalItemAccessPermissions,
    SubmittalListAccessPermissions,
    ProjectVersionAccessPermissions,
    SpecCentricViewAccessPermissions,
)
from apps.utils.feature_flags import (
    is_notices_feature_flag_active, is_versioning_feature_flag_active, is_v2_process_deliverables_feature_flag_active,
    is_full_spec_processing_feature_flag_active, is_specgpt_feature_flag_active, is_drawings_feature_flag_active
)
from ..constants import masterformat_to_section_title_map
from ..serializers.notices import NoticeMatchProcessingSerializer, NoticeMatchSerializer, NoticeProcessingCallbackSerializer
from ..serializers.procore import (ProcoreFetchAccessTokenSerializer, ProcoreAccessTokenSerializer,
                                   ProcoreCompanyMappingSerializer, ProcoreCompanySerializer, ProcoreMeSerializer,
                                   ProcoreProjectMappingSerializer, ProcoreSubmittalSerializer,
                                   ProcoreSubmittalCreationResponseSerializer, CreateProcoreProjectMappingSerializer,
                                   CreateProcoreCompanyMappingSerializer, UpdateProcoreSubmittalMappingsSerializer)
from ..services import SubmittalService, VersionComparisonService
from ..integrations.procore import (get_procore_access_token, get_companies, get_fresh_token_for_user, 
                                   ProcoreException, get_me, get_status, get_spec_divisions, get_spec_sections,
                                   create_spec_division, create_spec_section, create_submittal, get_projects,
                                   get_managers, get_submittal_types, check_token_info)

logger = logging.getLogger(__name__)


s3 = boto3.client(
    "s3",
    region_name=settings.AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
)


class ParsingMethod(str, Enum):
    REGEX_SUBMITTAL = "REGEX_SUBMITTAL"
    REGEX_PRODUCT_DATA = "REGEX_PRODUCT_DATA"
    AI_SUBMITTAL = "AI_SUBMITTAL"
    UNKNOWN = "UNKNOWN"


class SubmittalInfo(TypedDict):
    submittal_type: str
    submittal_description: str
    submittal_text: str
    llm_submittal_type: str
    master_format_section_number: str
    contextual_text: str
    section: str
    page_no: int
    parsing_method: ParsingMethod


class SubsectionType(str, Enum):
    SUBMITTAL_SECTION = "SUBMITTAL_SECTION"
    PART_1_GENERAL = "PART_1_GENERAL"
    PART_2_PRODUCTS = "PART_2_PRODUCTS"
    PART_3_EXECUTION = "PART_3_EXECUTION"
    UNKNOWN = "UNKNOWN"


class TextLocation(TypedDict):
    page_no: int
    x: int
    y: int


class TextChunk(TypedDict):
    text: str
    text_location: TextLocation


class SpecSubSection(TypedDict):
    subsection_type: SubsectionType
    master_format_section_number: str
    text_chunks: List[TextChunk]
    file_s3_key: str


class SpecStatusRequest(TypedDict):
    new_status: str
    document_id: str
    filename: str
    project_id: str
    user_id: str
    submittals: List[SubmittalInfo]
    subsections: List[SpecSubSection]


class SpecItem(TypedDict):
    item: List[str]
    topic: List[str]
    text: str
    spec_section: str
    spec_section_part: str
    paragraph_number: str
    text_location: TextLocation
    additional_text_locations: List[TextLocation]
    parsing_method: str

class FullSpecProcessingRequest(TypedDict):
    new_status: str
    document_id: str
    filename: str
    project_id: str
    project_version_id: str
    user_id: str
    master_format_section_number: str
    spec_items: List[SpecItem]

class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    permission_classes = [IsAuthenticated, ProjectAccessPermissions]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProjectDetailsSerializer
        if self.action == 'list':
            return ProjectListSerializer
        if self.action == 'overview':
            return ProjectOverviewSerializer
        return ProjectWriteSerializer
    

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='team_id',
                description='ID of the team to filter projects',
                required=False,
                type=OpenApiTypes.INT
            )
        ]
    )
    def list(self, request, *args, **kwargs):
        self.queryset = self.get_queryset_for_list()
        return super().list(request, *args, **kwargs)
    

    def get_queryset_for_list(self):
        # Get the team_id from query parameters
        team_id = self.request.query_params.get('team_id', None)
        
        if team_id is not None:
            try:
                team_id = int(team_id)
                team = get_object_or_404(Team, id=team_id)
                
                # Check if the user is a member of the team
                if not self.request.user.is_member_of_team(team):
                    raise PermissionDenied("You don't have permission to access projects for this team.")
                
                if self.request.user.is_admin_for_team(team):
                    queryset = self.queryset.filter(team_id=team_id)
                else:
                    queryset = self.queryset.filter(team_id=team_id, members=self.request.user)
            except ValueError:
                raise DRFValidationError("Invalid team_id. Must be an integer.")
        else:
            if self.request.user.is_superuser:
                queryset = self.queryset
            else:
                queryset = self.queryset.filter(members=self.request.user)

        return queryset.select_related('team').prefetch_related('members').prefetch_related('versions').order_by('name')

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='team_id',
                description='ID of the team to filter projects',
                required=False,
                type=OpenApiTypes.INT
            )
        ],
        description="Get a lightweight overview of projects with minimal data for list views. "
    )
    @action(detail=False, methods=['get'], url_path='overview')
    def overview(self, request, *args, **kwargs):
        """
        Lightweight endpoint for project list/overview pages.
        Returns minimal project data.
        """

        team_id = request.query_params.get('team_id', None)

        if team_id is not None:
            try:
                team_id = int(team_id)
                team = get_object_or_404(Team, id=team_id)

                # Check if the user is a member of the team
                # Return 404 instead of 403 to avoid disclosing team existence to non-members
                if not request.user.is_member_of_team(team):
                    raise Http404()

                # Filter based on user role
                if request.user.is_admin_for_team(team):
                    queryset = self.queryset.filter(team_id=team_id)
                else:
                    queryset = self.queryset.filter(team_id=team_id, members=request.user)
            except ValueError:
                raise DRFValidationError("Invalid team_id. Must be an integer.")
        else:
            if request.user.is_superuser:
                queryset = self.queryset
            else:
                queryset = self.queryset.filter(members=request.user)

        # Prefetch only the current user's membership to avoid N+1 queries in serializer
        queryset = queryset.prefetch_related(
            Prefetch(
                'project_memberships',
                queryset=ProjectMembership.objects.filter(user=request.user),
                to_attr='_current_user_memberships'
            )
        ).annotate(_members_count=Count('members')).order_by('name', 'id')

        # Paginate if pagination is enabled
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        print(f"serializer.validated_data: {serializer.validated_data}")
        team = serializer.validated_data["team"]
        if not self.request.user.is_member_of_team(team):
            raise PermissionDenied()
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'], url_path='archive')
    def archive(self, request, pk=None):
        """Toggle the archive status of a project."""
        project = self.get_object()
        action_type = request.data.get('action', 'archive').lower()
        if action_type == 'restore':
            project.is_archived = False
            status_message = "unarchived"
        else:
            project.is_archived = True
            status_message = "archived"

        project.save()
        return Response( {"status": f"Project {status_message} successfully."},
        status=status.HTTP_200_OK )
    
    @action(detail=True, methods=['post'], url_path='members-add')
    def members_add(self, request, pk=None):
        project = self.get_object()
        serializer = ProjectMembershipAddSerializer(data=request.data, context={'view': self})
        serializer.is_valid(raise_exception=True)
        users = serializer.validated_data.get('user_ids', [])
        with transaction.atomic():
            for user in users:
                try:
                    ProjectMembership.objects.create(
                        project=project,
                        user=user,
                        role=ROLE_PROJECT_MEMBER
                    )
                except IntegrityError:
                    # User is already in the project
                    continue
        return Response( {"status": f"Users added to project successfully."}, status=status.HTTP_200_OK)



    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='submittal_id',
                description='ID of the submittal to get the project ID',
                required=True,
                type=OpenApiTypes.INT
            )
        ],
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT
        },
        description="Get the project ID associated with a given submittal ID."
    )
    @action(detail=False, methods=['get'], url_path='project-id-by-submittal-id')
    def project_id_by_submittal_id(self, request):
        submittal_id = request.query_params.get('submittal_id')
        if not submittal_id:
            return Response({"error": "submittal_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            submittal_item = get_object_or_404(SubmittalItem, id=submittal_id)
            project_id = submittal_item.project.id
            return Response({"project_id": project_id}, status=status.HTTP_200_OK)
        except ValueError:
            return Response({"error": "Invalid submittal_id. Must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, context={"request": request})
        return Response(serializer.data)


class ProjectVersionViewSet(viewsets.ModelViewSet):
    queryset = ProjectVersion.objects.all()
    permission_classes = [IsAuthenticated, ProjectVersionAccessPermissions]
    serializer_class = ProjectVersionSerializer

    def get_queryset(self):
        project_id = self.kwargs.get('project_id')
        queryset = self.queryset.filter(project_id=project_id)
        if self.action == 'list':
            queryset = queryset.exclude(is_archived=True)
        elif self.action == 'archived':
            queryset = queryset.filter(is_archived=True)
        return queryset

    def perform_create(self, serializer):
        try:
            serializer.save(created_by=self.request.user, project_id=self.kwargs.get('project_id'))
        except IntegrityError:
            raise DRFValidationError("Version name must be different from all active and archived versions")

    def perform_update(self, serializer):
        try:
            serializer.save(last_updated_by=self.request.user)
        except IntegrityError:
            raise DRFValidationError("Version name must be different from all active and archived versions")

    def destroy(self, request, *args, **kwargs):
        return Response(
            {"detail": "Cannot delete project versions, use archive instead"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    @action(detail=False, methods=['get'], url_path='archived')
    def archived(self, request, project_id=None):
        """Retrieve all archived project versions for a given project."""
        queryset = self.get_queryset().filter(is_archived=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_path='archive')
    def archive(self, request, pk=None, project_id=None):
        """Toggle the archive status of a project version."""
        project_version = self.get_object()
        action_type = request.data.get('action', 'archive').lower()
        if action_type == 'restore':
            project_version.is_archived = False
            status_message = "unarchived"
        else:
            if project_version.project.versions.count() == 1:
                return Response(
                    {"detail": "Cannot archive the last remaining project version"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            project_version.is_archived = True
            status_message = "archived"

        project_version.save()

        return Response(
            {"status": f"Project version {status_message} successfully."},
            status=status.HTTP_200_OK
        )


class SubmittalItemPagination(PageNumberPagination):
    page_query_param = 'page_number'
    page_size_query_param = 'limit'
    max_page_size = 100


class SubmittalItemViewSet(viewsets.ModelViewSet):
    queryset = SubmittalItem.objects.all()
    permission_classes = [IsAuthenticated, SubmittalItemAccessPermissions]
    pagination_class = SubmittalItemPagination
    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return SubmittalItemReadSerializer
        return SubmittalItemWriteSerializer
    

    allowed_filter_keys = ['exported', 'spec_section', 'type', 'item_desc']
    allowed_order_cols = ['spec_section', 'type', 'item_desc', 'para_context']
    allowed_orders = ['asc', 'desc']
    
    def apply_filter(self, queryset, filter_key, filter_values):
        if filter_key == 'spec_section':
            queryset = queryset.filter(masterformat_section__masterformat_number__in=filter_values)
        elif filter_key == 'type':
            queryset = queryset.filter(submittal_type__in=filter_values)
        elif filter_key == 'item_desc':
            queryset = queryset.filter(submittal_description__in=filter_values)
        return queryset

    def apply_order(self, queryset, order_col, order):
        order_string = "-" if order == "desc" else ""
        order_items_list = []
        if order_col == 'spec_section':
            order_string += "masterformat_section__masterformat_number"
            order_items_list = [order_string, 'heirarchical_paragraph_number', 'submittal_number']
        elif order_col == 'type':
            order_string += "submittal_type"
            order_items_list = [order_string, 'masterformat_section__masterformat_number', 'heirarchical_paragraph_number', 'submittal_number']
        elif order_col == 'item_desc':
            order_string += "submittal_description"
            order_items_list = [order_string, 'masterformat_section__masterformat_number', 'heirarchical_paragraph_number', 'submittal_number']
        elif order_col == 'para_context':
            order_string += "submittal_content"
            order_items_list = [order_string, 'masterformat_section__masterformat_number', 'heirarchical_paragraph_number', 'submittal_number']
        return queryset.order_by(*order_items_list)

    def get_queryset_for_list(self):
        project_id = self.kwargs.get('project_id')
        search = self.request.query_params.get('search')
        order_col = self.request.query_params.get('order_col')
        order = self.request.query_params.get('order') or 'asc'
        list_id = self.request.query_params.get('list_id')
        records = self.request.query_params.getlist('records[]')

        filters = {}
        try:
            if self.request.query_params.get('filters[exported]'):
                filters['exported'] = self.request.query_params.get('filters[exported]').split(',')
            if self.request.query_params.get('filters[item_desc]'):
                filters['item_desc'] = self.request.query_params.get('filters[item_desc]').split(',')
            if self.request.query_params.get('filters[spec_section]'):
                filters['spec_section'] = self.request.query_params.get('filters[spec_section]').split(',')
            if self.request.query_params.get('filters[type]'):
                filters['type'] = self.request.query_params.get('filters[type]').split(',')
        except Exception as e:
            raise DRFValidationError(f"Invalid filters: {e}")

        queryset = self.queryset.filter(project_id=project_id)
        if self.project_version:
            queryset = queryset.filter(project_version_id=self.project_version.id)
        queryset = queryset.select_related('masterformat_section').select_related('document').select_related('project')
        queryset = queryset.exclude(submittal_type='Unclassified', masterformat_section__masterformat_number__regex='^0[012]\\d+')

        if search:
            queryset = queryset.filter(
                Q(masterformat_section__masterformat_number__icontains=search) | 
                Q(submittal_description__icontains=search) | 
                Q(submittal_type__icontains=search) |
                Q(submittal_content__icontains=search)
            )

        if filters and 'exported' in filters:
            filter_to_exported = filters['exported']
            queryset = queryset.filter(procore_submittal_id__isnull=not filter_to_exported)
            filters.pop('exported')

        if filters:
            for filter_key, filter_values in filters.items():
                if filter_key not in self.allowed_filter_keys:
                    raise DRFValidationError(f"Invalid filter key: {filter_key}")
                queryset = self.apply_filter(queryset, filter_key, filter_values)
        
        if order_col:
            if order_col not in self.allowed_order_cols:
                raise DRFValidationError(f"Invalid order column: {order_col}")
            if order not in self.allowed_orders:
                raise DRFValidationError(f"Invalid order direction: {order}")
            queryset = self.apply_order(queryset, order_col, order)
        else:
            queryset = queryset.order_by(
                Case(
                    *[When(spec_section__processing_method=k, then=v) 
                    for k, v in SpecSection.ProcessingMethod.get_order().items()],
                    default=1,
                    output_field=IntegerField(),
                ),
                'masterformat_section__masterformat_number',
                'heirarchical_paragraph_number',
                'submittal_number',
            )
        
        if list_id:
            queryset = queryset.filter(submittal_lists__id=list_id)
        
        if len(records) > 0 and records[0] != 'All':
            records = [int(record) for record in records]
            queryset = queryset.filter(id__in=records)

        return queryset
            

    def perform_create(self, serializer):
        project_id = self.kwargs.get('project_id')
        project = get_object_or_404(Project, id=project_id)
        project_version = serializer.validated_data.get('project_version')
        print(f"project_version: {project_version}")
        print(f"is_versioning_feature_flag_active: {is_versioning_feature_flag_active(self.request.user, project.team)}")
        if is_versioning_feature_flag_active(self.request.user, project.team):
            if not project_version:
                raise DRFValidationError("project_version_id is required when versioning is active")
            if not project_version.project == project:
                raise DRFValidationError("project_version_id does not match project_id")
            serializer.save(created_by=self.request.user, project_id=self.kwargs.get('project_id'), project_version=project_version)
        else:
            project_version = ProjectVersion.objects.filter(project=project, is_archived=False).order_by('-created_at').first()
            serializer.save(created_by=self.request.user, project_id=self.kwargs.get('project_id'), project_version=project_version)

    def perform_update(self, serializer):
        project_id = self.kwargs.get('project_id')
        project = get_object_or_404(Project, id=project_id)
        serializer.save(updated_by=self.request.user, project_id=self.kwargs.get('project_id'))

    def _get_sel_filter_vals(self, result_queryset):
        return {
            'item_desc': result_queryset.values_list('submittal_description', flat=True).distinct().order_by(),
            'para_no': result_queryset.values_list('paragraph_number', flat=True).distinct().order_by(),
            'spec_section': result_queryset.values_list('masterformat_section__masterformat_number', flat=True).distinct().order_by(),
            'type': result_queryset.values_list('submittal_type', flat=True).distinct().order_by(),
        }
    
    def _get_all_filter_vals(self, project_version_id, is_versioning_active):
        project_id = self.kwargs.get('project_id')
        queryset = self.queryset.filter(project_id=project_id)
        if is_versioning_active:
            queryset = queryset.filter(project_version_id=project_version_id)
        queryset = queryset.exclude(submittal_type='Unclassified', masterformat_section__masterformat_number__regex='^0[012]\\d+')
        return {
            'item_desc': queryset.exclude(submittal_description='').values_list('submittal_description', flat=True).distinct().order_by('submittal_description'),
            'para_no': queryset.exclude(paragraph_number='').values_list('paragraph_number', flat=True).distinct().order_by('heirarchical_paragraph_number'),
            'spec_section': queryset.values_list('masterformat_section__masterformat_number', flat=True).distinct().order_by('masterformat_section__masterformat_number'),
            'type': queryset.exclude(submittal_type='').values_list('submittal_type', flat=True).distinct().order_by('submittal_type'),
        }
    
    def _get_all_masterformat_numbers_for_project(self):
        project_id = self.kwargs.get('project_id')
        queryset = self.queryset.filter(project_id=project_id)
        # Do not consider versioning here as we want all masterformat numbers across all versions
        return queryset.values_list('masterformat_section__masterformat_number', flat=True).distinct().order_by('masterformat_section__masterformat_number')

    def _get_submittal_heading_lov(self, result_queryset):
        return result_queryset.values_list('submittal_type', flat=True).distinct().order_by()

    def _get_submittal_type_lov(self, result_queryset):
        return result_queryset.values_list('submittal_description', flat=True).distinct().order_by()

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='project_version_id',
                description='ID of the project version to filter submittal items, if not provided then latest version is used when versioning is active',
                required=False,
                type=OpenApiTypes.INT
            ),
            OpenApiParameter(
                name='search',
                description='Search for submittal items. Search across spec_section, type, item_desc, and para_context',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='filters[<column_name>]',
                description='Filters for submittal items, in the format filters[spec_section]=123,abc',
                required=False,
                type=OpenApiTypes.STR,
                enum=allowed_filter_keys
            ),
            OpenApiParameter(
                name='order_col',
                description='Column to order by',
                required=False,
                type=OpenApiTypes.STR,
                enum=allowed_order_cols
            ),
            OpenApiParameter(
                name='order',
                description='Order direction',
                required=False,
                type=OpenApiTypes.STR,
                enum=allowed_orders
            ),
            OpenApiParameter(
                name='list_id',
                description='ID of the list to filter submittal items',
                required=False,
                type=OpenApiTypes.INT
            ),
            OpenApiParameter(
                name='page_number',
                description='Page number',
                required=False,
                type=OpenApiTypes.INT
            ),
            OpenApiParameter(
                name='limit',
                description='Number of items per page',
                required=False,
                type=OpenApiTypes.INT
            )
        ]
    )
    def list(self, request, *args, **kwargs):
        project_version_id = request.query_params.get('project_version_id')
        project = Project.objects.get(id=kwargs.get('project_id'))
        team = project.team
        self.is_versioning_active = is_versioning_feature_flag_active(request.user, team)
        self.project_version = None
        if self.is_versioning_active:
            if not project_version_id:
                self.project_version = ProjectVersion.objects.filter(project=project, is_archived=False).order_by('-created_at').first()
            else:
                self.project_version = ProjectVersion.objects.get(id=project_version_id)
            if self.project_version.project != project:
                raise DRFValidationError("Not a valid project version for this project")
            
        queryset = self.filter_queryset(self.get_queryset_for_list())
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            data = self.get_paginated_response(serializer.data).data
        else:
            serializer = self.get_serializer(queryset, many=True)
            data = serializer.data

        response_data = {
            'sel_filter_vals': self._get_sel_filter_vals(queryset),
            'all_filter_vals': self._get_all_filter_vals(project_version_id, self.is_versioning_active),
            'all_masterformat_numbers_for_project': self._get_all_masterformat_numbers_for_project(),
            'log_id_list': [log.id for log in queryset],
            'message': data['results'],
            'project_version_id': self.project_version.id if self.project_version else None,
            'total_count': data['count'],
            'submittal_heading_lov': self._get_submittal_heading_lov(queryset),
            'submittal_type_lov': self._get_submittal_type_lov(queryset),
            'has_placeholder_submittals': queryset.filter(parsing_method='PLACEHOLDER').exists(),
        }

        if page is not None:
            response_data['next'] = data['next']
            response_data['previous'] = data['previous']


        return Response(response_data, status=status.HTTP_200_OK)
    

    def destroy(self, request, *args, **kwargs):
        ids = request.data.get('ids', [])
        if ids:
            deleted_count, _ = SubmittalItem.objects.filter(id__in=ids).delete()
            return Response({'deleted_count': deleted_count})
        return super().destroy(request, *args, **kwargs)

    def export_to_xlsx(self, request, *args, **kwargs):
        project_version_id = request.query_params.get('project_version_id')
        project = Project.objects.get(id=kwargs.get('project_id'))
        team = project.team
        self.is_versioning_active = is_versioning_feature_flag_active(request.user, team)
        self.project_version = None
        if self.is_versioning_active:
            if not project_version_id:
                raise DRFValidationError("project_version_id is required when versioning is active")
            else:
                try:
                    self.project_version = ProjectVersion.objects.get(id=project_version_id)
                except ProjectVersion.DoesNotExist:
                    raise DRFValidationError("Not a valid project version for this project")
            if self.project_version.project != project:
                raise DRFValidationError("Not a valid project version for this project")
            
        queryset = self.filter_queryset(self.get_queryset_for_list())
        header_options = []
        try:
            excel_header = ExcelExportHeader.objects.get(user=request.user)
            filtered_options = [item for item in excel_header.options if item['default']]
            idx = 0
            for filtered_option in filtered_options:
                opt = {
                    'col': idx,
                    'name': filtered_option['name'],
                    'width': 75 if filtered_option['name'] == 'Submittal Description' else 25
                }
                header_options.append(opt)
                idx = idx + 1
        except ExcelExportHeader.DoesNotExist:
            pass

        # Create a workbook and select the active worksheet
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.title = "Submittal Items"
        # Define the styles
        text_alignment = Alignment(wrap_text=True, vertical='center')
        header_alignment = Alignment(wrap_text=True, vertical='center')
        header_font = Font(bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='202a44', end_color='202a44', fill_type='solid')
        header_border = Border(right=Side(border_style='thin', color='FFFFFF'))
        # Define the headers
        if len(header_options) == 0:
            headers = ['Submittal #', 'Spec Section', 'Section Title', 'Paragraph', 'Submittal Type',
                    'Submittal Title', 'Submittal Description']
            worksheet.append(headers)
            for col in range(1, len(headers) + 1):
                cell = worksheet.cell(row=1, column=col)
                cell.alignment = header_alignment
                cell.font = header_font
                cell.fill = header_fill
                cell.border = header_border
        else:
            for header_option in header_options:
                cell = worksheet.cell(row=1, column=header_option['col'] + 1)
                cell.value = header_option['name']
                cell.alignment = header_alignment
                cell.font = header_font
                cell.fill = header_fill
                cell.border = header_border

        # Write data to the worksheet
        row_idx = 2
        for item in queryset:
            title_override = item.spec_section.custom_section_title if item.spec_section else None

            if len(header_options) == 0:
                row = [
                    item.submittal_number,
                    item.masterformat_section.masterformat_number,
                    title_override or item.masterformat_section.masterformat_description or masterformat_to_section_title_map.get(item.masterformat_section.masterformat_number, 'Custom Title'),
                    item.paragraph_number,
                    item.submittal_type,
                    item.submittal_description,
                    clean_excel_content(re.sub(ILLEGAL_CHARACTERS_RE, '', item.submittal_content))
                ]
                worksheet.append(row)
                for col in range(1, len(row) + 1):
                    cell = worksheet.cell(row=row_idx, column=col)
                    cell.alignment = text_alignment
            else:
                for header_option in header_options:
                    field_value = ''
                    if header_option['name'] == 'Submittal #':
                        field_value = item.submittal_number
                    elif header_option['name'] == 'Spec Section':
                        field_value = item.masterformat_section.masterformat_number
                    elif header_option['name'] == 'Section Title':
                        field_value = title_override or item.masterformat_section.masterformat_description or masterformat_to_section_title_map.get(item.masterformat_section.masterformat_number, 'Custom Title')
                    elif header_option['name'] == 'Paragraph':
                        field_value = item.paragraph_number
                    elif header_option['name'] == 'Submittal Type':
                        field_value = item.submittal_type
                    elif header_option['name'] == 'Submittal Title':
                        field_value = item.submittal_description
                    elif header_option['name'] == 'Submittal Description':
                        field_value = clean_excel_content(re.sub(ILLEGAL_CHARACTERS_RE, '', item.submittal_content))

                    cell = worksheet.cell(row=row_idx, column=header_option['col'] + 1)
                    cell.value = field_value
                    cell.alignment = text_alignment
            row_idx += 1

        # Adjust column widths
        if len(header_options) == 0:
            for col_num, col in enumerate(worksheet.columns, 1):
                max_length = 0
                column = get_column_letter(col_num)
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(cell.value)
                    except:
                        pass
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[column].width = adjusted_width
        else:
            char = 'A'
            for header_option in header_options:
                worksheet.column_dimensions[char].width = header_option['width']
                char = chr(ord(char) + 1)

        # Create a response object and set the appropriate headers
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename=submittal_items.xlsx'
        
        # Save the workbook to the response
        workbook.save(response)
        
        return response

    @extend_schema(
        summary="Export Submittal Items to XLSX",
        description="Export the filtered submittal items to an XLSX file.",
        parameters=[
            OpenApiParameter(
                name='filters[<column_name>]',
                description='Filters for submittal items, in the format filters[spec_section]=123,abc',
                required=False,
                type=OpenApiTypes.STR,
                enum=allowed_filter_keys
            ),
            OpenApiParameter(
                name='records[]',
                description='A list of submittal item IDs to export or All.',
                required=True,
                type=OpenApiTypes.OBJECT,
                default=['All']
            )
        ],
        responses={
            200: OpenApiResponse(
                description="XLSX file containing the exported submittal items"
            ),
            400: OpenApiResponse(description="Bad Request"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Not Found"),
        }
    )
    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request, *args, **kwargs):
        return self.export_to_xlsx(request, *args, **kwargs)

    def export_to_jet_build(self, request, *args, **kwargs):
        project_version_id = request.query_params.get('project_version_id')
        project = Project.objects.get(id=kwargs.get('project_id'))
        team = project.team
        self.is_versioning_active = is_versioning_feature_flag_active(request.user, team)
        self.project_version = None
        if self.is_versioning_active:
            if not project_version_id:
                raise DRFValidationError("project_version_id is required when versioning is active")
            else:
                try:
                    self.project_version = ProjectVersion.objects.get(id=project_version_id)
                except ProjectVersion.DoesNotExist:
                    raise DRFValidationError("Not a valid project version for this project")
            if self.project_version.project != project:
                raise DRFValidationError("Not a valid project version for this project")
        
        queryset = self.filter_queryset(self.get_queryset_for_list())
        header_options = []

        # Create a workbook and select the active worksheet
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.title = "Submittal Items"
        # Define the styles
        text_alignment = Alignment(wrap_text=True, vertical='center')

        # Write data to the worksheet
        row_idx = 1
        for item in queryset:
            row = [
                item.masterformat_section.masterformat_number[:2],
                ' '.join([item.masterformat_section.masterformat_number[i:i+2] for i in range(2, len(item.masterformat_section.masterformat_number), 2)]),
                item.submittal_description
            ]
            worksheet.append(row)
            for col in range(1, len(row) + 1):
                cell = worksheet.cell(row=row_idx, column=col)
                cell.alignment = text_alignment
            row_idx += 1

        # Adjust column widths
        worksheet.column_dimensions['A'].width = 15
        worksheet.column_dimensions['B'].width = 15
        worksheet.column_dimensions['C'].width = 100

        # Create a response object and set the appropriate headers
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename=submittal_items.xlsx'
        
        # Save the workbook to the response
        workbook.save(response)
        
        return response

    @extend_schema(
        summary="Export Submittal Items to Jet Build XLSX",
        description="Export the filtered submittal items to an XLSX file. XLSX file doesn't have header and it's formatted for Jet Build.",
        parameters=[
            OpenApiParameter(
                name='filters[<column_name>]',
                description='Filters for submittal items, in the format filters[spec_section]=123,abc',
                required=False,
                type=OpenApiTypes.STR,
                enum=allowed_filter_keys
            ),
            OpenApiParameter(
                name='records[]',
                description='A list of submittal item IDs to export or All.',
                required=True,
                type=OpenApiTypes.OBJECT,
                default=['All']
            )
        ],
        responses={
            200: OpenApiResponse(
                description="XLSX file containing the exported submittal items"
            ),
            400: OpenApiResponse(description="Bad Request"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Not Found"),
        }
    )
    @action(detail=False, methods=['get'], url_path='export-jet-build')
    def export_jet_build(self, request, *args, **kwargs):
        return self.export_to_jet_build(request, *args, **kwargs)
    

@extend_schema(
    summary="Combine multiple submittal items into one.",
    request=CombineSubmittalItemsSerializer,
    responses={200: {'description': 'Rows combined'}},
    description="Combine multiple submittal items into one.",
    methods=["POST"]
)
@api_view(['POST'])
def combine_rows(request):
    def _ensure_not_str(obj):
        if not isinstance(obj, str):
            return obj
        return _ensure_not_str(ast.literal_eval(obj))

    serializer = CombineSubmittalItemsSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    project_id = serializer.validated_data['project_id']
    project = Project.objects.get(id=project_id)
    if not request.user.is_member_of_project(project):
        return Response({'detail': 'User is not a member of the project'}, status=status.HTTP_403_FORBIDDEN)


    lst_all_logs_id = []
    lst_all_logs_spec_section = []
    lst_all_logs = []
    # lst_page_no = []
    lst_index = []
    for log in serializer.validated_data['lst_all_logs']:
        lst_all_logs_id.append(log['id'])
        lst_all_logs_spec_section.append(log['spec_section'])
        # lst_page_no.append(log['page_no'])
        lst_index.append(log['index'])

    # Combine all lists into a single list of tuples for sorting
    combined_logs = list(zip(
        lst_all_logs_spec_section,
        lst_all_logs_id,
        # lst_page_no,
        lst_index,
    ))

    # Sort the combined logs based on page number and then by index number
    sorted_combined_logs = sorted(
        combined_logs,
        key=lambda x: (
            # x[2],  # page_no
            x[2],
        ),
    )

    # Extract the sorted sorted_combined_logs
    sorted_lst_all_logs_id = [x[1] for x in sorted_combined_logs]

    logging.info(sorted_combined_logs)
    for log_id in sorted_lst_all_logs_id:
        for log in serializer.validated_data['lst_all_logs']:
            if log['id'] == log_id:
                lst_all_logs.append(log)

    get_db_logs = SubmittalItem.objects.filter(project_id=project_id, id__in=sorted_lst_all_logs_id)
    
    if not len(get_db_logs) == len(sorted_lst_all_logs_id):
        return Response({'detail': 'Log ID not found'}, status=status.HTTP_400_BAD_REQUEST)

    # Get the first log
    first_log = None
    logging.info(sorted_lst_all_logs_id)
    for log in get_db_logs:
        logging.info(log.id)
        logging.info(sorted_lst_all_logs_id[0])
        if log.id == sorted_lst_all_logs_id[0]:
            first_log = log
            break

    prepared_object = serializer.validated_data['prepared_object']

    # Update the first log with the prepared object
    first_log.submittal_description = prepared_object['item_desc']
    first_log.submittal_type = prepared_object['type']

    target_additional_text_locations = []
    initial_add_text_locs = first_log.additional_text_locations
    if initial_add_text_locs:
        initial_add_text_locs = _ensure_not_str(
            initial_add_text_locs or []
        )
        target_additional_text_locations.extend(initial_add_text_locs)

    for log in get_db_logs:
        if log.id == sorted_lst_all_logs_id[0]:
            continue

        if log.submittal_content != first_log.submittal_content:
            first_log.submittal_content += '\n' + log.submittal_content

        text_loc = _ensure_not_str(log.text_location)
        additional_text_locations = (
            _ensure_not_str(
                log.additional_text_locations or []
            )
        )

        if text_loc:
            target_additional_text_locations.append(text_loc)

        if additional_text_locations:
            target_additional_text_locations.extend(additional_text_locations)

    first_log.additional_text_locations = list(
        target_additional_text_locations,
    )

    first_log.save()

    # Delete the rest of data
    SubmittalItem.objects.filter(id__in=sorted_lst_all_logs_id[1:]).delete()

    return Response({'message': 'Rows combined'}, status=status.HTTP_200_OK)

def get_file_hash(uploaded_file):
    md5_hash = hashlib.md5()
    for chunk in uploaded_file.chunks():
        md5_hash.update(chunk)
    return md5_hash.hexdigest()


def has_differences(difference_summary):
    return len(difference_summary['additions']) > 0 or len(difference_summary['deletions']) > 0 or len(difference_summary['modifications']) > 0

def convert_difference_summary_to_api_format(difference_summary, only_include_differences=False, keyword=None):
    all_differences = []
    for addition in difference_summary['additions']:
        if keyword:
            if keyword.lower() in addition.submittal_description.lower() or keyword.lower() in addition.submittal_content.lower():
                all_differences.append({
                    'difference_type': 'addition',
                    'new_submittal': addition,
                })
        else:
            all_differences.append({
                'difference_type': 'addition',
                'new_submittal': addition,
            })
    for deletion in difference_summary['deletions']:
        if keyword:
            if keyword.lower() in deletion.submittal_description.lower() or keyword.lower() in deletion.submittal_content.lower():
                all_differences.append({
                    'difference_type': 'deletion',
                    'old_submittal': deletion,
                })
        else:
            all_differences.append({
                'difference_type': 'deletion',
                'old_submittal': deletion,
            })
    for modification in difference_summary['modifications']:
        if keyword:
            if (keyword.lower() in modification['old_submittal'].submittal_description.lower()
                 or keyword.lower() in modification['old_submittal'].submittal_content.lower()
                 or keyword.lower() in modification['new_submittal'].submittal_description.lower()
                 or keyword.lower() in modification['new_submittal'].submittal_content.lower()
            ):
                all_differences.append({
                    'difference_type': 'modification',
                    'old_submittal': modification['old_submittal'],
                    'new_submittal': modification['new_submittal'],
                    'content_differences': modification['content_differences'],
                    'paragraph_number_differences': modification['paragraph_number_differences'],
                })
        else:
            all_differences.append({
                'difference_type': 'modification',
                'old_submittal': modification['old_submittal'],
                'new_submittal': modification['new_submittal'],
                'content_differences': modification['content_differences'],
                'paragraph_number_differences': modification['paragraph_number_differences'],
            })
    if not only_include_differences:
        for unchanged in difference_summary['unchanged']:
            if keyword:
                if keyword.lower() in unchanged.submittal_description.lower() or keyword.lower() in unchanged.submittal_content.lower():
                    all_differences.append({
                        'difference_type': 'unchanged',
                        'old_submittal': unchanged,
                        'new_submittal': unchanged,
                    })
            else:
                all_differences.append({
                    'difference_type': 'unchanged', 
                    'old_submittal': unchanged,
                    'new_submittal': unchanged,
                })
    def get_hierarchical_paragraph_number(difference):
        if difference['difference_type'] == 'addition':
            return difference['new_submittal'].heirarchical_paragraph_number
        elif difference['difference_type'] == 'deletion':
            return difference['old_submittal'].heirarchical_paragraph_number
        else:
            return difference['new_submittal'].heirarchical_paragraph_number

    all_differences = sorted(all_differences, key=lambda x: get_hierarchical_paragraph_number(x))
    return all_differences


@extend_schema(
    summary="Get the differences between two versions of a project.",
    request=VersionComparisonSerializer,
    responses={
        200: VersionComparisonSerializer, 
        400: OpenApiResponse(description="Bad Request"),
        401: OpenApiResponse(description="Unauthorized"),
        403: OpenApiResponse(description="Forbidden"),
        404: OpenApiResponse(description="Not Found"),
    },
    description="Get the differences between two versions of a project.",
    methods=["GET"]
)
@api_view(['GET'])
def get_version_comparison(request):
    serializer = VersionComparisonSerializer(data=request.query_params)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    old_version = serializer.validated_data['old_version']
    new_version = serializer.validated_data['new_version']
    masterformat_number = serializer.validated_data['masterformat_number']
    project = Project.objects.get(id=old_version.project_id)
    if not request.user.is_member_of_project(project):
        return Response({'detail': 'User is not a member of the project'}, status=status.HTTP_403_FORBIDDEN)

    if old_version.project_id != new_version.project_id:
        return Response({'detail': 'Old and new versions must be from the same project'}, status=status.HTTP_400_BAD_REQUEST)
    
    difference_summary = VersionComparisonService.compare_versions(old_version, new_version, masterformat_number)
    print(difference_summary)

    all_differences = convert_difference_summary_to_api_format(difference_summary)

    output_serializer = VersionComparisonSerializer(
        instance={
            'old_version': old_version,
            'new_version': new_version,
            'masterformat_number': masterformat_number,
            'differences': all_differences
        }
    )

    return Response(output_serializer.data, status=status.HTTP_200_OK)



@extend_schema(
    summary="Get the differences between two versions of a project, filtered by a keyword.",
    request=FilteredVersionComparisonSerializer,
    responses={
        200: FilteredVersionComparisonSerializer, 
        400: OpenApiResponse(description="Bad Request"),
        401: OpenApiResponse(description="Unauthorized"),
        403: OpenApiResponse(description="Forbidden"),
        404: OpenApiResponse(description="Not Found"),
    },
    description="Get the differences between two versions of a project, filtered by a keyword.",
    methods=["GET"]
)
@api_view(['GET'])
def get_filtered_version_comparison(request):
    serializer = FilteredVersionComparisonSerializer(data=request.query_params)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    old_version = serializer.validated_data['old_version']
    new_version = serializer.validated_data['new_version']
    keyword = serializer.validated_data.get('keyword', '')
    only_differences = serializer.validated_data['only_differences']

    project = Project.objects.get(id=old_version.project_id)
    if not request.user.is_member_of_project(project):
        return Response({'detail': 'User is not a member of the project'}, status=status.HTTP_403_FORBIDDEN)

    if old_version.project_id != new_version.project_id:
        return Response({'detail': 'Old and new versions must be from the same project'}, status=status.HTTP_400_BAD_REQUEST)
    
    if keyword:
        masterformat_numbers_with_desired_differences = SubmittalItem.objects.filter(
            Q(submittal_description__icontains=keyword) | Q(submittal_content__icontains=keyword),
            project=project,
            project_version__in=[new_version, old_version],
        ).values_list('masterformat_section__masterformat_number', flat=True).distinct()
    else:
        masterformat_numbers_with_desired_differences = SubmittalItem.objects.filter(
            project=project,
            project_version__in=[new_version, old_version],
        ).values_list('masterformat_section__masterformat_number', flat=True).distinct()
    masterformat_numbers_with_desired_differences = list(masterformat_numbers_with_desired_differences)
    print(f"Masterformat numbers with desired differences: {masterformat_numbers_with_desired_differences}")

    comparison_data = []
    masterformat_numbers_to_return = []

    for masterformat_number in masterformat_numbers_with_desired_differences:
        masterformat_number = str(masterformat_number)
        print(f"Comparing {old_version} and {new_version} for masterformat number {masterformat_number}")
        difference_summary = VersionComparisonService.compare_versions(old_version, new_version, masterformat_number)
        print(difference_summary)
        if only_differences and not has_differences(difference_summary):
            continue

        all_differences = convert_difference_summary_to_api_format(
            difference_summary,
            only_include_differences=only_differences,
            keyword=keyword
        )
        if not all_differences:
            continue

        masterformat_numbers_to_return.append(masterformat_number)
        comparison_data.append({
            'old_version': old_version,
            'new_version': new_version,
            'masterformat_number': masterformat_number,
            'differences': all_differences
        })

    output_serializer = FilteredVersionComparisonSerializer(
        instance={
            'keyword': keyword,
            'only_differences': only_differences,
            'old_version': old_version,
            'new_version': new_version,
            'masterformat_numbers_with_desired_differences': masterformat_numbers_to_return,
            'comparison': comparison_data
        }
    )

    return Response(output_serializer.data, status=status.HTTP_200_OK)


def invoke_lambda(payload, lambda_url):
    try:
        requests.post(lambda_url, json=payload, timeout=2)
    except requests.exceptions.ReadTimeout:
        # if we timed out, it's a larger document and the lambda is processing it
        pass

def parse_spec(
    callback_url, 
    document_id, 
    project_id, 
    project_version_id, 
    object_key, 
    filename, 
    user_id, 
    is_v2_process_deliverables_flag_active, 
    is_specgpt_flag_active,
    specgpt_callback_url
):
    logging.debug(f"parse_spec: {object_key}")

    payload = {
        "object_key": object_key,
        "document_id": str(document_id),
        "filename": filename,
        "user_id": user_id,
        "project_id": project_id,
        "project_version_id": str(project_version_id),
        "callback_url": callback_url,
        "ENVIRONMENT": settings.ENVIRONMENT,
        "AWS_UPLOAD_BUCKET": settings.S3_BUCKET,
        "is_specgpt_flag_active": is_specgpt_flag_active,
        "chunk_size": settings.SPECGPT_CHUNK_SIZE,
        "chunk_overlap": settings.SPECGPT_CHUNK_OVERLAP,
        "pinecone_index_name": settings.PINECONE_INDEX_NAME,
        "specgpt_callback_url": specgpt_callback_url
    }

    # update the document status to processing
    UploadedFile.objects.filter(id=document_id).update(last_retry=datetime.now())

    print(f"Invoking lambda with URL: {settings.LAMBDA_FUNCTION_URL if not is_v2_process_deliverables_flag_active else settings.V2_PROCESS_DELIVERABLES_LAMBDA_FUNCTION_URL}")
    print(f"Invoking lambda with payload: {payload}")

    invoke_lambda(
        payload=payload,
        lambda_url=settings.LAMBDA_FUNCTION_URL if not is_v2_process_deliverables_flag_active else settings.V2_PROCESS_DELIVERABLES_LAMBDA_FUNCTION_URL
    )

    return "Kicked off processing job"



def call_full_spec_processing_lambda(
    callback_url, 
    document_id, 
    project_id, 
    project_version_id, 
    object_key, 
    filename, 
    user_id
):
    logging.debug(f"call_full_spec_processing_lambda: {object_key}")

    CHUNK_SIZE = 1200
    CHUNK_OVERLAP = 100

    payload = {
        "object_key": object_key,
        "document_id": str(document_id),
        "filename": filename,
        "user_id": user_id,
        "project_id": project_id,
        "project_version_id": str(project_version_id),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "callback_url": callback_url,
        "ENVIRONMENT": settings.ENVIRONMENT,
        "AWS_UPLOAD_BUCKET": settings.S3_BUCKET,
        "full_spec_processing": True
    }

    # update the document status to processing
    UploadedFile.objects.filter(id=document_id).update(last_retry=datetime.now())

    print(f"Invoking lambda with URL: {settings.FULL_SPEC_PROCESSING_LAMBDA_FUNCTION_URL}")
    print(f"Invoking lambda with payload: {payload}")

    invoke_lambda(
        payload=payload,
        lambda_url=settings.FULL_SPEC_PROCESSING_LAMBDA_FUNCTION_URL
    )

    return "Kicked off processing job"


def call_extract_notices_lambda(callback_url, document_id, object_key, project_version_id):
    logging.debug(f"call_extract_notices_lambda: {object_key}")

    payload = {
        "source_file_s3_uri": f"s3://{settings.S3_BUCKET}/{object_key}",
        "document_id": str(document_id),
        "project_version_id": str(project_version_id),
        "callback_url": callback_url,
        "ENVIRONMENT": settings.ENVIRONMENT,
    }

    # update the document status to processing
    UploadedFile.objects.filter(id=document_id).update(last_retry=datetime.now())

    print(f"Invoking lambda with URL: {settings.NOTICES_LAMBDA_FUNCTION_URL}")
    print(f"Invoking lambda with payload: {payload}")

    invoke_lambda(
        payload=payload,
        lambda_url=settings.NOTICES_LAMBDA_FUNCTION_URL
    )

    return "Kicked off processing job"


def call_extract_drawing_notes_lambda(
    callback_url,
    project_id,
    project_version_id,
    drawing_file_id,
    extraction_id,
    file_s3_key,
    use_llm=False,
):
    logging.debug(f"call_extract_drawing_notes_lambda: {file_s3_key}")

    if not settings.DRAWINGS_LAMBDA_FUNCTION_URL:
        raise ValueError("DRAWINGS_LAMBDA_FUNCTION_URL is not set")

    payload = {
        "source_file_s3_uri": f"s3://{settings.S3_BUCKET}/{file_s3_key}",
        "callback_url": callback_url,
        "project_id": str(project_id),
        "project_version_id": str(project_version_id),
        "drawing_file_id": str(drawing_file_id),
        "extraction_id": str(extraction_id),
        "ENVIRONMENT": settings.ENVIRONMENT,
        "AWS_UPLOAD_BUCKET": settings.S3_BUCKET,
        "use_llm": bool(use_llm),
    }

    print(f"Invoking lambda with URL: {settings.DRAWINGS_LAMBDA_FUNCTION_URL}")
    print(f"Invoking lambda with payload: {payload}")

    invoke_lambda(
        payload=payload,
        lambda_url=settings.DRAWINGS_LAMBDA_FUNCTION_URL
    )

    return "Kicked off drawing extraction job"


def upload_to_s3_and_process(file_data):
    """Handle S3 upload and Lambda processing for a single file"""
    try:
        file = file_data['file']
        file.seek(0)
        s3.upload_fileobj(
            Fileobj=file,
            Bucket=settings.S3_BUCKET,
            Key=file_data['document_path'],
        )

        if file_data['is_notices_flag_active'] and file_data['extract_notices']:
            call_extract_notices_lambda(
                callback_url=settings.BACKEND_NOTICES_CALLBACK_URL,
                document_id=str(file_data['uploaded_file_id']),
                object_key=file_data['document_path'],
                project_version_id=str(file_data['project_version_id']),
            )
        elif file_data['is_full_spec_processing_flag_active'] and file_data['full_spec_processing']:
            call_full_spec_processing_lambda(
                callback_url=settings.BACKEND_FULL_SPEC_PROCESSING_CALLBACK_URL,
                document_id=str(file_data['uploaded_file_id']),
                project_id=str(file_data['project_id']),
                project_version_id=str(file_data['project_version_id']),
                object_key=file_data['document_path'],
                filename=file_data['filename'],
                user_id=str(file_data['user_id']),
            )
        else:
            parse_spec(
                callback_url=settings.BACKEND_CALLBACK_URL,
                document_id=str(file_data['uploaded_file_id']),
                project_id=str(file_data['project_id']),
                project_version_id=str(file_data['project_version_id']),
                object_key=file_data['document_path'],
                filename=file_data['filename'],
                user_id=str(file_data['user_id']),
                is_v2_process_deliverables_flag_active=file_data['is_v2_process_deliverables_flag_active'],
                is_specgpt_flag_active=file_data['is_specgpt_flag_active'],
                specgpt_callback_url=settings.BACKEND_SPECGPT_CALLBACK_URL
            )
        return {'status': 'success', 'document_path': file_data['document_path']}
    except Exception as e:
        logging.error(f"Error processing file {file_data['filename']}: {e}")
        return {'status': 'error', 'filename': file_data['filename'], 'error': str(e)}
    finally:
        connection.close()


@extend_schema(
    request=FileUploadSerializer,
    responses={200: {'description': 'File uploaded successfully'}},
    description="Upload a file to the server.",
    methods=["POST"]
)
@api_view(['POST'])
def upload_file(request):
    if not request.user.is_authenticated:
        return Response({'detail': 'User is not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        serializer = FileUploadSerializer(data=request.data)
    except TooManyFilesSent as e:
        return Response({'error': 'TOO_MANY_FILES', 'detail': f'You can only upload up to {settings.DATA_UPLOAD_MAX_NUMBER_FILES} files at once'}, status=status.HTTP_400_BAD_REQUEST)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    project_id = serializer.validated_data['project_id']
    print(serializer.validated_data)
    extract_notices = serializer.validated_data.get('extract_notices', False)
    full_spec_processing = serializer.validated_data.get('full_spec_processing', False)
    project = Project.objects.get(id=project_id)
    if not request.user.is_member_of_project(project):
        return Response({'detail': 'User is not a member of the project'}, status=status.HTTP_403_FORBIDDEN)

    user = request.user
    files = serializer.validated_data['files']

    if not files:
        return Response({'detail': 'No files provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    files_to_process = []
    already_existing_files = []
    duplicate_files_for_confirmation = []
    async_processing = []
    not_parsed = []

    is_notices_flag_active = is_notices_feature_flag_active(request.user, project.team)
    is_versioning_flag_active = is_versioning_feature_flag_active(request.user, project.team)
    is_v2_process_deliverables_flag_active = is_v2_process_deliverables_feature_flag_active(request.user, project.team, project)
    is_full_spec_processing_flag_active = is_full_spec_processing_feature_flag_active(request.user, project.team, project)
    is_specgpt_flag_active = is_specgpt_feature_flag_active(request.user, project.team, project)

    print(f"is_notices_flag_active: {is_notices_flag_active}")
    print(f"is_versioning_flag_active: {is_versioning_flag_active}")

    if not is_versioning_flag_active:
        print("is_versioning_flag_active is false, using latest project version")
        project_version_id = ProjectVersion.objects.filter(project=project, is_archived=False).order_by('-created_at').first().id
    else:
        project_version_id = serializer.validated_data.get('project_version_id')
        print(f"versioning is active, project_version_id: {project_version_id}")
        if not project_version_id:
            if is_full_spec_processing_flag_active:
                project_version_id = ProjectVersion.objects.filter(project=project, is_archived=False).order_by('-created_at').first().id
            else:
                return Response({'detail': 'Versioning is active but no project_version_id was provided'}, status=status.HTTP_400_BAD_REQUEST)

    # Handle drawing file uploads
    file_type = serializer.validated_data.get('file_type', 'spec')
    print(f"[DRAWING UPLOAD] file_type={file_type}, project_id={project_id}, version_id={project_version_id}")
    if file_type == 'drawing':
        print(f"[DRAWING UPLOAD] Processing {len(files)} drawing file(s)")
        project_version = ProjectVersion.objects.get(id=project_version_id)
        uploaded_drawings = []
        for file in files:
            try:
                print(f"[DRAWING UPLOAD] Processing file: {file.name}, size={file.size}")
                file_md5 = get_file_hash(file)
                print(f"[DRAWING UPLOAD] File hash: {file_md5}")
                filename = f'project_{project_id}__version_{project_version_id}__{int(time.time())}_{file.name}'
                s3_key = f'drawings/{filename}'
                print(f"[DRAWING UPLOAD] S3 key: {s3_key}")

                # Check for existing DrawingFile with same md5, name, project, and version
                existing_drawing = DrawingFile.objects.filter(
                    md5=file_md5,
                    file_name=file.name,
                    project=project,
                    project_version=project_version
                ).first()

                if existing_drawing:
                    # Reuse existing DrawingFile record
                    print(f"[DRAWING UPLOAD] Found existing DrawingFile id={existing_drawing.id}")
                    drawing_file = existing_drawing
                else:
                    # Reset file pointer after hashing, then upload to S3
                    file.seek(0)
                    file_size_after_seek = file.size
                    print(f"[DRAWING UPLOAD] Uploading to S3 bucket={settings.S3_BUCKET}, key={s3_key}, size={file_size_after_seek}")
                    s3.upload_fileobj(file, settings.S3_BUCKET, s3_key)
                    print(f"[DRAWING UPLOAD] S3 upload completed")

                    # Create new DrawingFile
                    drawing_file = DrawingFile.objects.create(
                        project=project,
                        project_version=project_version,
                        uploaded_by=user,
                        file_name=file.name,
                        file_s3_key=s3_key,
                        md5=file_md5,
                    )
                    print(f"[DRAWING UPLOAD] Created DrawingFile id={drawing_file.id}")

                # Always create a new DrawingExtraction for each upload
                extraction = DrawingExtraction.objects.create(
                    drawing_file=drawing_file,
                    status=DrawingExtractionStatus.PENDING,
                )
                print(f"[DRAWING UPLOAD] Created DrawingExtraction id={extraction.id}")

                try:
                    call_extract_drawing_notes_lambda(
                        callback_url=settings.BACKEND_DRAWINGS_CALLBACK_URL,
                        project_id=project_id,
                        project_version_id=project_version_id,
                        drawing_file_id=drawing_file.id,
                        extraction_id=extraction.id,
                        file_s3_key=drawing_file.file_s3_key,
                    )
                except Exception as e:
                    logging.error(f"[DRAWING UPLOAD] Failed to invoke drawing extraction lambda: {e}")
                    not_parsed.append(file.name)

                uploaded_drawings.append({
                    'drawing_file_id': drawing_file.id,
                    'extraction_id': extraction.id,
                    'file_name': file.name,
                    'status': 'pending'
                })
            except Exception as e:
                import traceback
                print(f"[DRAWING UPLOAD] Error uploading drawing file {file.name}: {e}")
                traceback.print_exc()
                not_parsed.append(file.name)

        return Response({
            'drawings': uploaded_drawings,
            'error_parsing': not_parsed,
            'message': 'Drawing files uploaded successfully'
        }, status=status.HTTP_200_OK)

    for file in files:
        try:
            filename = f'project_{project_id}__version_{project_version_id}__{int(time.time())}_{file.name}'
            document_path = f'original/{filename}'
            parsed_document_path = f'parsed/{filename}'
            file_md5 = get_file_hash(file)

            # check if file already exists
            matching_files = UploadedFile.objects.filter(md5=file_md5, name=file.name, project_id=project_id, project_version_id=project_version_id)
            if matching_files.exists():
                # Instead of skipping, add to confirmation list with existing file info
                existing_file = matching_files.first()
                duplicate_files_for_confirmation.append({
                    'filename': file.name,
                    'existing_file_id': existing_file.id,
                    'existing_file_name': existing_file.name,
                    'upload_date': existing_file.created_at.isoformat() if existing_file.created_at else None
                })
                continue

            processing_method = UploadedFile.ProcessingMethodChoices.V1 if not is_v2_process_deliverables_flag_active else UploadedFile.ProcessingMethodChoices.V2
            if is_full_spec_processing_flag_active:
                processing_method = UploadedFile.ProcessingMethodChoices.FULL_SPEC_PROCESSING

            uploaded_file = UploadedFile.objects.create(
                project_id=project_id,
                project_version_id=project_version_id,
                uploaded_by=user,
                name=file.name,
                md5=file_md5,
                document_path=document_path,
                parsed_document_path=parsed_document_path,
                processing_status='PENDING_PROCESSING',
                processing_method=processing_method,
                specgpt_embedding_enabled=is_specgpt_flag_active,
                specgpt_processing_status=UploadedFile.SpecgptProcessingStatusChoices.IN_QUEUE if is_specgpt_flag_active else UploadedFile.SpecgptProcessingStatusChoices.NONE
            )

            files_to_process.append({
                'file': file,
                'filename': file.name,
                'document_path': document_path,
                'uploaded_file_id': uploaded_file.id,
                'project_id': project_id,
                'project_version_id': project_version_id,
                'user_id': request.user.id,
                'is_notices_flag_active': is_notices_flag_active,
                'is_v2_process_deliverables_flag_active': is_v2_process_deliverables_flag_active,
                'is_full_spec_processing_flag_active': is_full_spec_processing_flag_active,
                'extract_notices': extract_notices,
                'full_spec_processing': full_spec_processing,
                'is_specgpt_flag_active': is_specgpt_flag_active
            })
        except Exception as e:
            logging.error(f"Error uploading file: {e}")
            not_parsed.append(file.name)

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(upload_to_s3_and_process, files_to_process))

    # Process results
    for result in results:
        if result['status'] == 'success':
            async_processing.append(result['document_path'])
        else:
            not_parsed.append(result['filename'])
            # Update the status of failed uploads
            UploadedFile.objects.filter(
                name=result['filename'],
                project_id=project_id
            ).update(processing_status='FAILED')
        
    return Response({
        'error_parsing': not_parsed,
        'already_exist': already_existing_files,
        'duplicate_files_for_confirmation': duplicate_files_for_confirmation,
        'async_processing': async_processing,
        'message': 'Files uploaded successfully'
    }, status=status.HTTP_200_OK)


def change_encode_value(text):
    if '\uf0a3' in text:
        text = re.sub('\uf0a3', '≤', text)
    if '\uf0b2' in text:
        text = re.sub('\uf0b2', '”', text)
    if '\uf0b0' in text:
        text = re.sub('\uf0b0', 'º', text)
    if '\uf0a2' in text:
        text = re.sub('\uf0a2', '’', text)
    return text


# region submittal webhook
# TODO: Move to separate file

def save_submittal_items(submittals, masterformat_section_number, spec_section, project_id, project_version_id, document_id):
    for submittal in submittals:
        submittal_text = change_encode_value(submittal['submittal_text'])
        masterformat_section, created = MasterFormatSection.objects.get_or_create(masterformat_number=masterformat_section_number)
        submittal_item = SubmittalItem.objects.create(
            project_id=project_id,
            project_version_id=project_version_id,
            masterformat_section=masterformat_section,
            spec_section=spec_section,
            submittal_type=submittal['submittal_type'],
            submittal_description=submittal['submittal_description'],
            submittal_content=submittal_text,
            paragraph_number=submittal.get('section', '') or '',
            text_location=submittal.get('text_location'),
            document_id=document_id,
            parsing_method=submittal.get('parsing_method', 'UNKNOWN'),
            additional_text_locations=submittal.get('additional_text_locations', [])
        )

@extend_schema(
    request=FileUploadSerializer,
    responses={200: {'description': 'File uploaded successfully'}},
    description="Upload a file to the server.",
    methods=["POST"]
)
@api_view(['POST'])
@permission_classes([AllowAny])
def spec_status_webhook(request):
    request_payload = request.data
    print(f"SPEC STATUS WEBHOOK received request: {request_payload}")

    request_data = SpecStatusRequest(**request_payload)

    if request_data['new_status'] == 'SUBSECTIONS_EXTRACTED':
        print(f"SPEC STATUS WEBHOOK: setting document {request_data['document_id']} processing status to SUBSECTIONS_EXTRACTED")
        UploadedFile.objects.filter(id=int(request_data['document_id'])).update(
            processing_status=DocProcessingStatus.SUBSECTIONS_EXTRACTED,
            specgpt_processing_status=UploadedFile.SpecgptProcessingStatusChoices.SUBSECTIONS_EXTRACTED
        )
        if not request_data['subsections']:
            print(f"SPEC STATUS WEBHOOK: no subsections found for document {request_data['document_id']}, marking as processed")
            UploadedFile.objects.filter(id=int(request_data['document_id'])).update(
                processing_status=DocProcessingStatus.PROCESSED,
                specgpt_processing_status=UploadedFile.SpecgptProcessingStatusChoices.PROCESSED
            )
            return Response(status=status.HTTP_200_OK)
        for subsection in request_data['subsections']:
            print(f"SPEC STATUS WEBHOOK: inserting subsection {subsection['master_format_section_number']} for document {request_data['document_id']}")
            masterformat_section, created = MasterFormatSection.objects.get_or_create(masterformat_number=subsection['master_format_section_number'])
            section, created = SpecSection.objects.get_or_create(
                document_id=request_data['document_id'],
                masterformat_section=masterformat_section,
                file_s3_key=subsection.get('file_s3_key')
            )
            section.processing_status = DocProcessingStatus.PENDING_PROCESSING
            section.save()
    elif request_data['new_status'] == 'PROCESSED_SECTION':
        print(f"SPEC STATUS WEBHOOK: saving submittals")
        spec_sections = SpecSection.objects.filter(
            document_id=int(request_data['document_id']),
            masterformat_section__masterformat_number=request_data['master_format_section_number'],
        )
        if request_data.get('file_s3_key'):
            spec_section = spec_sections.filter(file_s3_key=request_data['file_s3_key']).first()
        else:
            spec_section = spec_sections.first()
        project_version_id = request_data.get('project_version_id')
        version_from_spec_section = spec_section.document.project_version.id
        if project_version_id and str(project_version_id) != str(version_from_spec_section):
            print(f"SPEC STATUS WEBHOOK: project_version_id {project_version_id} does not match version from spec section {version_from_spec_section}")
            return Response(status=status.HTTP_400_BAD_REQUEST)
        if not project_version_id:
            project_version_id = version_from_spec_section
        save_submittal_items(request_data['submittals'], request_data['master_format_section_number'], spec_section, request_data['project_id'], project_version_id, request_data['document_id'])
        if len(request_data['submittals']) == 1 and request_data['submittals'][0]['parsing_method'] == 'PLACEHOLDER':
            processing_method = 'REGEX_UNABLE_TO_DETECT_SUBMITTALS'
        else:
            processing_method = 'REGEX_SUCCESS' 
        spec_section.processing_status = DocProcessingStatus.PROCESSED
        spec_section.processing_method = processing_method
        spec_section.save()
    elif request_data['new_status'] == 'FAILED':
        print(f"SPEC STATUS WEBHOOK: received failure for request: {request_data}")
        document = UploadedFile.objects.filter(id=int(request_data['document_id'])).first()
        masterformat_section_number = request_data.get('master_format_section_number')
        if masterformat_section_number:
            spec_section = SpecSection.objects.filter(
                document_id=int(request_data['document_id']),
                masterformat_section__masterformat_number=masterformat_section_number
            ).first()
        else:
            spec_section = None
        if document.processing_status == DocProcessingStatus.SUBSECTIONS_EXTRACTED:
            print(f"SPEC STATUS WEBHOOK: setting document {request_data['document_id']} processing status to SECTION_PROCESSING_FAILED")
            document.processing_status = DocProcessingStatus.SECTION_PROCESSING_FAILED
            document.save()
            if spec_section:
                submittals = request_data.get('submittals', [])
                save_submittal_items(submittals, request_data['master_format_section_number'], spec_section, request_data['project_id'], request_data.get('project_version_id'), request_data['document_id'])
        else:
            print(f"SPEC STATUS WEBHOOK: setting document {request_data['document_id']} processing status to FAILED")
            document.processing_status = DocProcessingStatus.FAILED
            document.save()
    """IF document.processing_status == SUBSECTIONS_EXTRACTED or SECTION_PROCESSING_FAILED then we have records of all extracted subsections.
    If so, then update document.processing_status to PROCESSED if all subsections have been processed"""
    print(f"SPEC STATUS WEBHOOK: checking if all subsections have been processed for document {request_data['document_id']}")
    document = UploadedFile.objects.filter(id=int(request_data['document_id'])).first()
    if document.processing_status in [DocProcessingStatus.SUBSECTIONS_EXTRACTED, DocProcessingStatus.SECTION_PROCESSING_FAILED]:
        print(f"SPEC STATUS WEBHOOK: getting unprocessed section count for document {request_data['document_id']}")
        unprocessed_spec_section_count = SpecSection.objects.filter(document_id=request_data['document_id']).exclude(
            processing_status=DocProcessingStatus.PROCESSED
        ).exclude(
            masterformat_section__masterformat_number__regex='^0[012]' # exclude divisions 00,01,02
        ).count()
        print(f"SPEC STATUS WEBHOOK: unprocessed_spec_section_count: {unprocessed_spec_section_count}")
        if unprocessed_spec_section_count == 0:
            print(f"SPEC STATUS WEBHOOK: all subsections have been processed for document {request_data['document_id']}")
            document.processing_status = DocProcessingStatus.PROCESSED
            document.save()

    logger.debug(f"SPEC STATUS WEBHOOK: determining whether to assign submittal numbers...")
    SubmittalService.assign_submittal_numbers(
        # TODO: Replace `int` cast here with actually enforcing integer input
        project=int(request_data['project_id']),
        project_version_id=int(document.project_version.id),
        only_if_all_documents_processed=True,
    )

    return Response(status=status.HTTP_200_OK)



@api_view(['POST'])
@permission_classes([AllowAny])
def full_spec_processing_webhook(request):
    request_payload = request.data
    print(f"FULL SPEC PROCESSING WEBHOOK received request: {request_payload}")

    request_data = FullSpecProcessingRequest(**request_payload)

    if request_data['new_status'] == 'SUBSECTIONS_EXTRACTED':
        print(f"FULL SPEC PROCESSING WEBHOOK: setting document {request_data['document_id']} processing status to SUBSECTIONS_EXTRACTED")
        UploadedFile.objects.filter(id=int(request_data['document_id'])).update(processing_status=DocProcessingStatus.SUBSECTIONS_EXTRACTED)
        for subsection in request_data['subsections']:
            print(f"FULL SPEC PROCESSING WEBHOOK: inserting subsection {subsection['master_format_section_number']} for document {request_data['document_id']}")
            masterformat_section, created = MasterFormatSection.objects.get_or_create(masterformat_number=subsection['master_format_section_number'])
            section, created = SpecSection.objects.get_or_create(
                document_id=request_data['document_id'],
                masterformat_section=masterformat_section,
                file_s3_key=subsection.get('file_s3_key')
            )
            section.processing_status = DocProcessingStatus.PENDING_PROCESSING
            section.save()
    elif request_data['new_status'] == 'PROCESSED_SECTION':
        print(f"FULL SPEC PROCESSING WEBHOOK: saving submittals")
        spec_sections = SpecSection.objects.filter(
            document_id=int(request_data['document_id']),
            masterformat_section__masterformat_number=request_data['master_format_section_number'],
        )
        if request_data.get('file_s3_key'):
            spec_section = spec_sections.filter(file_s3_key=request_data['file_s3_key']).first()
        else:
            spec_section = spec_sections.first()
        project_version_id = request_data.get('project_version_id')
        version_from_spec_section = spec_section.document.project_version.id
        if project_version_id and str(project_version_id) != str(version_from_spec_section):
            print(f"FULL SPEC PROCESSING WEBHOOK: project_version_id {project_version_id} does not match version from spec section {version_from_spec_section}")
            return Response(status=status.HTTP_400_BAD_REQUEST)
        if not project_version_id:
            project_version_id = version_from_spec_section
        for spec_item in request_data['spec_items']:
            text = change_encode_value(spec_item['text'])
            masterformat_section, created = MasterFormatSection.objects.get_or_create(masterformat_number=request_data['master_format_section_number'])
            db_spec_item = SemanticallyProcessedSpecItem.objects.create(
                project_id=request_data['project_id'],
                project_version_id=project_version_id,
                masterformat_section=masterformat_section,
                spec_section=spec_section,
                topic=spec_item['topic'],
                item_type=spec_item['item'],
                item_content=text,
                spec_section_part=spec_item['spec_section_part'],
                paragraph_number=spec_item.get('paragraph_number', '') or '',
                text_location=spec_item.get('text_location'),
                additional_text_locations=spec_item.get('additional_text_locations', []),
                document_id=request_data['document_id'],
                parsing_method="FULL_SPEC_PROCESSING",
                parsing_version="1.0"
            )
        spec_section.processing_status = DocProcessingStatus.PROCESSED
        spec_section.processing_method = "FULL_SPEC_PROCESSING"
        spec_section.save()
    elif request_data['new_status'] == 'FAILED':
        print(f"SPEC STATUS WEBHOOK: received failure for request: {request_data}")
        document = UploadedFile.objects.filter(id=int(request_data['document_id'])).first()
        if document.processing_status == DocProcessingStatus.SUBSECTIONS_EXTRACTED:
            print(f"SPEC STATUS WEBHOOK: setting document {request_data['document_id']} processing status to SECTION_PROCESSING_FAILED")
            document.processing_status = DocProcessingStatus.SECTION_PROCESSING_FAILED
            document.save()
        else:
            print(f"SPEC STATUS WEBHOOK: setting document {request_data['document_id']} processing status to FAILED")
            document.processing_status = DocProcessingStatus.FAILED
            document.save()
    """IF document.processing_status == SUBSECTIONS_EXTRACTED or SECTION_PROCESSING_FAILED then we have records of all extracted subsections.
    If so, then update document.processing_status to PROCESSED if all subsections have been processed"""
    print(f"SPEC STATUS WEBHOOK: checking if all subsections have been processed for document {request_data['document_id']}")
    document = UploadedFile.objects.filter(id=int(request_data['document_id'])).first()
    if document.processing_status in [DocProcessingStatus.SUBSECTIONS_EXTRACTED, DocProcessingStatus.SECTION_PROCESSING_FAILED]:
        print(f"SPEC STATUS WEBHOOK: getting unprocessed section count for document {request_data['document_id']}")
        unprocessed_spec_section_count = SpecSection.objects.filter(document_id=request_data['document_id']).exclude(
            processing_status=DocProcessingStatus.PROCESSED
        ).count()
        print(f"SPEC STATUS WEBHOOK: unprocessed_spec_section_count: {unprocessed_spec_section_count}")
        if unprocessed_spec_section_count == 0:
            print(f"SPEC STATUS WEBHOOK: all subsections have been processed for document {request_data['document_id']}")
            document.processing_status = DocProcessingStatus.PROCESSED
            document.save()

    return Response(status=status.HTTP_200_OK)


# endregion submittal webhook


class SubmittalItemListViewSet(viewsets.ModelViewSet):
    queryset = SubmittalItemList.objects.all()
    permission_classes = [IsAuthenticated, SubmittalListAccessPermissions]
    serializer_class = SubmittalItemListSerializer

    def get_queryset(self):
        project_version_id = self.request.query_params.get('project_version_id')
        project_id = self.kwargs.get('project_id')
        project = Project.objects.get(id=project_id)
        team = project.team
        is_versioning_active = is_versioning_feature_flag_active(self.request.user, team)
        if is_versioning_active:
            if not project_version_id:
                project_version_id = ProjectVersion.objects.filter(project=project, is_archived=False).order_by('-created_at').first().id
        queryset = self.queryset.filter(project_id=project_id)
        if is_versioning_active and project_version_id:
            queryset = queryset.filter(project_version_id=project_version_id)
        return queryset
    
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='project_version_id',
                description='ID of the project version to filter submittal items, required when versioning is active',
                required=False,
                type=OpenApiTypes.INT
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        project_id = self.kwargs.get('project_id')
        project = get_object_or_404(Project, id=project_id)
        if is_versioning_feature_flag_active(self.request.user, project.team):
            if not serializer.validated_data.get('project_version'):
                raise DRFValidationError("project_version is required when versioning is active")
            serializer.save(project_version=serializer.validated_data.get('project_version'))
        else:
            project_version = ProjectVersion.objects.filter(project=project, is_archived=False).order_by('-created_at').first()
            serializer.save(project_version=project_version)


class UpsertExcelExportHeaderView(generics.GenericAPIView):
    serializer_class = ExcelExportHeaderSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Upsert Excel Export Header",
        description="Upsert the Excel export header options for the authenticated user.",
        request=ExcelExportHeaderSerializer,
        responses={
            200: OpenApiResponse(
                description="Excel export header options upserted successfully",
                response=ExcelExportHeaderSerializer
            ),
            400: OpenApiResponse(description="Bad Request"),
            401: OpenApiResponse(description="Unauthorized"),
        }
    )
    def post(self, request, *args, **kwargs):
        user = request.user
        options = request.data.get('options', {})
        excel_export_header, created = ExcelExportHeader.objects.update_or_create(
            user=user,
            defaults={'options': options}
        )
        serializer = self.get_serializer(excel_export_header)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GetExcelExportHeaderView(generics.RetrieveAPIView):
    serializer_class = ExcelExportHeaderSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get Excel Export Header",
        description="Retrieve the Excel export header options for the authenticated user.",
        responses={
            200: OpenApiResponse(
                description="Excel export header options retrieved successfully",
                response=ExcelExportHeaderSerializer
            ),
            401: OpenApiResponse(description="Unauthorized"),
        }
    )
    def get(self, request, *args, **kwargs):
        user = request.user
        try:
            excel_export_header = ExcelExportHeader.objects.get(user=user)
            serializer = self.get_serializer(excel_export_header)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ExcelExportHeader.DoesNotExist:
            return Response({"options": []}, status=status.HTTP_200_OK)
        


class SemanticallyProcessedSpecItemPagination(PageNumberPagination):
    page_query_param = 'page_number'
    page_size_query_param = 'limit'
    max_page_size = 200

class SemanticallyProcessedSpecItemViewSet(viewsets.ModelViewSet):
    serializer_class = SemanticallyProcessedSpecItemSerializer
    permission_classes = [IsAuthenticated, SubmittalItemAccessPermissions]
    queryset = SemanticallyProcessedSpecItem.objects.select_related('masterformat_section', 'spec_section', 'document')
    pagination_class = SemanticallyProcessedSpecItemPagination

    def get_queryset(self):
        project_id = self.kwargs.get('project_id')

        queryset = self.queryset.filter(project_id=project_id).order_by('id')

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(item_content__icontains=search) | 
                Q(topic__icontains=search) | 
                Q(item_type__icontains=search)
            )
        queryset = queryset.order_by(
            'masterformat_section__masterformat_number',
            'id',
        )
        return queryset
    

    @extend_schema(
        summary="Export Semantically Processed Spec Items to CSV",
        description="Export the semantically processed spec items to a CSV file for the current project.",
        parameters=[
            OpenApiParameter(
                name='project_version_id',
                description='ID of the project version to filter items, if versioning is active',
                required=False,
                type=OpenApiTypes.INT
            ),
        ],
        responses={
            200: OpenApiResponse(
                description="CSV file containing the exported spec items"
            ),
            400: OpenApiResponse(description="Bad Request"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Not Found"),
        }
    )
    @action(detail=False, methods=['get'], url_path='export-csv')
    def export_full_spec_csv(self, request, *args, **kwargs):
        project_id = self.kwargs.get('project_id')
        project_version_id = request.query_params.get('project_version_id')
        project = Project.objects.get(id=project_id)
        if not request.user.is_member_of_project(project):
            return Response(status=status.HTTP_403_FORBIDDEN)
        team = project.team    
        # Check for versioning
        is_versioning_active = is_versioning_feature_flag_active(request.user, team)
        if is_versioning_active and project_version_id:
            queryset = self.queryset.filter(
                project_id=project_id,
                project_version_id=project_version_id
            )
        else:
            queryset = self.queryset.filter(project_id=project_id)
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="spec_items.csv"'
        
        # Create CSV writer
        writer = csv.DictWriter(
            response, 
            fieldnames=[
                'spec_section', 'spec_section_part', 'paragraph_number', 
                'topic', 'item', 'text',  
            ]
        )
        writer.writeheader()
        
        # Get the multiple classification separator from settings or use default
        MULTIPLE_CLASSIFICATIONS_SEPARATOR = getattr(settings, 'MULTIPLE_CLASSIFICATIONS_SEPARATOR', '||')
        
        # Write each item to CSV
        for item in queryset:
            writer.writerow({
                'spec_section': item.masterformat_section.masterformat_number,
                'spec_section_part': item.spec_section_part,
                'paragraph_number': item.paragraph_number,
                'topic': item.topic,
                'item': item.item_type,
                'text': item.item_content,
            })
        
        return response


# region notices
# TODO:
#   - Split `views.py` into a module
#   - move this region into a separate file

class NoticeViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = NoticeMatchSerializer
    permission_classes = [IsAuthenticated, SubmittalItemAccessPermissions]
    queryset = (
        NoticeMatch.objects
        .select_related('document')
        .prefetch_related('excerpt_anchors')
    )

    def get_queryset(self):
        project_id = self.kwargs.get('project_id')
        return self.queryset.filter(project_id=project_id)


class NoticeProcessingWebhookView(CreateAPIView):
    serializer_class = NoticeProcessingCallbackSerializer
    permission_classes = [AllowAny]

# endregion notices


# region Procore

class ProcoreFetchAccessTokenView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        request_serializer = ProcoreFetchAccessTokenSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        code = request_serializer.validated_data['code']
        redirect_uri = request_serializer.validated_data['redirect_uri']

        response = get_procore_access_token(code, redirect_uri)
        print(response)
        if response.status_code != 200:
            return Response(response.text, status=status.HTTP_400_BAD_REQUEST)
        access_token_serializer = ProcoreAccessTokenSerializer(data=response.json())
        print(access_token_serializer)
        access_token_serializer.is_valid(raise_exception=True)

        ProcoreToken.objects.create(
            user=request.user,
            access_token=access_token_serializer.validated_data['access_token'],
            refresh_token=access_token_serializer.validated_data['refresh_token'],
            expires_in=access_token_serializer.validated_data['expires_in'],
            token_type=access_token_serializer.validated_data['token_type'],
            redirect_uri=redirect_uri,
            code=code,
        )

        return Response(access_token_serializer.data, status=status.HTTP_200_OK)
    
class ProcoreRefreshAccessTokenView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            procore_token = get_fresh_token_for_user(request.user)
        except ProcoreException as e:
            return Response(str(e), status=status.HTTP_400_BAD_REQUEST)

        access_token_serializer = ProcoreAccessTokenSerializer(
            data={
                'access_token': procore_token.access_token,
                'refresh_token': procore_token.refresh_token,
                'expires_in': procore_token.expires_in,
                'token_type': procore_token.token_type,
                'created_at': int(procore_token.created_at.timestamp()),
            }
        )
        print(access_token_serializer)
        access_token_serializer.is_valid(raise_exception=True)
        return Response(access_token_serializer.data, status=status.HTTP_200_OK)


class GetProcoreCompanyMappingView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        company_id = kwargs.get('company_id')
        company = get_object_or_404(Team, id=company_id)
        if not request.user.is_admin_for_team(company):
            return Response(status=status.HTTP_403_FORBIDDEN)

        if company.procore_id is None:
            return Response(status=status.HTTP_204_NO_CONTENT)

        procore_data = {
            'procore_company_id': company.procore_id,
            'procore_company_name': company.procore_name
        }
        serializer = ProcoreCompanyMappingSerializer(data=procore_data)
        serializer.is_valid(raise_exception=True)
        if company.procore_id is not None:
            return Response(serializer.data, status=status.HTTP_200_OK)
        

class GetProcoreCompaniesView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            procore_token = get_fresh_token_for_user(request.user)
        except ProcoreException as e:
            return Response(str(e), status=status.HTTP_400_BAD_REQUEST)
        response = get_companies(procore_token.access_token)
        serializer = ProcoreCompanySerializer(data=response.json(), many=True)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GetCurrentUserProcoreInfoView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            procore_token = get_fresh_token_for_user(request.user)
        except ProcoreException as e:
            return Response(str(e), status=status.HTTP_400_BAD_REQUEST)
        response = get_me(procore_token.access_token)
        serializer = ProcoreMeSerializer(data=response.json())
        print(serializer)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class GetProcoreProjectMappingView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        project_id = kwargs.get('project_id')
        project = get_object_or_404(Project, id=project_id)
        if not request.user.is_member_of_project(project):
            return Response(status=status.HTTP_403_FORBIDDEN)
        if project.procore_id is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        procore_data = {
            'procore_project_id': project.procore_id,
            'procore_project_name': project.procore_name,
            'submittal_manager_id': project.procore_submittal_manager_id,
            'procore_submittal_manager_name': project.procore_submittal_manager_name,
            'procore_company_id': project.team.procore_id,
            'procore_company_name': project.team.procore_name
        }
        serializer = ProcoreProjectMappingSerializer(data=procore_data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class SetProcoreProjectMappingView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CreateProcoreProjectMappingSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project_id = serializer.validated_data.get('project_id')
        project = get_object_or_404(Project, id=project_id)
        if not request.user.is_member_of_project(project):
            return Response(status=status.HTTP_403_FORBIDDEN)

        company = project.team
        project.procore_id = serializer.validated_data.get('procore_project_id')
        project.procore_name = serializer.validated_data.get('procore_project_name')
        project.procore_submittal_manager_id = serializer.validated_data.get('procore_submittal_manager_id')
        project.procore_submittal_manager_name = serializer.validated_data.get('procore_submittal_manager_name')
        project.save()
        company.procore_id = serializer.validated_data.get('procore_company_id')
        company.procore_name = serializer.validated_data.get('procore_company_name')
        company.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class CreateProcoreSubmittalsView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProcoreSubmittalSerializer

    def get_submittals(self, project, project_version, submittal_ids_to_post_to_procore, export_all):
        if export_all:
            submittals = SubmittalItem.objects.filter(project_id=project.id)
            if project_version:
                submittals = submittals.filter(project_version=project_version)
        else:
            submittals = SubmittalItem.objects.filter(id__in=submittal_ids_to_post_to_procore)
        return submittals


    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        project_id = serializer.validated_data.get('project_id')
        project_version_id = serializer.validated_data.get('project_version_id')
        submittal_ids_to_post_to_procore = serializer.validated_data.get('records')
        export_all = serializer.validated_data.get('export_all', False)


        project = get_object_or_404(Project, id=project_id)
        if not request.user.is_member_of_project(project):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            procore_token = get_fresh_token_for_user(request.user)
        except ProcoreException as e:
            print("Error getting fresh token for user: " + str(e))
            return Response(str(e), status=status.HTTP_400_BAD_REQUEST)

        token_info_response = check_token_info(procore_token.access_token)
        print("token_info_response", token_info_response.json())

        is_versioning_active = is_versioning_feature_flag_active(request.user, project.team)
        project_version = None
        if is_versioning_active:
            if not project_version_id:
                raise DRFValidationError("project_version_id is required when versioning is active")
            else:
                try:
                    project_version = ProjectVersion.objects.get(id=project_version_id)
                except ProjectVersion.DoesNotExist:
                    raise DRFValidationError("Not a valid project version for this project")
            if project_version.project != project:
                raise DRFValidationError("Not a valid project version for this project")
        
        status_response = get_status(project.team.procore_id, procore_token.access_token)
        if status_response.status_code != 200:
            print("Error getting procore status")
            return Response(status_response.text, status=status.HTTP_400_BAD_REQUEST)
        open_statuses = [status for status in status_response.json() if status["name"] == "Open"]
        status_id = open_statuses[0]["id"] if open_statuses else None
        if status_id is None:
            print("Error getting procore status id")
            return Response(status=status.HTTP_400_BAD_REQUEST)
        
        submittals: List[SubmittalItem] = self.get_submittals(project, project_version, submittal_ids_to_post_to_procore, export_all)
        spec_section_list = list(set([str(submittal.masterformat_section.masterformat_number) for submittal in submittals]))
        print("procore_token", procore_token.access_token)

        print("company id", project.team.procore_id)
        procore_spec_divisions_response = get_spec_divisions(project.procore_id, procore_token.access_token)
        if procore_spec_divisions_response.status_code != 200:
            print("Error getting procore spec divisions")
            return Response(procore_spec_divisions_response.text, status=status.HTTP_400_BAD_REQUEST)
        procore_spec_divisions = procore_spec_divisions_response.json()
        procore_division_numbers = [d['number'] for d in procore_spec_divisions]
        procore_division_ids = [str(d['id']) for d in procore_spec_divisions]
        procore_division_dict = dict(map(lambda i, j: (i, j), procore_division_numbers, procore_division_ids))
        print("procore_division_dict", procore_division_dict)

        procore_spec_sections = get_spec_sections(project.procore_id, procore_token.access_token)
        if procore_spec_sections.status_code != 200:
            print("Error getting procore spec sections")
            return Response(procore_spec_sections.text, status=status.HTTP_400_BAD_REQUEST)
        procore_spec_sections = procore_spec_sections.json()
        procore_spec_section_numbers = [d['number'] for d in procore_spec_sections]
        procore_spec_section_ids = [str(d['id']) for d in procore_spec_sections]
        procore_spec_section_dict = dict(map(lambda i, j: (i, j), procore_spec_section_numbers, procore_spec_section_ids))
        print("procore_spec_section_dict", procore_spec_section_dict)

        for spec_section in spec_section_list:
            spec_section_division = spec_section[0:2]
            if spec_section_division == "":
                continue
            if spec_section_division not in procore_division_numbers:
                print(f"Spec section division {spec_section_division} not in procore division numbers")
                create_div_response = create_spec_division(
                    project_id=project.procore_id,
                    division_number=spec_section_division,
                    procore_token=procore_token.access_token
                )
                if create_div_response.status_code != 201:
                    print("Error creating procore spec division")
                    print("create_div_response status code: " + str(create_div_response.status_code))
                    print("create_div_response json: " + str(create_div_response.json()))
                    
                    # Check for permission error
                    if create_div_response.status_code == 403:
                        return Response(
                            {"message": "Your current Procore account doesn't have permissions to create spec sections or submittals in the currently mapped project. Please contact your Procore administrator to grant the necessary permissions."},
                            status=status.HTTP_403_FORBIDDEN
                        )
                    continue
                else:
                    procore_division_dict[spec_section_division] = str(create_div_response.json()['id'])
                    procore_division_numbers.append(spec_section_division)
                    print("updated division dict", procore_division_dict)
            else:
                print("Division: " + spec_section_division + " already exists")
            
            if spec_section not in procore_spec_section_numbers:
                print("Spec section not in procore spec section numbers")
                create_spec_response = create_spec_section(
                    spec_section=spec_section,
                    division_id=procore_division_dict[spec_section_division],
                    project_id=project.procore_id,
                    procore_token=procore_token.access_token
                )
                if create_spec_response.status_code != 201:
                    print("Error creating procore spec section")
                    print("create_spec_response status code: " + str(create_spec_response.status_code))
                    print("create_spec_response json: " + str(create_spec_response.json()))
                    
                    # Check for permission error
                    if create_spec_response.status_code == 403:
                        return Response(
                            {"message": "Your current Procore account doesn't have permissions to create spec sections or submittals in the currently mapped project. Please contact your Procore administrator to grant the necessary permissions."},
                            status=status.HTTP_403_FORBIDDEN
                        )
                    return Response(create_spec_response.json(), status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                else:
                    procore_spec_section_dict[spec_section] = str(create_spec_response.json()['id'])
                    procore_spec_section_numbers.append(spec_section)
                    print("updated spec section dict", procore_spec_section_dict)
            else:
                print("Spec: " + spec_section + " already exists")
            # TODO ISSUE API does not increment ID from API, replacing with para no
            # num_dict[spec] = procore.get_next_number(request, spec_dict[spec])

        submittals_dict = {}
        submittal_type_mapping = {}
        submittal_types_for_company = ProcoreSubmittalTypeMapping.objects.filter(company=project.team)
        for mapping in submittal_types_for_company:
            submittal_type_mapping[mapping.link_type] = mapping.procore_type
        submittals_not_created = []
        for submittal in submittals:
            if submittal.masterformat_section.masterformat_number == "":
                continue
            print("procore_spec_section_id", procore_spec_section_dict[submittal.masterformat_section.masterformat_number])
            submittal_creation_response = create_submittal(
                submittal_content=submittal.submittal_content,
                paragraph_number=submittal.paragraph_number,
                procore_spec_section_id=procore_spec_section_dict[submittal.masterformat_section.masterformat_number],
                procore_status_id=status_id or 1,
                procore_submittal_manager_id=project.procore_submittal_manager_id,
                submittal_title=submittal.submittal_description,
                submittal_type=submittal_type_mapping.get(submittal.submittal_type, submittal.submittal_type),
                project_id=project.procore_id,
                procore_token=procore_token.access_token
            )
            if submittal_creation_response.status_code != 201:
                # Check for permission error
                if submittal_creation_response.status_code == 403:
                    return Response(
                        {"message": "Your current Procore account doesn't have permissions to create spec sections or submittals in the currently mapped project. Please contact your Procore administrator to grant the necessary permissions."},
                        status=status.HTTP_403_FORBIDDEN
                    )
                submittals_not_created.append(submittal)
                continue
            submittals_dict[submittal.id] = submittal_creation_response.json()['id']
            try:
                SubmittalItem.objects.filter(
                    id=submittal.id
                ).update(
                    procore_submittal_id=submittals_dict[submittal.id],
                    procore_export_date=datetime.now(timezone.utc)
                )
            except Exception as e:
                print("Error updating submittal item: " + str(submittal.id))
                print(e)
                submittals_not_created.append(submittal)
        
        response_payload = {
            'message': 'Submittal created',
            'divs': procore_division_dict,
            'specs': procore_spec_section_dict,
            'nums': {},
            'submittals': submittals_dict,
            'submittals_not_created': submittals_not_created
        }
        serializer = ProcoreSubmittalCreationResponseSerializer(data=response_payload)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class DeleteProcoreTokenView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user_id = self.request.query_params.get('user_id', '')
        user = get_object_or_404(CustomUser, id=user_id)
        ProcoreToken.objects.filter(user=user).delete()
        return Response(status=status.HTTP_200_OK)
    

class GetProcoreProjectsView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        procore_company_id = kwargs.get('procore_company_id')
        try:
            procore_token = get_fresh_token_for_user(request.user)
        except ProcoreException as e:
            return Response(str(e), status=status.HTTP_400_BAD_REQUEST)
        
        token_info_response = check_token_info(procore_token.access_token)
        print("get_projects token_info_response", token_info_response.json())
        response = get_projects(procore_company_id, procore_token.access_token)
        if response.status_code != 200:
            print("Error getting procore projects")
            print("response status code: " + str(response.status_code))
            print("response text: " + response.text)
            return Response(response.text, status=status.HTTP_400_BAD_REQUEST)
        projects_list = []
        for project in response.json():
            projects_list.append({
                'key': project['id'],
                'value': project['display_name']
            })
        response_payload = {
            'message': 'List of projects',
            'data': projects_list
        }
        return Response(response_payload, status=status.HTTP_200_OK)
    

class GetProcoreManagersView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        procore_project_id = kwargs.get('procore_project_id')
        try:
            procore_token = get_fresh_token_for_user(request.user)
        except ProcoreException as e:
            print("Error getting fresh token for user: " + str(e))
            return Response(str(e), status=status.HTTP_400_BAD_REQUEST)
        
        token_info_response = check_token_info(procore_token.access_token)
        print("token_info_response", token_info_response.json())
        
        response = get_managers(procore_project_id, procore_token.access_token)
        if response.status_code != 200:
            print("Error getting procore managers")
            print("response status code: " + str(response.status_code))
            print("response text: " + response.text)
            return Response(response.text, status=status.HTTP_400_BAD_REQUEST)
        managers_list = []
        print("get_managers response", response.json())
        for manager in response.json():
            managers_list.append({
                'key': manager['key'],
                'value': manager['value']
            })
        response_payload = {
            'message': 'List of managers',
            'data': managers_list
        }        
        return Response(response_payload, status=status.HTTP_200_OK)
    
class CreateProcoreCompanyMappingView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CreateProcoreCompanyMappingSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company_id = serializer.validated_data.get('link_company_id')
        company = get_object_or_404(Team, id=company_id)
        if not request.user.is_member_of_team(company):
            return Response(status=status.HTTP_403_FORBIDDEN)
        company.procore_id = serializer.validated_data.get('procore_company_id')
        company.procore_name = serializer.validated_data.get('procore_company_name')
        company.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class ProcoreSubmittalMappingsView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        company_id = kwargs.get('company_id')
        company: Team = get_object_or_404(Team, id=company_id)
        if not request.user.is_member_of_team(company):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            procore_token = get_fresh_token_for_user(request.user)
        except ProcoreException as e:
            return Response(str(e), status=status.HTTP_400_BAD_REQUEST)
        
        submittal_types_response = get_submittal_types(company.procore_id, procore_token.access_token)
        if submittal_types_response.status_code != 200:
            return Response(submittal_types_response.text, status=status.HTTP_400_BAD_REQUEST)
        procore_submittal_types = submittal_types_response.json()

        existing_mappings = ProcoreSubmittalTypeMapping.objects.filter(company=company)
        existing_mappings_dicts = []
        for mapping in existing_mappings:
            existing_mappings_dicts.append({
                'id': mapping.id,
                'link_submittal': mapping.link_type,
                'procore_type': mapping.procore_type
            })

        all_link_submittal_types = list(SubmittalItem.objects.all().values_list('submittal_type', flat=True).distinct())
        link_submittal_types_in_procore_format = []
        for submittal_type in all_link_submittal_types:
            link_submittal_types_in_procore_format.append({
                'id': None,
                'name': submittal_type,
                'translated_name': submittal_type
            })

        all_submittal_types = procore_submittal_types + link_submittal_types_in_procore_format
        list_of_mapped_types = [mapping['link_submittal'] for mapping in existing_mappings_dicts]
        for submittal_type in all_submittal_types:
            if submittal_type['name'] in list_of_mapped_types:
                continue
            existing_mappings_dicts.append({
                'id': submittal_type['id'],
                'link_submittal': submittal_type['name'],
                'procore_type': submittal_type['name']
            })

        response_payload = {
            'message': 'List of submittal types',
            'data': {
                'link_sub_mapping': existing_mappings_dicts,
                'procore_submittal_types': all_submittal_types
            }
        }
        return Response(response_payload, status=status.HTTP_200_OK)
    
    def post(self, request, *args, **kwargs):
        serializer = UpdateProcoreSubmittalMappingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company_id = kwargs.get('company_id')
        company = get_object_or_404(Team, id=company_id)
        if not request.user.is_admin_for_team(company):
            return Response(status=status.HTTP_403_FORBIDDEN)
        
        mappings = serializer.validated_data.get('mappings')
        for mapping in mappings:
            ProcoreSubmittalTypeMapping.objects.update_or_create(
                id=mapping.get('id'),
                defaults={
                    'link_type': mapping.get('link_submittal'),
                    'procore_type': mapping.get('procore_type'),
                    'company': company,
                    'procore_company_id': company.procore_id
                }
            )
        return Response(status=status.HTTP_200_OK)


    
        
# endregion Procore

def delete_submittals_for_document(document_id: int) -> int:
    """
    Delete all SubmittalItem rows linked to the specified document_id.

    Returns the number of deleted SubmittalItem records.
    """
    deleted_count, _ = SubmittalItem.objects.filter(document_id=document_id).delete()
    print(f"\n\n\n\n Deleted {deleted_count} submittal(s) for document_id={document_id}")
    return deleted_count

@extend_schema(
    responses={200: {'description': 'Document reprocessing started successfully'}},
    description="Reprocess an existing uploaded document.",
    methods=["POST"]
)
@api_view(['POST'])
def reprocess_document(request):
    if not request.user.is_authenticated:
        return Response({'detail': 'User is not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)
    
    document_id = request.data.get('document_id')
    if not document_id:
        return Response({'detail': 'document_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        uploaded_file = UploadedFile.objects.get(id=document_id)
    except UploadedFile.DoesNotExist:
        return Response({'detail': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)
    
    project = uploaded_file.project
    project_version = uploaded_file.project_version
    
    # Check if user has access to the project
    if not request.user.is_member_of_project(project):
        return Response({'detail': 'User is not a member of the project'}, status=status.HTTP_403_FORBIDDEN)
    
    # Remove all existing submittals tied to this document before reprocessing
    delete_submittals_for_document(uploaded_file.id)
    
    # Get feature flags for the project
    is_notices_flag_active = is_notices_feature_flag_active(request.user, project.team)
    is_v2_process_deliverables_flag_active = is_v2_process_deliverables_feature_flag_active(request.user, project.team, project)
    is_full_spec_processing_flag_active = is_full_spec_processing_feature_flag_active(request.user, project.team, project)
    is_specgpt_flag_active = is_specgpt_feature_flag_active(request.user, project.team, project)
    

    def _to_bool(val, default=False):
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        if isinstance(val, (int, float)):
            return bool(val)
        if isinstance(val, str):
            return val.strip().lower() in ['1', 'true', 't', 'yes', 'y', 'on']
        return default

    extract_notices = _to_bool(request.data.get('extract_notices'), False)
    full_spec_processing = _to_bool(request.data.get('full_spec_processing'), False)
    
    try:
        if is_notices_flag_active and extract_notices:
            call_extract_notices_lambda(
                callback_url=settings.BACKEND_NOTICES_CALLBACK_URL,
                document_id=str(uploaded_file.id),
                object_key=uploaded_file.document_path,
                project_version_id=str(project_version.id),
            )
        elif is_full_spec_processing_flag_active and full_spec_processing:
            call_full_spec_processing_lambda(
                callback_url=settings.BACKEND_FULL_SPEC_PROCESSING_CALLBACK_URL,
                document_id=str(uploaded_file.id),
                project_id=str(project.id),
                project_version_id=str(project_version.id),
                object_key=uploaded_file.document_path,
                filename=uploaded_file.name,
                user_id=str(request.user.id),
            )
        else:
            parse_spec(
                callback_url=settings.BACKEND_CALLBACK_URL,
                document_id=str(uploaded_file.id),
                project_id=str(project.id),
                project_version_id=str(project_version.id),
                object_key=uploaded_file.document_path,
                filename=uploaded_file.name,
                user_id=str(request.user.id),
                is_v2_process_deliverables_flag_active=is_v2_process_deliverables_flag_active,
                is_specgpt_flag_active=is_specgpt_flag_active,
                specgpt_callback_url=settings.BACKEND_SPECGPT_CALLBACK_URL
            )
        
        uploaded_file.processing_status = 'PENDING_PROCESSING'
        uploaded_file.last_retry = datetime.now()
        uploaded_file.save()
        
        return Response({
            'message': 'Document reprocessing started successfully',
            'document_id': document_id,
            'document_name': uploaded_file.name
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logging.error(f"Error reprocessing document {uploaded_file.name}: {e}")
        return Response({
            'detail': f'Error starting document reprocessing: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    responses={200: {'description': 'Document download URL generated successfully'}},
    description="Generate a presigned URL to download an uploaded document.",
    methods=["GET"]
)
@api_view(['GET'])
def download_document(request):
    if not request.user.is_authenticated:
        return Response({'detail': 'User is not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)
    
    document_id = request.query_params.get('document_id')
    if not document_id:
        return Response({'detail': 'document_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        uploaded_file = UploadedFile.objects.get(id=document_id)
    except UploadedFile.DoesNotExist:
        return Response({'detail': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)
    
    project = uploaded_file.project
    
    # Check if user has access to the project
    if not request.user.is_member_of_project(project):
        return Response({'detail': 'User is not a member of the project'}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        # Generate presigned URL for download
        presigned_url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.S3_BUCKET,
                'Key': uploaded_file.document_path,
                'ResponseContentDisposition': f'attachment; filename="{uploaded_file.name}"'
            },
            ExpiresIn=3600  # URL expires in 1 hour
        )
        
        return Response({
            'download_url': presigned_url,
            'document_name': uploaded_file.name,
            'document_id': document_id
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logging.error(f"Error generating download URL for document {uploaded_file.name}: {e}")
        return Response({
            'detail': f'Error generating download URL: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@extend_schema(
    responses={200: {'description': 'Document deleted successfully'}},
    description="Delete an uploaded document while preserving submittals and other related data.",
    methods=["POST"]
)
@api_view(['POST'])
def delete_document(request):
    if not request.user.is_authenticated:
        return Response({'detail': 'User is not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)
    
    document_id = request.data.get('document_id')
    if not document_id:
        return Response({'detail': 'document_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        uploaded_file = UploadedFile.objects.get(id=document_id)
    except UploadedFile.DoesNotExist:
        return Response({'detail': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)
    
    project = uploaded_file.project
    
    # Check if user has access to the project
    if not request.user.is_member_of_project(project):
        return Response({'detail': 'User is not a member of the project'}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        # Set document field to null for all related submittal items instead of deleting them
        submittal_items_updated = SubmittalItem.objects.filter(document=uploaded_file).update(document=None)
        
        # Set document field to null for all related notice matches instead of deleting them
        notice_matches_updated = NoticeMatch.objects.filter(document=uploaded_file).update(document=None)
        
        # Set spec_section to null for submittal items that reference spec sections from this document
        spec_sections_to_delete = SpecSection.objects.filter(document=uploaded_file)
        submittal_items_spec_section_updated = SubmittalItem.objects.filter(spec_section__in=spec_sections_to_delete).update(spec_section=None)
        semantically_processed_items_spec_section_updated = SemanticallyProcessedSpecItem.objects.filter(spec_section__in=spec_sections_to_delete).update(spec_section=None)
        
        # Now delete spec sections since they are directly tied to documents and don't make sense without a document
        spec_sections_deleted, _ = spec_sections_to_delete.delete()
        
        # Delete notice excerpts since they are directly tied to documents
        notice_excerpts_deleted, _ = NoticeExcerpt.objects.filter(document=uploaded_file).delete()
        
        # Set document field to null for all related semantically processed spec items instead of deleting them
        semantically_processed_items_updated = SemanticallyProcessedSpecItem.objects.filter(document=uploaded_file).update(document=None)
        
        # Delete the uploaded file record
        document_name = uploaded_file.name
        uploaded_file.delete()
        
        logging.info(f"Document '{document_name}' (ID: {document_id}) deleted successfully. "
                    f"Updated {submittal_items_updated} submittal items, "
                    f"{notice_matches_updated} notice matches, "
                    f"Updated {submittal_items_spec_section_updated} submittal items (spec_section), "
                    f"Updated {semantically_processed_items_spec_section_updated} semantically processed items (spec_section), "
                    f"Deleted {spec_sections_deleted} spec sections, "
                    f"Deleted {notice_excerpts_deleted} notice excerpts, "
                    f"{semantically_processed_items_updated} semantically processed items.")
        
        return Response({
            'detail': 'Document deleted successfully',
            'document_name': document_name,
            'submittal_items_updated': submittal_items_updated,
            'notice_matches_updated': notice_matches_updated,
            'submittal_items_spec_section_updated': submittal_items_spec_section_updated,
            'semantically_processed_items_spec_section_updated': semantically_processed_items_spec_section_updated,
            'spec_sections_deleted': spec_sections_deleted,
            'notice_excerpts_deleted': notice_excerpts_deleted,
            'semantically_processed_items_updated': semantically_processed_items_updated
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logging.error(f"Error deleting document {uploaded_file.name}: {e}")
        return Response({
            'detail': f'Error deleting document: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    parameters=[
        OpenApiParameter(
            name='project_version_id',
            description='ID of the project version to filter spec sections',
            required=False,
            type=OpenApiTypes.INT
        )
    ],
    responses={
        200: OpenApiTypes.OBJECT,
        400: OpenApiTypes.OBJECT
    },
    description="Get spec sections for a project."
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, SpecCentricViewAccessPermissions])
def get_project_spec_sections(request, project_id):
    try:
        project = get_object_or_404(Project, id=project_id)
        project_version_id = request.query_params.get('project_version_id')
        
        queryset = SpecSection.objects.filter(document__project=project)
        
        if project_version_id:
            queryset = queryset.filter(document__project_version_id=project_version_id)
        
        # Build the response data
        spec_sections_data = []
        for section in queryset:
            spec_sections_data.append({
                'id': section.id,
                'masterformat_number': section.masterformat_section.masterformat_number,
                'section_title': section.custom_section_title or section.masterformat_section.masterformat_description,
                'document_name': section.document.name,
                'file_s3_key': section.file_s3_key,
                'created_at': section.created_at.isoformat() if section.created_at else None,
            })
        
        return Response(spec_sections_data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    responses={
        200: OpenApiTypes.OBJECT,
        400: OpenApiTypes.OBJECT,
        404: OpenApiTypes.OBJECT
    },
    description="Download a spec section file."
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_spec_section(request, section_id):
    try:
        section = get_object_or_404(SpecSection, id=section_id)

        if not request.user.is_member_of_project(section.document.project):
            return Response({"error": "User is not a member of the project"}, status=status.HTTP_403_FORBIDDEN)
        
        if not section.file_s3_key:
            return Response({"error": "Spec section file not available"}, status=status.HTTP_404_NOT_FOUND)
        
        # Generate presigned URL
        download_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.S3_BUCKET, 'Key': section.file_s3_key},
            ExpiresIn=3600
        )
        
        # Generate a filename for download
        file_name = f"{section.masterformat_section.masterformat_number}_{section.document.name}"
        
        return Response({
            "download_url": download_url,
            "file_name": file_name
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    parameters=[
        OpenApiParameter(
            name='section_ids',
            description='Comma-separated list of spec section IDs to download',
            required=True,
            type=OpenApiTypes.STR
        )
    ],
    responses={
        200: OpenApiTypes.OBJECT,
        400: OpenApiTypes.OBJECT
    },
    description="Download multiple spec section files as a zip archive."
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bulk_download_spec_sections(request):
    try:
        section_ids_param = request.query_params.get('section_ids')
        if not section_ids_param:
            return Response({"error": "section_ids parameter is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse section IDs
        try:
            section_ids = [int(id.strip()) for id in section_ids_param.split(',')]
        except ValueError:
            return Response({"error": "Invalid section_ids format"}, status=status.HTTP_400_BAD_REQUEST)
        
        if not section_ids:
            return Response({"error": "No section IDs provided"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get spec sections
        sections = SpecSection.objects.filter(id__in=section_ids)
        
        if not sections.exists():
            return Response({"error": "No spec sections found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Check permissions for all sections
        for section in sections:
            if not request.user.is_member_of_project(section.document.project):
                return Response({"error": f"User is not a member of project for section {section.id}"}, status=status.HTTP_403_FORBIDDEN)
        
        # Filter sections that have files available
        sections_with_files = sections.filter(file_s3_key__isnull=False).exclude(file_s3_key='')
        
        if not sections_with_files.exists():
            return Response({"error": "No spec section files available for download"}, status=status.HTTP_404_NOT_FOUND)
        
        # If only one section, return single download URL
        if sections_with_files.count() == 1:
            section = sections_with_files.first()
            download_url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': settings.S3_BUCKET, 'Key': section.file_s3_key},
                ExpiresIn=3600
            )
            file_name = f"{section.masterformat_section.masterformat_number}_{section.document.name}"
            
            return Response({
                "download_url": download_url,
                "file_name": file_name,
                "single_file": True
            }, status=status.HTTP_200_OK)
        
        # For multiple sections, create a zip file
        import zipfile
        import tempfile
        import os
        import time
        
        # Create a temporary zip file
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        zip_name = temp_zip.name
        temp_zip.close()
        
        try:
            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for section in sections_with_files:
                    try:
                        # Download file from S3
                        s3_response = s3.get_object(Bucket=settings.S3_BUCKET, Key=section.file_s3_key)
                        file_content = s3_response['Body'].read()
                        
                        # Add to zip with proper filename
                        file_name = f"{section.masterformat_section.masterformat_number}_{section.document.name}"
                        zipf.writestr(file_name, file_content)
                    except Exception as e:
                        print(f"Error adding {section.id} to zip: {e}")
                        continue
            
            # Upload zip to S3
            zip_s3_key = f"temp_bulk_downloads/{request.user.id}_{int(time.time())}_spec_sections.zip"
            s3.upload_file(zip_name, settings.S3_BUCKET, zip_s3_key)
            
            # Generate presigned URL for zip
            download_url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': settings.S3_BUCKET, 'Key': zip_s3_key},
                ExpiresIn=3600
            )
            
            # Clean up temporary file
            os.unlink(zip_name)
            
            return Response({
                "download_url": download_url,
                "file_name": f"spec_sections_{len(sections_with_files)}_files.zip",
                "single_file": True,
                "count": len(sections_with_files)
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            # Clean up temporary file on error
            if os.path.exists(zip_name):
                os.unlink(zip_name)
            raise e
        
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    parameters=[
        OpenApiParameter(
            name='document_ids',
            description='Comma-separated list of document IDs to download',
            required=True,
            type=OpenApiTypes.STR
        )
    ],
    responses={
        200: OpenApiTypes.OBJECT,
        400: OpenApiTypes.OBJECT
    },
    description="Download multiple document files as a zip archive."
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bulk_download_documents(request):
    try:
        document_ids_param = request.query_params.get('document_ids')
        if not document_ids_param:
            return Response({"error": "document_ids parameter is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse document IDs
        try:
            document_ids = [int(id.strip()) for id in document_ids_param.split(',')]
        except ValueError:
            return Response({"error": "Invalid document_ids format"}, status=status.HTTP_400_BAD_REQUEST)
        
        if not document_ids:
            return Response({"error": "No document IDs provided"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get documents
        from ..models import UploadedFile
        documents = UploadedFile.objects.filter(id__in=document_ids)
        
        if not documents.exists():
            return Response({"error": "No documents found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Check permissions for all documents
        for document in documents:
            if not request.user.is_member_of_project(document.project):
                return Response({"error": f"User is not a member of project for document {document.id}"}, status=status.HTTP_403_FORBIDDEN)
        
        # Filter documents that have files available
        documents_with_files = documents.filter(document_path__isnull=False).exclude(document_path='')
        
        if not documents_with_files.exists():
            return Response({"error": "No document files available for download"}, status=status.HTTP_404_NOT_FOUND)
        
        # If only one document, return single download URL
        if documents_with_files.count() == 1:
            document = documents_with_files.first()
            download_url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': settings.S3_BUCKET, 'Key': document.document_path},
                ExpiresIn=3600
            )
            file_name = document.name
            
            return Response({
                "download_url": download_url,
                "file_name": file_name,
                "single_file": True
            }, status=status.HTTP_200_OK)
        
        # For multiple documents, create a zip file
        import zipfile
        import tempfile
        import os
        import time
        
        # Create a temporary zip file
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        zip_name = temp_zip.name
        temp_zip.close()
        
        try:
            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for document in documents_with_files:
                    try:
                        # Download file from S3
                        s3_response = s3.get_object(Bucket=settings.S3_BUCKET, Key=document.document_path)
                        file_content = s3_response['Body'].read()
                        
                        # Add to zip with proper filename
                        zipf.writestr(document.name, file_content)
                    except Exception as e:
                        print(f"Error adding {document.id} to zip: {e}")
                        continue
            
            # Upload zip to S3
            zip_s3_key = f"temp_bulk_downloads/{request.user.id}_{int(time.time())}_documents.zip"
            s3.upload_file(zip_name, settings.S3_BUCKET, zip_s3_key)
            
            # Generate presigned URL for zip
            download_url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': settings.S3_BUCKET, 'Key': zip_s3_key},
                ExpiresIn=3600
            )
            
            # Clean up temporary file
            os.unlink(zip_name)
            
            return Response({
                "download_url": download_url,
                "file_name": f"documents_{len(documents_with_files)}_files.zip",
                "single_file": True,
                "count": len(documents_with_files)
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            # Clean up temporary file on error
            if os.path.exists(zip_name):
                os.unlink(zip_name)
            raise e
        
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Get PDF URLs for version comparison",
    request=VersionComparisonSerializer,
    responses={
        200: OpenApiResponse(description="PDF URLs for both versions"),
        400: OpenApiResponse(description="Bad Request"),
        401: OpenApiResponse(description="Unauthorized"),
        403: OpenApiResponse(description="Forbidden"),
        404: OpenApiResponse(description="Not Found"),
    },
    description="Get PDF URLs for comparing two versions of a project for a specific spec section.",
    methods=["GET"]
)
@api_view(['GET'])
def get_pdf_version_comparison(request):
    """Get PDF URLs for version comparison"""
    from apps.utils.feature_flags import is_versioning_pdf_comparison_feature_flag_active
    from ..serializers import VersionComparisonSerializer
    import boto3
    
    serializer = VersionComparisonSerializer(data=request.query_params)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    old_version = serializer.validated_data['old_version']
    new_version = serializer.validated_data['new_version']
    masterformat_number = serializer.validated_data['masterformat_number']
    project = Project.objects.get(id=old_version.project_id)
    
    # Check project access
    if not request.user.is_member_of_project(project):
        return Response({'detail': 'User is not a member of the project'}, status=status.HTTP_403_FORBIDDEN)

    # Check feature flag
    if not is_versioning_pdf_comparison_feature_flag_active(request.user, project.team, project):
        return Response({'detail': 'PDF comparison feature is not enabled'}, status=status.HTTP_403_FORBIDDEN)

    if old_version.project_id != new_version.project_id:
        return Response({'detail': 'Old and new versions must be from the same project'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Get documents for both versions
    old_documents = UploadedFile.objects.filter(project_version=old_version)
    new_documents = UploadedFile.objects.filter(project_version=new_version)
    
    if not old_documents.exists():
        return Response({'detail': 'No documents found for old version'}, status=status.HTTP_404_NOT_FOUND)
    
    if not new_documents.exists():
        return Response({'detail': 'No documents found for new version'}, status=status.HTTP_404_NOT_FOUND)
    
    # For now, we'll use the first document from each version
    # In the future, this could be enhanced to filter by spec section
    old_document = old_documents.first()
    new_document = new_documents.first()
    
    # Generate S3 presigned URLs
    s3 = boto3.client('s3')
    
    try:
        old_pdf_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.S3_BUCKET, 'Key': old_document.document_path},
            ExpiresIn=3600
        )
        
        new_pdf_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.S3_BUCKET, 'Key': new_document.document_path},
            ExpiresIn=3600
        )
        
        response_data = {
            'oldPdfUrl': old_pdf_url,
            'newPdfUrl': new_pdf_url,
            'metadata': {
                'oldVersionName': old_version.version_name,
                'newVersionName': new_version.version_name,
                'specSection': masterformat_number,
                'oldDocumentName': old_document.name,
                'newDocumentName': new_document.name
            }
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({'detail': f'Error generating PDF URLs: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
