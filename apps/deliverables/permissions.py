from rest_framework import permissions
from rest_framework.request import Request
from django.urls import reverse
from .models import Project, SubmittalItem


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