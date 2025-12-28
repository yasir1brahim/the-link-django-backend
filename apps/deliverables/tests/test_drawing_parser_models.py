from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.teams.models import Team
from apps.deliverables.models import (
    Project,
    DrawingFile,
    DrawingExtraction,
    DrawingPage,
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


class TestDrawingExtractionModel(TestCase):
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
            uploaded_by=self.user,
            file_name="Mechanical IFC Set.pdf",
            file_s3_key="drawings/test.pdf",
            md5="abc123",
        )

    def test_extraction_creation(self):
        """Test DrawingExtraction creation"""
        extraction = DrawingExtraction.objects.create(
            drawing_file=self.drawing_file,
            status=DrawingExtractionStatus.PENDING,
        )

        self.assertEqual(extraction.drawing_file, self.drawing_file)
        self.assertEqual(extraction.status, DrawingExtractionStatus.PENDING)
        self.assertIsNone(extraction.started_at)
        self.assertIsNone(extraction.completed_at)

    def test_extraction_with_metadata(self):
        """Test DrawingExtraction with processing metadata"""
        now = timezone.now()
        extraction = DrawingExtraction.objects.create(
            drawing_file=self.drawing_file,
            status=DrawingExtractionStatus.SUCCESS,
            started_at=now,
            completed_at=now,
            model_version="v1.2.3",
            processing_time_ms=5000,
            output_s3_key="outputs/result.json",
        )

        self.assertEqual(extraction.model_version, "v1.2.3")
        self.assertEqual(extraction.processing_time_ms, 5000)

    def test_drawing_file_latest_extraction_property(self):
        """Test DrawingFile.latest_extraction returns most recent"""
        extraction1 = DrawingExtraction.objects.create(
            drawing_file=self.drawing_file,
            status=DrawingExtractionStatus.FAILED,
        )
        extraction2 = DrawingExtraction.objects.create(
            drawing_file=self.drawing_file,
            status=DrawingExtractionStatus.SUCCESS,
        )

        self.assertEqual(self.drawing_file.latest_extraction, extraction2)
        self.assertEqual(self.drawing_file.extraction_status, DrawingExtractionStatus.SUCCESS)


class TestDrawingPageModel(TestCase):
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

    def test_drawing_page_creation(self):
        """Test DrawingPage creation for drawing type"""
        page = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=1,
            page_type=DrawingPageType.DRAWING,
            extraction_status=DrawingPageExtractionStatus.SUCCESS,
        )

        self.assertEqual(page.page_number, 1)
        self.assertEqual(page.page_type, DrawingPageType.DRAWING)
        self.assertEqual(page.extraction_status, DrawingPageExtractionStatus.SUCCESS)
        self.assertIsNone(page.spec_content)

    def test_spec_page_with_content(self):
        """Test DrawingPage for spec type with content"""
        page = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=13,
            page_type=DrawingPageType.SPEC,
            extraction_status=DrawingPageExtractionStatus.SUCCESS,
            spec_content="Long specification text content...",
        )

        self.assertEqual(page.page_type, DrawingPageType.SPEC)
        self.assertEqual(page.spec_content, "Long specification text content...")

    def test_page_ordering(self):
        """Test pages are ordered by page_number"""
        DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=3,
            page_type=DrawingPageType.DRAWING,
            extraction_status=DrawingPageExtractionStatus.SUCCESS,
        )
        DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=1,
            page_type=DrawingPageType.DRAWING,
            extraction_status=DrawingPageExtractionStatus.SUCCESS,
        )

        pages = list(DrawingPage.objects.filter(extraction=self.extraction))
        self.assertEqual(pages[0].page_number, 1)
        self.assertEqual(pages[1].page_number, 3)
