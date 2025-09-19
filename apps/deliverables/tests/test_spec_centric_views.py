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
    ProjectMembership
)
from apps.deliverables.constants import ROLE_PROJECT_MEMBER
from apps.utils.feature_flags import is_spec_centered_view_feature_flag_active

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
