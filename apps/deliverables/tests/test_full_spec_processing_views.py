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
from apps.deliverables.models import UploadedFile, SemanticallyProcessedSpecItem, DocProcessingStatus, SpecSection

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
        
        

class SubmittalItemViewSetTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.User = get_user_model()

        self.user = self.User.objects.create_user(
            username='user1', 
            password='password123'
        )
        self.non_member = self.User.objects.create_user(
            username='non_member', 
            password='password123'
        )
        self.superuser = self.User.objects.create_superuser(username='superuser', password='password123')
        self.team = Team.objects.create(name='Team 1', slug='team-1')
        TeamMembership.objects.create(
            user=self.user,
            team=self.team,
            role=ROLE_MEMBER
        )

        self.project = Project.objects.create(
            name='Project 1',
            team=self.team,
        )
        self.project_version_1 = ProjectVersion.objects.get(project=self.project)
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ROLE_PROJECT_MEMBER
        )
        self.masterformat_section = MasterFormatSection.objects.create(masterformat_number='033000')

        self.spec_item = SemanticallyProcessedSpecItem.objects.create(
            project=self.project,
            masterformat_section=self.masterformat_section,
            parsing_method='PLACEHOLDER',
            project_version=self.project_version_1,
            topic='Test Topic',
            item_type='Test Item Type',
            item_content='Test Item Content',
        )
        self.document = UploadedFile.objects.create(
            project=self.project,
            project_version=self.project_version_1,
            uploaded_by=self.user,
            document_path='test_file.txt',
            md5='1234567890',
            processing_status=DocProcessingStatus.PROCESSED,
        )
        self.document2 = UploadedFile.objects.create(
            project=self.project,
            project_version=self.project_version_1,
            uploaded_by=self.user,
            document_path='test_file2.txt',
            md5='1234567890',
        )
        self.list_url = reverse('semantically-processed-spec-item-list', kwargs={'project_id': self.project.id})

    def test_user_can_see_submittal_items_for_their_project(self):
        """Test that users can see submittal items for their project"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print(f"response.data: {response.data}")
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], self.spec_item.id)

    def test_superuser_can_see_submittal_items_for_project(self):
        """Test that a superuser can see submittal items for a project"""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], self.spec_item.id)

    def test_user_cannot_see_submittal_items_for_other_projects(self):
        """Test that users cannot see submittal items for projects they are not a member of"""
        self.client.force_authenticate(user=self.non_member)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_submittal_item_list_returns_correct_parsing_method(self):
        """Test that the submittal item list returns the correct parsing method"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['parsing_method'], 'PLACEHOLDER')

    def set_up_test_data(self):
        # Create MasterFormatSections
        mf1 = MasterFormatSection.objects.create(masterformat_number="033001")
        mf2 = MasterFormatSection.objects.create(masterformat_number="033002")
        mf3 = MasterFormatSection.objects.create(masterformat_number="033003")
        mf4 = MasterFormatSection.objects.create(masterformat_number="033004")
        
        # Create SpecSections with different processing methods
        spec1 = SpecSection.objects.create(
            masterformat_section=mf1,
            document=self.document,
            processing_method=SpecSection.ProcessingMethod.REGEX_UNABLE_TO_DETECT
        )
        spec2 = SpecSection.objects.create(
            masterformat_section=mf2,
            document=self.document,
            processing_method=SpecSection.ProcessingMethod.REGEX_SUCCESS
        )
        spec3 = SpecSection.objects.create(
            masterformat_section=mf3,
            document=self.document,
            processing_method=SpecSection.ProcessingMethod.REGEX_SUCCESS
        )
        spec4 = SpecSection.objects.create(
            masterformat_section=mf4,
            document=self.document2,
            processing_method=SpecSection.ProcessingMethod.REGEX_UNABLE_TO_DETECT
        )

        # Create SemanticallyProcessedSpecItems in non-ordered sequence
        SemanticallyProcessedSpecItem.objects.create(
            project=self.project,
            document=self.document,
            masterformat_section=mf2,
            spec_section=spec2,
            paragraph_number="2.1",
            project_version=self.project_version_1,
            topic='Test Topic',
            item_type='Test Item Type',
            item_content='Test Item Content',
        )
        SemanticallyProcessedSpecItem.objects.create(
            project=self.project,
            document=self.document,
            masterformat_section=mf1,
            spec_section=spec1,
            paragraph_number="1.1",
            project_version=self.project_version_1,
            topic='Test Topic',
            item_type='Test Item Type',
            item_content='Test Item Content',
        )
        SemanticallyProcessedSpecItem.objects.create(
            project=self.project,
            document=self.document,
            masterformat_section=mf1,
            spec_section=spec1,
            paragraph_number="1.2",
            project_version=self.project_version_1,
            topic='Test Topic',
            item_type='Test Item Type',
            item_content='Test Item Content',
        )
        SemanticallyProcessedSpecItem.objects.create(
            project=self.project,
            document=self.document,
            masterformat_section=mf3,
            spec_section=spec3,
            paragraph_number="3.1",
            project_version=self.project_version_1,
            topic='Test Topic',
            item_type='Test Item Type',
            item_content='Test Item Content',
        )
        SemanticallyProcessedSpecItem.objects.create(
            project=self.project,
            document=self.document2,
            masterformat_section=mf4,
            spec_section=spec4,
            paragraph_number="4.1",
            project_version=self.project_version_1,
            topic='Test Topic',
            item_type='Test Item Type',
            item_content='Test Item Content',
        )
        SemanticallyProcessedSpecItem.objects.create(
            project=self.project,
            document=self.document2,
            masterformat_section=mf4,
            spec_section=spec4,
            paragraph_number="4.2",
            project_version=self.project_version_1,
            topic='Test Topic',
            item_type='Test Item Type',
            item_content='Test Item Content',
        )

    def test_default_ordering(self):
        self.set_up_test_data()

        # Make API request
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)
        
        # Verify response status
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify ordering
        results = response.data['results']
        
        # Items should be ordered by:
        # 1. Masterformat number (051200 before 052100)

        self.assertEqual(results[0]['spec_section'], "033000")
        # self.assertEqual(results[0]['paragraph_number'], '')

        self.assertEqual(results[1]['spec_section'], "033001")
        # self.assertEqual(results[1]['paragraph_number'], "1.1")

        self.assertEqual(results[2]['spec_section'], "033001")
        # self.assertEqual(results[2]['paragraph_number'], "1.2")
        
        self.assertEqual(results[3]['spec_section'], "033002")
        # self.assertEqual(results[3]['paragraph_number'], "2.1")
        
        self.assertEqual(results[4]['spec_section'], "033003")
        # self.assertEqual(results[4]['paragraph_number'], "3.1")


        self.assertEqual(results[5]['spec_section'], "033004")
        # self.assertEqual(results[5]['paragraph_number'], "4.1")

        self.assertEqual(results[6]['spec_section'], "033004")
        # self.assertEqual(results[6]['paragraph_number'], "4.2")
        
