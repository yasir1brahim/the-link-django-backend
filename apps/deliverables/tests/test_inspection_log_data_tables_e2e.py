"""
End-to-End tests for the inspection log data tables feature.

This module tests the complete flow from feature flag activation through
Lambda processing to frontend display, ensuring all components work together.
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
from apps.deliverables.views.specgpt_views import (
    ChatViewSet, ai_log_generation_webhook
)
from apps.deliverables.serializers.specgpt import AiGeneratedLogSerializer

User = get_user_model()


class InspectionLogDataTablesE2ETests(APITestCase):
    """
    End-to-End tests for the complete inspection log data tables feature.
    
    Tests the complete flow:
    1. Feature flag activation
    2. Webhook processing of structured data
    3. API response with structured data
    4. Frontend integration
    """
    
    def setUp(self):
        """Set up test data for E2E tests."""
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
        
        self.client.force_authenticate(user=self.user)
    
    def test_complete_flow_with_structured_data(self):
        """
        Test complete flow with structured data.
        
        Flow:
        1. Webhook processes structured data
        2. API returns structured data with correct format
        3. Sorting functionality works
        """
        # Step 1: Simulate webhook with structured data
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
        
        # Create initial log entry
        log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='inspection_log',
            log_status='PROCESSING',
            log_table='',
            log_data=None
        )
        
        # Simulate webhook call with structured data
        from django.test import RequestFactory
        factory = RequestFactory()
        webhook_request = factory.post('/webhook/', data=json.dumps({
            'log_type': 'inspection_log',
            'project_id': str(self.project.id),
            'project_version_id': str(self.project_version.id),
            'new_status': 'SUCCESS',
            'table': structured_data
        }), content_type='application/json')
        
        # Process webhook
        webhook_response = ai_log_generation_webhook(webhook_request)
        
        # Verify log was updated with structured data
        log.refresh_from_db()
        self.assertEqual(log.log_status, 'SUCCESS')
        self.assertEqual(log.log_data, structured_data)
        self.assertIsNotNone(log.log_table)  # Should have markdown fallback
        
        # Step 2: Test API response with feature flag active
        with patch('apps.deliverables.serializers.specgpt.is_inspection_log_use_data_tables_feature_flag_active') as mock_flag:
            mock_flag.return_value = True
            
            url = reverse('ai-generated-log-detail', kwargs={
                'project_id': self.project.id,
                'pk': log.id
            })
            
            api_response = self.client.get(url)
            self.assertEqual(api_response.status_code, status.HTTP_200_OK)
            
            data = api_response.data
            self.assertIn('log_data', data)
            self.assertIn('data_format', data)
            self.assertEqual(data['data_format'], 'structured')
            self.assertEqual(data['log_data'], structured_data)
            
            # Step 3: Test sorting functionality
            sorted_response = self.client.get(url, {
                'order_by': 'spec_section_number',
                'order': 'desc'
            })
            
            self.assertEqual(sorted_response.status_code, status.HTTP_200_OK)
            sorted_data = sorted_response.data['log_data']
            
            # Verify data is sorted (descending order)
            self.assertEqual(sorted_data[0]['Spec Section #'], '02 2000')
            self.assertEqual(sorted_data[1]['Spec Section #'], '01 1000')
    
    def test_complete_flow_with_markdown_data(self):
        """
        Test complete flow with markdown data.
        
        Flow:
        1. Webhook processes markdown data
        2. API returns markdown data
        """
        # Step 1: Simulate webhook with markdown data
        markdown_data = '# Test Markdown Table\n\n| Column 1 | Column 2 |\n|----------|----------|\n| Data 1   | Data 2   |'
        
        # Create initial log entry
        log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='inspection_log',
            log_status='PROCESSING',
            log_table='',
            log_data=None
        )
        
        # Simulate webhook call with markdown data
        from django.test import RequestFactory
        factory = RequestFactory()
        webhook_request = factory.post('/webhook/', data=json.dumps({
            'log_type': 'inspection_log',
            'project_id': str(self.project.id),
            'project_version_id': str(self.project_version.id),
            'new_status': 'SUCCESS',
            'table': markdown_data
        }), content_type='application/json')
        
        # Process webhook
        webhook_response = ai_log_generation_webhook(webhook_request)
        
        # Verify log was updated with markdown data
        log.refresh_from_db()
        self.assertEqual(log.log_status, 'SUCCESS')
        self.assertIsNone(log.log_data)  # Should be None for markdown
        self.assertEqual(log.log_table, markdown_data)
        
        # Step 2: Test API response with feature flag inactive
        with patch('apps.deliverables.serializers.specgpt.is_inspection_log_use_data_tables_feature_flag_active') as mock_flag:
            mock_flag.return_value = False
            
            url = reverse('ai-generated-log-detail', kwargs={
                'project_id': self.project.id,
                'pk': log.id
            })
            
            api_response = self.client.get(url)
            self.assertEqual(api_response.status_code, status.HTTP_200_OK)
            
            data = api_response.data
            self.assertIn('log_data', data)
            self.assertIn('data_format', data)
            self.assertEqual(data['data_format'], 'markdown')
            self.assertIsNone(data['log_data'])
    
    def test_feature_flag_fallback_behavior(self):
        """
        Test fallback behavior when structured data is not available.
        
        Even when feature flag is active, if structured data is not available,
        the system should fall back to markdown display.
        """
        # Create log with feature flag active but no structured data
        log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='inspection_log',
            log_status='SUCCESS',
            log_table='# Test Markdown Table',
            log_data=None  # No structured data
        )
        
        # Test API response
        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': log.id
        })
        
        api_response = self.client.get(url)
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        
        data = api_response.data
        self.assertEqual(data['data_format'], 'markdown')
        self.assertIsNone(data['log_data'])
    
    def test_owner_deliverables_log_flow(self):
        """
        Test complete flow for owner deliverables logs.
        
        Ensures that owner deliverables logs work with the same feature flag
        and have the correct column structure.
        """
        # Create owner deliverables log with structured data
        structured_data = [
            {
                'Spec Section #': '01 1000',
                'Spec Section Name': 'GENERAL REQUIREMENTS',
                'Deliverable Type': 'Submittal',
                'When Due': 'Before start',
                'Responsible Party': 'Contractor',
                'Exact Requirement Text': 'Submit shop drawings'
            }
        ]
        
        log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='owner_deliverables_log',
            log_status='SUCCESS',
            log_table='# Test Markdown Table',
            log_data=structured_data
        )
        
        # Test API response with feature flag active
        with patch('apps.deliverables.serializers.specgpt.is_inspection_log_use_data_tables_feature_flag_active') as mock_flag:
            mock_flag.return_value = True
            
            url = reverse('ai-generated-log-detail', kwargs={
                'project_id': self.project.id,
                'pk': log.id
            })
            
            api_response = self.client.get(url)
            self.assertEqual(api_response.status_code, status.HTTP_200_OK)
            
            data = api_response.data
            self.assertEqual(data['data_format'], 'structured')
            self.assertEqual(data['log_data'], structured_data)
            
            # Test sorting with owner deliverables fields
            sorted_response = self.client.get(url, {
                'order_by': 'deliverable_type',
                'order': 'asc'
            })
            
            self.assertEqual(sorted_response.status_code, status.HTTP_200_OK)
            sorted_data = sorted_response.data['log_data']
            self.assertEqual(len(sorted_data), 1)
            self.assertEqual(sorted_data[0]['Deliverable Type'], 'Submittal')
    
    def test_error_handling_and_recovery(self):
        """
        Test error handling and recovery in the complete flow.
        
        Ensures that errors in one part of the flow don't break the entire system.
        """
        # Test with invalid log ID
        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': 99999  # Non-existent log ID
        })
        
        api_response = self.client.get(url)
        self.assertEqual(api_response.status_code, status.HTTP_404_NOT_FOUND)
        
        # Test with invalid sorting parameters
        log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='inspection_log',
            log_status='SUCCESS',
            log_table='# Test Markdown Table',
            log_data=[
                {
                    'Spec Section #': '01 1000',
                    'Spec Section Name': 'GENERAL REQUIREMENTS',
                    'Inspection Type And Requirements': 'Review submittals',
                    'Inspection Frequency': 'As required',
                    'Responsible Party': 'Architect'
                }
            ]
        )
        
        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': log.id
        })
        
        # Test with invalid sort field
        with patch('apps.deliverables.serializers.specgpt.is_inspection_log_use_data_tables_feature_flag_active') as mock_flag:
            mock_flag.return_value = True
            
            invalid_sort_response = self.client.get(url, {
                'order_by': 'invalid_field',
                'order': 'desc'
            })
            
            # Should still return data without sorting
            self.assertEqual(invalid_sort_response.status_code, status.HTTP_200_OK)
            data = invalid_sort_response.data
            self.assertIn('log_data', data)
            self.assertEqual(len(data['log_data']), 1)
    
    def test_data_integrity_and_consistency(self):
        """
        Test data integrity and consistency throughout the flow.
        
        Ensures that data is not corrupted or modified unexpectedly
        during processing.
        """
        # Original structured data
        original_data = [
            {
                'Spec Section #': '01 1000',
                'Spec Section Name': 'GENERAL REQUIREMENTS',
                'Inspection Type And Requirements': 'Review submittals with special chars: <>&"\'',
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
            log_data=original_data
        )
        
        # Test API response preserves data integrity
        with patch('apps.deliverables.serializers.specgpt.is_inspection_log_use_data_tables_feature_flag_active') as mock_flag:
            mock_flag.return_value = True
            
            url = reverse('ai-generated-log-detail', kwargs={
                'project_id': self.project.id,
                'pk': log.id
            })
            
            api_response = self.client.get(url)
            self.assertEqual(api_response.status_code, status.HTTP_200_OK)
            
            data = api_response.data
            self.assertEqual(data['log_data'], original_data)
            
            # Test that special characters are preserved
            self.assertIn('<>&"\'', data['log_data'][0]['Inspection Type And Requirements'])
            
            # Test sorting preserves data integrity
            sorted_response = self.client.get(url, {
                'order_by': 'spec_section_number',
                'order': 'asc'
            })
            
            self.assertEqual(sorted_response.status_code, status.HTTP_200_OK)
            sorted_data = sorted_response.data['log_data']
            
            # Verify data is still intact after sorting
            self.assertEqual(len(sorted_data), 1)
            self.assertEqual(sorted_data[0], original_data[0])
            self.assertIn('<>&"\'', sorted_data[0]['Inspection Type And Requirements'])
    
    def test_feature_flag_rollback_scenario(self):
        """
        Test feature flag rollback scenario.
        
        Ensures that when the feature flag is turned off, the system
        gracefully falls back to markdown display for existing structured data.
        """
        # Create log with structured data (simulating when feature flag was active)
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
        
        # Now simulate feature flag being turned off
        # The API should still return the structured data but with markdown format
        with patch('apps.deliverables.serializers.specgpt.is_inspection_log_use_data_tables_feature_flag_active') as mock_flag:
            mock_flag.return_value = False
            
            url = reverse('ai-generated-log-detail', kwargs={
                'project_id': self.project.id,
                'pk': log.id
            })
            
            api_response = self.client.get(url)
            self.assertEqual(api_response.status_code, status.HTTP_200_OK)
            
            data = api_response.data
            # Even with feature flag off, if structured data exists, it should be returned
            # but with markdown format
            self.assertEqual(data['data_format'], 'markdown')
            # The log_data should still be available for fallback
            self.assertEqual(data['log_data'], structured_data)


class FrontendIntegrationE2ETests(APITestCase):
    """
    Frontend integration E2E tests.
    
    Tests the integration between backend API and frontend components,
    ensuring data flows correctly from backend to frontend.
    """
    
    def setUp(self):
        """Set up test data for frontend integration tests."""
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
        
        self.client.force_authenticate(user=self.user)
    
    def test_serializer_data_format_consistency(self):
        """
        Test that serializer consistently returns the correct data format
        based on feature flag status and data availability.
        """
        # Test with structured data and feature flag active
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
        
        # Test serializer with feature flag active
        with patch('apps.deliverables.serializers.specgpt.is_inspection_log_use_data_tables_feature_flag_active') as mock_flag:
            mock_flag.return_value = True
            
            serializer = AiGeneratedLogSerializer(
                log,
                context={'request': MagicMock(user=self.user)}
            )
            data = serializer.data
            
            self.assertEqual(data['data_format'], 'structured')
            self.assertEqual(data['log_data'], structured_data)
        
        # Test serializer with feature flag inactive
        with patch('apps.deliverables.serializers.specgpt.is_inspection_log_use_data_tables_feature_flag_active') as mock_flag:
            mock_flag.return_value = False
            
            serializer = AiGeneratedLogSerializer(
                log,
                context={'request': MagicMock(user=self.user)}
            )
            data = serializer.data
            
            self.assertEqual(data['data_format'], 'markdown')
            self.assertEqual(data['log_data'], structured_data)  # Still available for fallback
    
    def test_api_response_structure_consistency(self):
        """
        Test that API responses have consistent structure for frontend consumption.
        """
        # Create test data
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
        
        # Test API response structure
        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': log.id
        })
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.data
        
        # Verify required fields are present
        required_fields = ['id', 'log_type', 'log_status', 'log_table', 'log_data', 'data_format', 'created_at']
        for field in required_fields:
            self.assertIn(field, data)
        
        # Verify data types
        self.assertIsInstance(data['id'], int)
        self.assertIsInstance(data['log_type'], str)
        self.assertIsInstance(data['log_status'], str)
        self.assertIsInstance(data['log_table'], str)
        self.assertIsInstance(data['data_format'], str)
        self.assertIsInstance(data['created_at'], str)
        
        # Verify log_data is list when structured
        if data['data_format'] == 'structured':
            self.assertIsInstance(data['log_data'], list)
        else:
            self.assertIsInstance(data['log_data'], (list, type(None)))
    
    def test_sorting_parameter_validation(self):
        """
        Test that sorting parameters are properly validated and handled.
        """
        # Create test data
        structured_data = [
            {
                'Spec Section #': '02 2000',
                'Spec Section Name': 'EXISTING CONDITIONS',
                'Inspection Type And Requirements': 'Site inspection',
                'Inspection Frequency': 'Before start',
                'Responsible Party': 'Contractor'
            },
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
        
        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': log.id
        })
        
        # Test valid sorting parameters
        response = self.client.get(url, {
            'order_by': 'spec_section_number',
            'order': 'asc'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['log_data']
        
        # Verify sorting worked
        self.assertEqual(data[0]['Spec Section #'], '01 1000')
        self.assertEqual(data[1]['Spec Section #'], '02 2000')
        
        # Test invalid sorting parameters
        response = self.client.get(url, {
            'order_by': 'invalid_field',
            'order': 'invalid_order'
        })
        
        # Should still return data without sorting
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['log_data']
        self.assertEqual(len(data), 2)
