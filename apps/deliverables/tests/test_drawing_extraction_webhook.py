# apps/deliverables/tests/test_drawing_extraction_webhook.py
import json
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.deliverables.models import (
    Project, DrawingFile, DrawingExtraction, DrawingExtractionStatus,
)
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class TestDrawingExtractionWebhookBasic(TestCase):
    def setUp(self):
        self.client = APIClient()
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
            status=DrawingExtractionStatus.PENDING,
        )
        self.webhook_url = reverse('deliverables:drawing-extraction-webhook')

    def test_webhook_accepts_post_without_auth(self):
        """Test webhook endpoint exists and allows unauthenticated POST"""
        payload = {
            "event_id": "evt_001",
            "extraction_id": self.extraction.id,
            "new_status": "PROCESSING",
        }

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestDrawingExtractionWebhookStatusTransitions(TestCase):
    def setUp(self):
        self.client = APIClient()
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
            status=DrawingExtractionStatus.PENDING,
        )
        self.webhook_url = reverse('deliverables:drawing-extraction-webhook')

    def test_pending_to_processing(self):
        """Test transition from PENDING to PROCESSING"""
        payload = {
            "event_id": "evt_001",
            "extraction_id": self.extraction.id,
            "new_status": "PROCESSING",
        }

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.extraction.refresh_from_db()
        self.assertEqual(self.extraction.status, DrawingExtractionStatus.PROCESSING)
        self.assertIsNotNone(self.extraction.started_at)

    def test_processing_to_success(self):
        """Test transition from PROCESSING to SUCCESS with data"""
        self.extraction.status = DrawingExtractionStatus.PROCESSING
        self.extraction.save()

        payload = {
            "event_id": "evt_002",
            "extraction_id": self.extraction.id,
            "new_status": "SUCCESS",
            "model_version": "v1.0",
            "processing_time_ms": 5000,
            "data": {
                "file_name": "Mechanical.pdf",
                "total_pages": 2,
                "pages": [
                    {
                        "page_number": 1,
                        "extraction_status": "success",
                        "page_type": "drawing",
                        "note_sections": [
                            {
                                "header": "GENERAL NOTES:",
                                "header_bbox": [100, 200, 300, 250],
                                "notes": [
                                    {
                                        "note_number": 1,
                                        "category": "GENERAL NOTES",
                                        "text": "Test note content",
                                        "bounding_box": [100, 300, 500, 350],
                                        "drawing_references": []
                                    }
                                ]
                            }
                        ],
                        "spec_content": None
                    }
                ]
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.extraction.refresh_from_db()
        self.assertEqual(self.extraction.status, DrawingExtractionStatus.SUCCESS)
        self.assertEqual(self.extraction.model_version, "v1.0")
        self.assertEqual(self.extraction.processing_time_ms, 5000)

        # Check drawing file was updated
        self.drawing_file.refresh_from_db()
        self.assertEqual(self.drawing_file.total_pages, 2)

        # Check records were created
        from apps.deliverables.models import DrawingPage, DrawingNoteSection, DrawingNote
        self.assertEqual(DrawingPage.objects.filter(extraction=self.extraction).count(), 1)
        self.assertEqual(DrawingNoteSection.objects.filter(page__extraction=self.extraction).count(), 1)
        self.assertEqual(DrawingNote.objects.filter(section__page__extraction=self.extraction).count(), 1)

    def test_processing_to_failed(self):
        """Test transition from PROCESSING to FAILED"""
        self.extraction.status = DrawingExtractionStatus.PROCESSING
        self.extraction.save()

        payload = {
            "event_id": "evt_003",
            "extraction_id": self.extraction.id,
            "new_status": "FAILED",
            "error_message": "PDF parsing failed",
            "failure_summary": "Unable to read PDF",
        }

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.extraction.refresh_from_db()
        self.assertEqual(self.extraction.status, DrawingExtractionStatus.FAILED)
        self.assertEqual(self.extraction.error_message, "PDF parsing failed")

    def test_invalid_transition_ignored(self):
        """Test that invalid transitions are silently ignored"""
        self.extraction.status = DrawingExtractionStatus.SUCCESS
        self.extraction.save()

        payload = {
            "event_id": "evt_004",
            "extraction_id": self.extraction.id,
            "new_status": "PROCESSING",  # Invalid: can't go from SUCCESS to PROCESSING
        }

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.extraction.refresh_from_db()
        self.assertEqual(self.extraction.status, DrawingExtractionStatus.SUCCESS)  # Unchanged

    def test_idempotency_duplicate_event_id(self):
        """Test that duplicate event_ids are ignored"""
        payload = {
            "event_id": "evt_005",
            "extraction_id": self.extraction.id,
            "new_status": "PROCESSING",
        }

        # First call
        response1 = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.extraction.refresh_from_db()
        self.assertEqual(self.extraction.status, DrawingExtractionStatus.PROCESSING)

        # Set to SUCCESS for visibility
        self.extraction.status = DrawingExtractionStatus.SUCCESS
        self.extraction.save()

        # Second call with same event_id - should be ignored
        response2 = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.extraction.refresh_from_db()
        self.assertEqual(self.extraction.status, DrawingExtractionStatus.SUCCESS)  # Not changed back


class TestDrawingExtractionWebhookSheetFields(TestCase):
    """Tests for sheet_number and sheet_title field extraction"""

    def setUp(self):
        self.client = APIClient()
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
            status=DrawingExtractionStatus.PROCESSING,
        )
        self.webhook_url = reverse('deliverables:drawing-extraction-webhook')

    def test_sheet_number_and_title_extracted(self):
        """Test that sheet_number and sheet_title are properly extracted from webhook payload"""
        from apps.deliverables.models import DrawingPage

        payload = {
            "event_id": "evt_sheet_001",
            "extraction_id": self.extraction.id,
            "new_status": "SUCCESS",
            "model_version": "v1.0",
            "data": {
                "total_pages": 1,
                "pages": [
                    {
                        "page_number": 1,
                        "extraction_status": "success",
                        "page_type": "drawing",
                        "sheet_number": "M103",
                        "sheet_title": "FLOOR PLAN - DRAINAGE - MAIN",
                        "note_sections": [],
                    }
                ]
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify sheet fields were saved
        page = DrawingPage.objects.get(extraction=self.extraction)
        self.assertEqual(page.sheet_number, "M103")
        self.assertEqual(page.sheet_title, "FLOOR PLAN - DRAINAGE - MAIN")

    def test_missing_sheet_fields_does_not_break_processing(self):
        """Test that missing sheet_number/sheet_title in payload doesn't break processing"""
        from apps.deliverables.models import DrawingPage

        payload = {
            "event_id": "evt_sheet_002",
            "extraction_id": self.extraction.id,
            "new_status": "SUCCESS",
            "model_version": "v1.0",
            "data": {
                "total_pages": 1,
                "pages": [
                    {
                        "page_number": 1,
                        "extraction_status": "success",
                        "page_type": "drawing",
                        # No sheet_number or sheet_title
                        "note_sections": [],
                    }
                ]
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify page was created with null sheet fields
        page = DrawingPage.objects.get(extraction=self.extraction)
        self.assertIsNone(page.sheet_number)
        self.assertIsNone(page.sheet_title)

    def test_multiple_pages_with_different_sheet_values(self):
        """Test webhook correctly stores different sheet values for each page"""
        from apps.deliverables.models import DrawingPage

        payload = {
            "event_id": "evt_sheet_003",
            "extraction_id": self.extraction.id,
            "new_status": "SUCCESS",
            "model_version": "v1.0",
            "data": {
                "total_pages": 3,
                "pages": [
                    {
                        "page_number": 1,
                        "extraction_status": "success",
                        "page_type": "drawing",
                        "sheet_number": "A-101",
                        "sheet_title": "First Floor Plan",
                        "note_sections": [],
                    },
                    {
                        "page_number": 2,
                        "extraction_status": "success",
                        "page_type": "drawing",
                        "sheet_number": "M-201",
                        "sheet_title": "Mechanical Plan",
                        "note_sections": [],
                    },
                    {
                        "page_number": 3,
                        "extraction_status": "success",
                        "page_type": "spec",
                        # Spec pages may not have sheet numbers
                        "note_sections": [],
                    }
                ]
            }
        }

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify each page has correct sheet values
        pages = DrawingPage.objects.filter(extraction=self.extraction).order_by('page_number')
        self.assertEqual(pages.count(), 3)

        self.assertEqual(pages[0].sheet_number, "A-101")
        self.assertEqual(pages[0].sheet_title, "First Floor Plan")

        self.assertEqual(pages[1].sheet_number, "M-201")
        self.assertEqual(pages[1].sheet_title, "Mechanical Plan")

        self.assertIsNone(pages[2].sheet_number)
        self.assertIsNone(pages[2].sheet_title)
