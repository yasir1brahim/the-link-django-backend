# apps/deliverables/tests/test_drawing_note_serializers.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.teams.models import Team
from apps.deliverables.models import (
    Project, DrawingFile, DrawingExtraction, DrawingPage,
    DrawingNoteSection, DrawingNote, DrawingExtractionStatus,
    DrawingPageType, DrawingPageExtractionStatus,
)
from apps.deliverables.serializers.drawing_serializers import DrawingNoteReadSerializer

User = get_user_model()


class TestDrawingNoteReadSerializer(TestCase):
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
        self.page = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=5,
            page_type=DrawingPageType.DRAWING,
            extraction_status=DrawingPageExtractionStatus.SUCCESS,
        )
        self.section = DrawingNoteSection.objects.create(
            page=self.page,
            header="GENERAL NOTES:",
        )
        self.note = DrawingNote.objects.create(
            section=self.section,
            note_number=1,
            category="GENERAL NOTES",
            text="All work shall comply with applicable codes.",
            bounding_box=[100.0, 300.0, 500.0, 350.0],
            drawing_references=[{"reference_text": "M702", "drawing_id": "M702"}],
        )

    def test_serializer_flattens_fields(self):
        """Test serializer flattens nested relationships for table display"""
        serializer = DrawingNoteReadSerializer(self.note)
        data = serializer.data

        self.assertEqual(data['id'], self.note.id)
        self.assertEqual(data['drawing_file_id'], self.drawing_file.id)
        self.assertEqual(data['drawing_file_name'], "Mechanical.pdf")
        self.assertEqual(data['page_number'], 5)
        self.assertEqual(data['section_header'], "GENERAL NOTES:")
        self.assertEqual(data['note_number'], 1)
        self.assertEqual(data['category'], "GENERAL NOTES")
        self.assertEqual(data['text'], "All work shall comply with applicable codes.")
        self.assertEqual(data['page_extraction_status'], "success")
        self.assertEqual(data['page_extraction_failed'], False)

    def test_serializer_includes_drawing_file_url(self):
        """Test serializer includes presigned URL for the drawing file"""
        serializer = DrawingNoteReadSerializer(self.note)
        data = serializer.data

        self.assertIn('drawing_file_url', data)
        # URL should be a presigned S3 URL containing the file key
        self.assertIn('drawings/test.pdf', data['drawing_file_url'])

    def test_serializer_page_extraction_failed_true(self):
        """Test page_extraction_failed is True when extraction failed"""
        self.page.extraction_status = DrawingPageExtractionStatus.FAILED
        self.page.save()

        serializer = DrawingNoteReadSerializer(self.note)
        data = serializer.data

        self.assertEqual(data['page_extraction_failed'], True)
