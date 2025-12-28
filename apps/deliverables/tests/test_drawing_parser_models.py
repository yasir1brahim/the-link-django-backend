from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.teams.models import Team
from apps.deliverables.models import (
    Project,
    DrawingFile,
    DrawingExtractionStatus,
    DrawingPageType,
    DrawingPageExtractionStatus,
)

User = get_user_model()


class TestDrawingFileModel(TestCase):
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

    def test_drawing_file_creation(self):
        """Test basic DrawingFile creation"""
        drawing_file = DrawingFile.objects.create(
            project=self.project,
            project_version=self.project_version,
            uploaded_by=self.user,
            file_name="Mechanical IFC Set.pdf",
            file_s3_key="drawings/project_1__version_1__123456_Mechanical.pdf",
            md5="abc123def456",
            total_pages=23,
        )

        self.assertEqual(drawing_file.file_name, "Mechanical IFC Set.pdf")
        self.assertEqual(drawing_file.project, self.project)
        self.assertEqual(drawing_file.project_version, self.project_version)
        self.assertEqual(drawing_file.uploaded_by, self.user)
        self.assertIsNotNone(drawing_file.created_at)

    def test_extraction_status_enum_values(self):
        """Test DrawingExtractionStatus enum has expected values"""
        self.assertEqual(DrawingExtractionStatus.PENDING, "PENDING")
        self.assertEqual(DrawingExtractionStatus.PROCESSING, "PROCESSING")
        self.assertEqual(DrawingExtractionStatus.SUCCESS, "SUCCESS")
        self.assertEqual(DrawingExtractionStatus.PARTIAL_SUCCESS, "PARTIAL_SUCCESS")
        self.assertEqual(DrawingExtractionStatus.FAILED, "FAILED")

    def test_page_type_enum_values(self):
        """Test DrawingPageType enum has expected values"""
        self.assertEqual(DrawingPageType.DRAWING, "drawing")
        self.assertEqual(DrawingPageType.SPEC, "spec")

    def test_page_extraction_status_enum_values(self):
        """Test DrawingPageExtractionStatus enum has expected values"""
        self.assertEqual(DrawingPageExtractionStatus.SUCCESS, "success")
        self.assertEqual(DrawingPageExtractionStatus.NO_NOTES_FOUND, "no_notes_found")
        self.assertEqual(DrawingPageExtractionStatus.FAILED, "failed")
