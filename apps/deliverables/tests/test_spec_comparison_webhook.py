import json
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status

from apps.deliverables.models import (
    Project,
    SpecComparison,
    SpecComparisonStatus,
    SpecComparisonWebhookEvent,
    SpecConflict,
    SkippedNote,
    SkipReason,
    DrawingFile,
    DrawingExtraction,
    DrawingExtractionStatus,
    DrawingPage,
    DrawingNoteSection,
    DrawingNote,
)
from apps.teams.models import Team

User = get_user_model()


class TestUtilityFunctions(TestCase):
    """Test utility functions used in spec comparison webhook"""

    def test_parse_s3_uri_to_key_valid(self):
        """Test extracting S3 key from valid s3:// URI"""
        from apps.deliverables.views.spec_comparison_views import parse_s3_uri_to_key

        result = parse_s3_uri_to_key('s3://bucket/path/to/file.pdf')
        self.assertEqual(result, 'path/to/file.pdf')

    def test_parse_s3_uri_to_key_nested_path(self):
        """Test extracting S3 key with nested path"""
        from apps.deliverables.views.spec_comparison_views import parse_s3_uri_to_key

        result = parse_s3_uri_to_key('s3://my-bucket/specs/plumbing/section-22.pdf')
        self.assertEqual(result, 'specs/plumbing/section-22.pdf')

    def test_parse_s3_uri_to_key_invalid_no_path(self):
        """Test parse_s3_uri_to_key raises ValueError for URI without path"""
        from apps.deliverables.views.spec_comparison_views import parse_s3_uri_to_key

        with self.assertRaises(ValueError) as ctx:
            parse_s3_uri_to_key('s3://bucket')
        self.assertIn('Invalid S3 URI format', str(ctx.exception))

    def test_safe_int_valid_integer(self):
        """Test safe_int with valid integer string"""
        from apps.deliverables.views.spec_comparison_views import safe_int

        self.assertEqual(safe_int('123'), 123)
        self.assertEqual(safe_int('0'), 0)
        self.assertEqual(safe_int('-5'), -5)

    def test_safe_int_invalid_string(self):
        """Test safe_int returns None for non-integer string"""
        from apps.deliverables.views.spec_comparison_views import safe_int

        self.assertIsNone(safe_int('abc'))
        self.assertIsNone(safe_int('12.5'))
        self.assertIsNone(safe_int(''))

    def test_safe_int_none_input(self):
        """Test safe_int returns None for None input"""
        from apps.deliverables.views.spec_comparison_views import safe_int

        self.assertIsNone(safe_int(None))


@override_settings(S3_BUCKET='bucket', DEBUG=True)
class TestSpecComparisonWebhook(APITestCase):
    """Test the spec comparison webhook endpoint"""

    def setUp(self):
        self.user = User.objects.create_user(
            'test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()

        # Create a comparison in PROCESSING state
        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            triggered_by=self.user,
            status=SpecComparisonStatus.PROCESSING,
            event_id='test-event-id-123',
        )

        # Create a drawing note for FK linking tests
        self.drawing_file = DrawingFile.objects.create(
            project=self.project,
            project_version=self.project_version,
            file_name='test.pdf',
            file_s3_key='drawings/test.pdf',
            md5='abc123',
        )
        self.extraction = DrawingExtraction.objects.create(
            drawing_file=self.drawing_file,
            status=DrawingExtractionStatus.SUCCESS,
        )
        self.page = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=1,
            page_type='drawing',
            extraction_status='success',
        )
        self.section = DrawingNoteSection.objects.create(
            page=self.page,
            header='GENERAL NOTES',
        )
        self.note = DrawingNote.objects.create(
            section=self.section,
            note_number=1,
            category='general',
            text='Test note text',
        )

        self.webhook_url = reverse('deliverables:spec-comparison-webhook')

    def _make_payload(self, event_id, comparison_id, status, data_fields=None):
        """Helper to create webhook payload with nested data structure."""
        payload = {
            'event_id': event_id,
            'comparison_id': comparison_id,
            'status': status,
            'data': data_fields or {}
        }
        return payload

    def test_success_webhook_creates_conflicts(self):
        """Test successful webhook creates conflict records"""
        payload = self._make_payload(
            'test-event-id-123',
            self.comparison.id,
            'SUCCESS',
            {
                'conflicts': [
                    {
                        'note_id': str(self.note.id),
                        'note_text': 'Test note text',
                        'spec_text': 'Conflicting spec text',
                        'spec_source_file': 's3://bucket/specs/plumbing.pdf',
                        'spec_page_number': 15,
                        'spec_masterformat_number': '220500',
                        'confidence': 0.85,
                        'reason': 'Ball vs gate valve conflict',
                        'pdf_locations': [
                            {'page_no': 15, 'x': 72.0, 'y': 144.5, 'width': 200.0, 'height': 12.0}
                        ],
                    }
                ],
                'skipped_notes': [],
                'notes_processed': 100,
                'notes_skipped': 5,
                'specs_processed': 10,
                'notes_with_mismatch': 3,
            }
        )

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify comparison updated
        self.comparison.refresh_from_db()
        self.assertEqual(self.comparison.status, SpecComparisonStatus.SUCCESS)
        self.assertEqual(self.comparison.notes_processed, 100)
        self.assertIsNotNone(self.comparison.completed_at)

        # Verify conflict created
        self.assertEqual(SpecConflict.objects.count(), 1)
        conflict = SpecConflict.objects.first()
        self.assertEqual(conflict.note, self.note)
        self.assertEqual(conflict.spec_file_s3_key, 'specs/plumbing.pdf')
        self.assertEqual(conflict.confidence, 0.85)

        # Verify webhook event created
        self.assertEqual(SpecComparisonWebhookEvent.objects.count(), 1)

    def test_success_webhook_creates_skipped_notes(self):
        """Test successful webhook creates skipped note records"""
        payload = self._make_payload(
            'test-event-id-123',
            self.comparison.id,
            'SUCCESS',
            {
                'conflicts': [],
                'skipped_notes': [
                    {
                        'note_id': str(self.note.id),
                        'disciplines': ['plumbing'],
                        'sheet_discipline': 'mechanical',
                        'reason': 'no_matching_specs',
                        'detail': 'Division 22 has no specs uploaded',
                    }
                ],
                'notes_processed': 50,
                'notes_skipped': 10,
                'specs_processed': 5,
                'notes_with_mismatch': 0,
            }
        )

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify skipped note created
        self.assertEqual(SkippedNote.objects.count(), 1)
        skipped = SkippedNote.objects.first()
        self.assertEqual(skipped.note, self.note)
        self.assertEqual(skipped.reason, SkipReason.NO_MATCHING_SPECS)

    def test_failed_webhook_does_not_create_conflicts(self):
        """Test FAILED status does not store conflicts/skipped notes"""
        payload = self._make_payload(
            'test-event-id-123',
            self.comparison.id,
            'FAILED',
            {
                'conflicts': [
                    {
                        'note_id': '999',
                        'note_text': 'Should not be stored',
                        'spec_text': 'Should not be stored',
                        'spec_source_file': 's3://bucket/specs/test.pdf',
                        'spec_page_number': 1,
                        'spec_masterformat_number': '220500',
                        'confidence': 0.5,
                        'reason': 'Test',
                    }
                ],
                'error_message': 'Lambda timeout',
            }
        )

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify comparison updated to FAILED
        self.comparison.refresh_from_db()
        self.assertEqual(self.comparison.status, SpecComparisonStatus.FAILED)
        self.assertEqual(self.comparison.error_message, 'Lambda timeout')
        self.assertIsNotNone(self.comparison.completed_at)

        # Verify NO conflicts created
        self.assertEqual(SpecConflict.objects.count(), 0)

    def test_idempotency_duplicate_event_id(self):
        """Test duplicate event_ids are ignored"""
        payload = self._make_payload(
            'test-event-id-123',
            self.comparison.id,
            'SUCCESS',
            {
                'conflicts': [],
                'skipped_notes': [],
                'notes_processed': 100,
            }
        )

        # First call
        response1 = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertEqual(SpecComparisonWebhookEvent.objects.count(), 1)

        # Second call with same event_id
        response2 = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.data['status'], 'already_processed')

        # Still only one webhook event
        self.assertEqual(SpecComparisonWebhookEvent.objects.count(), 1)

    def test_event_id_mismatch_returns_400(self):
        """Test mismatched event_id returns 400"""
        payload = self._make_payload(
            'wrong-event-id',
            self.comparison.id,
            'SUCCESS',
            {}
        )

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Event ID mismatch', response.data['error'])

    def test_comparison_not_found_returns_404(self):
        """Test non-existent comparison returns 404"""
        payload = self._make_payload(
            'some-event-id',
            99999,
            'SUCCESS',
            {}
        )

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_payload_returns_400(self):
        """Test invalid payload returns 400"""
        payload = {
            'event_id': '',  # Empty not allowed
            'comparison_id': self.comparison.id,
            'status': 'SUCCESS',
            'data': {}
        }

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_spec_source_file_returns_400(self):
        """Test invalid spec_source_file format returns 400"""
        payload = self._make_payload(
            'test-event-id-123',
            self.comparison.id,
            'SUCCESS',
            {
                'conflicts': [
                    {
                        'note_id': '1',
                        'note_text': 'Note',
                        'spec_text': 'Spec',
                        'spec_source_file': 'https://not-s3.com/file.pdf',
                        'spec_page_number': 1,
                        'spec_masterformat_number': '220500',
                        'confidence': 0.5,
                        'reason': 'Reason',
                    }
                ],
            }
        )

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_note_fk_null_when_not_found(self):
        """Test note FK is null when note_id not found"""
        payload = self._make_payload(
            'test-event-id-123',
            self.comparison.id,
            'SUCCESS',
            {
                'conflicts': [
                    {
                        'note_id': '999999',  # Non-existent
                        'note_text': 'Note text',
                        'spec_text': 'Spec text',
                        'spec_source_file': 's3://bucket/specs/test.pdf',
                        'spec_page_number': 1,
                        'spec_masterformat_number': '220500',
                        'confidence': 0.5,
                        'reason': 'Reason',
                    }
                ],
            }
        )

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        conflict = SpecConflict.objects.first()
        self.assertIsNone(conflict.note)
        self.assertEqual(conflict.note_id_from_lambda, '999999')

    def test_non_integer_note_id_handled_gracefully(self):
        """Test non-integer note_id is handled gracefully"""
        payload = self._make_payload(
            'test-event-id-123',
            self.comparison.id,
            'SUCCESS',
            {
                'conflicts': [
                    {
                        'note_id': 'not-an-integer',
                        'note_text': 'Note text',
                        'spec_text': 'Spec text',
                        'spec_source_file': 's3://bucket/specs/test.pdf',
                        'spec_page_number': 1,
                        'spec_masterformat_number': '220500',
                        'confidence': 0.5,
                        'reason': 'Reason',
                    }
                ],
            }
        )

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        conflict = SpecConflict.objects.first()
        self.assertIsNone(conflict.note)
        self.assertEqual(conflict.note_id_from_lambda, 'not-an-integer')

    def test_partial_success_stores_data(self):
        """Test PARTIAL_SUCCESS status stores conflicts and skipped notes"""
        payload = self._make_payload(
            'test-event-id-123',
            self.comparison.id,
            'PARTIAL_SUCCESS',
            {
                'conflicts': [
                    {
                        'note_id': str(self.note.id),
                        'note_text': 'Note',
                        'spec_text': 'Spec',
                        'spec_source_file': 's3://bucket/specs/test.pdf',
                        'spec_page_number': 1,
                        'spec_masterformat_number': '220500',
                        'confidence': 0.5,
                        'reason': 'Reason',
                    }
                ],
                'skipped_notes': [
                    {
                        'note_id': '456',
                        'reason': 'unknown_discipline',
                    }
                ],
                'notes_processed': 50,
                'notes_skipped': 20,
            }
        )

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.comparison.refresh_from_db()
        self.assertEqual(self.comparison.status, SpecComparisonStatus.PARTIAL_SUCCESS)
        self.assertEqual(SpecConflict.objects.count(), 1)
        self.assertEqual(SkippedNote.objects.count(), 1)

