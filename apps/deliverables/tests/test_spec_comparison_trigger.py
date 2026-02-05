import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status

from apps.deliverables.models import (
    Project,
    ProjectMembership,
    SpecComparison,
    SpecComparisonStatus,
    SpecSection,
    MasterFormatSection,
    UploadedFile,
    DrawingFile,
    DrawingExtraction,
    DrawingExtractionStatus,
    DrawingPage,
    DrawingNoteSection,
    DrawingNote,
)
from apps.teams.models import Team

User = get_user_model()


class TestTriggerSpecComparison(APITestCase):
    """Test the trigger spec comparison endpoint"""

    def setUp(self):
        self.user = User.objects.create_user(
            'test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role='project_member'
        )

        # Create drawing notes
        self.drawing_file = DrawingFile.objects.create(
            project=self.project,
            project_version=self.project_version,
            file_name='test.pdf',
            file_s3_key='drawings/test.pdf',
            md5='abc123',
        )
        self.extraction = DrawingExtraction.objects.create(
            drawing_file=self.drawing_file,
            status=DrawingExtractionStatus.SUCCESS,
        )
        self.page = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=1,
            page_type='drawing',
            extraction_status='success',
        )
        self.section = DrawingNoteSection.objects.create(
            page=self.page,
            header='GENERAL NOTES',
        )
        self.note = DrawingNote.objects.create(
            section=self.section,
            note_number=1,
            category='general',
            text='Test note text',
        )

        # Create spec sections
        self.masterformat = MasterFormatSection.objects.create(
            masterformat_number='220500',
            masterformat_description='Common Work Results'
        )
        self.uploaded_file = UploadedFile.objects.create(
            project=self.project,
            project_version=self.project_version,
            document_path='specs/test.pdf',
            name='test.pdf',
            md5='def456',
            processing_status='PROCESSED',
        )
        self.spec_section = SpecSection.objects.create(
            masterformat_section=self.masterformat,
            document=self.uploaded_file,
            file_s3_key='specs/test.pdf',
        )

        self.client.force_authenticate(user=self.user)
        self.trigger_url = reverse(
            'deliverables:trigger-spec-comparison',
            kwargs={'project_id': self.project.id}
        )

    @patch('apps.deliverables.views.spec_comparison_views.is_drawing_spec_comparison_active')
    def test_missing_project_version_id_returns_400(self, mock_flag):
        """Test 400 when project_version_id is not provided"""
        mock_flag.return_value = True

        response = self.client.post(self.trigger_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('project_version_id', str(response.data))

    @patch('apps.deliverables.views.spec_comparison_views.is_drawing_spec_comparison_active')
    @patch('apps.deliverables.views.spec_comparison_views.invoke_spec_comparison_lambda')
    @patch('apps.deliverables.views.spec_comparison_views.upload_payload_to_s3')
    def test_successful_trigger(self, mock_upload, mock_invoke, mock_flag):
        """Test successful comparison trigger"""
        mock_flag.return_value = True
        mock_upload.return_value = 'spec-comparisons/1/payload.json'
        mock_invoke.return_value = None

        response = self.client.post(
            self.trigger_url,
            data={'project_version_id': self.project_version.id},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], SpecComparisonStatus.PROCESSING)
        self.assertIn('event_id', response.data)

        # Verify comparison created
        comparison = SpecComparison.objects.get(id=response.data['id'])
        self.assertEqual(comparison.project, self.project)
        self.assertEqual(comparison.project_version, self.project_version)
        self.assertEqual(comparison.status, SpecComparisonStatus.PROCESSING)
        self.assertIsNotNone(comparison.started_at)

    @patch('apps.deliverables.views.spec_comparison_views.is_drawing_spec_comparison_active')
    def test_feature_flag_disabled_returns_403(self, mock_flag):
        """Test 403 when feature flag is disabled"""
        mock_flag.return_value = False

        response = self.client.post(
            self.trigger_url,
            data={'project_version_id': self.project_version.id},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.deliverables.views.spec_comparison_views.is_drawing_spec_comparison_active')
    def test_no_notes_returns_400(self, mock_flag):
        """Test 400 when no drawing notes exist"""
        mock_flag.return_value = True
        DrawingNote.objects.all().delete()

        response = self.client.post(
            self.trigger_url,
            data={'project_version_id': self.project_version.id},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('No drawing notes', response.data['error'])

    @patch('apps.deliverables.views.spec_comparison_views.is_drawing_spec_comparison_active')
    def test_no_specs_returns_400(self, mock_flag):
        """Test 400 when no spec sections exist"""
        mock_flag.return_value = True
        SpecSection.objects.all().delete()

        response = self.client.post(
            self.trigger_url,
            data={'project_version_id': self.project_version.id},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('No spec sections', response.data['error'])

    def test_unauthenticated_returns_403(self):
        """Test 403 for unauthenticated requests"""
        self.client.force_authenticate(user=None)

        response = self.client.post(self.trigger_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_member_returns_403(self):
        """Test 403 for non-project members"""
        other_user = User.objects.create_user(
            'other@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=other_user)

        response = self.client.post(self.trigger_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.deliverables.views.spec_comparison_views.is_drawing_spec_comparison_active')
    @patch('apps.deliverables.views.spec_comparison_views.invoke_spec_comparison_lambda')
    @patch('apps.deliverables.views.spec_comparison_views.upload_payload_to_s3')
    def test_lambda_invoke_failure_sets_failed_status(self, mock_upload, mock_invoke, mock_flag):
        """Test that lambda invoke failure sets FAILED status"""
        mock_flag.return_value = True
        mock_upload.return_value = 'spec-comparisons/1/payload.json'
        mock_invoke.side_effect = Exception('Lambda timeout')

        response = self.client.post(
            self.trigger_url,
            data={'project_version_id': self.project_version.id},
            format='json'
        )

        # Should still return 201 but with FAILED status
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], SpecComparisonStatus.FAILED)

        # Verify comparison has error
        comparison = SpecComparison.objects.get(id=response.data['id'])
        self.assertEqual(comparison.status, SpecComparisonStatus.FAILED)
        self.assertIn('Lambda timeout', comparison.error_message)
        self.assertIsNotNone(comparison.completed_at)

    @patch('apps.deliverables.views.spec_comparison_views.is_drawing_spec_comparison_active')
    def test_invalid_project_version_id_returns_400(self, mock_flag):
        """Test 400 for invalid project_version_id"""
        mock_flag.return_value = True

        response = self.client.post(
            self.trigger_url,
            data={'project_version_id': 99999},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Project version not found', response.data['error'])

    def test_project_not_found_returns_404(self):
        """Test 404 for non-existent project"""
        url = reverse(
            'deliverables:trigger-spec-comparison',
            kwargs={'project_id': 99999}
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
