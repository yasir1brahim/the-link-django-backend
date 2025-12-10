# apps/deliverables/tests/test_extraction_note_integration.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.deliverables.models import (
    ExtractedData, ExtractionNote, Project, ProjectVersion,
    ExtractionSource, ProjectMembership, ROLE_PROJECT_MEMBER,
    CustomItemType
)
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class TestExtractionNoteIntegration(TestCase):
    """End-to-end integration tests for the complete notes workflow"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('test@example.com', password='testpass123', first_name='Test', last_name='User')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(name="Test Project", team=self.team, created_by=self.user)
        self.version = self.project.versions.first()

        ProjectMembership.objects.create(project=self.project, user=self.user, role=ROLE_PROJECT_MEMBER)

        self.custom_item_type = CustomItemType.objects.create(
            project=self.project,
            name="Test Highlight Type",
            color="#FF0000"
        )

        self.extracted_data = ExtractedData.objects.create(
            project=self.project,
            project_version=self.version,
            spec_section_number="01 1000",
            spec_section_name="General Requirements",
            extraction_type="custom_highlights",
            custom_item_type=self.custom_item_type,
            requirement_text="Test requirement",
            source=ExtractionSource.HUMAN,
            created_by=self.user
        )

        self.client.force_authenticate(user=self.user)

    def test_complete_note_workflow(self):
        """Test complete workflow: create extracted data, add notes, fetch with notes, update, delete"""

        # Step 1: Create first note
        create_url = reverse('deliverables:extractionnote-list', kwargs={
            'project_pk': self.project.id,
            'extracteddata_pk': self.extracted_data.id
        })
        response = self.client.post(create_url, {'text': 'First note'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        first_note_id = response.data['id']

        # Step 2: Create second note
        response = self.client.post(create_url, {'text': 'Second note'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        second_note_id = response.data['id']

        # Step 3: Fetch ExtractedData and verify notes are inline
        extracted_data_url = reverse('deliverables:extracted-data-detail', kwargs={
            'project_id': self.project.id,
            'pk': self.extracted_data.id
        })
        response = self.client.get(extracted_data_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('notes', response.data)
        self.assertEqual(len(response.data['notes']), 2)
        self.assertEqual(response.data['notes'][0]['text'], 'First note')
        self.assertEqual(response.data['notes'][1]['text'], 'Second note')

        # Step 4: Update first note
        update_url = reverse('deliverables:extractionnote-detail', kwargs={
            'project_pk': self.project.id,
            'extracteddata_pk': self.extracted_data.id,
            'pk': first_note_id
        })
        response = self.client.patch(update_url, {'text': 'Updated first note'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Step 5: Verify update
        response = self.client.get(extracted_data_url)
        self.assertEqual(response.data['notes'][0]['text'], 'Updated first note')

        # Step 6: Delete second note
        delete_url = reverse('deliverables:extractionnote-detail', kwargs={
            'project_pk': self.project.id,
            'extracteddata_pk': self.extracted_data.id,
            'pk': second_note_id
        })
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Step 7: Verify deletion
        response = self.client.get(extracted_data_url)
        self.assertEqual(len(response.data['notes']), 1)
        self.assertEqual(response.data['notes'][0]['text'], 'Updated first note')

    def test_notes_included_in_list_view(self):
        """Test that notes are included when fetching list of ExtractedData"""
        # Create multiple ExtractedData with notes
        for i in range(3):
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
            ExtractionNote.objects.create(
                extracted_data=extracted,
                text=f"Note for item {i}",
                created_by=self.user
            )

        # Fetch list
        list_url = reverse('deliverables:extracted-data-list', kwargs={'project_id': self.project.id})
        response = self.client.get(list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Handle paginated response
        payload = response.data.get('results', response.data)
        # Should have at least 4 items (setUp + 3 new, but may have more with --keepdb)
        self.assertGreaterEqual(len(payload), 4)

        # Verify all have notes field
        for item in payload:
            self.assertIn('notes', item)
