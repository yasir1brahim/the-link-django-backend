# apps/deliverables/tests/test_drawing_note_viewset.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.deliverables.models import (
    Project, ProjectMembership, ROLE_PROJECT_MEMBER,
    DrawingFile, DrawingExtraction, DrawingPage, DrawingNoteSection, DrawingNote,
    DrawingExtractionStatus, DrawingPageType, DrawingPageExtractionStatus,
)
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class TestDrawingNoteViewSet(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('test@example.com', password='testpass')
        self.other_user = User.objects.create_user('other@example.com', password='testpass')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(
            name="Test Project",
            project_number="P-001",
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ROLE_PROJECT_MEMBER
        )

        # Create drawing data
        self.drawing_file = DrawingFile.objects.create(
            project=self.project,
            project_version=self.project_version,
            file_name="Mechanical.pdf",
            file_s3_key="drawings/test.pdf",
            md5="abc123",
        )
        self.extraction = DrawingExtraction.objects.create(
            drawing_file=self.drawing_file,
            status=DrawingExtractionStatus.SUCCESS,
        )
        self.page = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=1,
            page_type=DrawingPageType.DRAWING,
            extraction_status=DrawingPageExtractionStatus.SUCCESS,
        )
        self.section = DrawingNoteSection.objects.create(
            page=self.page,
            header="GENERAL NOTES:",
        )
        self.note = DrawingNote.objects.create(
            section=self.section,
            note_number=1,
            category="GENERAL NOTES",
            text="Test note content",
        )

        self.client.force_authenticate(user=self.user)

    def test_list_notes(self):
        """Test listing drawing notes for a project"""
        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['text'], "Test note content")

    def test_list_notes_unauthenticated_denied(self):
        """Test unauthenticated access is denied"""
        self.client.logout()
        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url)

        # DRF may return 401 or 403 depending on authentication backend
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_list_notes_non_member_denied(self):
        """Test non-member access is denied"""
        self.client.force_authenticate(user=self.other_user)
        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_filter_by_project_version(self):
        """Test filtering by project_version_id"""
        # Create note in different version
        version2 = self.project.versions.create(version_number=2, version_name="V2")
        drawing_file2 = DrawingFile.objects.create(
            project=self.project,
            project_version=version2,
            file_name="Electrical.pdf",
            file_s3_key="drawings/test2.pdf",
            md5="def456",
        )
        extraction2 = DrawingExtraction.objects.create(
            drawing_file=drawing_file2,
            status=DrawingExtractionStatus.SUCCESS,
        )
        page2 = DrawingPage.objects.create(
            drawing_file=drawing_file2,
            extraction=extraction2,
            page_number=1,
            page_type=DrawingPageType.DRAWING,
            extraction_status=DrawingPageExtractionStatus.SUCCESS,
        )
        section2 = DrawingNoteSection.objects.create(page=page2, header="ELECTRICAL:")
        DrawingNote.objects.create(
            section=section2,
            note_number=1,
            category="ELECTRICAL",
            text="Electrical note",
        )

        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})

        # Filter by first version
        response = self.client.get(url, {'project_version_id': self.project_version.id})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['category'], "GENERAL NOTES")

        # Filter by second version
        response = self.client.get(url, {'project_version_id': version2.id})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['category'], "ELECTRICAL")

    def test_filter_by_category(self):
        """Test filtering by category"""
        # Create note with different category
        DrawingNote.objects.create(
            section=self.section,
            note_number=2,
            category="MECHANICAL",
            text="Mechanical note",
        )

        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url, {'category': 'MECHANICAL'})

        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['category'], "MECHANICAL")

    def test_all_filter_vals_returned(self):
        """Test that filter options are returned in response"""
        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url)

        self.assertIn('all_filter_vals', response.data)
        self.assertIn('category', response.data['all_filter_vals'])
        self.assertIn('drawing_files', response.data['all_filter_vals'])

        # drawing_files should be array of {id, name} objects
        drawing_files = response.data['all_filter_vals']['drawing_files']
        self.assertTrue(len(drawing_files) > 0)
        self.assertIn('id', drawing_files[0])
        self.assertIn('name', drawing_files[0])
        self.assertEqual(drawing_files[0]['id'], self.drawing_file.id)
        self.assertEqual(drawing_files[0]['name'], "Mechanical.pdf")

    def test_processing_status_returned(self):
        """Test that processing_status is included in response"""
        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url)

        self.assertIn('processing_status', response.data)
        status_data = response.data['processing_status']
        self.assertIn('is_processing', status_data)
        self.assertIn('files_processing', status_data)
        self.assertIn('files_completed', status_data)
        self.assertIn('files_failed', status_data)
        self.assertIn('files', status_data)

    def test_processing_status_shows_processing_files(self):
        """Test processing_status correctly shows files being processed"""
        # Create a file that is still processing
        processing_file = DrawingFile.objects.create(
            project=self.project,
            project_version=self.project_version,
            file_name="Electrical.pdf",
            file_s3_key="drawings/electrical.pdf",
            md5="def456",
        )
        DrawingExtraction.objects.create(
            drawing_file=processing_file,
            status=DrawingExtractionStatus.PROCESSING,
        )

        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url)

        status_data = response.data['processing_status']
        self.assertTrue(status_data['is_processing'])
        self.assertEqual(status_data['files_processing'], 1)
        self.assertEqual(status_data['files_completed'], 1)  # Original file
        self.assertEqual(len(status_data['files']), 1)
        self.assertEqual(status_data['files'][0]['name'], "Electrical.pdf")
        self.assertEqual(status_data['files'][0]['status'], "PROCESSING")
