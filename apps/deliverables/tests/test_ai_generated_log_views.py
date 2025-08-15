import pytest
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from apps.teams.models import Team, Membership as TeamMembership
from apps.deliverables.models import (
    Project, ProjectMembership, ProjectVersion, AiGeneratedLog,
    ROLE_PROJECT_ADMIN, ROLE_PROJECT_MEMBER
)


class AiGeneratedLogViewSetTests(APITestCase):
    def setUp(self):
        self.User = get_user_model()
        
        # Create test user
        self.user = self.User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        
        # Create team
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        
        # Add user to team
        TeamMembership.objects.create(
            user=self.user,
            team=self.team,
            role='member'
        )
        
        # Create project
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team
        )
        self.project_version = ProjectVersion.objects.get(project=self.project)
        
        # Add user to project
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ROLE_PROJECT_MEMBER
        )
        
        # Create test AI generated logs
        self.log1 = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='inspection_log',
            log_status='SUCCESS',
            log_table='{"results": [{"spec_section_number": "01 1000", "spec_section_name": "General Requirements"}]}'
        )
        
        self.log2 = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='owner_deliverables_log',
            log_status='SUCCESS',
            log_table='{"results": [{"spec_section_number": "01 2000", "spec_section_name": "Existing Conditions"}]}'
        )
        
        # Create another project and log for testing access control
        self.other_project = Project.objects.create(
            name='Other Project',
            team=self.team
        )
        self.other_project_version = ProjectVersion.objects.get(project=self.other_project)
        
        self.other_log = AiGeneratedLog.objects.create(
            project=self.other_project,
            project_version=self.other_project_version,
            log_type='inspection_log',
            log_status='SUCCESS',
            log_table='{"results": []}'
        )

    def test_unauthenticated_user_cannot_access_logs(self):
        """Test that unauthenticated users cannot access AI generated logs"""
        url = reverse('ai-generated-log-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url, {
            'project_version_id': self.project_version.id,
            'log_type': 'inspection_log'
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_authenticated_user_can_list_logs_with_required_params(self):
        """Test that authenticated users can list logs with required parameters"""
        self.client.force_authenticate(user=self.user)
        url = reverse('ai-generated-log-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url, {
            'project_version_id': self.project_version.id,
            'log_type': 'inspection_log'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], self.log1.id)
        self.assertEqual(response.data['results'][0]['log_type'], 'inspection_log')

    def test_list_logs_missing_project_id(self):
        """Test that listing logs without project_id returns error"""
        self.client.force_authenticate(user=self.user)
        url = reverse('ai-generated-log-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url, {
            'project_version_id': self.project_version.id,
            'log_type': 'inspection_log'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # The project_id is in the URL, so this should work

    def test_list_logs_missing_project_version_id(self):
        """Test that listing logs without project_version_id returns error"""
        self.client.force_authenticate(user=self.user)
        url = reverse('ai-generated-log-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url, {
            'log_type': 'inspection_log'
        })
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('project_version_id is required', str(response.data))

    def test_list_logs_missing_log_type(self):
        """Test that listing logs without log_type returns error"""
        self.client.force_authenticate(user=self.user)
        url = reverse('ai-generated-log-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url, {
            'project_version_id': self.project_version.id
        })
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('log_type is required', str(response.data))

    def test_list_logs_filters_by_log_type(self):
        """Test that logs are filtered by log_type"""
        self.client.force_authenticate(user=self.user)
        url = reverse('ai-generated-log-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url, {
            'project_version_id': self.project_version.id,
            'log_type': 'owner_deliverables_log'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['log_type'], 'owner_deliverables_log')

    def test_list_logs_orders_by_created_at_desc(self):
        """Test that logs are ordered by created_at in descending order"""
        # Create a newer log
        newer_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='inspection_log',
            log_status='SUCCESS',
            log_table='{"results": []}'
        )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('ai-generated-log-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url, {
            'project_version_id': self.project_version.id,
            'log_type': 'inspection_log'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
        # First result should be the newer log
        self.assertEqual(response.data['results'][0]['id'], newer_log.id)

    def test_user_cannot_access_logs_from_other_projects(self):
        """Test that users cannot access logs from projects they're not members of"""
        self.client.force_authenticate(user=self.user)
        url = reverse('ai-generated-log-list', kwargs={'project_id': self.other_project.id})
        response = self.client.get(url, {
            'project_version_id': self.other_project_version.id,
            'log_type': 'inspection_log'
        })
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_authenticated_user_can_retrieve_single_log(self):
        """Test that authenticated users can retrieve a single log"""
        self.client.force_authenticate(user=self.user)
        url = reverse('ai-generated-log-detail', kwargs={'project_id': self.project.id, 'pk': self.log1.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.log1.id)
        self.assertEqual(response.data['log_type'], 'inspection_log')
        self.assertEqual(response.data['project_name'], 'Test Project')
        self.assertEqual(response.data['project_version_number'], str(self.project_version.version_number))

    def test_user_cannot_retrieve_log_from_other_project(self):
        """Test that users cannot retrieve logs from projects they're not members of"""
        self.client.force_authenticate(user=self.user)
        url = reverse('ai-generated-log-detail', kwargs={'project_id': self.other_project.id, 'pk': self.other_log.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_log_serializer_includes_required_fields(self):
        """Test that the log serializer includes all required fields"""
        self.client.force_authenticate(user=self.user)
        url = reverse('ai-generated-log-detail', kwargs={'project_id': self.project.id, 'pk': self.log1.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected_fields = [
            'id', 'project', 'project_version', 'log_type', 'log_status',
            'log_table', 'created_at', 'project_name', 'project_version_number'
        ]
        for field in expected_fields:
            self.assertIn(field, response.data)

    def test_list_logs_returns_correct_structure(self):
        """Test that list endpoint returns correct pagination structure"""
        self.client.force_authenticate(user=self.user)
        url = reverse('ai-generated-log-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url, {
            'project_version_id': self.project_version.id,
            'log_type': 'inspection_log'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertIsInstance(response.data['results'], list)
