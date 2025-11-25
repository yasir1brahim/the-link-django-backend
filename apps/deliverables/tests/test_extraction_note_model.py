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

    def test_multiple_notes_per_extraction(self):
        """Test that ExtractedData can have multiple notes"""
        note1 = ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="First note",
            created_by=self.user
        )
        note2 = ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="Second note",
            created_by=self.user
        )

        notes = self.extracted_data.notes.all()
        self.assertEqual(notes.count(), 2)
        self.assertEqual(notes[0].text, "First note")
        self.assertEqual(notes[1].text, "Second note")

    def test_cascade_delete_with_extracted_data(self):
        """Test that notes are deleted when ExtractedData is deleted"""
        note = ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="Will be deleted",
            created_by=self.user
        )
        note_id = note.id

        self.extracted_data.delete()

        self.assertFalse(ExtractionNote.objects.filter(id=note_id).exists())

    def test_set_null_on_user_delete(self):
        """Test that notes persist when user is deleted"""
        # Create a separate user for the note (not the project owner)
        note_user = User.objects.create_user('noteuser@example.com')
        note = ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="Note from deleted user",
            created_by=note_user
        )
        note_id = note.id

        note_user.delete()

        note.refresh_from_db()
        self.assertIsNone(note.created_by)
        self.assertEqual(note.text, "Note from deleted user")

    def test_notes_ordered_by_created_at(self):
        """Test that notes are ordered chronologically"""
        import time
        note1 = ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="First",
            created_by=self.user
        )
        time.sleep(0.01)  # Ensure different timestamps
        note2 = ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="Second",
            created_by=self.user
        )
        time.sleep(0.01)
        note3 = ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="Third",
            created_by=self.user
        )

        notes = list(self.extracted_data.notes.all())
        self.assertEqual(len(notes), 3)
        self.assertEqual(notes[0].text, "First")
        self.assertEqual(notes[1].text, "Second")
        self.assertEqual(notes[2].text, "Third")
