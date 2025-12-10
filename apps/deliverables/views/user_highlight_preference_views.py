from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.deliverables.models import UserHighlightPreference, Project
from apps.deliverables.permissions import ProjectAccessPermissions
from apps.deliverables.serializers.user_highlight_preference import (
    UserHighlightPreferenceSerializer,
)


class UserHighlightPreferenceAccessPermissions(ProjectAccessPermissions):
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, "project"):
            obj = obj.project
        return super().has_object_permission(request, view, obj)


class UserHighlightPreferenceViewSet(viewsets.ViewSet):
    """
    Manage user's last used highlight type preference per project.

    Endpoints:
    - GET /api/deliverables/projects/{project_id}/highlight-preference/ - Get user's preference
    - POST /api/deliverables/projects/{project_id}/highlight-preference/ - Set user's preference
    """

    permission_classes = [IsAuthenticated, UserHighlightPreferenceAccessPermissions]

    def _get_project_id(self):
        return self.kwargs.get("project_pk") or self.kwargs.get("project_id")

    def _get_project(self):
        project_id = self._get_project_id()
        return get_object_or_404(Project, pk=project_id)

    def list(self, request, *args, **kwargs):
        """
        Get the user's last used highlight type preference for this project.
        Returns 404 if no preference exists yet.
        """
        project = self._get_project()
        self.check_object_permissions(request, project)

        try:
            preference = UserHighlightPreference.objects.select_related(
                'custom_item_type', 'project', 'user'
            ).get(
                user=request.user,
                project=project
            )
            serializer = UserHighlightPreferenceSerializer(preference)
            return Response(serializer.data)
        except UserHighlightPreference.DoesNotExist:
            return Response(
                {"detail": "No highlight preference found for this user and project."},
                status=status.HTTP_404_NOT_FOUND
            )

    def create(self, request, *args, **kwargs):
        """
        Create or update the user's highlight preference for this project.
        Uses upsert logic - only one preference per user per project.
        """
        project = self._get_project()
        self.check_object_permissions(request, project)

        serializer = UserHighlightPreferenceSerializer(
            data=request.data,
            context={"request": request, "project": project}
        )

        if serializer.is_valid():
            preference = serializer.save()
            return Response(
                UserHighlightPreferenceSerializer(preference).data,
                status=status.HTTP_200_OK
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
