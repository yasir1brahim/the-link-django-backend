from typing import TypedDict, List

import logging
import time
import hashlib
import boto3
import requests
import re
from enum import Enum
from datetime import datetime

import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

from django.http import HttpResponse
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import generics, status
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

from apps.teams.models import Team
from .serializers import (
    ProjectDetailsSerializer,
    ProjectListSerializer,
    ProjectWriteSerializer,
    FileUploadSerializer,
    SubmittalItemReadSerializer,
    SubmittalItemWriteSerializer,
    SubmittalItemListSerializer,
    ExcelExportHeaderSerializer,
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
)
from .permissions import (
    ProjectAccessPermissions,
    SubmittalItemAccessPermissions,
    SubmittalListAccessPermissions,
)
from .constants import masterformat_to_section_title_map
from .services import SubmittalService


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
    logger.debug(f"SPEC STATUS WEBHOOK: Received request")
    logger.debug(f"SPEC STATUS WEBHOOK: {request.data}")

    request_data = SpecStatusRequest(**request.data)

    if request_data['new_status'] == 'SUBSECTIONS_EXTRACTED':
        logger.debug(f"SPEC STATUS WEBHOOK: setting document {request_data['document_id']} processing status to SUBSECTIONS_EXTRACTED")
        UploadedFile.objects.filter(id=request_data['document_id']).update(processing_status=DocProcessingStatus.SUBSECTIONS_EXTRACTED)
        for subsection in request_data['subsections']:
            logger.debug(f"SPEC STATUS WEBHOOK: inserting subsection {subsection['master_format_section_number']} for document {request_data['document_id']}")
            masterformat_section, created = MasterFormatSection.objects.get_or_create(masterformat_number=subsection['master_format_section_number'])
            section, created = SpecSection.objects.get_or_create(
                document_id=request_data['document_id'],
                masterformat_section=masterformat_section,
            )
            section.processing_status = DocProcessingStatus.PENDING_PROCESSING
            section.save()
    elif request_data['new_status'] == 'PROCESSED_SECTION':
        logger.debug(f"SPEC STATUS WEBHOOK: saving submittals")
        submittal_items = []
        for submittal in request_data['submittals']:
            submittal_text = change_encode_value(submittal['submittal_text'])
            masterformat_section, created = MasterFormatSection.objects.get_or_create(masterformat_number=request_data['master_format_section_number'])
            submittal_item = SubmittalItem(
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
            submittal_items.append(submittal_item)
        SubmittalItem.objects.bulk_create(submittal_items, ignore_conflicts=True)
        SpecSection.objects.filter(
            document_id=request_data['document_id'],
            masterformat_section__masterformat_number=request_data['master_format_section_number']
        ).update(processing_status=DocProcessingStatus.PROCESSED)
    elif request_data['new_status'] == 'FAILED':
        document = UploadedFile.objects.filter(id=request_data['document_id']).first()
        if document.processing_status == DocProcessingStatus.SUBSECTIONS_EXTRACTED:
            document.processing_status = DocProcessingStatus.SECTION_PROCESSING_FAILED
            document.save()
        else:
            document.processing_status = DocProcessingStatus.FAILED
            document.save()
    """IF document.processing_status == SUBSECTIONS_EXTRACTED or SECTION_PROCESSING_FAILED then we have records of all extracted subsections.
    If so, then update document.processing_status to PROCESSED if all subsections have been processed"""
    logger.debug(f"SPEC STATUS WEBHOOK: checking if all subsections have been processed for document {request_data['document_id']}")
    document = UploadedFile.objects.filter(id=request_data['document_id']).first()
    if document.processing_status in [DocProcessingStatus.SUBSECTIONS_EXTRACTED, DocProcessingStatus.SECTION_PROCESSING_FAILED]:
        logger.debug(f"SPEC STATUS WEBHOOK: getting unprocessed section count for document {request_data['document_id']}")
        unprocessed_spec_section_count = SpecSection.objects.filter(document_id=request_data['document_id']).exclude(
            processing_status=DocProcessingStatus.PROCESSED
        ).count()
        if unprocessed_spec_section_count == 0:
            logger.debug(f"SPEC STATUS WEBHOOK: all subsections have been processed for document {request_data['document_id']}")
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
