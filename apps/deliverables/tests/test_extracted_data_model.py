import pytest
from django.test import TestCase
from apps.deliverables.models import ExtractedData, AiGeneratedLog, Project, ProjectVersion, ExtractionSource
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()

class TestExtractedDataModel(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('test@example.com')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(name="Test Project", team=self.team, created_by=self.user)
        # Project automatically creates Version 1 on save
        self.version = self.project.versions.first()
        self.ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type="inspection_log",
            log_status="SUCCESS"
        )

    def test_extracted_data_creation(self):
        """Test basic ExtractedData model creation from AI"""
        extracted = ExtractedData.objects.create(
            ai_generated_log=self.ai_log,
            project=self.project,
            project_version=self.version,
            spec_section_number="03 3000",
            spec_section_name="Concrete",
            extraction_type="inspection_log",
            requirement_text="Visual inspection of formwork",
            responsible_party="QC Inspector",
            when_due="Daily",
            inspection_frequency="Daily",
            source="AI",
            created_by=self.user
        )

        self.assertEqual(extracted.spec_section_number, "03 3000")
        self.assertEqual(extracted.extraction_type, "inspection_log")
        self.assertEqual(extracted.source, "AI")
        self.assertEqual(extracted.created_by, self.user)

    def test_human_created_extraction(self):
        """Test human-created extraction via Apryse highlight"""
        extracted = ExtractedData.objects.create(
            project=self.project,
            project_version=self.version,
            spec_section_number="05 1000",
            spec_section_name="Metals",
            extraction_type="submittal",
            item_type="submittal",
            requirement_text="Manual entry by user via highlight",
            source="HUMAN",
            created_by=self.user,
            pdf_locations=[{'page': 5, 'x': 100, 'y': 200}]
        )

        self.assertEqual(extracted.source, "HUMAN")
        self.assertIsNone(extracted.ai_generated_log)  # No AI log for human entries
        self.assertEqual(extracted.created_by, self.user)
        self.assertEqual(extracted.item_type, "submittal")

    def test_item_type_categorization(self):
        """Test item_type field for categorizing extractions"""
        extracted = ExtractedData.objects.create(
            ai_generated_log=self.ai_log,
            project=self.project,
            project_version=self.version,
            spec_section_number="01 1000",
            spec_section_name="General",
            extraction_type="qa_planner",
            item_type="qa_warranty",
            requirement_text="Warranty requirements",
            source="AI",
            created_by=self.user
        )

        self.assertEqual(extracted.extraction_type, "qa_planner")
        self.assertEqual(extracted.item_type, "qa_warranty")
