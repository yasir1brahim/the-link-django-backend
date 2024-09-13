from rest_framework import permissions
from rest_framework.request import Request

from .models import Project


class ProjectAccessPermissions(permissions.BasePermission):
    """
    Permission to only allow admins of a project to edit the project object.

    Members of the project still have read-only access.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request
        # so we'll always allow GET, HEAD or OPTIONS requests for members
        return _view_for_members_edit_for_admins(request, obj)
    

def _view_for_members_edit_for_admins(request: Request, project: Project):
    if request.method in permissions.SAFE_METHODS:
        return request.user.is_member_of_project(project)
    return request.user.is_admin_for_project(project)