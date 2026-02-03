from django.test import TestCase, override_settings
from apps.deliverables.serializers.spec_comparison_serializers import (
    PdfLocationSerializer,
    SpecConflictPayloadSerializer,
    SkippedNotePayloadSerializer,
    SpecComparisonWebhookSerializer,
)
from apps.deliverables.models import SpecComparisonStatus, SkipReason


class TestPdfLocationSerializer(TestCase):
    """Test PdfLocationSerializer validation"""

    def test_valid_pdf_location(self):
        data = {
            'page_no': 1,
            'x': 72.0,
            'y': 144.5,
            'width': 200.0,
            'height': 12.0,
        }
        serializer = PdfLocationSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_invalid_missing_fields(self):
        data = {'page_no': 1}
        serializer = PdfLocationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('x', serializer.errors)


@override_settings(S3_BUCKET='bucket')
class TestSpecConflictPayloadSerializer(TestCase):
    """Test SpecConflictPayloadSerializer validation"""

    def test_valid_conflict_payload(self):
        data = {
            'note_id': '123',
            'note_text': 'Provide shutoff valves',
            'spec_text': 'Shutoff valves shall be gate type',
            'spec_source_file': 's3://bucket/specs/plumbing.pdf',
            'spec_page_number': 15,
            'spec_masterformat_number': '220500',
            'confidence': 0.85,
            'reason': 'Ball vs gate valve conflict',
            'pdf_locations': [
                {'page_no': 15, 'x': 72.0, 'y': 144.5, 'width': 200.0, 'height': 12.0}
            ],
        }
        serializer = SpecConflictPayloadSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_valid_without_pdf_locations(self):
        data = {
            'note_id': '123',
            'note_text': 'Provide shutoff valves',
            'spec_text': 'Shutoff valves shall be gate type',
            'spec_source_file': 's3://bucket/specs/plumbing.pdf',
            'spec_page_number': 15,
            'spec_masterformat_number': '220500',
            'confidence': 0.85,
            'reason': 'Ball vs gate valve conflict',
        }
        serializer = SpecConflictPayloadSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['pdf_locations'], [])

    def test_rejects_non_s3_uri(self):
        data = {
            'note_id': '123',
            'note_text': 'Note text',
            'spec_text': 'Spec text',
            'spec_source_file': 'https://example.com/file.pdf',
            'spec_page_number': 1,
            'spec_masterformat_number': '220500',
            'confidence': 0.5,
            'reason': 'Reason',
        }
        serializer = SpecConflictPayloadSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('spec_source_file', serializer.errors)

    def test_rejects_malformed_s3_uri_bucket_only(self):
        data = {
            'note_id': '123',
            'note_text': 'Note text',
            'spec_text': 'Spec text',
            'spec_source_file': 's3://bucket',
            'spec_page_number': 1,
            'spec_masterformat_number': '220500',
            'confidence': 0.5,
            'reason': 'Reason',
        }
        serializer = SpecConflictPayloadSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('spec_source_file', serializer.errors)

    def test_rejects_malformed_s3_uri_trailing_slash(self):
        data = {
            'note_id': '123',
            'note_text': 'Note text',
            'spec_text': 'Spec text',
            'spec_source_file': 's3://bucket/',
            'spec_page_number': 1,
            'spec_masterformat_number': '220500',
            'confidence': 0.5,
            'reason': 'Reason',
        }
        serializer = SpecConflictPayloadSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('spec_source_file', serializer.errors)

    def test_rejects_s3_uri_without_bucket(self):
        data = {
            'note_id': '123',
            'note_text': 'Note text',
            'spec_text': 'Spec text',
            'spec_source_file': 's3:///key',
            'spec_page_number': 1,
            'spec_masterformat_number': '220500',
            'confidence': 0.5,
            'reason': 'Reason',
        }
        serializer = SpecConflictPayloadSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('spec_source_file', serializer.errors)


class TestSkippedNotePayloadSerializer(TestCase):
    """Test SkippedNotePayloadSerializer validation"""

    def test_valid_skipped_note(self):
        data = {
            'note_id': '456',
            'disciplines': ['plumbing', 'mechanical'],
            'sheet_discipline': 'mechanical',
            'reason': 'no_matching_specs',
            'detail': 'Division 22 has no specs uploaded',
        }
        serializer = SkippedNotePayloadSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_valid_minimal_skipped_note(self):
        data = {
            'note_id': '456',
            'reason': 'unknown_discipline',
        }
        serializer = SkippedNotePayloadSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['disciplines'], [])

    def test_invalid_skip_reason(self):
        data = {
            'note_id': '456',
            'reason': 'invalid_reason',
        }
        serializer = SkippedNotePayloadSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('reason', serializer.errors)


@override_settings(S3_BUCKET='bucket')
class TestSpecComparisonWebhookSerializer(TestCase):
    """Test SpecComparisonWebhookSerializer validation"""

    def test_valid_success_payload(self):
        data = {
            'event_id': 'evt-123',
            'comparison_id': 1,
            'status': 'SUCCESS',
            'conflicts': [],
            'skipped_notes': [],
            'notes_processed': 100,
            'notes_skipped': 5,
            'spec_files_processed': 10,
            'notes_with_mismatch': 3,
        }
        serializer = SpecComparisonWebhookSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_valid_failed_payload(self):
        data = {
            'event_id': 'evt-456',
            'comparison_id': 1,
            'status': 'FAILED',
            'error_message': 'Lambda timeout',
        }
        serializer = SpecComparisonWebhookSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_rejects_empty_event_id(self):
        data = {
            'event_id': '',
            'comparison_id': 1,
            'status': 'SUCCESS',
        }
        serializer = SpecComparisonWebhookSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('event_id', serializer.errors)

    def test_rejects_missing_event_id(self):
        data = {
            'comparison_id': 1,
            'status': 'SUCCESS',
        }
        serializer = SpecComparisonWebhookSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('event_id', serializer.errors)

    def test_rejects_pending_status(self):
        """Only terminal statuses allowed in webhook"""
        data = {
            'event_id': 'evt-789',
            'comparison_id': 1,
            'status': 'PENDING',
        }
        serializer = SpecComparisonWebhookSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('status', serializer.errors)

    def test_rejects_processing_status(self):
        """Only terminal statuses allowed in webhook"""
        data = {
            'event_id': 'evt-789',
            'comparison_id': 1,
            'status': 'PROCESSING',
        }
        serializer = SpecComparisonWebhookSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('status', serializer.errors)

    def test_accepts_partial_success(self):
        data = {
            'event_id': 'evt-partial',
            'comparison_id': 1,
            'status': 'PARTIAL_SUCCESS',
            'notes_processed': 50,
        }
        serializer = SpecComparisonWebhookSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validates_nested_conflicts(self):
        data = {
            'event_id': 'evt-nested',
            'comparison_id': 1,
            'status': 'SUCCESS',
            'conflicts': [
                {
                    'note_id': '1',
                    'note_text': 'Note',
                    'spec_text': 'Spec',
                    'spec_source_file': 'invalid-uri',  # Invalid
                    'spec_page_number': 1,
                    'spec_masterformat_number': '220500',
                    'confidence': 0.9,
                    'reason': 'Conflict',
                }
            ],
        }
        serializer = SpecComparisonWebhookSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('conflicts', serializer.errors)
