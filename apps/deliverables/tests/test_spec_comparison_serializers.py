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


@override_settings(S3_BUCKET='bucket')
class TestSpecConflictReadSerializerDrawingFields(TestCase):
    """Test drawing-related fields in SpecConflictReadSerializer"""

    def setUp(self):
        from unittest.mock import patch, MagicMock
        from apps.deliverables.models import (
            Project,
            SpecComparison,
            SpecComparisonStatus,
            SpecConflict,
            DrawingFile,
            DrawingExtraction,
            DrawingExtractionStatus,
            DrawingPage,
            DrawingNoteSection,
            DrawingNote,
        )
        from apps.teams.models import Team
        from apps.users.models import CustomUser

        self.user = CustomUser.objects.create_user('test@example.com', password='test')
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()

        # Create drawing structures
        self.drawing_file = DrawingFile.objects.create(
            project=self.project,
            project_version=self.project_version,
            file_name='P-201.pdf',
            file_s3_key='projects/123/drawings/P-201.pdf',
            md5='abc123',
        )
        self.extraction = DrawingExtraction.objects.create(
            drawing_file=self.drawing_file,
            status=DrawingExtractionStatus.SUCCESS,
        )
        self.page = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=3,
            page_type='drawing',
            extraction_status='success',
            sheet_number='P-201',
            sheet_title='Plumbing Riser Diagram',
        )
        self.section = DrawingNoteSection.objects.create(
            page=self.page,
            header='GENERAL NOTES',
        )
        self.note = DrawingNote.objects.create(
            section=self.section,
            note_number=1,
            category='general',
            text='Test note',
            unrotated_bounding_box=[120.5, 340.2, 280.0, 360.8],
        )

        # Create comparison and conflict
        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event',
        )
        self.conflict = SpecConflict.objects.create(
            comparison=self.comparison,
            note=self.note,
            note_id_from_lambda=str(self.note.id),
            note_text='Test note',
            spec_text='Spec text',
            spec_file_s3_key='specs/test.pdf',
            spec_page_number=15,
            spec_masterformat_number='220500',
            confidence=0.85,
            reason='Test conflict',
        )

    def test_includes_sheet_number(self):
        """Test serializer includes sheet_number from drawing page"""
        from unittest.mock import patch
        with patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url') as mock_presigned:
            mock_presigned.return_value = 'https://presigned-url.com'
            from apps.deliverables.serializers.spec_comparison_serializers import SpecConflictReadSerializer

            serializer = SpecConflictReadSerializer(self.conflict, context={})
            self.assertEqual(serializer.data['sheet_number'], 'P-201')

    def test_includes_sheet_title(self):
        """Test serializer includes sheet_title from drawing page"""
        from unittest.mock import patch
        with patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url') as mock_presigned:
            mock_presigned.return_value = 'https://presigned-url.com'
            from apps.deliverables.serializers.spec_comparison_serializers import SpecConflictReadSerializer

            serializer = SpecConflictReadSerializer(self.conflict, context={})
            self.assertEqual(serializer.data['sheet_title'], 'Plumbing Riser Diagram')

    def test_includes_drawing_file_url(self):
        """Test serializer includes presigned drawing file URL"""
        from unittest.mock import patch
        with patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url') as mock_presigned:
            mock_presigned.return_value = 'https://presigned-url.com/drawing.pdf'
            from apps.deliverables.serializers.spec_comparison_serializers import SpecConflictReadSerializer

            serializer = SpecConflictReadSerializer(self.conflict, context={})
            self.assertEqual(serializer.data['drawing_file_url'], 'https://presigned-url.com/drawing.pdf')

    def test_includes_drawing_page_number(self):
        """Test serializer includes drawing page number"""
        from unittest.mock import patch
        with patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url') as mock_presigned:
            mock_presigned.return_value = 'https://presigned-url.com'
            from apps.deliverables.serializers.spec_comparison_serializers import SpecConflictReadSerializer

            serializer = SpecConflictReadSerializer(self.conflict, context={})
            self.assertEqual(serializer.data['drawing_page_number'], 3)

    def test_includes_drawing_bounding_box(self):
        """Test serializer includes drawing bounding box"""
        from unittest.mock import patch
        with patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url') as mock_presigned:
            mock_presigned.return_value = 'https://presigned-url.com'
            from apps.deliverables.serializers.spec_comparison_serializers import SpecConflictReadSerializer

            serializer = SpecConflictReadSerializer(self.conflict, context={})
            self.assertEqual(serializer.data['drawing_bounding_box'], [120.5, 340.2, 280.0, 360.8])

    def test_drawing_fields_null_when_note_missing(self):
        """Test drawing fields are null when note FK is null"""
        from unittest.mock import patch
        from apps.deliverables.models import SpecConflict
        with patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url') as mock_presigned:
            mock_presigned.return_value = 'https://presigned-url.com'
            from apps.deliverables.serializers.spec_comparison_serializers import SpecConflictReadSerializer

            # Create conflict without note FK
            conflict_no_note = SpecConflict.objects.create(
                comparison=self.comparison,
                note=None,
                note_id_from_lambda='999',
                note_text='Orphan note',
                spec_text='Spec text',
                spec_file_s3_key='specs/test.pdf',
                spec_page_number=1,
                spec_masterformat_number='220500',
                confidence=0.5,
                reason='Test',
            )

            serializer = SpecConflictReadSerializer(conflict_no_note, context={})
            self.assertIsNone(serializer.data['sheet_number'])
            self.assertIsNone(serializer.data['sheet_title'])
            self.assertIsNone(serializer.data['drawing_file_url'])
            self.assertIsNone(serializer.data['drawing_page_number'])
            self.assertIsNone(serializer.data['drawing_bounding_box'])
