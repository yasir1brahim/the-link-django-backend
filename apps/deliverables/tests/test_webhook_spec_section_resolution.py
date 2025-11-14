from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.deliverables.models import (
    Project, ProjectVersion, AiGeneratedLog, ExtractedData,
    SpecSection, MasterFormatSection, UploadedFile
)
from apps.teams.models import Team
from apps.deliverables.views.specgpt_views import _fuzzy_match_spec_section, _create_extracted_data_from_log

User = get_user_model()


class TestFuzzyMatchSpecSection(TestCase):
    """Tests for _fuzzy_match_spec_section helper function"""

    def setUp(self):
        self.user = User.objects.create_user('test@example.com')
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team,
            created_by=self.user
        )
        # Project automatically creates Version 1 on save
        self.version = self.project.versions.first()

        # Create uploaded file
        self.document = UploadedFile.objects.create(
            name='Test Spec.pdf',
            project=self.project,
            project_version=self.version
        )

        # Create masterformat sections with various formats
        self.masterformat_01 = MasterFormatSection.objects.create(
            masterformat_number='01 1000',
            masterformat_description='General Requirements'
        )
        self.masterformat_03 = MasterFormatSection.objects.create(
            masterformat_number='03 3000',
            masterformat_description='Concrete'
        )
        self.masterformat_09 = MasterFormatSection.objects.create(
            masterformat_number='09-6000',
            masterformat_description='Flooring'
        )

        # Create spec sections
        self.spec_01 = SpecSection.objects.create(
            document=self.document,
            masterformat_section=self.masterformat_01
        )
        self.spec_03 = SpecSection.objects.create(
            document=self.document,
            masterformat_section=self.masterformat_03
        )
        self.spec_09 = SpecSection.objects.create(
            document=self.document,
            masterformat_section=self.masterformat_09
        )

    def test_exact_match_with_spaces(self):
        """Test matching '01 1000' to '01 1000'"""
        result = _fuzzy_match_spec_section('01 1000', self.project.id, self.version.id)
        self.assertEqual(result, self.spec_01)

    def test_match_without_spaces(self):
        """Test matching '011000' to '01 1000'"""
        result = _fuzzy_match_spec_section('011000', self.project.id, self.version.id)
        self.assertEqual(result, self.spec_01)

    def test_match_with_different_separator(self):
        """Test matching '09-6000' to '09 6000'"""
        result = _fuzzy_match_spec_section('09-6000', self.project.id, self.version.id)
        self.assertEqual(result, self.spec_09)

    def test_match_with_extra_spaces(self):
        """Test matching '03  3000' to '03 3000'"""
        result = _fuzzy_match_spec_section('03  3000', self.project.id, self.version.id)
        self.assertEqual(result, self.spec_03)

    def test_no_match_returns_none(self):
        """Test that non-existent section returns None"""
        result = _fuzzy_match_spec_section('99 9999', self.project.id, self.version.id)
        self.assertIsNone(result)

    def test_empty_string_returns_none(self):
        """Test that empty string returns None"""
        result = _fuzzy_match_spec_section('', self.project.id, self.version.id)
        self.assertIsNone(result)

    def test_none_returns_none(self):
        """Test that None returns None"""
        result = _fuzzy_match_spec_section(None, self.project.id, self.version.id)
        self.assertIsNone(result)

    def test_project_isolation(self):
        """Test that matching is isolated to the correct project"""
        # Create another project with same masterformat section
        other_project = Project.objects.create(
            name='Other Project',
            team=self.team,
            created_by=self.user
        )
        other_version = other_project.versions.first()
        other_document = UploadedFile.objects.create(
            name='Other Spec.pdf',
            project=other_project,
            project_version=other_version
        )
        other_spec = SpecSection.objects.create(
            document=other_document,
            masterformat_section=self.masterformat_01
        )

        # Should match the spec from the correct project
        result = _fuzzy_match_spec_section('01 1000', self.project.id)
        self.assertEqual(result, self.spec_01)
        self.assertNotEqual(result, other_spec)


class TestWebhookExtractedDataCreation(TestCase):
    """Tests for _create_extracted_data_from_log function"""

    def setUp(self):
        self.user = User.objects.create_user('test@example.com')
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team,
            created_by=self.user
        )
        # Project automatically creates Version 1 on save
        self.version = self.project.versions.first()

        # Create uploaded file
        self.document = UploadedFile.objects.create(
            name='Test Spec.pdf',
            project=self.project,
            project_version=self.version
        )

        # Create masterformat section and spec section
        self.masterformat = MasterFormatSection.objects.create(
            masterformat_number='03 3000',
            masterformat_description='Concrete'
        )
        self.spec_section = SpecSection.objects.create(
            document=self.document,
            masterformat_section=self.masterformat
        )

    def test_creates_extracted_data_with_spec_section(self):
        """Test that ExtractedData is created with correct spec_section FK"""
        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='inspection_log',
            log_status='SUCCESS',
            created_by=self.user,
            log_data=[
                {
                    'Spec Section #': '03 3000',
                    'Spec Section Name': 'Concrete',
                    'Inspection Type And Requirements': 'Test inspection',
                    'pdf_locations': [{'page': 1, 'rects': [[0, 0, 100, 100]]}]
                }
            ]
        )

        _create_extracted_data_from_log(ai_log)

        # Verify ExtractedData was created
        extracted = ExtractedData.objects.filter(ai_generated_log=ai_log).first()
        self.assertIsNotNone(extracted)
        self.assertEqual(extracted.spec_section, self.spec_section)
        self.assertEqual(extracted.spec_section_number, '03 3000')
        self.assertEqual(extracted.source, 'AI')

    def test_creates_multiple_items(self):
        """Test creating multiple ExtractedData items from one log"""
        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='inspection_log',
            log_status='SUCCESS',
            created_by=self.user,
            log_data=[
                {
                    'Spec Section #': '03 3000',
                    'Spec Section Name': 'Concrete',
                    'Inspection Type And Requirements': 'Test 1',
                    'pdf_locations': [{'page': 1, 'rects': [[0, 0, 100, 100]]}]
                },
                {
                    'Spec Section #': '033000',  # Different format
                    'Spec Section Name': 'Concrete',
                    'Inspection Type And Requirements': 'Test 2',
                    'pdf_locations': [{'page': 2, 'rects': [[0, 0, 100, 100]]}]
                }
            ]
        )

        _create_extracted_data_from_log(ai_log)

        # Verify both items were created
        extracted_items = ExtractedData.objects.filter(ai_generated_log=ai_log)
        self.assertEqual(extracted_items.count(), 2)

        # Both should have the same spec_section
        for item in extracted_items:
            self.assertEqual(item.spec_section, self.spec_section)

    def test_handles_no_match_gracefully(self):
        """Test that items without matching spec_section are still created"""
        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='inspection_log',
            log_status='SUCCESS',
            created_by=self.user,
            log_data=[
                {
                    'Spec Section #': '99 9999',  # Non-existent
                    'Spec Section Name': 'Unknown',
                    'Inspection Type And Requirements': 'Test',
                    'pdf_locations': [{'page': 1, 'rects': [[0, 0, 100, 100]]}]
                }
            ]
        )

        _create_extracted_data_from_log(ai_log)

        # Verify item was created without spec_section
        extracted = ExtractedData.objects.filter(ai_generated_log=ai_log).first()
        self.assertIsNotNone(extracted)
        self.assertIsNone(extracted.spec_section)
        self.assertEqual(extracted.spec_section_number, '99 9999')

    def test_replaces_existing_extracted_data(self):
        """Test that calling function again replaces old ExtractedData"""
        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='inspection_log',
            log_status='SUCCESS',
            created_by=self.user,
            log_data=[
                {
                    'Spec Section #': '03 3000',
                    'Spec Section Name': 'Concrete',
                    'Inspection Type And Requirements': 'Original',
                    'pdf_locations': [{'page': 1, 'rects': [[0, 0, 100, 100]]}]
                }
            ]
        )

        # Create first time
        _create_extracted_data_from_log(ai_log)
        first_count = ExtractedData.objects.filter(ai_generated_log=ai_log).count()
        self.assertEqual(first_count, 1)

        # Update log data and create again
        ai_log.log_data = [
            {
                'Spec Section #': '03 3000',
                'Spec Section Name': 'Concrete',
                'Inspection Type And Requirements': 'Updated 1',
                'pdf_locations': [{'page': 1, 'rects': [[0, 0, 100, 100]]}]
            },
            {
                'Spec Section #': '03 3000',
                'Spec Section Name': 'Concrete',
                'Inspection Type And Requirements': 'Updated 2',
                'pdf_locations': [{'page': 2, 'rects': [[0, 0, 100, 100]]}]
            }
        ]
        ai_log.save()

        _create_extracted_data_from_log(ai_log)

        # Should have replaced with 2 new items
        final_count = ExtractedData.objects.filter(ai_generated_log=ai_log).count()
        self.assertEqual(final_count, 2)

        # Verify old data is gone
        self.assertFalse(
            ExtractedData.objects.filter(
                ai_generated_log=ai_log,
                requirement_text='Original'
            ).exists()
        )
