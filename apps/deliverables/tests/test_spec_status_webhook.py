import json
from unittest.mock import patch
from unittest import skip

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from rest_framework import status

from apps.teams.models import Team, Membership as TeamMembership
from apps.teams.roles import ROLE_ADMIN
from apps.deliverables.models import Project, UploadedFile, SubmittalItem, ProjectVersion
from copy import deepcopy
from apps.deliverables.tests.test_data.sample_webhook import (
    sample_processing_webhook,
    sample_subsections_extracted_webhook,
    sample_processed_section_webhook,
    expected_paragraph_numbers_in_order,
    sample_processed_placeholder_webhook,
    sample_multiple_subsections_extracted_webhook,
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
        self.default_project_version = ProjectVersion.objects.get(project=self.project)
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

    def tearDown(self):
        SubmittalItem.objects.all().delete()
        UploadedFile.objects.all().delete()
        ProjectVersion.objects.all().delete()


    @patch('apps.deliverables.views.parse_spec')
    def test_spec_status_webhook_end_to_end_success_with_null_project_version_id(self, mock_parse_spec):
        # Upload a file to the project
        upload_response = self.client.post(reverse('deliverables:upload_file'), {
            'project_id': self.project.id,
            'files': [self.mock_file],
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
        sample_processed_section_webhook['document_id'] = uploaded_file.id
        sample_processed_section_webhook['project_id'] = self.project.id
        sample_processed_section_webhook['user_id'] = self.user.id
    

        # Simulate receiving the processing webhook
        response = self.client.post(self.webhook_url, data=json.dumps(sample_processing_webhook), content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Simulate receiving the subsections extracted webhook
        response = self.client.post(self.webhook_url, data=json.dumps(sample_subsections_extracted_webhook), content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        uploaded_file.refresh_from_db()
        self.assertEqual(uploaded_file.processing_status, 'SUBSECTIONS_EXTRACTED')

        # Simulate receiving the processed section webhook
        response = self.client.post(self.webhook_url, data=json.dumps(sample_processed_section_webhook), content_type='application/json')
        print("PROCESSED SECTION WEBHOOK RESPONSE: ", response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        uploaded_file.refresh_from_db()
        self.assertEqual(uploaded_file.processing_status, 'PROCESSED')

        # check that the submittal items were created as expected
        submittal_items = SubmittalItem.objects.filter(project=self.project).order_by('heirarchical_paragraph_number')
        self.assertEqual(submittal_items.count(), 53)
        filtered_submittal_items = submittal_items.filter(project_version=self.default_project_version)
        self.assertEqual(filtered_submittal_items.count(), 53)
        self.assertEqual(submittal_items[0].submittal_type, 'Action/Information Submittals')
        self.assertEqual(submittal_items[0].submittal_description, 'Product Data')
        self.assertEqual(submittal_items[0].submittal_content, 'Product Data:  Submit preprinted data for each type of manufactured material')

        # check that submittal numbers were assigned as expected
        for index, expected_paragraph_number in enumerate(expected_paragraph_numbers_in_order):
            expected_submittal_number = index + 1
            submittal_item = submittal_items.filter(paragraph_number=expected_paragraph_number).first()
            self.assertEqual(int(submittal_item.submittal_number), expected_submittal_number)
            self.assertEqual(submittal_item.paragraph_number, expected_paragraph_number)
            # check that the project version is the default project version
            self.assertEqual(submittal_item.project_version, self.default_project_version)

        # check that get submittal items API returns the submittal items in the correct order
        url = reverse('submittal-item-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['message']), 53)

        for index, submittal_item in enumerate(response.data['message']):
            displayed_submittal_number = submittal_item['submittal_number']
            if displayed_submittal_number.endswith('.0'):
                displayed_submittal_number = displayed_submittal_number[:-2]
            self.assertEqual(submittal_item['para_no'], expected_paragraph_numbers_in_order[index])
            self.assertEqual(int(displayed_submittal_number), index + 1)

    @patch('apps.deliverables.views.is_versioning_feature_flag_active', return_value=True)
    @patch('apps.deliverables.views.parse_spec')
    def test_spec_status_webhook_end_to_end_success_with_provided_project_version_id(self, mock_parse_spec, mock_is_versioning_feature_flag_active):
        project_version_2 = ProjectVersion.objects.create(project=self.project, version_number=2, version_name="Version 2")
        project_version_3 = ProjectVersion.objects.create(project=self.project, version_number=3, version_name="Version 3")
        # Upload a file to the project
        upload_response = self.client.post(reverse('deliverables:upload_file'), {
            'project_id': self.project.id,
            'files': [self.mock_file],
            'project_version_id': project_version_2.id,
        })
        self.assertEqual(upload_response.status_code, status.HTTP_200_OK)
        uploaded_file = UploadedFile.objects.get(project=self.project)
        self.assertEqual(uploaded_file.processing_status, 'PENDING_PROCESSING')
        self.assertEqual(uploaded_file.project_version, project_version_2)

        # Update test data to use correct IDs
        sample_processing_webhook['document_id'] = uploaded_file.id
        sample_processing_webhook['project_id'] = self.project.id
        sample_processing_webhook['user_id'] = self.user.id
        sample_processing_webhook['project_version_id'] = project_version_2.id
        sample_subsections_extracted_webhook['document_id'] = uploaded_file.id
        sample_subsections_extracted_webhook['project_id'] = self.project.id
        sample_subsections_extracted_webhook['user_id'] = self.user.id
        sample_subsections_extracted_webhook['project_version_id'] = project_version_2.id
        sample_processed_section_webhook['document_id'] = uploaded_file.id
        sample_processed_section_webhook['project_id'] = self.project.id
        sample_processed_section_webhook['user_id'] = self.user.id
        sample_processed_section_webhook['project_version_id'] = project_version_2.id
    

        # Simulate receiving the processing webhook
        response = self.client.post(self.webhook_url, data=json.dumps(sample_processing_webhook), content_type='application/json')
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
            # check that the project version is the given project version
            self.assertEqual(submittal_item.project_version, project_version_2)

        # check that get submittal items API returns the submittal items in the correct order
        url = reverse('submittal-item-list', kwargs={'project_id': self.project.id}) + '?project_version_id=' + str(project_version_2.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['message']), 53)

        for index, submittal_item in enumerate(response.data['message']):
            displayed_submittal_number = submittal_item['submittal_number']
            if displayed_submittal_number.endswith('.0'):
                displayed_submittal_number = displayed_submittal_number[:-2]
            self.assertEqual(submittal_item['para_no'], expected_paragraph_numbers_in_order[index])
            self.assertEqual(int(displayed_submittal_number), index + 1)


    @patch('apps.deliverables.views.parse_spec')
    def test_spec_status_webhook_end_to_end_success_with_regex_failure(self, mock_parse_spec):
        # Upload a file to the project
        upload_response = self.client.post(reverse('deliverables:upload_file'), {
            'project_id': self.project.id,
            'files': [self.mock_file],
        })
        self.assertEqual(upload_response.status_code, status.HTTP_200_OK)
        uploaded_file = UploadedFile.objects.get(project=self.project)
        self.assertEqual(uploaded_file.processing_status, 'PENDING_PROCESSING')
        uploaded_file.refresh_from_db()

        # Update test data to use correct IDs
        sample_processing_webhook['document_id'] = uploaded_file.id
        sample_processing_webhook['project_id'] = self.project.id
        sample_processing_webhook['user_id'] = self.user.id
        sample_subsections_extracted_webhook['document_id'] = uploaded_file.id
        sample_subsections_extracted_webhook['project_id'] = self.project.id
        sample_subsections_extracted_webhook['user_id'] = self.user.id
        sample_processed_placeholder_webhook['document_id'] = uploaded_file.id
        sample_processed_placeholder_webhook['project_id'] = self.project.id
        sample_processed_placeholder_webhook['user_id'] = self.user.id

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
        response = self.client.post(self.webhook_url, data=json.dumps(sample_processed_placeholder_webhook), content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        uploaded_file.refresh_from_db()
        self.assertEqual(uploaded_file.processing_status, 'PROCESSED')
        
        # Assert that a placeholder submittal item was created
        placeholder_submittal_items = SubmittalItem.objects.filter(project=self.project)
        self.assertEqual(placeholder_submittal_items.count(), 1)
        self.assertEqual(placeholder_submittal_items[0].submittal_type, 'N/A')
        self.assertEqual(placeholder_submittal_items[0].submittal_description, 'N/A')
        self.assertEqual(placeholder_submittal_items[0].submittal_content, 'Unable to extract submittals from text')
        # Assert that the submittal item has record of the spec section being unable to be processed
        self.assertEqual(placeholder_submittal_items[0].spec_section.processing_method, 'REGEX_UNABLE_TO_DETECT_SUBMITTALS')



    @patch('apps.deliverables.views.parse_spec')
    def test_spec_status_webhook_end_to_end_success_with_placeholder_sections(self, mock_parse_spec):
        # Upload a file to the project
        upload_response = self.client.post(reverse('deliverables:upload_file'), {
            'project_id': self.project.id,
            'files': [self.mock_file],
        })
        self.assertEqual(upload_response.status_code, status.HTTP_200_OK)
        uploaded_file = UploadedFile.objects.get(project=self.project)
        self.assertEqual(uploaded_file.processing_status, 'PENDING_PROCESSING')
        uploaded_file.refresh_from_db()

        # Update test data to use correct IDs
        sample_processing_webhook['document_id'] = uploaded_file.id
        sample_processing_webhook['project_id'] = self.project.id
        sample_processing_webhook['user_id'] = self.user.id
        sample_multiple_subsections_extracted_webhook['document_id'] = uploaded_file.id
        sample_multiple_subsections_extracted_webhook['project_id'] = self.project.id
        sample_multiple_subsections_extracted_webhook['user_id'] = self.user.id
        sample_processed_placeholder_webhook['document_id'] = uploaded_file.id
        sample_processed_placeholder_webhook['project_id'] = self.project.id
        sample_processed_placeholder_webhook['user_id'] = self.user.id
        sample_processed_section_webhook['document_id'] = uploaded_file.id
        sample_processed_section_webhook['project_id'] = self.project.id
        sample_processed_section_webhook['user_id'] = self.user.id
    

        # Simulate receiving the processing webhook
        response = self.client.post(self.webhook_url, data=json.dumps(sample_processing_webhook), content_type='application/json')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Simulate receiving the subsections extracted webhook
        response = self.client.post(self.webhook_url, data=json.dumps(sample_multiple_subsections_extracted_webhook), content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        uploaded_file.refresh_from_db()
        self.assertEqual(uploaded_file.processing_status, 'SUBSECTIONS_EXTRACTED')

        # Simulate receiving the processed section webhooks
        processed_sections = [subsection['master_format_section_number'] for subsection in sample_multiple_subsections_extracted_webhook['subsections']]
        section_number_to_have_actual_submittals = processed_sections[2]

        for section_number in processed_sections:
            if section_number == section_number_to_have_actual_submittals:
                webhook_data = deepcopy(sample_processed_section_webhook)
                webhook_data['master_format_section_number'] = section_number
            else:
                webhook_data = deepcopy(sample_processed_placeholder_webhook)
                webhook_data['master_format_section_number'] = section_number
            
            response = self.client.post(self.webhook_url, data=json.dumps(webhook_data), content_type='application/json')
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        uploaded_file.refresh_from_db()
        self.assertEqual(uploaded_file.processing_status, 'PROCESSED')

        # check that the submittal items were created as expected
        submittal_items = SubmittalItem.objects.filter(project=self.project)

        self.assertEqual(submittal_items.count(), 53 + 3) # 3 placeholder sections plus 53 actual submittals

        actual_submittal_items = submittal_items.exclude(parsing_method='PLACEHOLDER').order_by('heirarchical_paragraph_number')
        self.assertEqual(actual_submittal_items[0].submittal_type, 'Action/Information Submittals')
        self.assertEqual(actual_submittal_items[0].submittal_description, 'Product Data')
        self.assertEqual(actual_submittal_items[0].submittal_content, 'Product Data:  Submit preprinted data for each type of manufactured material')
        # check that submittal numbers were assigned as expected
        for index, expected_paragraph_number in enumerate(expected_paragraph_numbers_in_order):
            expected_submittal_number = index + 1
            submittal_item = actual_submittal_items.filter(paragraph_number=expected_paragraph_number).first()
            self.assertEqual(int(submittal_item.submittal_number), expected_submittal_number)
            self.assertEqual(submittal_item.paragraph_number, expected_paragraph_number)

        for placeholder_submittal_item in submittal_items.filter(parsing_method='PLACEHOLDER'):
            self.assertEqual(placeholder_submittal_item.submittal_type, 'N/A')
            self.assertEqual(placeholder_submittal_item.submittal_description, 'N/A')
            self.assertEqual(placeholder_submittal_item.submittal_content, 'Unable to extract submittals from text')
            self.assertEqual(placeholder_submittal_item.submittal_number, None)

        # check that get submittal items API returns the submittal items in the correct order
        url = reverse('submittal-item-list', kwargs={'project_id': self.project.id})
        print(url)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print([submittal_item['spec_section'] for submittal_item in response.data['message']])
        self.assertEqual(len(response.data['message']), 53 + 3) # 3 placeholder sections plus 53 actual submittals

        for index, submittal_item in enumerate(response.data['message']):
            if index < 53:
                self.assertEqual(submittal_item['spec_section'], section_number_to_have_actual_submittals)
                displayed_submittal_number = submittal_item['submittal_number']
                if displayed_submittal_number.endswith('.0'):
                    displayed_submittal_number = displayed_submittal_number[:-2]
                self.assertEqual(submittal_item['para_no'], expected_paragraph_numbers_in_order[index])
                self.assertEqual(int(displayed_submittal_number), index + 1)
        placeholder_submittal_items = response.data['message'][53:]
        master_format_section_numbers = [submittal_item['spec_section'] for submittal_item in placeholder_submittal_items]
        self.assertEqual(master_format_section_numbers, ["033001", "033002", "033004"])

    @skip("Skipping this test for now, keeps causing weird issues with the other tests in this file")
    @patch('apps.deliverables.views.is_versioning_feature_flag_active', return_value=True)
    @patch('apps.deliverables.views.parse_spec')
    def test_spec_status_webhook_end_to_end_success_with_multiple_versions(self, mock_parse_spec, mock_is_versioning_feature_flag_active):
        def simulate_end_to_end_success_with_version(project_version_id: int):
            mock_file = SimpleUploadedFile(
                name='test_file.txt',
                content=b'This is some test file content',
                content_type='text/plain'
            )
            upload_response = self.client.post(reverse('deliverables:upload_file'), {
                'project_id': self.project.id,
                'files': [mock_file],
                'project_version_id': project_version_id,
            })
            self.assertEqual(upload_response.status_code, status.HTTP_200_OK)
            uploaded_file = UploadedFile.objects.get(project=self.project, project_version=project_version_id)
            self.assertEqual(uploaded_file.processing_status, 'PENDING_PROCESSING')
            self.assertEqual(uploaded_file.project_version.id, project_version_id)

            # Update test data to use correct IDs
            sample_processing_webhook['document_id'] = uploaded_file.id
            sample_processing_webhook['project_id'] = self.project.id
            sample_processing_webhook['user_id'] = self.user.id
            sample_processing_webhook['project_version_id'] = project_version_id
            sample_subsections_extracted_webhook['document_id'] = uploaded_file.id
            sample_subsections_extracted_webhook['project_id'] = self.project.id
            sample_subsections_extracted_webhook['user_id'] = self.user.id
            sample_subsections_extracted_webhook['project_version_id'] = project_version_id
            sample_processed_section_webhook['document_id'] = uploaded_file.id
            sample_processed_section_webhook['project_id'] = self.project.id
            sample_processed_section_webhook['user_id'] = self.user.id
            sample_processed_section_webhook['project_version_id'] = project_version_id
        

            # Simulate receiving the processing webhook
            response = self.client.post(self.webhook_url, data=json.dumps(sample_processing_webhook), content_type='application/json')
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


        def check_submittal_items_for_version(project_version_id: int):
            submittal_items = SubmittalItem.objects.filter(project=self.project, project_version=project_version_id).order_by('heirarchical_paragraph_number')

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
                # check that the project version is the given project version
                self.assertEqual(submittal_item.project_version.id, project_version_id)

            # check that get submittal items API returns the submittal items in the correct order
            url = reverse('submittal-item-list', kwargs={'project_id': self.project.id}) + '?project_version_id=' + str(project_version_id)
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(response.data['message']), 53)

            for index, submittal_item in enumerate(response.data['message']):
                displayed_submittal_number = submittal_item['submittal_number']
                if displayed_submittal_number.endswith('.0'):
                    displayed_submittal_number = displayed_submittal_number[:-2]
                self.assertEqual(submittal_item['para_no'], expected_paragraph_numbers_in_order[index])
                self.assertEqual(int(displayed_submittal_number), index + 1)

        project_version_2 = ProjectVersion.objects.create(project=self.project, version_number=2, version_name="Version 2")
        project_version_3 = ProjectVersion.objects.create(project=self.project, version_number=3, version_name="Version 3")
        # Upload a file to project version 1 and then to project version 2
        simulate_end_to_end_success_with_version(self.default_project_version.id)
        simulate_end_to_end_success_with_version(project_version_2.id)


        # check that the submittal items were created as expected
        check_submittal_items_for_version(self.default_project_version.id)
        check_submittal_items_for_version(project_version_2.id)




