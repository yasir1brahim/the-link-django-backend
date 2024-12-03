from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from unittest.mock import patch
from apps.teams.models import Team, Membership as TeamMembership
from apps.teams.roles import ROLE_ADMIN, ROLE_MEMBER
from apps.deliverables.models import Project, ProjectMembership, SubmittalItemList, SubmittalItem, MasterFormatSection, ROLE_PROJECT_ADMIN, ROLE_PROJECT_MEMBER
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from waffle.testutils import override_flag
from apps.deliverables.models import UploadedFile
class UploadFileForNoticeParsingTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.User = get_user_model()

        self.company_admin = self.User.objects.create_user(
            username='company_admin', 
            password='password123'
        )
        self.company_member = self.User.objects.create_user(
            username='company_member', 
            password='password123'
        )
        self.team = Team.objects.create(name='Team 1', slug='team-1')
        TeamMembership.objects.create(
            user=self.company_admin,
            team=self.team,
            role=ROLE_ADMIN
        )
        TeamMembership.objects.create(
            user=self.company_member,
            team=self.team,
            role=ROLE_MEMBER
        )

        self.existing_project = Project.objects.create(
            name='Existing Project',
            project_number='123456',
            team=self.team,
        )
        ProjectMembership.objects.create(
            project=self.existing_project,
            user=self.company_member,
            role=ROLE_PROJECT_MEMBER
        )

        self.mock_file = SimpleUploadedFile(
            name='test_file.txt',
            content=b'This is some test file content',
            content_type='text/plain'
        )
    @override_flag(settings.NOTICES_FEATURE_FLAG_NAME, active=True)
    @patch('apps.deliverables.views.call_extract_notices_lambda')
    @patch('apps.deliverables.views.parse_spec')
    def test_upload_file_with_notices_parameter_calls_notices_lambda(self, mock_parse_spec, mock_call_extract_notices_lambda):
        url = reverse('deliverables:upload_file')
        data = {
            'project_id': self.existing_project.id,
            'files': [self.mock_file],
            'extract_notices': True
        }
        self.client.force_authenticate(user=self.company_member)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_call_extract_notices_lambda.assert_called_once()
        mock_parse_spec.assert_not_called()

    @override_flag(settings.NOTICES_FEATURE_FLAG_NAME, active=True)
    @patch('apps.deliverables.views.call_extract_notices_lambda')
    @patch('apps.deliverables.views.parse_spec')        
    def test_upload_file_without_notices_parameter_does_not_call_notices_lambda(self, mock_parse_spec, mock_call_extract_notices_lambda):
        url = reverse('deliverables:upload_file')
        data = {
            'project_id': self.existing_project.id,
            'files': [self.mock_file],
        }
        self.client.force_authenticate(user=self.company_member)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_call_extract_notices_lambda.assert_not_called()
        mock_parse_spec.assert_called_once()

    @override_flag(settings.NOTICES_FEATURE_FLAG_NAME, active=False)
    @patch('apps.deliverables.views.call_extract_notices_lambda')
    @patch('apps.deliverables.views.parse_spec')  
    def test_notices_feature_flag_must_be_active_for_notices_lambda_to_be_called(self, mock_parse_spec, mock_call_extract_notices_lambda):
        url = reverse('deliverables:upload_file')
        data = {
            'project_id': self.existing_project.id,
            'files': [self.mock_file],
            'extract_notices': True
        }
        self.client.force_authenticate(user=self.company_member)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_call_extract_notices_lambda.assert_not_called()
        mock_parse_spec.assert_called_once()

    @override_flag(settings.NOTICES_FEATURE_FLAG_NAME, active=True)
    @patch('apps.deliverables.views.invoke_lambda')
    def test_call_extract_notices_lambda(self, mock_invoke_lambda):
        
        url = reverse('deliverables:upload_file')
        data = {
            'project_id': self.existing_project.id,
            'files': [self.mock_file],
            'extract_notices': True
        }
        self.client.force_authenticate(user=self.company_member)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        db_file = UploadedFile.objects.get(project_id=self.existing_project.id, name=self.mock_file.name)
        self.assertEqual(db_file.processing_status, 'PENDING_PROCESSING')

        expected_payload = {
            "source_file_s3_uri": f"s3://{settings.S3_BUCKET}/{db_file.document_path}",
            "document_id": str(db_file.id),
            "callback_url": settings.BACKEND_CALLBACK_URL,
            "ENVIRONMENT": settings.ENVIRONMENT,
        }
        mock_invoke_lambda.assert_called_with(
            payload=expected_payload,
            lambda_url=settings.LAMBDA_FUNCTION_URL
        )