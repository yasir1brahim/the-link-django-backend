import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from rest_framework import status

from apps.teams.models import Team, Membership as TeamMembership
from apps.teams.roles import ROLE_ADMIN
from apps.deliverables.models import Project, UploadedFile, SubmittalItem
from apps.deliverables.tests.test_data.sample_webhook import (
    sample_processing_webhook,
    sample_subsections_extracted_webhook,
    sample_processed_section_webhook,
    expected_paragraph_numbers_in_order
)

class TestSpecStatusWebhook(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="testuser", password="testpassword")
        self.client.force_authenticate(user=self.user)
        self.team = Team.objects.create(name="Test Team")
        self.project = Project.objects.create(
            name="Test Project",
            project_number="123456",
            team=self.team,
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
        self.webhook_url = reverse('deliverables:spec_status_webhook')

    @patch('apps.deliverables.views.parse_spec')
    def test_spec_status_webhook_end_to_end_success(self, mock_parse_spec):
        # Upload a file to the project
        upload_response = self.client.post(reverse('deliverables:upload_file'), {
            'project_id': self.project.id,
            'files': [self.mock_file],
        })
        self.assertEqual(upload_response.status_code, status.HTTP_200_OK)
        uploaded_file = UploadedFile.objects.get(project=self.project)
        self.assertEqual(uploaded_file.processing_status, 'PENDING_PROCESSING')

        # Update test data to use correct IDs
        sample_processing_webhook['document_id'] = uploaded_file.id
        sample_processing_webhook['project_id'] = self.project.id
        sample_processing_webhook['user_id'] = self.user.id
        sample_subsections_extracted_webhook['document_id'] = uploaded_file.id
        sample_subsections_extracted_webhook['project_id'] = self.project.id
        sample_subsections_extracted_webhook['user_id'] = self.user.id
        sample_processed_section_webhook['document_id'] = uploaded_file.id
        sample_processed_section_webhook['project_id'] = self.project.id
        sample_processed_section_webhook['user_id'] = self.user.id
    

        # Simulate receiving the processing webhook
        response = self.client.post(self.webhook_url, data=json.dumps(sample_processing_webhook), content_type='application/json')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Simulate receiving the subsections extracted webhook
        response = self.client.post(self.webhook_url, data=json.dumps(sample_subsections_extracted_webhook), content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        uploaded_file.refresh_from_db()
        self.assertEqual(uploaded_file.processing_status, 'SUBSECTIONS_EXTRACTED')

        # Simulate receiving the processed section webhook
        response = self.client.post(self.webhook_url, data=json.dumps(sample_processed_section_webhook), content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        uploaded_file.refresh_from_db()
        self.assertEqual(uploaded_file.processing_status, 'PROCESSED')

        # check that the submittal items were created as expected
        submittal_items = SubmittalItem.objects.filter(project=self.project).order_by('heirarchical_paragraph_number')
        print([submittal_item.heirarchical_paragraph_number for submittal_item in submittal_items])

        self.assertEqual(submittal_items.count(), 53)
        self.assertEqual(submittal_items[0].submittal_type, 'Action/Information Submittals')
        self.assertEqual(submittal_items[0].submittal_description, 'Product Data')
        self.assertEqual(submittal_items[0].submittal_content, 'Product Data:  Submit preprinted data for each type of manufactured material')

        # check that submittal numbers were assigned as expected
        for index, expected_paragraph_number in enumerate(expected_paragraph_numbers_in_order):
            expected_submittal_number = index + 1
            submittal_item = submittal_items.filter(paragraph_number=expected_paragraph_number).first()
            self.assertEqual(int(submittal_item.submittal_number), expected_submittal_number)
            self.assertEqual(submittal_item.paragraph_number, expected_paragraph_number)

        # check that get submittal items API returns the submittal items in the correct order
        url = reverse('submittal-item-list', kwargs={'project_id': self.project.id})
        print(url)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print([submittal_item['submittal_number'] for submittal_item in response.data['message']])
        self.assertEqual(len(response.data['message']), 53)

        for index, submittal_item in enumerate(response.data['message']):
            displayed_submittal_number = submittal_item['submittal_number']
            if displayed_submittal_number.endswith('.0'):
                displayed_submittal_number = displayed_submittal_number[:-2]
            self.assertEqual(submittal_item['para_no'], expected_paragraph_numbers_in_order[index])
            self.assertEqual(int(displayed_submittal_number), index + 1)







