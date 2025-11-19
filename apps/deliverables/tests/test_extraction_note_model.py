# apps/deliverables/tests/test_extraction_note_model.py
import pytest
from django.test import TestCase
from apps.deliverables.models import ExtractedData, ExtractionNote, AiGeneratedLog, Project, ProjectVersion, ExtractionSource, CustomItemType
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class TestExtractionNoteModel(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('test@example.com')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(name="Test Project", team=self.team, created_by=self.user)
        self.version = self.project.versions.first()
        self.custom_item_type = CustomItemType.objects.create(
            project=self.project,
            name="Test Highlight Type",
            color="#FF0000"
        )
        self.extracted_data = ExtractedData.objects.create(
            project=self.project,
            project_version=self.version,
            spec_section_number="01 1000",
            spec_section_name="General Requirements",
            extraction_type="custom_highlights",
            custom_item_type=self.custom_item_type,
            requirement_text="Test requirement",
            source=ExtractionSource.HUMAN,
            created_by=self.user
        )

    def test_note_creation(self):
        """Test basic note creation"""
        note = ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="This is a test note",
            created_by=self.user
        )

        self.assertEqual(note.text, "This is a test note")
        self.assertEqual(note.created_by, self.user)
        self.assertEqual(note.extracted_data, self.extracted_data)
        self.assertIsNotNone(note.created_at)
        self.assertIsNotNone(note.updated_at)
