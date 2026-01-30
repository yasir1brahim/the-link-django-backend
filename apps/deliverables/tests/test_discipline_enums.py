# apps/deliverables/tests/test_discipline_enums.py
from django.test import TestCase
from apps.deliverables.models import (
    DrawingPage, DrawingFile, DrawingExtraction, DrawingExtractionStatus,
    DrawingPageType, DrawingPageExtractionStatus, Discipline, DisciplineConfidence,
    Project,
)
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class TestDisciplineEnum(TestCase):
    def test_discipline_enum_has_all_ncs_codes(self):
        """Test Discipline enum contains all 21 NCS discipline codes"""
        expected_values = {
            "general", "hazardous_materials", "survey_mapping", "geotechnical",
            "civil", "landscape", "structural", "architectural", "interiors",
            "equipment", "fire_protection", "plumbing", "process", "mechanical",
            "electrical", "distributed_energy", "telecommunications", "resource",
            "other", "contractor_shop", "operations"
        }
        actual_values = {choice.value for choice in Discipline}
        self.assertEqual(actual_values, expected_values)

    def test_discipline_confidence_enum_has_levels(self):
        """Test DisciplineConfidence enum has high/medium/low"""
        expected_values = {"high", "medium", "low"}
        actual_values = {choice.value for choice in DisciplineConfidence}
        self.assertEqual(actual_values, expected_values)


class TestDrawingPageDisciplineFields(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('test@example.com')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(
            name="Test Project",
            project_number="P-001",
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        self.drawing_file = DrawingFile.objects.create(
            project=self.project,
            project_version=self.project_version,
            file_name="Mechanical.pdf",
            file_s3_key="drawings/test.pdf",
            md5="abc123",
        )
        self.extraction = DrawingExtraction.objects.create(
            drawing_file=self.drawing_file,
            status=DrawingExtractionStatus.SUCCESS,
        )

    def test_drawing_page_has_sheet_discipline_field(self):
        """Test DrawingPage can store sheet_discipline"""
        page = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=1,
            page_type=DrawingPageType.DRAWING,
            extraction_status=DrawingPageExtractionStatus.SUCCESS,
            sheet_discipline=Discipline.MECHANICAL,
            sheet_discipline_confidence=DisciplineConfidence.HIGH,
        )
        page.refresh_from_db()
        self.assertEqual(page.sheet_discipline, Discipline.MECHANICAL)
        self.assertEqual(page.sheet_discipline_confidence, DisciplineConfidence.HIGH)

    def test_drawing_page_discipline_fields_nullable(self):
        """Test discipline fields are nullable"""
        page = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=1,
            page_type=DrawingPageType.DRAWING,
            extraction_status=DrawingPageExtractionStatus.SUCCESS,
            sheet_discipline=None,
            sheet_discipline_confidence=None,
        )
        page.refresh_from_db()
        self.assertIsNone(page.sheet_discipline)
        self.assertIsNone(page.sheet_discipline_confidence)
