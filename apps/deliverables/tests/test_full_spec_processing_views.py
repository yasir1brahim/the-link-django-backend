import json

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
from apps.deliverables.models import UploadedFile, SemanticallyProcessedSpecItem

from apps.deliverables.tests.test_data.sample_webhook import (
    sample_processing_webhook,
    sample_subsections_extracted_webhook,
    sample_processed_section_webhook,
    expected_paragraph_numbers_in_order,
    full_spec_processing_webhook_payload,
    sample_multiple_subsections_extracted_webhook,
    sample_v2_subsections_extracted_webhook,
)


class FullSpecProcessingWebhookTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="testuser", password="testpassword")
        self.client.force_authenticate(user=self.user)

        self.team = Team.objects.create(name='Team 1', slug='team-1')

        self.project = Project.objects.create(
            name='Test Project',
            project_number='123456',
            team=self.team,
        )
        self.default_project_version = ProjectVersion.objects.get(
            project=self.project
        )
        TeamMembership.objects.create(
            user=self.user,
            team=self.team,
            role=ROLE_ADMIN
        )
        self.mock_file = SimpleUploadedFile(
            name='test_file.txt',
            content=b'This is some test file content',
            content_type='text/plain'
        )

        self.webhook_url = reverse('deliverables:webhook-full-spec-processing')


    def test_successful_callback_sets_document_as_processed(self):
        # Upload a file to the project
        upload_response = self.client.post(reverse('deliverables:upload_file'), {
            'project_id': self.project.id,
            'files': [self.mock_file],
            'full_spec_processing': True,
        })
        self.assertEqual(upload_response.status_code, status.HTTP_200_OK)
        uploaded_file = UploadedFile.objects.get(project=self.project)
        self.assertEqual(uploaded_file.processing_status, 'PENDING_PROCESSING')
        self.assertEqual(uploaded_file.project_version, self.default_project_version)

        # Update test data to use correct IDs
        sample_processing_webhook['document_id'] = uploaded_file.id
        sample_processing_webhook['project_id'] = self.project.id
        sample_processing_webhook['user_id'] = self.user.id
        sample_subsections_extracted_webhook['document_id'] = uploaded_file.id
        sample_subsections_extracted_webhook['project_id'] = self.project.id
        sample_subsections_extracted_webhook['user_id'] = self.user.id
        full_spec_processing_webhook_payload['document_id'] = uploaded_file.id
        full_spec_processing_webhook_payload['project_id'] = self.project.id
        full_spec_processing_webhook_payload['user_id'] = self.user.id
    

        # Simulate receiving the processing webhook
        response = self.client.post(self.webhook_url, data=json.dumps(sample_processing_webhook), content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Simulate receiving the subsections extracted webhook
        response = self.client.post(self.webhook_url, data=json.dumps(sample_subsections_extracted_webhook), content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        uploaded_file.refresh_from_db()
        self.assertEqual(uploaded_file.processing_status, 'SUBSECTIONS_EXTRACTED')

        # Simulate receiving the processed section webhook
        response = self.client.post(self.webhook_url, data=json.dumps(full_spec_processing_webhook_payload), content_type='application/json')
        print("PROCESSED SECTION WEBHOOK RESPONSE: ", response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        uploaded_file.refresh_from_db()
        self.assertEqual(uploaded_file.processing_status, 'PROCESSED')

        # check that the submittal items were created as expected
        spec_items = SemanticallyProcessedSpecItem.objects.filter(project=self.project).order_by('heirarchical_paragraph_number')
        self.assertEqual(spec_items.count(), 5)
        filtered_spec_items = spec_items.filter(project_version=self.default_project_version)
        self.assertEqual(filtered_spec_items.count(), 5)
        self.assertEqual(filtered_spec_items[0].project, self.project)
        self.assertEqual(filtered_spec_items[0].project_version, self.default_project_version)
        self.assertEqual(filtered_spec_items[0].document, uploaded_file)
        self.assertEqual(filtered_spec_items[0].masterformat_section.masterformat_number, full_spec_processing_webhook_payload['master_format_section_number'])
        self.assertEqual(filtered_spec_items[0].spec_section_part, full_spec_processing_webhook_payload['spec_items'][0]['spec_section_part'])
        self.assertEqual(filtered_spec_items[0].topic, full_spec_processing_webhook_payload['spec_items'][0]['topic'])
        self.assertEqual(filtered_spec_items[0].item_type, full_spec_processing_webhook_payload['spec_items'][0]['item'])
        self.assertEqual(filtered_spec_items[0].item_content, full_spec_processing_webhook_payload['spec_items'][0]['text'])
        self.assertEqual(filtered_spec_items[0].paragraph_number, full_spec_processing_webhook_payload['spec_items'][0]['paragraph_number'])
        self.assertEqual(filtered_spec_items[0].parsing_method, "FULL_SPEC_PROCESSING")
        self.assertEqual(filtered_spec_items[0].parsing_version, "1.0")


        # check that get submittal items API returns the submittal items in the correct order
        url = reverse('semantically-processed-spec-item-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print(response.data)
        self.assertEqual(len(response.data), 5)
        
        

        
