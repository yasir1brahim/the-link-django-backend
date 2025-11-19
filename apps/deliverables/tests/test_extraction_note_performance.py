# apps/deliverables/tests/test_extraction_note_performance.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.test.utils import CaptureQueriesContext
from django.db import connection
from apps.deliverables.models import (
    ExtractedData,
    ExtractionNote,
    Project,
    ExtractionSource,
    ProjectMembership,
    ROLE_PROJECT_MEMBER,
    CustomItemType,
)
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class TestExtractionNotePerformance(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('test@example.com')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(name="Test Project", team=self.team, created_by=self.user)
        self.version = self.project.versions.first()
        ProjectMembership.objects.create(project=self.project, user=self.user, role=ROLE_PROJECT_MEMBER)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.custom_item_type = CustomItemType.objects.create(
            project=self.project,
            name="Test Highlight Type",
            color="#FF0000"
        )

    def test_no_n_plus_1_queries_with_notes(self):
        """Test that fetching multiple ExtractedData with notes doesn't cause N+1 queries"""
        # Create 5 ExtractedData items with notes
        for i in range(5):
            extracted = ExtractedData.objects.create(
                project=self.project,
                project_version=self.version,
                spec_section_number=f"0{i} 1000",
                spec_section_name=f"Section {i}",
                extraction_type="custom_highlights",
                custom_item_type=self.custom_item_type,
                requirement_text=f"Requirement {i}",
                source=ExtractionSource.HUMAN,
                created_by=self.user
            )
            # Add 3 notes to each
            for j in range(3):
                ExtractionNote.objects.create(
                    extracted_data=extracted,
                    text=f"Note {j} for item {i}",
                    created_by=self.user
                )

        list_url = reverse('deliverables:extracted-data-list', kwargs={'project_id': self.project.id})

        with CaptureQueriesContext(connection) as context:
            response = self.client.get(list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data.get('results', response.data)
        # Ensure we got our extracted data items (may have more from other tests with --keepdb)
        self.assertIsInstance(payload, list)
        # Just verify notes are present in the response
        if len(payload) > 0:
            self.assertIn('notes', payload[0])

        # Should be approximately 3 queries:
        # 1. ExtractedData select
        # 2. Prefetch notes
        # 3. Prefetch note creators
        # Allow some tolerance for database setup queries
        self.assertLess(len(context.captured_queries), 8,
            f"Too many queries: {len(context.captured_queries)}. Possible N+1 issue.")
