from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from apps.teams.models import Team, Flag
from apps.deliverables.models import (
    Project,
    ProjectVersion,
    SpecSection,
    SubmittalItem,
    MasterFormatSection,
    UploadedFile,
    ProjectMembership,
    AiGeneratedLog,
    ExtractedData,
    ExtractionSource,
)
from apps.deliverables.constants import ROLE_PROJECT_MEMBER
from apps.utils.feature_flags import is_spec_centered_view_feature_flag_active
from apps.deliverables.serializers.spec_centric_serializers import SpecSectionContentSerializer

User = get_user_model()


class SpecCentricViewTests(APITestCase):
    """Test cases for spec centric view API endpoints."""
    
    def setUp(self):
        """Set up test data."""
        # Create test user
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        
        # Create test team
        self.team = Team.objects.create(
            name='Test Team',
            created_by=self.user
        )
        
        # Create test project
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team,
            created_by=self.user
        )
        
        # Add user to project
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ROLE_PROJECT_MEMBER
        )
        
        # Create test project version
        self.project_version = ProjectVersion.objects.create(
            project=self.project,
            version_number='1.0',
            created_by=self.user
        )
        
        # Create test master format section
        self.masterformat_section = MasterFormatSection.objects.create(
            masterformat_number='03 30 00',
            title='Cast-in-Place Concrete'
        )
        
        # Create test uploaded file
        self.uploaded_file = UploadedFile.objects.create(
            name='test_spec.pdf',
            project=self.project,
            project_version=self.project_version,
            uploaded_by=self.user,
            file_s3_key='test/spec.pdf'
        )
        
        # Create test spec section
        self.spec_section = SpecSection.objects.create(
            masterformat_section=self.masterformat_section,
            document=self.uploaded_file,
            processing_status='COMPLETED',
            processing_method='REGEX_SUCCESS'
        )
        
        # Create test submittal item
        self.submittal_item = SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version,
            document=self.uploaded_file,
            masterformat_section=self.masterformat_section,
            spec_section=self.spec_section,
            paragraph_number='3.1.1',
            heirarchical_paragraph_number='3.1.1',
            text_location={'page': 1, 'x': 100, 'y': 200},
            parsing_method='REGEX',
            parsing_version='1.0'
        )
        
        # Create feature flag
        self.feature_flag = Flag.objects.create(
            name='spec_centered_view',
            everyone=True  # Enable for everyone in tests
        )
        
        # Authenticate user
        self.client.force_authenticate(user=self.user)
    
    def test_get_spec_sections_success(self):
        """Test getting spec sections successfully."""
        url = reverse('deliverables:spec-section-list', kwargs={'project_pk': self.project.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('spec_sections', response.data)
        self.assertIn('total_sections', response.data)
        self.assertEqual(response.data['total_sections'], 1)
    
    def test_get_spec_sections_with_version_filter(self):
        """Test getting spec sections with project version filter."""
        url = reverse('deliverables:spec-section-list', kwargs={'project_pk': self.project.id})
        response = self.client.get(url, {'project_version_id': self.project_version.id})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['project_version_id'], str(self.project_version.id))
    
    def test_get_spec_section_content_success(self):
        """Test getting spec section content successfully."""
        url = reverse('deliverables:spec-section-detail', kwargs={
            'project_pk': self.project.id, 
            'pk': self.spec_section.id
        })
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('spec_section', response.data)
        self.assertIn('submittal_highlights', response.data)
    
    def test_get_submittal_highlights_success(self):
        """Test getting submittal highlights successfully."""
        url = reverse('deliverables:spec-section-submittal-highlights', kwargs={
            'project_pk': self.project.id, 
            'pk': self.spec_section.id
        })
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.submittal_item.id)
    
    def test_get_spec_centric_data_success(self):
        """Test getting comprehensive spec centric data successfully."""
        url = reverse('deliverables:spec-section-spec-centric-data', kwargs={
            'project_pk': self.project.id
        })
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('spec_sections', response.data)
        self.assertIn('total_sections', response.data)
        self.assertIn('project_id', response.data)
    
    def test_feature_flag_disabled(self):
        """Test that endpoints return 403 when feature flag is disabled."""
        # Disable the feature flag
        self.feature_flag.everyone = False
        self.feature_flag.save()
        
        url = reverse('deliverables:spec-section-list', kwargs={'project_pk': self.project.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('error', response.data)
        self.assertIn('not enabled', response.data['error'])
    
    def test_unauthorized_access(self):
        """Test that unauthenticated users cannot access endpoints."""
        self.client.logout()
        
        url = reverse('deliverables:spec-section-list', kwargs={'project_pk': self.project.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_non_member_access(self):
        """Test that non-project members cannot access endpoints."""
        # Create another user who is not a project member
        other_user = User.objects.create_user(
            email='other@example.com',
            password='testpass123',
            first_name='Other',
            last_name='User'
        )
        
        # Authenticate as the other user
        self.client.force_authenticate(user=other_user)
        
        url = reverse('deliverables:spec-section-list', kwargs={'project_pk': self.project.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_nonexistent_project(self):
        """Test that 404 is returned for nonexistent project."""
        url = reverse('deliverables:spec-section-list', kwargs={'project_pk': 99999})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_nonexistent_spec_section(self):
        """Test that 404 is returned for nonexistent spec section."""
        url = reverse('deliverables:spec-section-detail', kwargs={
            'project_pk': self.project.id, 
            'pk': 99999
        })
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class SpecSectionContentSerializerTests(TestCase):
    """Unit tests for SpecSectionContentSerializer data filtering."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='serializer@example.com',
            password='testpass123',
            first_name='Serializer',
            last_name='User'
        )

        self.team = Team.objects.create(
            name='Serializer Team',
            created_by=self.user
        )

        self.project = Project.objects.create(
            name='Serializer Project',
            project_number='SP-001',
            team=self.team,
            created_by=self.user
        )

        self.project_version = ProjectVersion.objects.create(
            project=self.project,
            version_number=1,
            version_name='Version 1',
            created_by=self.user
        )

        self.masterformat_section = MasterFormatSection.objects.create(
            masterformat_number='01 00 00',
            masterformat_description='General Requirements'
        )

        self.uploaded_file = UploadedFile.objects.create(
            project=self.project,
            project_version=self.project_version,
            uploaded_by=self.user,
            document_path='specs/test.pdf',
            parsed_document_path='specs/test.pdf',
            name='test.pdf',
            md5='dummy-md5',
            processing_status='PROCESSED',
            file_s3_key='specs/test.pdf'
        )

        self.spec_section = SpecSection.objects.create(
            masterformat_section=self.masterformat_section,
            document=self.uploaded_file,
            custom_section_title='General Requirements',
            processing_status='PROCESSED',
            processing_method=SpecSection.ProcessingMethod.REGEX_SUCCESS
        )

        self.serializer = SpecSectionContentSerializer()

    def test_get_ai_log_highlights_only_returns_latest_ai_log_per_type(self):
        """Ensure only the most recent AI log per type contributes highlights."""
        older_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='qa_planner',
            log_status='COMPLETED',
            created_by=self.user
        )

        newer_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.project_version,
            log_type='qa_planner',
            log_status='COMPLETED',
            created_by=self.user
        )

        ExtractedData.objects.create(
            ai_generated_log=older_log,
            project=self.project,
            project_version=self.project_version,
            spec_section=self.spec_section,
            source=ExtractionSource.AI,
            extraction_type='qa_planner',
            item_type='inspections',
            spec_section_number='01 00 00',
            spec_section_name='General Requirements',
            requirement_text='Older AI requirement',
            pdf_locations=[{
                'page_no': 1,
                'x': 10,
                'y': 20,
                'width': 100,
                'height': 20
            }],
            metadata={}
        )

        ExtractedData.objects.create(
            ai_generated_log=newer_log,
            project=self.project,
            project_version=self.project_version,
            spec_section=self.spec_section,
            source=ExtractionSource.AI,
            extraction_type='qa_planner',
            item_type='inspections',
            spec_section_number='01 00 00',
            spec_section_name='General Requirements',
            requirement_text='Newer AI requirement',
            pdf_locations=[{
                'page_no': 1,
                'x': 15,
                'y': 25,
                'width': 110,
                'height': 25
            }],
            metadata={}
        )

        ExtractedData.objects.create(
            ai_generated_log=None,
            project=self.project,
            project_version=self.project_version,
            spec_section=self.spec_section,
            source=ExtractionSource.HUMAN,
            extraction_type='manual_highlight',
            item_type=None,
            spec_section_number='01 00 00',
            spec_section_name='General Requirements',
            requirement_text='Manual requirement',
            pdf_locations=[{
                'page_no': 2,
                'x': 5,
                'y': 30,
                'width': 120,
                'height': 18
            }],
            metadata={}
        )

        highlights = self.serializer.get_ai_log_highlights(self.spec_section)

        self.assertEqual(len(highlights), 2)
        requirement_texts = {item['requirement_text'] for item in highlights}
        self.assertIn('Newer AI requirement', requirement_texts)
        self.assertIn('Manual requirement', requirement_texts)
        self.assertNotIn('Older AI requirement', requirement_texts)
