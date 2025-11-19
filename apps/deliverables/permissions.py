from rest_framework import permissions
from rest_framework.request import Request
from django.urls import reverse
from .models import Project, ProjectVersion, SubmittalItem, Chat, AiGeneratedLog
from apps.utils.feature_flags import is_versioning_feature_flag_active


class ProjectAccessPermissions(permissions.BasePermission):
    """
    Permission to only allow admins of a project to edit the project object.

    Members of the project still have read-only access.
    """

    def has_permission(self, request: Request, view):
        # Allow read operations for any authenticated user
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated
        
        if request.method == 'POST' and request.path == reverse('deliverables:project-list'):
            team_id = request.data.get('team')
            if not team_id:
                return False
            return request.user.is_admin_for_team(team_id)
        
        if request.method == 'PATCH':
            team_id = request.data.get('team')
            if not team_id:
                return True
            return request.user.is_admin_for_team(team_id)
            
        # For other write operations, let has_object_permission handle it
        return True


    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request
        # so we'll always allow GET, HEAD or OPTIONS requests for members
        if request.method == 'DELETE':
            return request.user.is_admin_for_team(obj.team)
        
        # Allow members to add users to a project
        if request.path == reverse('deliverables:project-members-add', kwargs={'pk': obj.id}):
            return request.user.is_member_of_project(obj)
        return self._view_for_members_edit_for_admins(request, obj)
    

    def _view_for_members_edit_for_admins(self, request: Request, project: Project):
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_member_of_project(project)
        return request.user.is_admin_for_project(project)


class ProjectVersionAccessPermissions(permissions.BasePermission):
    """
    Permission to only allow admins of a project with versioning active to create, update, and delete project versions.
    """

    def has_permission(self, request: Request, view):
        project = Project.objects.get(id=view.kwargs['project_id'])
        return request.user.is_admin_for_project(project) and is_versioning_feature_flag_active(request.user, project.team)


class SubmittalListAccessPermissions(permissions.BasePermission):
    """
    Permission to allow any member of a project to access submittal lists.
    """

    def has_permission(self, request, view):
        return request.user.is_member_of_project(view.kwargs['project_id'])


class SubmittalItemAccessPermissions(permissions.BasePermission):
    """
    Permission to only allow members of a project to access submittal items.
    """

    def has_permission(self, request, view):
        return request.user.is_member_of_project(view.kwargs['project_id'])
    

class ChatAccessPermissions(permissions.BasePermission):
    """
    Permission to only allow members of a project to access chats.
    """

    def has_permission(self, request, view):
        return request.user.is_member_of_project(view.kwargs['project_id'])


class SpecCentricViewAccessPermissions(permissions.BasePermission):
    """
    Permission to only allow members of a project to access spec centric view.
    """

    def has_permission(self, request, view):
        return request.user.is_member_of_project(view.kwargs['project_id'])


class AiGeneratedLogAccessPermissions(permissions.BasePermission):
    """
    Permission to only allow members of a project to access AI generated logs.
    """

    def has_permission(self, request, view):
        project_id = view.kwargs.get('project_id')
        if project_id:
            return request.user.is_member_of_project(project_id)
        return True


    def has_object_permission(self, request, view, obj: AiGeneratedLog):
        return request.user.is_member_of_project(obj.project)


class ExtractionNoteAccessPermissions(permissions.BasePermission):
    """
    Ensure only project members can access notes and that only the author (or notes without an author)
    can be modified.
    """

    def _get_project_id(self, view):
        project_pk = view.kwargs.get('project_pk')
        if project_pk:
            return project_pk
        extracted_data = getattr(view, 'kwargs', {}).get('extracteddata_pk')
        if extracted_data:
            from apps.deliverables.models import ExtractedData
            try:
                return ExtractedData.objects.only('project_id').get(id=extracted_data).project_id
            except ExtractedData.DoesNotExist:
                return None
        return None

    def has_permission(self, request, view):
        project_id = self._get_project_id(view)
        return (
            request.user.is_authenticated
            and project_id is not None
            and request.user.is_member_of_project(project_id)
        )

    def has_object_permission(self, request, view, obj):
        project = obj.extracted_data.project
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_member_of_project(project)
        return obj.created_by is None or obj.created_by_id == request.user.id
