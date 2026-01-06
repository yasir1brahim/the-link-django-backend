from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch
from apps.deliverables.models import Project, DrawingFile, DrawingExtraction, DrawingExtractionStatus, ProjectMembership, ROLE_PROJECT_MEMBER
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class DrawingUploadTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('test@example.com', password='testpass')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(
            name="Test Project",
            project_number="P-001",
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        self.team.members.add(self.user)
        ProjectMembership.objects.create(project=self.project, user=self.user, role=ROLE_PROJECT_MEMBER)
        self.client.force_authenticate(user=self.user)

    @patch('apps.deliverables.views.main_views.s3.upload_fileobj')
    def test_upload_drawing_file(self, mock_upload):
        """Test uploading a file with file_type='drawing'"""
        mock_upload.return_value = None

        pdf_content = b"%PDF-1.4 test content"
        drawing_file = SimpleUploadedFile("mechanical.pdf", pdf_content, content_type="application/pdf")

        url = reverse('deliverables:upload_file')
        data = {
            'files': [drawing_file],
            'project_id': self.project.id,
            'project_version_id': self.project_version.id,
            'file_type': 'drawing'
        }

        response = self.client.post(url, data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify DrawingFile was created
        self.assertEqual(DrawingFile.objects.count(), 1)
        df = DrawingFile.objects.first()
        self.assertEqual(df.file_name, "mechanical.pdf")
        self.assertEqual(df.project, self.project)
        self.assertEqual(df.project_version, self.project_version)

        # Verify DrawingExtraction was created
        self.assertEqual(DrawingExtraction.objects.count(), 1)
        ext = DrawingExtraction.objects.first()
        self.assertEqual(ext.drawing_file, df)
        self.assertEqual(ext.status, DrawingExtractionStatus.PENDING)

    @patch('apps.deliverables.views.main_views.s3.upload_fileobj')
    def test_upload_duplicate_drawing_reuses_file_record(self, mock_upload):
        """Test that uploading the same drawing reuses the DrawingFile record but creates new Extraction"""
        mock_upload.return_value = None

        pdf_content = b"%PDF-1.4 unique content"

        url = reverse('deliverables:upload_file')

        # First upload
        file1 = SimpleUploadedFile("mechanical.pdf", pdf_content, content_type="application/pdf")
        self.client.post(url, {
            'files': [file1],
            'project_id': self.project.id,
            'project_version_id': self.project_version.id,
            'file_type': 'drawing'
        }, format='multipart')

        self.assertEqual(DrawingFile.objects.count(), 1)
        self.assertEqual(DrawingExtraction.objects.count(), 1)

        # Second upload of same file
        file2 = SimpleUploadedFile("mechanical.pdf", pdf_content, content_type="application/pdf")
        self.client.post(url, {
            'files': [file2],
            'project_id': self.project.id,
            'project_version_id': self.project_version.id,
            'file_type': 'drawing'
        }, format='multipart')

        # Should still be 1 DrawingFile but 2 Extractions
        self.assertEqual(DrawingFile.objects.count(), 1)
        self.assertEqual(DrawingExtraction.objects.count(), 2)

    @patch('apps.deliverables.views.main_views.s3.upload_fileobj')
    def test_upload_drawing_uses_drawings_s3_prefix(self, mock_upload):
        """Test that drawing files are uploaded to drawings/ S3 prefix"""
        mock_upload.return_value = None

        pdf_content = b"%PDF-1.4 test content"
        drawing_file = SimpleUploadedFile("mechanical.pdf", pdf_content, content_type="application/pdf")

        url = reverse('deliverables:upload_file')
        data = {
            'files': [drawing_file],
            'project_id': self.project.id,
            'project_version_id': self.project_version.id,
            'file_type': 'drawing'
        }

        self.client.post(url, data, format='multipart')

        # Verify S3 key starts with drawings/
        df = DrawingFile.objects.first()
        self.assertTrue(df.file_s3_key.startswith('drawings/'))
