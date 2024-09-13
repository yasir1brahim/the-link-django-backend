from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied, ValidationError as DRFValidationError

from .serializers import ProjectSerializer
from rest_framework import viewsets
from .models import Entitlement, Project, ROLE_PROJECT_ADMIN
from .permissions import ProjectAccessPermissions


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, ProjectAccessPermissions]
    
    def get_queryset(self):
        return self.queryset.filter(members=self.request.user)

    def perform_create(self, serializer):
        team = serializer.validated_data["team"]
        if not self.request.user.is_member_of_team(team):
            raise PermissionDenied()
        project = serializer.save()
        project.members.add(self.request.user, through_defaults={"role": ROLE_PROJECT_ADMIN})






class CanCreateProject(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_admin_for_team(request.team)


@api_view(['POST'])
@permission_classes([IsAuthenticated, CanCreateProject])
def create_project(request):
    serializer = ProjectSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)