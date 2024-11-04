from rest_framework import status
from rest_framework.test import APITestCase
from django.urls import reverse
from .models import Project
from apps.users.models import CustomUser
from apps.teams.helpers import create_default_team_for_user

class ProjectArchiveTests(APITestCase):

    def setUp(self):
        email = "testuser@example.com"
        self.user = CustomUser.objects.create_user(username=email, email=email, password="testpass")
        self.team = create_default_team_for_user(self.user)
        self.client.force_authenticate(user=self.user)

        self.project = Project.objects.create(
            name="Test Project",
            owner=self.user,
            team=self.team,
            is_archived=False,
            status=Project.PROJECT_STATUS_OPEN
        )

    def test_archive_project(self):
        """Test that a project can be archived and status is updated to 'archived'."""
        url = reverse('deliverables:project-archive', args=[self.project.id])
        response = self.client.post(url)
        self.project.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(self.project.is_archived)
        self.assertEqual(self.project.status, Project.PROJECT_STATUS_ARCHIVED)
        self.assertIn("Project archived successfully.", response.data["status"])

    def test_unarchive_project(self):
        """Test that an archived project can be unarchived and status is restored."""
        self.project.is_archived = True
        self.project.status = Project.PROJECT_STATUS_ARCHIVED
        self.project.save()

        url = reverse('deliverables:project-archive', args=[self.project.id])
        response = self.client.post(url, data={"action": "restore"})  # Send payload to restore the project
        self.project.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(self.project.is_archived)
        self.assertEqual(self.project.status, Project.PROJECT_STATUS_OPEN)
        self.assertIn("Project unarchived successfully.", response.data["status"])

    def test_list_archived_projects(self):
        """Test filtering for archived projects."""
        self.project.is_archived = True
        self.project.status = Project.PROJECT_STATUS_ARCHIVED
        self.project.save()

        url = reverse('deliverables:project-list') + '?is_archived=true'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(any(proj['id'] == self.project.id for proj in response.data['results']))
        self.assertTrue(all(proj['status'] == Project.PROJECT_STATUS_ARCHIVED for proj in response.data['results']))
