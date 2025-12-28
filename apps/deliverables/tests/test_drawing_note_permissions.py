# apps/deliverables/tests/test_drawing_note_permissions.py
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from apps.teams.models import Team
from apps.deliverables.models import (
    Project, ProjectMembership, ROLE_PROJECT_MEMBER,
)
from apps.deliverables.permissions import DrawingNoteAccessPermissions

User = get_user_model()


class TestDrawingNoteAccessPermissions(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user('test@example.com')
        self.other_user = User.objects.create_user('other@example.com')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(
            name="Test Project",
            project_number="P-001",
            team=self.team,
            created_by=self.user
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ROLE_PROJECT_MEMBER
        )
        self.permission = DrawingNoteAccessPermissions()

    def test_member_has_permission(self):
        """Test project member has access"""
        request = self.factory.get('/')
        request.user = self.user

        class MockView:
            kwargs = {'project_id': self.project.id}

        self.assertTrue(self.permission.has_permission(request, MockView()))

    def test_non_member_denied(self):
        """Test non-member is denied access"""
        request = self.factory.get('/')
        request.user = self.other_user

        class MockView:
            kwargs = {'project_id': self.project.id}

        self.assertFalse(self.permission.has_permission(request, MockView()))
