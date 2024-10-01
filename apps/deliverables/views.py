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

from .serializers import ProjectReadSerializer, ProjectWriteSerializer
from rest_framework import viewsets
from .models import Entitlement, Project, ROLE_PROJECT_ADMIN
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

