import os
import time
import logging
from werkzeug.utils import secure_filename

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied, ValidationError as DRFValidationError

from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .serializers import ProjectReadSerializer, ProjectWriteSerializer, FileUploadSerializer
from rest_framework import viewsets
from .models import Entitlement, Project, ROLE_PROJECT_ADMIN, Document
from apps.teams.models import Team
from .permissions import ProjectAccessPermissions


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
        serializer.save()



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
            filename = secure_filename(f'project_{project_id}_{file.name}')
            document_path = f'original/{filename}'
            parsed_document_path = f'parsed/{filename}'

            Document.objects.create(
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

