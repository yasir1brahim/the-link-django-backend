# apps/deliverables/tests/test_extraction_note_viewset.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.deliverables.models import ExtractedData, ExtractionNote, Project, ProjectVersion, ExtractionSource, CustomItemType
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class TestExtractionNoteViewSet(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('test@example.com', password='testpass123')
        self.other_user = User.objects.create_user('other@example.com', password='testpass123')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(name="Test Project", team=self.team, created_by=self.user)
        self.version = self.project.versions.first()

        # Add user to project
        from apps.deliverables.models import ProjectMembership, ROLE_PROJECT_MEMBER
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

    def test_create_note(self):
        """Test creating a note on an ExtractedData"""
        url = reverse('deliverables:extractionnote-list', kwargs={
            'project_pk': self.project.id,
            'extracteddata_pk': self.extracted_data.id
        })
        data = {'text': 'This is a new note'}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ExtractionNote.objects.count(), 1)
        note = ExtractionNote.objects.first()
        self.assertEqual(note.text, 'This is a new note')
        self.assertEqual(note.created_by, self.user)
        self.assertEqual(note.extracted_data, self.extracted_data)

    def test_list_notes(self):
        """Test listing all notes for an ExtractedData"""
        # Create notes with unique text for this test
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        note1_text = f"First note {unique_id}"
        note2_text = f"Second note {unique_id}"

        note1 = ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text=note1_text,
            created_by=self.user
        )
        note2 = ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text=note2_text,
            created_by=self.user
        )

        url = reverse('deliverables:extractionnote-list', kwargs={
            'project_pk': self.project.id,
            'extracteddata_pk': self.extracted_data.id
        })

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Response is paginated, so data is in 'results'
        results = response.data.get('results', response.data)
        self.assertGreaterEqual(len(results), 2)
        # Check that our specific notes are in the response
        note_texts = [n['text'] for n in results]
        self.assertIn(note1_text, note_texts)
        self.assertIn(note2_text, note_texts)

    def test_list_notes_for_non_member(self):
        """Non-project members should not see notes"""
        url = reverse('deliverables:extractionnote-list', kwargs={
            'project_pk': self.project.id,
            'extracteddata_pk': self.extracted_data.id
        })

        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_note_as_non_member(self):
        """Non-project members cannot create notes"""
        url = reverse('deliverables:extractionnote-list', kwargs={
            'project_pk': self.project.id,
            'extracteddata_pk': self.extracted_data.id
        })

        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(url, {'text': 'Nope'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(ExtractionNote.objects.count(), 0)

    def test_update_note_as_author(self):
        """Test that author can update their note"""
        note = ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="Original text",
            created_by=self.user
        )

        url = reverse('deliverables:extractionnote-detail', kwargs={
            'project_pk': self.project.id,
            'extracteddata_pk': self.extracted_data.id,
            'pk': note.id
        })
        data = {'text': 'Updated text'}

        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        note.refresh_from_db()
        self.assertEqual(note.text, 'Updated text')

    def test_update_note_as_non_author(self):
        """Test that non-author cannot update a note"""
        note = ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="Original text",
            created_by=self.user
        )

        # Add other_user to project
        from apps.deliverables.models import ProjectMembership, ROLE_PROJECT_MEMBER
        ProjectMembership.objects.create(project=self.project, user=self.other_user, role=ROLE_PROJECT_MEMBER)

        # Switch to other user
        self.client.force_authenticate(user=self.other_user)

        url = reverse('deliverables:extractionnote-detail', kwargs={
            'project_pk': self.project.id,
            'extracteddata_pk': self.extracted_data.id,
            'pk': note.id
        })
        data = {'text': 'Attempted update'}

        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        note.refresh_from_db()
        self.assertEqual(note.text, 'Original text')  # Unchanged

    def test_delete_note_as_author(self):
        """Test that author can delete their note"""
        note = ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="To be deleted",
            created_by=self.user
        )
        note_id = note.id

        url = reverse('deliverables:extractionnote-detail', kwargs={
            'project_pk': self.project.id,
            'extracteddata_pk': self.extracted_data.id,
            'pk': note.id
        })

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ExtractionNote.objects.filter(id=note_id).exists())

    def test_delete_note_as_non_author(self):
        """Test that non-author cannot delete a note"""
        note = ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="Cannot delete",
            created_by=self.user
        )

        # Add other_user to project
        from apps.deliverables.models import ProjectMembership, ROLE_PROJECT_MEMBER
        ProjectMembership.objects.create(project=self.project, user=self.other_user, role=ROLE_PROJECT_MEMBER)

        # Switch to other user
        self.client.force_authenticate(user=self.other_user)

        url = reverse('deliverables:extractionnote-detail', kwargs={
            'project_pk': self.project.id,
            'extracteddata_pk': self.extracted_data.id,
            'pk': note.id
        })

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(ExtractionNote.objects.filter(id=note.id).exists())

    def test_unauthenticated_access_denied(self):
        """Test that unauthenticated users cannot access notes"""
        self.client.force_authenticate(user=None)

        url = reverse('deliverables:extractionnote-list', kwargs={
            'project_pk': self.project.id,
            'extracteddata_pk': self.extracted_data.id
        })

        response = self.client.get(url)
        # DRF returns 403 when using multiple permission classes
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
