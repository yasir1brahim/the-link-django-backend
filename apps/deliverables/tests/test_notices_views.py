from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from unittest.mock import patch
from apps.teams.models import Team, Membership as TeamMembership
from apps.teams.roles import ROLE_ADMIN, ROLE_MEMBER
from apps.deliverables.models import Project, ProjectVersion, ProjectMembership, SubmittalItemList, SubmittalItem, MasterFormatSection, ROLE_PROJECT_ADMIN, ROLE_PROJECT_MEMBER
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
        self.project_version_1 = ProjectVersion.objects.get(project=self.existing_project)
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
            "project_version_id": str(self.project_version_1.id),
            "callback_url": settings.BACKEND_NOTICES_CALLBACK_URL,
            "ENVIRONMENT": settings.ENVIRONMENT,
        }
        mock_invoke_lambda.assert_called_with(
            payload=expected_payload,
            lambda_url=settings.NOTICES_LAMBDA_FUNCTION_URL
        )
    
    @override_flag(settings.VERSIONING_FEATURE_FLAG_NAME, active=False)
    @override_flag(settings.NOTICES_FEATURE_FLAG_NAME, active=True)
    @patch('apps.deliverables.views.invoke_lambda')
    def test_call_extract_notices_lambda_with_versioning_inactive_assigns_to_default_version(self, mock_invoke_lambda):
        url = reverse('deliverables:upload_file')
        data = {
            'project_id': self.existing_project.id,
            'files': [self.mock_file],
            'extract_notices': True,
        }
        self.client.force_authenticate(user=self.company_member)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        db_file = UploadedFile.objects.get(project_id=self.existing_project.id, name=self.mock_file.name)
        self.assertEqual(db_file.processing_status, 'PENDING_PROCESSING')

        expected_payload = {
            "source_file_s3_uri": f"s3://{settings.S3_BUCKET}/{db_file.document_path}",
            "document_id": str(db_file.id),
            "project_version_id": str(self.project_version_1.id),
            "callback_url": settings.BACKEND_NOTICES_CALLBACK_URL,
            "ENVIRONMENT": settings.ENVIRONMENT,
        }
        mock_invoke_lambda.assert_called_with(
            payload=expected_payload,
            lambda_url=settings.NOTICES_LAMBDA_FUNCTION_URL
        )

    @override_flag(settings.VERSIONING_FEATURE_FLAG_NAME, active=True)
    @override_flag(settings.NOTICES_FEATURE_FLAG_NAME, active=True)
    @patch('apps.deliverables.views.invoke_lambda')
    def test_call_extract_notices_lambda_with_versioning_active_assigns_to_given_version(self, mock_invoke_lambda):
        url = reverse('deliverables:upload_file')
        project_version_2 = ProjectVersion.objects.create(project=self.existing_project, version_number=2, version_name="Version 2")
        project_version_3 = ProjectVersion.objects.create(project=self.existing_project, version_number=3, version_name="Version 3")
        data = {
            'project_id': self.existing_project.id,
            'files': [self.mock_file],
            'extract_notices': True,
            'project_version_id': project_version_2.id
        }
        self.client.force_authenticate(user=self.company_member)

        response = self.client.post(url, data)
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        db_file = UploadedFile.objects.get(project_id=self.existing_project.id, name=self.mock_file.name)
        self.assertEqual(db_file.processing_status, 'PENDING_PROCESSING')

        expected_payload = {
            "source_file_s3_uri": f"s3://{settings.S3_BUCKET}/{db_file.document_path}",
            "document_id": str(db_file.id),
            "project_version_id": str(project_version_2.id),
            "callback_url": settings.BACKEND_NOTICES_CALLBACK_URL,
            "ENVIRONMENT": settings.ENVIRONMENT,
        }
        mock_invoke_lambda.assert_called_with(
            payload=expected_payload,
            lambda_url=settings.NOTICES_LAMBDA_FUNCTION_URL
        )

    @override_flag(settings.VERSIONING_FEATURE_FLAG_NAME, active=True)
    @override_flag(settings.NOTICES_FEATURE_FLAG_NAME, active=True)
    @patch('apps.deliverables.views.invoke_lambda')
    def test_call_extract_notices_lambda_with_versioning_active_requires_project_version(self, mock_invoke_lambda):
        url = reverse('deliverables:upload_file')
        data = {
            'project_id': self.existing_project.id,
            'files': [self.mock_file],
            'extract_notices': True,
        }
        self.client.force_authenticate(user=self.company_member)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class NoticeProcessingWebhookTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.User = get_user_model()

        self.team = Team.objects.create(name='Team 1', slug='team-1')

        self.project = Project.objects.create(
            name='Test Project',
            project_number='123456',
            team=self.team,
        )
        self.project_version_1 = ProjectVersion.objects.get(project=self.project)

        self.document = UploadedFile.objects.create(
            project=self.project,
            name='Test Document',
            document_path='test/document/path',
            processing_status="PENDING_PROCESSING",
            project_version=self.project_version_1
        )

        self.example_payload = {
            'excerpts': [
                {
                    'anchor': ('1.03', 'A.', '2.'),
                    'lines': [
                        {'text': '2. Within time specified in Proposal Request or 20 days, when not otherwise specified,', 'page_no': 1, 'x_start': 115.20100402832031, 'x_end': 554.9420776367188, 'y_start': 506.48577880859375, 'y_end': 518.8195190429688},
                        {'text': 'after receipt of Proposal Request, submit a quotation estimating cost adjustments to the', 'page_no': 1, 'x_start': 144.0008087158203, 'x_end': 573.3023681640625, 'y_start': 519.0858154296875, 'y_end': 531.4195556640625},
                        {'text': 'Contract Sum and the Contract Time necessary to execute the change.', 'page_no': 1, 'x_start': 144.0008087158203, 'x_end': 493.7425842285156, 'y_start': 531.8057861328125, 'y_end': 544.1395263671875}
                    ]
                }
            ],
            'matches': [
                {
                    'highlight_heuristic_match': None,
                    'highlight_discriminators': ['days'],
                    'excerpt_anchors': [('1.03', 'A.', '2.')],
                    'leading_anchor': ('1.03', 'A.', '2.'),
                }
            ],
            'document': str(self.document.id),
            'project_version_id': str(self.project_version_1.id),
        }

    def test_successful_callback_sets_document_as_processed(self):
        url = reverse('deliverables:webhook-notice-processing')
        response = self.client.post(url, self.example_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.document.refresh_from_db()
        self.assertEqual(self.document.processing_status, 'PROCESSED')
        self.assertEqual(self.document.project_version, self.project_version_1)

    def test_successful_callback_sets_project_version_correctly(self):
        project_version_2 = ProjectVersion.objects.create(project=self.project, version_number=2, version_name="Version 2")
        project_version_3 = ProjectVersion.objects.create(project=self.project, version_number=3, version_name="Version 3")
        self.document.project_version = project_version_2
        self.document.save()
        url = reverse('deliverables:webhook-notice-processing')
        self.example_payload['project_version_id'] = str(project_version_2.id)
        response = self.client.post(url, self.example_payload, format='json')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.document.refresh_from_db()
        self.assertEqual(self.document.processing_status, 'PROCESSED')
        self.assertEqual(self.document.project_version, project_version_2)
        


class NoticeMatchViewSetTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.User = get_user_model()

        self.team = Team.objects.create(name='Team 1', slug='team-1')
        self.project = Project.objects.create(name='Test Project', project_number='123456', team=self.team)
        self.project_version_1 = ProjectVersion.objects.get(project=self.project)
        self.project_without_notices = Project.objects.create(name='Test Project 2', project_number='123457', team=self.team)
        self.document = UploadedFile.objects.create(project=self.project, name='Test Document', document_path='test/document/path', processing_status="PENDING_PROCESSING", project_version=self.project_version_1)
        self.team_member = self.User.objects.create_user(username='team_member', password='password123')
        TeamMembership.objects.create(user=self.team_member, team=self.team, role=ROLE_MEMBER)
        ProjectMembership.objects.create(project=self.project, user=self.team_member, role=ROLE_PROJECT_MEMBER)

    def create_notices(self):
        example_payload = {
            'excerpts': [
                {
                    'anchor': ('1.03', 'A.', '2.'),
                    'lines': [
                        {'text': '2. Within time specified in Proposal Request or 20 days, when not otherwise specified,', 'page_no': 1, 'x_start': 115.20100402832031, 'x_end': 554.9420776367188, 'y_start': 506.48577880859375, 'y_end': 518.8195190429688},
                        {'text': 'after receipt of Proposal Request, submit a quotation estimating cost adjustments to the', 'page_no': 1, 'x_start': 144.0008087158203, 'x_end': 573.3023681640625, 'y_start': 519.0858154296875, 'y_end': 531.4195556640625},
                        {'text': 'Contract Sum and the Contract Time necessary to execute the change.', 'page_no': 1, 'x_start': 144.0008087158203, 'x_end': 493.7425842285156, 'y_start': 531.8057861328125, 'y_end': 544.1395263671875}
                    ]
                }
            ],
            'matches': [
                {
                    'highlight_heuristic_match': None,
                    'highlight_discriminators': ['days'],
                    'excerpt_anchors': [('1.03', 'A.', '2.')],
                    'leading_anchor': ('1.03', 'A.', '2.'),
                }
            ],
            'document': str(self.document.id),
        }
        url = reverse('deliverables:webhook-notice-processing')
        self.client.post(url, example_payload, format='json')

    def test_unauthenticated_user_cannot_see_notices(self):
        url = reverse('notice-list-list', kwargs={'project_id': self.project_without_notices.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_project_member_cannot_see_notices_for_other_projects(self):
        url = reverse('notice-list-list', kwargs={'project_id': self.project_without_notices.id})
        self.client.force_login(self.team_member)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_returns_notices_for_given_project(self):
        self.create_notices()
        ProjectMembership.objects.create(
            project=self.project_without_notices,
            user=self.team_member,
            role=ROLE_PROJECT_MEMBER
        )
        url = reverse('notice-list-list', kwargs={'project_id': self.project_without_notices.id})
        self.client.force_login(self.team_member)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print(response.data)
        self.assertEqual(len(response.data['results']), 0)


