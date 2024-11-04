import os
import time
import logging
import hashlib
import boto3
import shutil
import requests
import json
import re
from datetime import datetime

from django.conf import settings
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Func, F
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied, ValidationError as DRFValidationError
from rest_framework.pagination import PageNumberPagination

from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .serializers import (ProjectReadSerializer, ProjectWriteSerializer, FileUploadSerializer, SubmittalItemReadSerializer, SubmittalItemWriteSerializer,
                          SubmittalItemListSerializer)
from rest_framework import viewsets
from .models import (Entitlement, Project, ROLE_PROJECT_ADMIN, UploadedFile, SubmittalItem, SubmittalItemList, MasterFormatSection, SpecSection, DocProcessingStatus)
from apps.teams.models import Team
from .permissions import ProjectAccessPermissions, SubmittalItemAccessPermissions
import logging
from typing import TypedDict, Optional, List
from enum import Enum



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
        if self.action in ['list', 'retrieve']:
            return ProjectReadSerializer
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

        return queryset.order_by('name')

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
        
        if 'action' in request.data and request.data['action'] == 'restore':
            # Restore the project
            project.is_archived = False
            project.status = Project.PROJECT_STATUS_OPEN if project.status == Project.PROJECT_STATUS_ARCHIVED else project.status
            status_message = "unarchived"
        else:
            # Archive the project
            project.is_archived = True
            project.status = Project.PROJECT_STATUS_ARCHIVED
            status_message = "archived"
        
        project.save()
        return Response(
            {"status": f"Project {status_message} successfully."},
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
    # TODO: assign submittal numbers

    return Response(status=status.HTTP_200_OK)


class SubmittalItemListViewSet(viewsets.ModelViewSet):
    queryset = SubmittalItemList.objects.all()
    permission_classes = [IsAuthenticated, ProjectAccessPermissions]
    serializer_class = SubmittalItemListSerializer

    def get_queryset(self):
        project_id = self.kwargs.get('project_id')
        return self.queryset.filter(project_id=project_id)

