from django.test import TestCase

# Create your tests here.
from rest_framework import status
from rest_framework.test import APITestCase
from django.urls import reverse
from .models import Project
from apps.users.models import CustomUser
from apps.teams.helpers import create_default_team_for_user

class ProjectArchiveTests(APITestCase):

    def setUp(self):
        # Setup user and team instances for testing
        email = "testuser@example.com"
        self.user = CustomUser.objects.create_user(username=email, email=email, password="testpass")
        self.team = create_default_team_for_user(self.user)  # Create a default team for the user
        self.client.force_authenticate(user=self.user)
        
        self.project = Project.objects.create(
            name="Test Project",
            owner=self.user,
            team=self.team,  # Associate the project with the created team
            is_archived=False
        )
    
    def test_archive_project(self):
        """Test that a project can be archived."""
        url = reverse('deliverables:project-archive', args=[self.project.id])
        response = self.client.post(url)
        self.project.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(self.project.is_archived)
        self.assertIn("Project archived successfully.", response.data["status"])

    def test_unarchive_project(self):
        """Test that an archived project can be unarchived."""
        # First archive the project
        self.project.is_archived = True
        self.project.save()
        
        url = reverse('deliverables:project-archive', args=[self.project.id])
        response = self.client.post(url)
        self.project.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(self.project.is_archived)
        self.assertIn("Project unarchived successfully.", response.data["status"])

    def test_list_archived_projects(self):
        """Test filtering for archived projects."""
        # Archive the project
        self.project.is_archived = True
        self.project.save()

        url = reverse('deliverables:project-list') + '?is_archived=true'
        response = self.client.get(url)

        # Print response content for debugging
        print(f"Response content: {response.content}")
        print(f"Response data: {response.data}")

        
        # Ensure archived projects are returned
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(any(proj['id'] == self.project.id for proj in response.data['results']))

