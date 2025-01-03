from typing import TypedDict, List

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
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

from django.http import HttpResponse
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.db.models import Q
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
from .serializers import (
    ProjectDetailsSerializer,
    ProjectListSerializer,
    ProjectWriteSerializer,
    FileUploadSerializer,
    SubmittalItemReadSerializer,
    SubmittalItemWriteSerializer,
    SubmittalItemListSerializer,
    ExcelExportHeaderSerializer,
    CombineSubmittalItemsSerializer,
)
from .models import (
    Project,
    UploadedFile,
    SubmittalItem,
    SubmittalItemList,
    MasterFormatSection,
    SpecSection,
    DocProcessingStatus,
    ExcelExportHeader,
    NoticeMatch,
    ProcoreToken,
    ProcoreSubmittalTypeMapping,
)
from .permissions import (
    ProjectAccessPermissions,
    SubmittalItemAccessPermissions,
    SubmittalListAccessPermissions,
)
from .constants import masterformat_to_section_title_map
from .serializers.notices import NoticeMatchProcessingSerializer, NoticeMatchSerializer, NoticeProcessingCallbackSerializer
from .serializers.procore import (ProcoreFetchAccessTokenSerializer, ProcoreAccessTokenSerializer,
                                   ProcoreCompanyMappingSerializer, ProcoreCompanySerializer, ProcoreMeSerializer,
                                   ProcoreProjectMappingSerializer, ProcoreSubmittalSerializer,
                                   ProcoreSubmittalCreationResponseSerializer, CreateProcoreProjectMappingSerializer,
                                   CreateProcoreCompanyMappingSerializer, UpdateProcoreSubmittalMappingsSerializer)
from .services import SubmittalService
from .integrations.procore import (get_procore_access_token, get_companies, get_fresh_token_for_user, 
                                   ProcoreException, get_me, get_status, get_spec_divisions, get_spec_sections,
                                   create_spec_division, create_spec_section, create_submittal, get_projects,
                                   get_managers, get_submittal_types)

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


class SpecStatusRequest(TypedDict):
    new_status: str
    document_id: str
    filename: str
    project_id: str
    user_id: str
    submittals: List[SubmittalInfo]
    subsections: List[SpecSubSection]


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    permission_classes = [IsAuthenticated, ProjectAccessPermissions]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProjectDetailsSerializer
        if self.action == 'list':
            return ProjectListSerializer
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

        return queryset.select_related('team').prefetch_related('members').order_by('name')

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
        if order_col == 'spec_section':
            order_string += "masterformat_section__masterformat_number"
        elif order_col == 'type':
            order_string += "submittal_type"
        elif order_col == 'item_desc':
            order_string += "submittal_description"
        elif order_col == 'para_context':
            order_string += "submittal_content"
        return queryset.order_by(order_string)

    def get_queryset(self):
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
                'submittal_number',
                'masterformat_section__masterformat_number',
                'heirarchical_paragraph_number'
            )
        
        if list_id:
            queryset = queryset.filter(submittal_lists__id=list_id)
        
        if len(records) > 0 and records[0] != 'All':
            records = [int(record) for record in records]
            queryset = queryset.filter(id__in=records)

        return queryset
            

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, project_id=self.kwargs.get('project_id'))

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def _get_sel_filter_vals(self, result_queryset):
        return {
            'item_desc': result_queryset.values_list('submittal_description', flat=True).distinct().order_by(),
            'para_no': result_queryset.values_list('paragraph_number', flat=True).distinct().order_by(),
            'spec_section': result_queryset.values_list('masterformat_section__masterformat_number', flat=True).distinct().order_by(),
            'type': result_queryset.values_list('submittal_type', flat=True).distinct().order_by(),
        }
    
    def _get_all_filter_vals(self):
        project_id = self.kwargs.get('project_id')
        queryset = self.queryset.filter(project_id=project_id)
        queryset = queryset.exclude(submittal_type='Unclassified', masterformat_section__masterformat_number__regex='^0[012]\\d+')
        return {
            'item_desc': queryset.values_list('submittal_description', flat=True).distinct().order_by(),
            'para_no': queryset.values_list('paragraph_number', flat=True).distinct().order_by(),
            'spec_section': queryset.values_list('masterformat_section__masterformat_number', flat=True).distinct().order_by(),
            'type': queryset.values_list('submittal_type', flat=True).distinct().order_by(),
        }

    def _get_submittal_heading_lov(self, result_queryset):
        return result_queryset.values_list('submittal_type', flat=True).distinct().order_by()

    def _get_submittal_type_lov(self, result_queryset):
        return result_queryset.values_list('submittal_description', flat=True).distinct().order_by()

    @extend_schema(
        parameters=[
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
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            data = self.get_paginated_response(serializer.data).data
        else:
            serializer = self.get_serializer(queryset, many=True)
            data = serializer.data


        response_data = {
            'sel_filter_vals': self._get_sel_filter_vals(queryset),
            'all_filter_vals': self._get_all_filter_vals(),
            'log_id_list': [log.id for log in queryset],
            'message': data['results'],
            'total_count': data['count'],
            'submittal_heading_lov': self._get_submittal_heading_lov(queryset),
            'submittal_type_lov': self._get_submittal_type_lov(queryset),
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
        queryset = self.filter_queryset(self.get_queryset())
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
            if len(header_options) == 0:
                row = [
                    item.submittal_number,
                    item.masterformat_section.masterformat_number,
                    item.masterformat_section.masterformat_description or masterformat_to_section_title_map.get(item.masterformat_section.masterformat_number, 'Custom Title'),
                    item.paragraph_number,
                    item.submittal_type,
                    item.submittal_description,
                    item.submittal_content
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
                        field_value = item.masterformat_section.masterformat_description or masterformat_to_section_title_map.get(item.masterformat_section.masterformat_number, 'Custom Title')
                    elif header_option['name'] == 'Paragraph':
                        field_value = item.paragraph_number
                    elif header_option['name'] == 'Submittal Type':
                        field_value = item.submittal_type
                    elif header_option['name'] == 'Submittal Title':
                        field_value = item.submittal_description
                    elif header_option['name'] == 'Submittal Description':
                        field_value = item.submittal_content
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
        queryset = self.filter_queryset(self.get_queryset())
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


    
def invoke_lambda(payload, lambda_url):
    try:
        requests.post(lambda_url, json=payload, timeout=2)
    except requests.exceptions.ReadTimeout:
        # if we timed out, it's a larger document and the lambda is processing it
        pass

def parse_spec(callback_url, document_id, project_id, object_key, filename, user_id):
    logging.debug(f"parse_spec: {object_key}")

    CHUNK_SIZE = 1200
    CHUNK_OVERLAP = 100

    payload = {
        "object_key": object_key,
        "document_id": str(document_id),
        "filename": filename,
        "user_id": user_id,
        "project_id": project_id,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "callback_url": callback_url,
        "ENVIRONMENT": settings.ENVIRONMENT,
        "AWS_UPLOAD_BUCKET": settings.S3_BUCKET
    }

    # update the document status to processing
    UploadedFile.objects.filter(id=document_id).update(last_retry=datetime.now())

    print(f"Invoking lambda with URL: {settings.LAMBDA_FUNCTION_URL}")
    print(f"Invoking lambda with payload: {payload}")

    invoke_lambda(
        payload=payload,
        lambda_url=settings.LAMBDA_FUNCTION_URL
    )

    return "Kicked off processing job"



def call_extract_notices_lambda(callback_url, document_id, object_key):
    logging.debug(f"call_extract_notices_lambda: {object_key}")

    payload = {
        "source_file_s3_uri": f"s3://{settings.S3_BUCKET}/{object_key}",
        "document_id": str(document_id),
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


def is_notices_flag_active(request, team):
    return flag_is_active(request, settings.NOTICES_FEATURE_FLAG_NAME) or Flag.objects.filter(name=settings.NOTICES_FEATURE_FLAG_NAME, teams=team).exists()



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
        
    serializer = FileUploadSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    project_id = serializer.validated_data['project_id']
    print(serializer.validated_data)
    extract_notices = serializer.validated_data.get('extract_notices', False)
    project = Project.objects.get(id=project_id)
    if not request.user.is_member_of_project(project):
        return Response({'detail': 'User is not a member of the project'}, status=status.HTTP_403_FORBIDDEN)

    user = request.user
    files = serializer.validated_data['files']

    if not files:
        return Response({'detail': 'No files provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    already_existing_files = []
    async_processing = []
    not_parsed = []

    for file in files:
        try:
            filename = f'project_{project_id}__{int(time.time())}_{file.name}'
            document_path = f'original/{filename}'
            parsed_document_path = f'parsed/{filename}'
            file_md5 = get_file_hash(file)

            # check if file already exists
            matching_files = UploadedFile.objects.filter(md5=file_md5, name=file.name, project_id=project_id)
            if matching_files.exists():
                already_existing_files.append(file.name)
                continue

            uploaded_file = UploadedFile.objects.create(
                project_id=project_id,
                uploaded_by=user,
                name=file.name,
                md5=file_md5,
                document_path=document_path,
                parsed_document_path=parsed_document_path,
                processing_status='PENDING_PROCESSING',
            )
            
            file.seek(0)
            s3.upload_fileobj(
                Fileobj=file,
                Bucket=settings.S3_BUCKET,
                Key=document_path,
            )
            if is_notices_flag_active(request, project.team) and extract_notices:
                call_extract_notices_lambda(
                    callback_url=settings.BACKEND_NOTICES_CALLBACK_URL,
                    document_id=str(uploaded_file.id),
                    object_key=document_path,
                )
            else:
                parse_spec(
                    callback_url=settings.BACKEND_CALLBACK_URL,
                    document_id=str(uploaded_file.id),
                    project_id=str(project_id),
                    object_key=document_path,
                    filename=file.name,
                    user_id=str(user.id)
                )
            async_processing.append(document_path)
        except Exception as e:
            logging.error(f"Error uploading file: {e}")
            not_parsed.append(file.name)
    return Response({
        'error_parsing': not_parsed,
        'already_exist': already_existing_files,
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

@extend_schema(
    request=FileUploadSerializer,
    responses={200: {'description': 'File uploaded successfully'}},
    description="Upload a file to the server.",
    methods=["POST"]
)
@api_view(['POST'])
@permission_classes([AllowAny])
def spec_status_webhook(request):
    print(f"SPEC STATUS WEBHOOK: Received request")
    print(request.__dict__)
    request_payload = request.data
    print(f"SPEC STATUS WEBHOOK: {request_payload}")

    request_data = SpecStatusRequest(**request_payload)

    if request_data['new_status'] == 'SUBSECTIONS_EXTRACTED':
        print(f"SPEC STATUS WEBHOOK: setting document {request_data['document_id']} processing status to SUBSECTIONS_EXTRACTED")
        UploadedFile.objects.filter(id=int(request_data['document_id'])).update(processing_status=DocProcessingStatus.SUBSECTIONS_EXTRACTED)
        for subsection in request_data['subsections']:
            print(f"SPEC STATUS WEBHOOK: inserting subsection {subsection['master_format_section_number']} for document {request_data['document_id']}")
            masterformat_section, created = MasterFormatSection.objects.get_or_create(masterformat_number=subsection['master_format_section_number'])
            section, created = SpecSection.objects.get_or_create(
                document_id=request_data['document_id'],
                masterformat_section=masterformat_section,
            )
            section.processing_status = DocProcessingStatus.PENDING_PROCESSING
            section.save()
    elif request_data['new_status'] == 'PROCESSED_SECTION':
        print(f"SPEC STATUS WEBHOOK: saving submittals")
        for submittal in request_data['submittals']:
            submittal_text = change_encode_value(submittal['submittal_text'])
            masterformat_section, created = MasterFormatSection.objects.get_or_create(masterformat_number=request_data['master_format_section_number'])
            submittal_item = SubmittalItem.objects.create(
                project_id=request_data['project_id'],
                masterformat_section=masterformat_section,
                submittal_type=submittal['submittal_type'],
                submittal_description=submittal['submittal_description'],
                submittal_content=submittal_text,
                paragraph_number=submittal['section'],
                text_location=submittal['text_location'],
                document_id=request_data['document_id'],
                parsing_method=submittal.get('parsing_method', 'UNKNOWN'),
                additional_text_locations=submittal.get('additional_text_locations', [])
            )
        SpecSection.objects.filter(
            document_id=int(request_data['document_id']),
            masterformat_section__masterformat_number=request_data['master_format_section_number']
        ).update(processing_status=DocProcessingStatus.PROCESSED)
    elif request_data['new_status'] == 'FAILED':
        document = UploadedFile.objects.filter(id=int(request_data['document_id'])).first()
        if document.processing_status == DocProcessingStatus.SUBSECTIONS_EXTRACTED:
            document.processing_status = DocProcessingStatus.SECTION_PROCESSING_FAILED
            document.save()
        else:
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
        if unprocessed_spec_section_count == 0:
            print(f"SPEC STATUS WEBHOOK: all subsections have been processed for document {request_data['document_id']}")
            document.processing_status = DocProcessingStatus.PROCESSED
            document.save()

    logger.debug(f"SPEC STATUS WEBHOOK: determining whether to assign submittal numbers...")
    SubmittalService.assign_submittal_numbers(
        # TODO: Replace `int` cast here with actually enforcing integer input
        project=int(request_data['project_id']),
        only_if_all_documents_processed=True,
    )

    return Response(status=status.HTTP_200_OK)

# endregion submittal webhook


class SubmittalItemListViewSet(viewsets.ModelViewSet):
    queryset = SubmittalItemList.objects.all()
    permission_classes = [IsAuthenticated, SubmittalListAccessPermissions]
    serializer_class = SubmittalItemListSerializer

    def get_queryset(self):
        project_id = self.kwargs.get('project_id')
        return self.queryset.filter(project_id=project_id)


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
                'created_at': procore_token.created_at,
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

    def get_submittals(self, project, submittal_ids_to_post_to_procore, export_all):
        if export_all:
            submittals = SubmittalItem.objects.filter(project_id=project.id)
        else:
            submittals = SubmittalItem.objects.filter(id__in=submittal_ids_to_post_to_procore)
        return submittals


    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project_id = serializer.validated_data.get('project_id')
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
        
        status_response = get_status(project.team.procore_id, procore_token.access_token)
        if status_response.status_code != 200:
            print("Error getting procore status")
            return Response(status_response.text, status=status.HTTP_400_BAD_REQUEST)
        open_statuses = [status for status in status_response.json() if status["name"] == "Open"]
        status_id = open_statuses[0]["id"] if open_statuses else None
        if status_id is None:
            print("Error getting procore status id")
            return Response(status=status.HTTP_400_BAD_REQUEST)
        
        submittals: List[SubmittalItem] = self.get_submittals(project, submittal_ids_to_post_to_procore, export_all)
        spec_section_list = list(set([str(submittal.masterformat_section.masterformat_number) for submittal in submittals]))

        procore_spec_divisions_response = get_spec_divisions(project.procore_id, procore_token.access_token)
        if procore_spec_divisions_response.status_code != 200:
            print("Error getting procore spec divisions")
            return Response(procore_spec_divisions_response.text, status=status.HTTP_400_BAD_REQUEST)
        procore_spec_divisions = procore_spec_divisions_response.json()
        procore_division_numbers = [d['number'] for d in procore_spec_divisions]
        procore_division_ids = [str(d['id']) for d in procore_spec_divisions]
        procore_division_dict = dict(map(lambda i, j: (i, j), procore_division_numbers, procore_division_ids))

        procore_spec_sections = get_spec_sections(project.procore_id, procore_token.access_token)
        if procore_spec_sections.status_code != 200:
            print("Error getting procore spec sections")
            return Response(procore_spec_sections.text, status=status.HTTP_400_BAD_REQUEST)
        procore_spec_sections = procore_spec_sections.json()
        procore_spec_section_numbers = [d['number'] for d in procore_spec_sections]
        procore_spec_section_ids = [str(d['id']) for d in procore_spec_sections]
        procore_spec_section_dict = dict(map(lambda i, j: (i, j), procore_spec_section_numbers, procore_spec_section_ids))

        for spec_section in spec_section_list:
            spec_section_division = spec_section[0:2]
            if spec_section_division == "":
                continue
            if spec_section_division not in procore_division_numbers:
                create_div_response = create_spec_division(project.procore_id, spec_section_division, procore_token.access_token)
                if create_div_response.status_code != 201:
                    continue
                else:
                    procore_division_dict[spec_section_division] = create_div_response.json()
            else:
                print("Division: " + spec_section_division + " already exists")
            
            if spec_section not in procore_spec_section_numbers:
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
                    return Response(create_spec_response.json(), status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                else:
                    procore_spec_section_dict[spec_section] = create_spec_response.json()
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
        token = get_object_or_404(ProcoreToken, user=user)
        token.delete()
        return Response(status=status.HTTP_200_OK)
    

class GetProcoreProjectsView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        procore_company_id = kwargs.get('procore_company_id')
        try:
            procore_token = get_fresh_token_for_user(request.user)
        except ProcoreException as e:
            return Response(str(e), status=status.HTTP_400_BAD_REQUEST)
        
        response = get_projects(procore_company_id, procore_token.access_token)
        if response.status_code != 200:
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
            return Response(str(e), status=status.HTTP_400_BAD_REQUEST)
        
        response = get_managers(procore_project_id, procore_token.access_token)
        if response.status_code != 200:
            return Response(response.text, status=status.HTTP_400_BAD_REQUEST)
        managers_list = []
        for manager in response.json():
            managers_list.append({
                'key': manager['id'],
                'value': manager['name']
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
