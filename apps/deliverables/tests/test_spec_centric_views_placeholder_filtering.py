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
    ROLE_PROJECT_MEMBER,
)

User = get_user_model()


class SpecCentricViewPlaceholderFilteringTests(APITestCase):
    def setUp(self):
        """Set up test data."""
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        # Create test team
        self.team = Team.objects.create(
            name='Test Team',
            slug='test-team'
        )

        # Create test project
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team
        )

        # Add user to project
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ROLE_PROJECT_MEMBER
        )

        # Get the default project version (auto-created)
        self.project_version = ProjectVersion.objects.get(project=self.project)

        # Create test master format section
        self.masterformat_section = MasterFormatSection.objects.create(
            masterformat_number='033000'
        )

        # Create test uploaded file
        self.uploaded_file = UploadedFile.objects.create(
            project=self.project,
            project_version=self.project_version,
            uploaded_by=self.user,
            document_path='test_spec.pdf',
            md5='test123456'
        )

        # Create test spec section
        self.spec_section = SpecSection.objects.create(
            masterformat_section=self.masterformat_section,
            document=self.uploaded_file,
            processing_status='COMPLETED',
            processing_method='REGEX_SUCCESS'
        )

        # Create test submittal item (regular, not placeholder)
        self.submittal_item = SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version,
            document=self.uploaded_file,
            masterformat_section=self.masterformat_section,
            spec_section=self.spec_section,
            paragraph_number='3.1.1',
            submittal_type='Product Data',
            submittal_description='Concrete Mix Design',
            submittal_content='Submit mix design for approval',
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

    def test_retrieve_excludes_placeholder_submittals(self):
        """Test that retrieve method excludes placeholder submittals."""
        # Create a placeholder submittal item
        placeholder_submittal = SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version,
            masterformat_section=self.masterformat_section,
            spec_section=self.spec_section,
            paragraph_number='',
            submittal_type='N/A',
            submittal_description='N/A',
            submittal_content='Unable to extract submittals from text',
            parsing_method='PLACEHOLDER',
            parsing_version='1.0'
        )

        url = f'/api/deliverables/projects/{self.project.id}/spec-sections/{self.spec_section.id}/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('submittal_highlights', response.data)

        # Should only include the regular submittal, not the placeholder
        self.assertEqual(len(response.data['submittal_highlights']), 1)
        self.assertEqual(response.data['submittal_highlights'][0]['id'], self.submittal_item.id)

        # Verify placeholder is not in the results
        placeholder_ids = [item['id'] for item in response.data['submittal_highlights']]
        self.assertNotIn(placeholder_submittal.id, placeholder_ids)

    def test_get_submittal_highlights_excludes_placeholder_submittals(self):
        """Test that get_submittal_highlights method excludes placeholder submittals."""
        # Create a placeholder submittal item
        placeholder_submittal = SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version,
            masterformat_section=self.masterformat_section,
            spec_section=self.spec_section,
            paragraph_number='',
            submittal_type='N/A',
            submittal_description='N/A',
            submittal_content='Unable to extract submittals from text',
            parsing_method='PLACEHOLDER',
            parsing_version='1.0'
        )

        url = f'/api/deliverables/projects/{self.project.id}/spec-sections/{self.spec_section.id}/submittal-highlights/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

        # Should only include the regular submittal, not the placeholder
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.submittal_item.id)
        self.assertEqual(response.data[0]['parsing_method'], 'REGEX')

        # Verify placeholder is not in the results
        placeholder_ids = [item['id'] for item in response.data]
        self.assertNotIn(placeholder_submittal.id, placeholder_ids)

    def test_retrieve_shows_zero_submittals_when_only_placeholder_exists(self):
        """Test that retrieve returns empty list when only placeholder submittals exist."""
        # Delete the regular submittal
        self.submittal_item.delete()

        # Create only a placeholder submittal item
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version,
            masterformat_section=self.masterformat_section,
            spec_section=self.spec_section,
            paragraph_number='',
            submittal_type='N/A',
            submittal_description='N/A',
            submittal_content='Unable to extract submittals from text',
            parsing_method='PLACEHOLDER',
            parsing_version='1.0'
        )

        url = f'/api/deliverables/projects/{self.project.id}/spec-sections/{self.spec_section.id}/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('submittal_highlights', response.data)

        # Should return empty list since only placeholder exists
        self.assertEqual(len(response.data['submittal_highlights']), 0)

    def test_get_submittal_highlights_shows_zero_when_only_placeholder_exists(self):
        """Test that get_submittal_highlights returns empty list when only placeholder submittals exist."""
        # Delete the regular submittal
        self.submittal_item.delete()

        # Create only a placeholder submittal item
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version,
            masterformat_section=self.masterformat_section,
            spec_section=self.spec_section,
            paragraph_number='',
            submittal_type='N/A',
            submittal_description='N/A',
            submittal_content='Unable to extract submittals from text',
            parsing_method='PLACEHOLDER',
            parsing_version='1.0'
        )

        url = f'/api/deliverables/projects/{self.project.id}/spec-sections/{self.spec_section.id}/submittal-highlights/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

        # Should return empty list since only placeholder exists
        self.assertEqual(len(response.data), 0)

    def test_multiple_placeholder_submittals_all_excluded(self):
        """Test that multiple placeholder submittals are all excluded."""
        # Create multiple placeholder submittal items
        for i in range(3):
            SubmittalItem.objects.create(
                project=self.project,
                project_version=self.project_version,
                masterformat_section=self.masterformat_section,
                spec_section=self.spec_section,
                paragraph_number='',
                submittal_type='N/A',
                submittal_description='N/A',
                submittal_content=f'Unable to extract submittals from text {i}',
                parsing_method='PLACEHOLDER',
                parsing_version='1.0'
            )

        url = f'/api/deliverables/projects/{self.project.id}/spec-sections/{self.spec_section.id}/submittal-highlights/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

        # Should only include the 1 regular submittal, not the 3 placeholders
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.submittal_item.id)
        self.assertEqual(response.data[0]['parsing_method'], 'REGEX')

    def test_mixed_parsing_methods_only_placeholder_excluded(self):
        """Test that only PLACEHOLDER parsing_method is excluded, not other methods."""
        # Create submittals with different parsing methods
        regex_submittal = SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version,
            masterformat_section=self.masterformat_section,
            spec_section=self.spec_section,
            paragraph_number='3.1.2',
            submittal_type='Shop Drawings',
            submittal_description='Formwork Design',
            submittal_content='Submit formwork design',
            parsing_method='REGEX_SUBMITTAL',
            parsing_version='1.0'
        )

        ai_submittal = SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version,
            masterformat_section=self.masterformat_section,
            spec_section=self.spec_section,
            paragraph_number='3.1.3',
            submittal_type='Samples',
            submittal_description='Concrete Samples',
            submittal_content='Submit concrete samples',
            parsing_method='AI_EXTRACTED',
            parsing_version='1.0'
        )

        # Create a placeholder submittal
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version,
            masterformat_section=self.masterformat_section,
            spec_section=self.spec_section,
            paragraph_number='',
            submittal_type='N/A',
            submittal_description='N/A',
            submittal_content='Unable to extract submittals from text',
            parsing_method='PLACEHOLDER',
            parsing_version='1.0'
        )

        url = f'/api/deliverables/projects/{self.project.id}/spec-sections/{self.spec_section.id}/submittal-highlights/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

        # Should include all submittals except the placeholder (3 total)
        self.assertEqual(len(response.data), 3)

        # Verify all returned submittals are not placeholders
        for item in response.data:
            self.assertNotEqual(item['parsing_method'], 'PLACEHOLDER')

        # Verify the expected submittals are included
        returned_ids = [item['id'] for item in response.data]
        self.assertIn(self.submittal_item.id, returned_ids)
        self.assertIn(regex_submittal.id, returned_ids)
        self.assertIn(ai_submittal.id, returned_ids)
