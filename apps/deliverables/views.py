import os
import time
import logging

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Func, F
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
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
from .models import Entitlement, Project, ROLE_PROJECT_ADMIN, UploadedFile, SubmittalItem, SubmittalItemList
from apps.teams.models import Team
from .permissions import ProjectAccessPermissions, SubmittalItemAccessPermissions


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
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        queryset = self.queryset.filter(Q(members=self.request.user) | Q(owner=self.request.user))
        # Get the team_id from query parameters
        team_id = self.request.query_params.get('team_id', None)
        
        if team_id is not None:
            try:
                team_id = int(team_id)
                team = get_object_or_404(Team, id=team_id)
                
                # Check if the user is a member of the team
                if not self.request.user.is_member_of_team(team):
                    raise PermissionDenied("You don't have permission to access projects for this team.")
                
                queryset = queryset.filter(team_id=team_id)
            except ValueError:
                raise DRFValidationError("Invalid team_id. Must be an integer.")
        
        return queryset.order_by('name')

    def perform_create(self, serializer):
        team = serializer.validated_data["team"]
        if not self.request.user.is_member_of_team(team):
            raise PermissionDenied()
        serializer.save(created_by=self.request.user)


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



def create_temp_dir():
    dir_path = os.getcwd() + '/uploads/'
    if not os.path.exists(dir_path):
        os.mkdir(dir_path)
    dir_path += str(int(time.time())) + '/'
    if os.path.exists(dir_path):
        for f in os.listdir(dir_path):
            os.remove(os.path.join(dir_path, f))
        logging.debug("Temp files deleted")
    else:
        os.mkdir(dir_path)
    return dir_path


@extend_schema(
    request=FileUploadSerializer,
    responses={200: {'description': 'File uploaded successfully'}},
    description="Upload a file to the server.",
    methods=["POST"]
)
@api_view(['POST'])
def upload_file(request):
    serializer = FileUploadSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    project_id = serializer.validated_data['project_id']
    user = request.user
    files = serializer.validated_data['files']

    if not files:
        return Response({'detail': 'No files provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    temp_base_dir = create_temp_dir()

    for file in files:
        try:
            filename = f'project_{project_id}_{file.name}_{int(time.time())}'
            document_path = f'original/{filename}'
            parsed_document_path = f'parsed/{filename}'

            UploadedFile.objects.create(
                file=file,
                project_id=project_id,
                uploaded_by=user,
                name=filename,
                path=document_path,
                parsed_path=parsed_document_path,
                status='uploaded',
            )
        except Exception as e:
            logging.error(f"Error uploading file: {e}")
            return Response({'detail': 'Error uploading file'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response({'detail': 'File uploaded successfully'}, status=status.HTTP_200_OK)


class SubmittalItemListViewSet(viewsets.ModelViewSet):
    queryset = SubmittalItemList.objects.all()
    permission_classes = [IsAuthenticated, ProjectAccessPermissions]
    serializer_class = SubmittalItemListSerializer

    def get_queryset(self):
        project_id = self.kwargs.get('project_id')
        return self.queryset.filter(project_id=project_id)

