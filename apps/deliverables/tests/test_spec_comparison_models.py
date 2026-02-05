from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.deliverables.models import (
    SpecComparisonStatus,
    SkipReason,
    SpecComparison,
    SpecComparisonWebhookEvent,
    SpecConflict,
    SkippedNote,
    Project,
    DrawingNote,
    DrawingNoteSection,
    DrawingPage,
    DrawingFile,
    DrawingExtraction,
    DrawingExtractionStatus,
)
from apps.teams.models import Team

User = get_user_model()


class TestSpecComparisonStatusEnum(TestCase):
    """Test SpecComparisonStatus enum values"""

    def test_all_status_values_exist(self):
        self.assertEqual(SpecComparisonStatus.PENDING, "PENDING")
        self.assertEqual(SpecComparisonStatus.PROCESSING, "PROCESSING")
        self.assertEqual(SpecComparisonStatus.SUCCESS, "SUCCESS")
        self.assertEqual(SpecComparisonStatus.PARTIAL_SUCCESS, "PARTIAL_SUCCESS")
        self.assertEqual(SpecComparisonStatus.FAILED, "FAILED")

    def test_status_labels(self):
        self.assertEqual(SpecComparisonStatus.PENDING.label, "Pending")
        self.assertEqual(SpecComparisonStatus.PROCESSING.label, "Processing")
        self.assertEqual(SpecComparisonStatus.SUCCESS.label, "Success")
        self.assertEqual(SpecComparisonStatus.PARTIAL_SUCCESS.label, "Partial Success")
        self.assertEqual(SpecComparisonStatus.FAILED.label, "Failed")


class TestSkipReasonEnum(TestCase):
    """Test SkipReason enum values"""

    def test_all_skip_reason_values_exist(self):
        self.assertEqual(SkipReason.UNKNOWN_DISCIPLINE, "unknown_discipline")
        self.assertEqual(SkipReason.SKIP_BY_POLICY, "skip_by_policy")
        self.assertEqual(SkipReason.NO_MATCHING_SPECS, "no_matching_specs")
        self.assertEqual(SkipReason.MALFORMED_DISCIPLINE, "malformed_discipline")


class TestSpecComparisonModel(TestCase):
    """Test SpecComparison model"""

    def setUp(self):
        self.user = User.objects.create_user('test@example.com', password='testpass123')
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()

    def test_create_spec_comparison(self):
        comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            triggered_by=self.user,
            status=SpecComparisonStatus.PENDING,
            event_id='test-event-123',
        )
        self.assertEqual(comparison.status, SpecComparisonStatus.PENDING)
        self.assertEqual(comparison.notes_processed, 0)
        self.assertEqual(comparison.notes_skipped, 0)
        self.assertIsNotNone(comparison.created_at)

    def test_event_id_unique(self):
        SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.PENDING,
            event_id='unique-event-id',
        )
        with self.assertRaises(Exception):
            SpecComparison.objects.create(
                project=self.project,
                project_version=self.project_version,
                status=SpecComparisonStatus.PENDING,
                event_id='unique-event-id',
            )

    def test_triggered_by_set_null(self):
        # Use a separate user for triggering (not the project owner)
        # since Project.created_by has CASCADE delete
        trigger_user = User.objects.create_user('trigger@example.com', password='testpass123')
        comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            triggered_by=trigger_user,
            status=SpecComparisonStatus.PENDING,
            event_id='test-event-456',
        )
        trigger_user.delete()
        comparison.refresh_from_db()
        self.assertIsNone(comparison.triggered_by)


class TestSpecConflictModel(TestCase):
    """Test SpecConflict model"""

    def setUp(self):
        self.user = User.objects.create_user('test@example.com', password='testpass123')
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event-789',
        )
        # Create drawing note for FK testing
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

    def test_create_spec_conflict(self):
        conflict = SpecConflict.objects.create(
            comparison=self.comparison,
            note=self.note,
            note_id_from_lambda=str(self.note.id),
            note_text='Test note text',
            spec_text='Conflicting spec text',
            spec_file_s3_key='specs/plumbing.pdf',
            spec_page_number=15,
            spec_masterformat_number='220500',
            confidence=0.85,
            reason='Note specifies ball valves but spec requires gate valves',
        )
        self.assertEqual(conflict.confidence, 0.85)
        self.assertEqual(conflict.pdf_locations, [])

    def test_note_fk_set_null(self):
        note_id = self.note.id  # Save before deletion
        conflict = SpecConflict.objects.create(
            comparison=self.comparison,
            note=self.note,
            note_id_from_lambda=str(note_id),
            note_text='Test note text',
            spec_text='Conflicting spec text',
            spec_file_s3_key='specs/plumbing.pdf',
            spec_page_number=15,
            spec_masterformat_number='220500',
            confidence=0.85,
            reason='Test reason',
        )
        self.note.delete()
        conflict.refresh_from_db()
        self.assertIsNone(conflict.note)
        self.assertEqual(conflict.note_id_from_lambda, str(note_id))

    def test_conflict_ordering(self):
        """Test conflicts are ordered by id for deterministic pagination"""
        conflict1 = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='1',
            note_text='Note 1',
            spec_text='Spec 1',
            spec_file_s3_key='specs/a.pdf',
            spec_page_number=1,
            spec_masterformat_number='220500',
            confidence=0.9,
            reason='Reason 1',
        )
        conflict2 = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='2',
            note_text='Note 2',
            spec_text='Spec 2',
            spec_file_s3_key='specs/b.pdf',
            spec_page_number=2,
            spec_masterformat_number='220500',
            confidence=0.8,
            reason='Reason 2',
        )
        conflicts = list(SpecConflict.objects.filter(comparison=self.comparison))
        self.assertEqual(conflicts[0].id, conflict1.id)
        self.assertEqual(conflicts[1].id, conflict2.id)


class TestSkippedNoteModel(TestCase):
    """Test SkippedNote model"""

    def setUp(self):
        self.user = User.objects.create_user('test@example.com', password='testpass123')
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event-skipped',
        )

    def test_create_skipped_note(self):
        skipped = SkippedNote.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='123',
            disciplines=['plumbing'],
            sheet_discipline='mechanical',
            reason=SkipReason.NO_MATCHING_SPECS,
            detail='Division 22 has no specs uploaded',
        )
        self.assertEqual(skipped.reason, SkipReason.NO_MATCHING_SPECS)
        self.assertEqual(skipped.disciplines, ['plumbing'])

    def test_skipped_note_ordering(self):
        """Test skipped notes are ordered by id for deterministic pagination"""
        skipped1 = SkippedNote.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='1',
            reason=SkipReason.UNKNOWN_DISCIPLINE,
        )
        skipped2 = SkippedNote.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='2',
            reason=SkipReason.NO_MATCHING_SPECS,
        )
        skipped_notes = list(SkippedNote.objects.filter(comparison=self.comparison))
        self.assertEqual(skipped_notes[0].id, skipped1.id)
        self.assertEqual(skipped_notes[1].id, skipped2.id)


class TestSpecComparisonWebhookEventModel(TestCase):
    """Test SpecComparisonWebhookEvent model"""

    def setUp(self):
        self.user = User.objects.create_user('test@example.com', password='testpass123')
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.PROCESSING,
            event_id='test-event-webhook',
        )

    def test_create_webhook_event(self):
        event = SpecComparisonWebhookEvent.objects.create(
            comparison=self.comparison,
            event_id='test-event-webhook',
            new_status=SpecComparisonStatus.SUCCESS,
        )
        self.assertEqual(event.new_status, SpecComparisonStatus.SUCCESS)

    def test_event_id_unique(self):
        SpecComparisonWebhookEvent.objects.create(
            comparison=self.comparison,
            event_id='unique-webhook-event',
            new_status=SpecComparisonStatus.SUCCESS,
        )
        with self.assertRaises(Exception):
            SpecComparisonWebhookEvent.objects.create(
                comparison=self.comparison,
                event_id='unique-webhook-event',
                new_status=SpecComparisonStatus.FAILED,
            )
