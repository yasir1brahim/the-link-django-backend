"""
Tests for the inspection log data tables feature.

This module tests all backend changes related to the inspection_log_use_data_tables feature flag,
including model updates, webhook handling, API serializers, and sorting functionality.
"""

import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.deliverables.models import (
    Project, ProjectVersion, AiGeneratedLog, ProjectMembership
)
from apps.teams.models import Team, Membership
from apps.utils.feature_flags import is_inspection_log_use_data_tables_feature_flag_active
from apps.deliverables.serializers.specgpt import AiGeneratedLogSerializer
from apps.deliverables.views.specgpt_views import AiGeneratedLogViewSet

User = get_user_model()


class FeatureFlagTests(TestCase):
    """Test feature flag functionality."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team')
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team
        )
        
    def test_feature_flag_inactive_by_default(self):
        """Test that feature flag is inactive by default."""
        is_active = is_inspection_log_use_data_tables_feature_flag_active(
            self.user, self.team, self.project
        )
        self.assertFalse(is_active)
    
    @override_settings(INSPECTION_LOG_USE_DATA_TABLES_FEATURE_FLAG_NAME='test_flag')
    def test_feature_flag_active_when_enabled(self):
        """Test that feature flag is active when enabled."""
        # Mock the feature flag as active
        with patch('apps.utils.feature_flags.get_active_flags_for_user') as mock_user_flags, \
             patch('apps.utils.feature_flags.get_active_flags_for_team') as mock_team_flags, \
             patch('apps.utils.feature_flags.get_active_flags_for_project') as mock_project_flags:
            
            mock_user_flags.return_value = ['test_flag']
            mock_team_flags.return_value = []
            mock_project_flags.return_value = []
            
            is_active = is_inspection_log_use_data_tables_feature_flag_active(
                self.user, self.team, self.project
            )
            self.assertTrue(is_active)


class AiGeneratedLogModelTests(TestCase):
    """Test AiGeneratedLog model updates."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team')
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team
        )
        self.project_version = ProjectVersion.objects.create(
            project=self.project,
            version_name='v1.0'
        )
    
    def test_log_data_field_exists(self):
        """Test that log_data field exists and can store JSON data."""
        # Sample structured data
        structured_data = [
            {
                'Spec Section #': '01 1000',
                'Spec Section Name': 'GENERAL REQUIREMENTS',
                'Inspection Type And Requirements': 'Review submittals',
                'Inspection Frequency': 'As required',
                'Responsible Party': 'Architect'
            }
        ]
        
        log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='inspection_log',
            log_status='SUCCESS',
            log_table='# Test Markdown Table',
            log_data=structured_data
        )
        
        self.assertEqual(log.log_data, structured_data)
        self.assertIsInstance(log.log_data, list)
        self.assertEqual(len(log.log_data), 1)
        self.assertEqual(log.log_data[0]['Spec Section #'], '01 1000')
    
    def test_log_data_field_nullable(self):
        """Test that log_data field can be null."""
        log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='inspection_log',
            log_status='SUCCESS',
            log_table='# Test Markdown Table',
            log_data=None
        )
        
        self.assertIsNone(log.log_data)
    
    def test_log_data_field_blank(self):
        """Test that log_data field can be blank."""
        log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='inspection_log',
            log_status='SUCCESS',
            log_table='# Test Markdown Table',
            log_data=[]
        )
        
        self.assertEqual(log.log_data, [])


class WebhookHandlerTests(TestCase):
    """Test webhook handler for structured data processing."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team')
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team
        )
        self.project_version = ProjectVersion.objects.create(
            project=self.project,
            version_name='v1.0'
        )
        self.log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='inspection_log',
            log_status='PROCESSING',
            log_table='',
            log_data=None
        )
    
    @patch('apps.deliverables.views.specgpt_views.convert_to_markdown_table')
    def test_webhook_handles_structured_data(self, mock_convert):
        """Test webhook handles structured data correctly."""
        from apps.deliverables.views.specgpt_views import ai_log_generation_webhook
        from django.test import RequestFactory
        from django.http import HttpRequest
        import json
        
        # Mock the conversion function
        mock_convert.return_value = '# Converted Markdown Table'
        
        # Sample structured data
        structured_data = [
            {
                'Spec Section #': '01 1000',
                'Spec Section Name': 'GENERAL REQUIREMENTS',
                'Inspection Type And Requirements': 'Review submittals',
                'Inspection Frequency': 'As required',
                'Responsible Party': 'Architect'
            }
        ]
        
        # Create a real Django request
        factory = RequestFactory()
        request = factory.post('/webhook/', data=json.dumps({
            'log_type': 'inspection_log',
            'project_id': str(self.project.id),
            'project_version_id': str(self.project_version.id),
            'new_status': 'SUCCESS',
            'table': structured_data  # Structured data instead of markdown string
        }), content_type='application/json')
        
        # Call the webhook
        response = ai_log_generation_webhook(request)
        
        # Refresh the log from database
        self.log.refresh_from_db()
        
        # Verify the log was updated correctly
        self.assertEqual(self.log.log_status, 'SUCCESS')
        self.assertEqual(self.log.log_data, structured_data)
        self.assertEqual(self.log.log_table, '# Converted Markdown Table')
        
        # Verify conversion was called
        mock_convert.assert_called_once()
    
    def test_webhook_handles_markdown_fallback(self):
        """Test webhook handles markdown data correctly."""
        from apps.deliverables.views.specgpt_views import ai_log_generation_webhook
        from django.test import RequestFactory
        import json
        
        # Sample markdown data
        markdown_table = '# Test Markdown Table\n\n| Column 1 | Column 2 |\n|----------|----------|\n| Data 1   | Data 2   |'
        
        # Create a real Django request
        factory = RequestFactory()
        request = factory.post('/webhook/', data=json.dumps({
            'log_type': 'inspection_log',
            'project_id': str(self.project.id),
            'project_version_id': str(self.project_version.id),
            'new_status': 'SUCCESS',
            'table': markdown_table  # Markdown string
        }), content_type='application/json')
        
        # Call the webhook
        response = ai_log_generation_webhook(request)
        
        # Refresh the log from database
        self.log.refresh_from_db()
        
        # Verify the log was updated correctly
        self.assertEqual(self.log.log_status, 'SUCCESS')
        self.assertIsNone(self.log.log_data)  # Should be None for markdown
        self.assertEqual(self.log.log_table, markdown_table)


class AiGeneratedLogSerializerTests(TestCase):
    """Test AiGeneratedLogSerializer updates."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team')
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team
        )
        self.project_version = ProjectVersion.objects.create(
            project=self.project,
            version_name='v1.0'
        )
        
        # Sample structured data
        self.structured_data = [
            {
                'Spec Section #': '01 1000',
                'Spec Section Name': 'GENERAL REQUIREMENTS',
                'Inspection Type And Requirements': 'Review submittals',
                'Inspection Frequency': 'As required',
                'Responsible Party': 'Architect'
            },
            {
                'Spec Section #': '02 2000',
                'Spec Section Name': 'EXISTING CONDITIONS',
                'Inspection Type And Requirements': 'Site inspection',
                'Inspection Frequency': 'Before start',
                'Responsible Party': 'Contractor'
            }
        ]
        
        self.log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='inspection_log',
            log_status='SUCCESS',
            log_table='# Test Markdown Table',
            log_data=self.structured_data
        )
    
    def test_serializer_includes_log_data_field(self):
        """Test that serializer includes log_data field."""
        serializer = AiGeneratedLogSerializer(self.log)
        data = serializer.data
        
        self.assertIn('log_data', data)
        self.assertEqual(data['log_data'], self.structured_data)
    
    def test_serializer_includes_data_format_field(self):
        """Test that serializer includes data_format field."""
        serializer = AiGeneratedLogSerializer(self.log)
        data = serializer.data
        
        self.assertIn('data_format', data)
    
    @patch('apps.deliverables.serializers.specgpt.is_inspection_log_use_data_tables_feature_flag_active')
    def test_data_format_structured_when_flag_active(self, mock_flag):
        """Test data_format is 'structured' when feature flag is active."""
        mock_flag.return_value = True
        
        serializer = AiGeneratedLogSerializer(
            self.log,
            context={'request': MagicMock(user=self.user)}
        )
        data = serializer.data
        
        self.assertEqual(data['data_format'], 'structured')
    
    @patch('apps.deliverables.serializers.specgpt.is_inspection_log_use_data_tables_feature_flag_active')
    def test_data_format_markdown_when_flag_inactive(self, mock_flag):
        """Test data_format is 'markdown' when feature flag is inactive."""
        mock_flag.return_value = False
        
        serializer = AiGeneratedLogSerializer(
            self.log,
            context={'request': MagicMock(user=self.user)}
        )
        data = serializer.data
        
        self.assertEqual(data['data_format'], 'markdown')
    
    def test_data_format_markdown_when_no_log_data(self):
        """Test data_format is 'markdown' when no structured data exists."""
        log_no_data = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='inspection_log',
            log_status='SUCCESS',
            log_table='# Test Markdown Table',
            log_data=None
        )
        
        serializer = AiGeneratedLogSerializer(log_no_data)
        data = serializer.data
        
        self.assertEqual(data['data_format'], 'markdown')
    
    @patch('apps.deliverables.serializers.specgpt.is_inspection_log_use_data_tables_feature_flag_active')
    def test_serializer_sorts_structured_data(self, mock_flag):
        """Test that serializer sorts structured data correctly."""
        mock_flag.return_value = True
        
        # Create a mock request with sorting parameters
        mock_request = MagicMock()
        mock_request.sort_field = 'spec_section_number'
        mock_request.sort_direction = 'desc'
        mock_request.user = self.user
        
        serializer = AiGeneratedLogSerializer(
            self.log,
            context={'request': mock_request}
        )
        data = serializer.data
        
        # Verify data is sorted (descending order)
        sorted_data = data['log_data']
        self.assertEqual(len(sorted_data), 2)
        self.assertEqual(sorted_data[0]['Spec Section #'], '02 2000')  # Higher number first
        self.assertEqual(sorted_data[1]['Spec Section #'], '01 1000')  # Lower number second
    
    @patch('apps.deliverables.serializers.specgpt.is_inspection_log_use_data_tables_feature_flag_active')
    def test_serializer_sorts_structured_data_ascending(self, mock_flag):
        """Test that serializer sorts structured data in ascending order."""
        mock_flag.return_value = True
        
        # Create a mock request with sorting parameters
        mock_request = MagicMock()
        mock_request.sort_field = 'spec_section_number'
        mock_request.sort_direction = 'asc'
        mock_request.user = self.user
        
        serializer = AiGeneratedLogSerializer(
            self.log,
            context={'request': mock_request}
        )
        data = serializer.data
        
        # Verify data is sorted (ascending order)
        sorted_data = data['log_data']
        self.assertEqual(len(sorted_data), 2)
        self.assertEqual(sorted_data[0]['Spec Section #'], '01 1000')  # Lower number first
        self.assertEqual(sorted_data[1]['Spec Section #'], '02 2000')  # Higher number second


class AiGeneratedLogViewSetTests(APITestCase):
    """Test AiGeneratedLogViewSet functionality."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team')
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team
        )
        self.project_version = ProjectVersion.objects.create(
            project=self.project,
            version_name='v1.0'
        )
        
        # Create team membership
        Membership.objects.create(
            user=self.user,
            team=self.team,
            role='MEMBER'
        )
        
        # Create project membership
        ProjectMembership.objects.create(
            user=self.user,
            project=self.project,
            role='MEMBER'
        )
        
        # Sample structured data
        self.structured_data = [
            {
                'Spec Section #': '01 1000',
                'Spec Section Name': 'GENERAL REQUIREMENTS',
                'Inspection Type And Requirements': 'Review submittals',
                'Inspection Frequency': 'As required',
                'Responsible Party': 'Architect'
            },
            {
                'Spec Section #': '02 2000',
                'Spec Section Name': 'EXISTING CONDITIONS',
                'Inspection Type And Requirements': 'Site inspection',
                'Inspection Frequency': 'Before start',
                'Responsible Party': 'Contractor'
            }
        ]
        
        self.log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='inspection_log',
            log_status='SUCCESS',
            log_table='# Test Markdown Table',
            log_data=self.structured_data
        )
        
        self.client.force_authenticate(user=self.user)
    
    def test_get_log_detail_without_sorting(self):
        """Test getting log detail without sorting parameters."""
        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': self.log.id
        })
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        
        self.assertIn('log_data', data)
        self.assertIn('data_format', data)
        self.assertEqual(len(data['log_data']), 2)
    
    def test_get_log_detail_with_sorting(self):
        """Test getting log detail with sorting parameters."""
        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': self.log.id
        })
        
        # Add sorting parameters
        response = self.client.get(url, {
            'order_by': 'spec_section_number',
            'order': 'desc'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        
        # Verify data is sorted (descending order)
        sorted_data = data['log_data']
        self.assertEqual(len(sorted_data), 2)
        self.assertEqual(sorted_data[0]['Spec Section #'], '02 2000')  # Higher number first
        self.assertEqual(sorted_data[1]['Spec Section #'], '01 1000')  # Lower number second
    
    def test_get_log_detail_with_invalid_sort_field(self):
        """Test getting log detail with invalid sort field."""
        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': self.log.id
        })
        
        # Add invalid sorting parameters
        response = self.client.get(url, {
            'order_by': 'invalid_field',
            'order': 'desc'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        
        # Should still return data without sorting
        self.assertIn('log_data', data)
        self.assertEqual(len(data['log_data']), 2)
    
    def test_get_valid_sort_fields_inspection_log(self):
        """Test get_valid_sort_fields for inspection_log."""
        viewset = AiGeneratedLogViewSet()
        viewset.request = MagicMock()
        viewset.kwargs = {'pk': self.log.id}
        
        valid_fields = viewset.get_valid_sort_fields()
        
        expected_fields = [
            'created_at', 'spec_section_number', 'spec_section_name',
            'inspection_type_and_requirements', 'inspection_frequency', 'responsible_party'
        ]
        self.assertEqual(valid_fields, expected_fields)
    
    def test_get_valid_sort_fields_owner_deliverables_log(self):
        """Test get_valid_sort_fields for owner_deliverables_log."""
        # Create owner deliverables log
        owner_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='owner_deliverables_log',
            log_status='SUCCESS',
            log_table='# Test Markdown Table',
            log_data=[]
        )
        
        viewset = AiGeneratedLogViewSet()
        viewset.request = MagicMock()
        viewset.kwargs = {'pk': owner_log.id}
        
        valid_fields = viewset.get_valid_sort_fields()
        
        expected_fields = [
            'created_at', 'spec_section_number', 'spec_section_name',
            'deliverable_type', 'when_due', 'responsible_party', 'exact_requirement_text'
        ]
        self.assertEqual(valid_fields, expected_fields)
    
    def test_get_valid_sort_fields_unknown_log_type(self):
        """Test get_valid_sort_fields for unknown log type."""
        # Create log with unknown type
        unknown_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='unknown_type',
            log_status='SUCCESS',
            log_table='# Test Markdown Table',
            log_data=[]
        )
        
        viewset = AiGeneratedLogViewSet()
        viewset.request = MagicMock()
        viewset.kwargs = {'pk': unknown_log.id}
        
        valid_fields = viewset.get_valid_sort_fields()
        
        # Should default to created_at only
        self.assertEqual(valid_fields, ['created_at'])


class IntegrationTests(TestCase):
    """Integration tests for the complete feature."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team')
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team
        )
        self.project_version = ProjectVersion.objects.create(
            project=self.project,
            version_name='v1.0'
        )
    
    @patch('apps.deliverables.views.specgpt_views.convert_to_markdown_table')
    @patch('apps.deliverables.serializers.specgpt.is_inspection_log_use_data_tables_feature_flag_active')
    def test_complete_flow_with_feature_flag_active(self, mock_flag, mock_convert):
        """Test complete flow with feature flag active."""
        from apps.deliverables.views.specgpt_views import ai_log_generation_webhook
        from django.test import RequestFactory
        import json
        
        # Mock feature flag as active
        mock_flag.return_value = True
        
        # Mock conversion function
        mock_convert.return_value = '# Converted Markdown Table'
        
        # Create initial log
        log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='inspection_log',
            log_status='PROCESSING',
            log_table='',
            log_data=None
        )
        
        # Sample structured data from Lambda
        structured_data = [
            {
                'Spec Section #': '01 1000',
                'Spec Section Name': 'GENERAL REQUIREMENTS',
                'Inspection Type And Requirements': 'Review submittals',
                'Inspection Frequency': 'As required',
                'Responsible Party': 'Architect'
            },
            {
                'Spec Section #': '02 2000',
                'Spec Section Name': 'EXISTING CONDITIONS',
                'Inspection Type And Requirements': 'Site inspection',
                'Inspection Frequency': 'Before start',
                'Responsible Party': 'Contractor'
            }
        ]
        
        # Create a real Django request
        factory = RequestFactory()
        request = factory.post('/webhook/', data=json.dumps({
            'log_type': 'inspection_log',
            'project_id': str(self.project.id),
            'project_version_id': str(self.project_version.id),
            'new_status': 'SUCCESS',
            'table': structured_data
        }), content_type='application/json')
        
        # Process webhook
        response = ai_log_generation_webhook(request)
        
        # Refresh log from database
        log.refresh_from_db()
        
        # Verify log was updated correctly
        self.assertEqual(log.log_status, 'SUCCESS')
        self.assertEqual(log.log_data, structured_data)
        self.assertEqual(log.log_table, '# Converted Markdown Table')
        
        # Test serializer with feature flag active
        serializer = AiGeneratedLogSerializer(
            log,
            context={'request': MagicMock(user=self.user)}
        )
        data = serializer.data
        
        self.assertEqual(data['data_format'], 'structured')
        self.assertEqual(data['log_data'], structured_data)
        
        # Test sorting
        mock_request_with_sort = MagicMock()
        mock_request_with_sort.sort_field = 'spec_section_number'
        mock_request_with_sort.sort_direction = 'desc'
        
        serializer_with_sort = AiGeneratedLogSerializer(
            log,
            context={'request': mock_request_with_sort}
        )
        sorted_data = serializer_with_sort.data['log_data']
        
        # Verify sorting worked
        self.assertEqual(sorted_data[0]['Spec Section #'], '02 2000')
        self.assertEqual(sorted_data[1]['Spec Section #'], '01 1000')
    
    @patch('apps.deliverables.serializers.specgpt.is_inspection_log_use_data_tables_feature_flag_active')
    def test_complete_flow_with_feature_flag_inactive(self, mock_flag):
        """Test complete flow with feature flag inactive."""
        # Mock feature flag as inactive
        mock_flag.return_value = False
        
        # Create log with markdown data
        log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='inspection_log',
            log_status='SUCCESS',
            log_table='# Test Markdown Table',
            log_data=None
        )
        
        # Test serializer with feature flag inactive
        serializer = AiGeneratedLogSerializer(
            log,
            context={'request': MagicMock(user=self.user)}
        )
        data = serializer.data
        
        self.assertEqual(data['data_format'], 'markdown')
        self.assertIsNone(data['log_data'])
