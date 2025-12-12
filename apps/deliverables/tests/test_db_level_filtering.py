"""
Test DB-level filtering, sorting, and searching for QA planner and other log types.
This tests the new implementation that uses database queries instead of Python loops.
"""
import json
import pytest
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from apps.teams.models import Team, Membership as TeamMembership
from apps.deliverables.models import (
    Project, ProjectMembership, ProjectVersion, AiGeneratedLog,
    ExtractedData, ExtractionSource,
    ROLE_PROJECT_ADMIN, ROLE_PROJECT_MEMBER
)
import logging

logger = logging.getLogger(__name__)



class DBLevelFilteringTests(APITestCase):
    """Test DB-level filtering, sorting, and searching for AI generated logs"""

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

        # Create test QA planner log with ExtractedData records
        self.qa_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='qa_planner',
            log_status='SUCCESS',
            log_data=[],  # Empty since we're using ExtractedData
            created_by=self.user
        )

        # Create ExtractedData records for QA planner
        self.extracted_items = []
        test_data = [
            {
                'spec_section_number': '01 1000',
                'spec_section_name': 'General Requirements',
                'paragraph_number': '1.1',
                'item_type': 'inspections',
                'requirement_text': 'All work must comply with local codes',
                'responsible_party': 'General Contractor',
                'metadata': {'when_due': 'Before construction'}
            },
            {
                'spec_section_number': '01 1000',
                'spec_section_name': 'General Requirements',
                'paragraph_number': '1.2',
                'item_type': 'warranties',
                'requirement_text': 'Submit material certificates',
                'responsible_party': 'Subcontractor',
                'metadata': {'when_due': 'Prior to installation'}
            },
            {
                'spec_section_number': '02 2000',
                'spec_section_name': 'Earthwork',
                'paragraph_number': '2.1',
                'item_type': 'inspections',
                'requirement_text': 'Excavate to specified depths',
                'responsible_party': 'Excavation Contractor',
                'metadata': {'when_due': 'During excavation phase'}
            },
            {
                'spec_section_number': '03 3000',
                'spec_section_name': 'Concrete',
                'paragraph_number': '3.1',
                'item_type': 'certificates',
                'requirement_text': 'Concrete strength testing',
                'responsible_party': 'Testing Laboratory',
                'metadata': {'when_due': 'After curing period'}
            },
            {
                'spec_section_number': '03 3000',
                'spec_section_name': 'Concrete',
                'paragraph_number': '3.2',
                'item_type': 'inspections',
                'requirement_text': 'Visual inspection of formwork',
                'responsible_party': 'General Contractor',
                'metadata': {'when_due': 'Before concrete placement'}
            },
        ]

        for data in test_data:
            item = ExtractedData.objects.create(
                ai_generated_log=self.qa_log,
                project=self.project,
                project_version=self.project_version,
                extraction_type='qa_planner',
                source=ExtractionSource.AI,
                created_by=self.user,
                **data
            )
            self.extracted_items.append(item)

    def test_db_filtering_by_spec_section(self):
        """Test DB-level filtering by Spec Section #"""
        self.client.force_authenticate(user=self.user)

        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': self.qa_log.id
        })

        # Filter by spec section
        response = self.client.get(url, {
            'filter_spec_section__': '01 1000'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Should only return items from spec section 01 1000
        self.assertEqual(len(data['log_data']), 2)
        for item in data['log_data']:
            self.assertEqual(item['Spec Section #'], '01 1000')

    def test_db_filtering_by_item_type(self):
        """Test DB-level filtering by item_type""" 
        self.client.force_authenticate(user=self.user)

        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': self.qa_log.id
        })

        # Filter by item_type
        response = self.client.get(url, {
            'filter_item_type': 'inspections'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Should only return inspection items
        self.assertEqual(len(data['log_data']), 3)
        for item in data['log_data']:
            self.assertEqual(item['item_type'], 'inspections')

    def test_db_filtering_by_responsible_party(self):
        """Test DB-level filtering by Responsible Party"""
        self.client.force_authenticate(user=self.user)

        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': self.qa_log.id
        })

        # Filter by responsible party
        response = self.client.get(url, {
            'filter_responsible_party': 'General Contractor'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Should only return items for General Contractor
        self.assertEqual(len(data['log_data']), 2)
        for item in data['log_data']:
            self.assertEqual(item['Responsible Party'], 'General Contractor')

    def test_db_filtering_multiple_columns(self):
        """Test DB-level filtering with multiple columns (AND logic)"""
        self.client.force_authenticate(user=self.user)

        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': self.qa_log.id
        })

        # Filter by spec section AND item_type
        response = self.client.get(url, {
            'filter_spec_section__': '03 3000',
            'filter_item_type': 'inspections'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Should only return inspection items from spec section 03 3000
        self.assertEqual(len(data['log_data']), 1)
        self.assertEqual(data['log_data'][0]['Spec Section #'], '03 3000')
        self.assertEqual(data['log_data'][0]['item_type'], 'inspections')

    def test_db_filtering_multiple_values_same_column(self):
        """Test DB-level filtering with multiple values in same column (OR logic)"""
        self.client.force_authenticate(user=self.user)

        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': self.qa_log.id
        })

        # Filter by multiple spec sections (OR logic)
        response = self.client.get(url, {
            'filter_spec_section__': '01 1000,02 2000'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Should return items from either spec section
        self.assertEqual(len(data['log_data']), 3)
        spec_sections = {item['Spec Section #'] for item in data['log_data']}
        self.assertEqual(spec_sections, {'01 1000', '02 2000'})

    def test_db_searching_text_fields(self):
        """Test DB-level searching across text fields"""
        self.client.force_authenticate(user=self.user)

        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': self.qa_log.id
        })

        # Search for 'concrete'
        response = self.client.get(url, {
            'search': 'concrete'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Should return items with 'concrete' in any text field
        self.assertGreater(len(data['log_data']), 0)
        # Check that at least one item contains 'concrete' (case-insensitive)
        found = any('concrete' in str(item.get('Requirement Text', '')).lower() or
                   'concrete' in str(item.get('Spec Section Name', '')).lower()
                   for item in data['log_data'])
        self.assertTrue(found)

    def test_db_sorting_asc(self):
        """Test DB-level sorting in ascending order"""
        self.client.force_authenticate(user=self.user)

        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': self.qa_log.id
        })

        # Sort by item_type ascending
        response = self.client.get(url, {
            'order_by': 'item_type',
            'order': 'asc'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Extract item_types
        item_types = [item['item_type'] for item in data['log_data']]

        # Should be in alphabetical order
        self.assertEqual(item_types, sorted(item_types))

    def test_db_sorting_desc(self):
        """Test DB-level sorting in descending order"""
        self.client.force_authenticate(user=self.user)

        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': self.qa_log.id
        })

        # Sort by spec_section_number descending
        response = self.client.get(url, {
            'order_by': 'spec_section_number',
            'order': 'desc'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Extract spec section numbers
        spec_sections = [item['Spec Section #'] for item in data['log_data']]

        # Should be in reverse order
        self.assertEqual(spec_sections, sorted(spec_sections, reverse=True))

    def test_db_pagination(self):
        """Test DB-level pagination"""
        self.client.force_authenticate(user=self.user)

        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': self.qa_log.id
        })

        # Get first page with page_size=2
        response = self.client.get(url, {
            'page': 1,
            'page_size': 2
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Should return 2 items
        self.assertEqual(len(data['log_data']), 2)

        # Check pagination metadata
        self.assertEqual(data['pagination']['current_page'], 1)
        self.assertEqual(data['pagination']['page_size'], 2)
        self.assertEqual(data['pagination']['total_items'], 5)
        self.assertTrue(data['pagination']['has_next'])
        self.assertFalse(data['pagination']['has_previous'])

        # Get second page
        response = self.client.get(url, {
            'page': 2,
            'page_size': 2
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Should return 2 items
        self.assertEqual(len(data['log_data']), 2)
        self.assertEqual(data['pagination']['current_page'], 2)
        self.assertTrue(data['pagination']['has_next'])
        self.assertTrue(data['pagination']['has_previous'])

    def test_db_combined_operations(self):
        """Test DB-level filtering + searching + sorting + pagination together"""
        self.client.force_authenticate(user=self.user)

        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': self.qa_log.id
        })

        # Filter by item_type, search, sort, and paginate
        response = self.client.get(url, {
            'filter_item_type': 'inspections',
            'search': 'inspection',
            'order_by': 'spec_section_number',
            'order': 'asc',
            'page': 1,
            'page_size': 2
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Should return filtered, searched, sorted, and paginated results
        self.assertLessEqual(len(data['log_data']), 2)

        # Verify all items are inspections
        for item in data['log_data']:
            self.assertEqual(item['item_type'], 'inspections')

    def test_db_filter_values_endpoint(self):
        """Test DB-level filter_values endpoint"""
        self.client.force_authenticate(user=self.user)

        url = reverse('ai-generated-log-filter-values', kwargs={
            'project_id': self.project.id,
            'pk': self.qa_log.id
        })

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Check that filter_values are returned
        self.assertIn('filter_values', data)
        filter_values = data['filter_values']

        # Verify expected columns are present
        self.assertIn('Spec Section #', filter_values)
        self.assertIn('item_type', filter_values)
        self.assertIn('Responsible Party', filter_values)

        # Verify values are correct and sorted
        self.assertEqual(set(filter_values['Spec Section #']), {'01 1000', '02 2000', '03 3000'})
        self.assertEqual(set(filter_values['item_type']), {'inspections', 'warranties', 'certificates'})

        # Values should be sorted
        self.assertEqual(filter_values['Spec Section #'], sorted(filter_values['Spec Section #']))
        self.assertEqual(filter_values['item_type'], sorted(filter_values['item_type']))

    def test_db_filter_values_returns_no_duplicates(self):
        """Test that filter_values endpoint returns unique values without duplicates.

        Regression test for TBL-765: The filter dropdown was showing duplicate entries
        because the Django distinct() wasn't working correctly due to default model ordering
        including the 'id' field in the SELECT clause.
        """
        self.client.force_authenticate(user=self.user)

        url = reverse('ai-generated-log-filter-values', kwargs={
            'project_id': self.project.id,
            'pk': self.qa_log.id
        })

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        filter_values = response.data['filter_values']

        # Verify NO duplicate values in any filter column
        # This is the key assertion - the list length should equal the set length
        for column_key, values in filter_values.items():
            unique_count = len(set(values))
            actual_count = len(values)
            self.assertEqual(
                actual_count,
                unique_count,
                f"Filter column '{column_key}' contains duplicates: "
                f"got {actual_count} values but only {unique_count} unique. "
                f"Values: {values}"
            )

    def test_db_filtering_with_human_highlights(self):
        """Test that DB queries include human-created highlights"""
        # Create a human-created highlight
        human_item = ExtractedData.objects.create(
            ai_generated_log=None,  # Human highlight
            project=self.project,
            project_version=self.project_version,
            extraction_type='qa_planner',
            source=ExtractionSource.HUMAN,
            created_by=self.user,
            spec_section_number='04 4000',
            spec_section_name='Masonry',
            paragraph_number='4.1',
            item_type='inspections',
            requirement_text='Inspect masonry joints',
            responsible_party='Mason',
            metadata={'when_due': 'Daily'}
        )

        self.client.force_authenticate(user=self.user)

        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': self.qa_log.id
        })

        # Get all items
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Should include human-created item
        self.assertEqual(data['pagination']['total_items'], 6)  # 5 AI + 1 human

        # Verify human item is present
        spec_sections = {item['Spec Section #'] for item in data['log_data']}
        self.assertIn('04 4000', spec_sections)

    def test_db_empty_filters(self):
        """Test DB queries with filters that match no records"""
        self.client.force_authenticate(user=self.user)

        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': self.qa_log.id
        })

        # Filter by non-existent spec section
        response = self.client.get(url, {
            'filter_spec_section__': '99 9999'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Should return empty results
        self.assertEqual(len(data['log_data']), 0)
        self.assertEqual(data['pagination']['total_items'], 0)

    def test_db_performance_logs(self):
        """Test that performance logs are generated (check logs manually)"""
        self.client.force_authenticate(user=self.user)

        url = reverse('ai-generated-log-detail', kwargs={
            'project_id': self.project.id,
            'pk': self.qa_log.id
        })

        # Make a request that should trigger logging
        response = self.client.get(url, {
            'filter_item_type': 'inspections',
            'search': 'inspection',
            'order_by': 'spec_section_number',
            'order': 'asc'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check logs manually to verify logging is working
        # Logs should show:
        # - "Starting DB-level query for log X"
        # - "Base queryset count (before filters): Y"
        # - "Queryset count after filtering: Z"
        # - "Total items after all filters: N"
