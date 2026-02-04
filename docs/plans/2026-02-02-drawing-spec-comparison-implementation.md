# Drawing Spec Comparison Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement backend support for comparing drawing notes against project specifications to detect conflicts.

**Architecture:** Feature-flagged API endpoints that trigger AWS Lambda for analysis, receive results via webhook, and expose conflicts/skipped notes through read endpoints. Uses existing patterns from DrawingExtraction for idempotency and atomic processing.

**Tech Stack:** Django 4.x, Django REST Framework, PostgreSQL, boto3 (S3), AWS Lambda (HTTP invoke)

**Prerequisites:**
- This plan requires the discipline classification feature from PR #238 (`note-discipline`) which adds:
  - `DrawingNote.disciplines` - ArrayField of discipline values
  - `DrawingNote.discipline_confidence` - confidence level
  - `DrawingPage.sheet_discipline` - discipline from sheet number prefix
  - `DrawingPage.sheet_discipline_confidence` - confidence level
- Ensure you're on a branch based on `develop` with PR #238 merged

---

## Task 1: Add Models and Enums

**Files:**
- Modify: `apps/deliverables/models.py`

**Step 1: Write the model tests**

Create test file `apps/deliverables/tests/test_spec_comparison_models.py`:

```python
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
        self.user = User.objects.create_user(
            email='test@example.com',
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
        comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            triggered_by=self.user,
            status=SpecComparisonStatus.PENDING,
            event_id='test-event-456',
        )
        self.user.delete()
        comparison.refresh_from_db()
        self.assertIsNone(comparison.triggered_by)


class TestSpecConflictModel(TestCase):
    """Test SpecConflict model"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
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
            reason='Test reason',
        )
        self.note.delete()
        conflict.refresh_from_db()
        self.assertIsNone(conflict.note)
        self.assertEqual(conflict.note_id_from_lambda, str(self.note.id))

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
        self.user = User.objects.create_user(
            email='test@example.com',
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
        self.user = User.objects.create_user(
            email='test@example.com',
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
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_spec_comparison_models -v 2`
Expected: FAIL with import errors (models don't exist yet)

**Step 3: Add enums and models to models.py**

Add after `DrawingExtractionWebhookEvent` class (around line 1070):

```python
class SpecComparisonStatus(models.TextChoices):
    """Status of a spec comparison run"""
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    SUCCESS = "SUCCESS", "Success"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS", "Partial Success"
    FAILED = "FAILED", "Failed"


class SkipReason(models.TextChoices):
    """Reason why a note was skipped during comparison"""
    UNKNOWN_DISCIPLINE = "unknown_discipline", "Unknown Discipline"
    SKIP_BY_POLICY = "skip_by_policy", "Skip by Policy"
    NO_MATCHING_SPECS = "no_matching_specs", "No Matching Specs"
    MALFORMED_DISCIPLINE = "malformed_discipline", "Malformed Discipline"


class SpecComparison(BaseModel):
    """Tracks each spec comparison run for a project"""

    project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        related_name="spec_comparisons"
    )
    project_version = models.ForeignKey(
        "ProjectVersion",
        on_delete=models.CASCADE,
        related_name="spec_comparisons"
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_spec_comparisons"
    )
    status = models.CharField(
        max_length=32,
        choices=SpecComparisonStatus.choices,
        default=SpecComparisonStatus.PENDING
    )
    event_id = models.CharField(max_length=64, unique=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes_processed = models.IntegerField(default=0)
    notes_skipped = models.IntegerField(default=0)
    spec_files_processed = models.IntegerField(default=0)
    notes_with_mismatch = models.IntegerField(default=0)
    error_message = models.TextField(null=True, blank=True)
    payload_s3_key = models.CharField(max_length=1024, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['project', 'project_version', 'created_at']),
            models.Index(fields=['project', 'status', 'completed_at']),
        ]

    def __str__(self):
        return f"SpecComparison {self.id} ({self.status})"


class SpecComparisonWebhookEvent(BaseModel):
    """Tracks webhook deliveries for idempotency"""

    comparison = models.ForeignKey(
        "SpecComparison",
        on_delete=models.CASCADE,
        related_name="webhook_events"
    )
    event_id = models.CharField(max_length=64, unique=True)
    new_status = models.CharField(
        max_length=32,
        choices=SpecComparisonStatus.choices
    )

    def __str__(self):
        return f"WebhookEvent {self.event_id} -> {self.new_status}"


class SpecConflict(BaseModel):
    """Stores each detected conflict between a drawing note and spec"""

    comparison = models.ForeignKey(
        "SpecComparison",
        on_delete=models.CASCADE,
        related_name="conflicts"
    )
    note = models.ForeignKey(
        "DrawingNote",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="spec_conflicts"
    )
    note_id_from_lambda = models.CharField(max_length=64)
    note_text = models.TextField()
    spec_text = models.TextField()
    spec_file_s3_key = models.CharField(max_length=1024)
    spec_page_number = models.IntegerField()
    spec_masterformat_number = models.CharField(max_length=256)  # Match MasterFormatSection.masterformat_number
    confidence = models.FloatField()
    reason = models.TextField()
    pdf_locations = models.JSONField(default=list)

    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['comparison']),
        ]

    def __str__(self):
        return f"Conflict {self.id}: {self.note_text[:50]}..."


class SkippedNote(BaseModel):
    """Stores why notes were not analyzed during comparison"""

    comparison = models.ForeignKey(
        "SpecComparison",
        on_delete=models.CASCADE,
        related_name="skipped_notes"
    )
    note = models.ForeignKey(
        "DrawingNote",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="skipped_in_comparisons"
    )
    note_id_from_lambda = models.CharField(max_length=64)
    disciplines = models.JSONField(default=list)
    sheet_discipline = models.CharField(max_length=32, null=True, blank=True)
    reason = models.CharField(max_length=32, choices=SkipReason.choices)
    detail = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['comparison', 'reason']),
        ]

    def __str__(self):
        return f"SkippedNote {self.note_id_from_lambda}: {self.reason}"
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_spec_comparison_models -v 2`
Expected: PASS

**Step 5: Create migration**

Run: `docker-compose exec web python manage.py makemigrations deliverables --name add_spec_comparison_models`

**Step 6: Apply migration**

Run: `docker-compose exec web python manage.py migrate`

**Step 7: Commit**

```bash
git add apps/deliverables/models.py apps/deliverables/tests/test_spec_comparison_models.py apps/deliverables/migrations/
git commit -m "$(cat <<'EOF'
feat: add SpecComparison models for drawing spec comparison

- Add SpecComparisonStatus and SkipReason enums
- Add SpecComparison model to track comparison runs
- Add SpecComparisonWebhookEvent for idempotency
- Add SpecConflict to store detected conflicts
- Add SkippedNote to track skipped notes with reasons
- Include database indexes for query performance

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add Feature Flag and Settings

**Files:**
- Modify: `apps/utils/feature_flags.py`
- Modify: `the_link/settings.py`

**Step 1: Write tests for feature flag helper**

Create `apps/utils/tests/test_spec_comparison_feature_flag.py`:

```python
from django.test import TestCase, override_settings
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from apps.utils.feature_flags import is_drawing_spec_comparison_active
from apps.teams.models import Team
from apps.deliverables.models import Project

User = get_user_model()


class TestIsDrawingSpecComparisonActive(TestCase):
    """Test is_drawing_spec_comparison_active feature flag helper"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )

    @patch('apps.utils.feature_flags.get_active_flags_for_user')
    @patch('apps.utils.feature_flags.get_active_flags_for_team')
    @patch('apps.utils.feature_flags.get_active_flags_for_project')
    @override_settings(DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME='drawing_spec_comparison')
    def test_returns_true_when_user_has_flag(self, mock_project, mock_team, mock_user):
        mock_user.return_value = ['drawing_spec_comparison']
        mock_team.return_value = []
        mock_project.return_value = []

        result = is_drawing_spec_comparison_active(self.user, self.team, self.project)
        self.assertTrue(result)

    @patch('apps.utils.feature_flags.get_active_flags_for_user')
    @patch('apps.utils.feature_flags.get_active_flags_for_team')
    @patch('apps.utils.feature_flags.get_active_flags_for_project')
    @override_settings(DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME='drawing_spec_comparison')
    def test_returns_true_when_team_has_flag(self, mock_project, mock_team, mock_user):
        mock_user.return_value = []
        mock_team.return_value = ['drawing_spec_comparison']
        mock_project.return_value = []

        result = is_drawing_spec_comparison_active(self.user, self.team, self.project)
        self.assertTrue(result)

    @patch('apps.utils.feature_flags.get_active_flags_for_user')
    @patch('apps.utils.feature_flags.get_active_flags_for_team')
    @patch('apps.utils.feature_flags.get_active_flags_for_project')
    @override_settings(DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME='drawing_spec_comparison')
    def test_returns_true_when_project_has_flag(self, mock_project, mock_team, mock_user):
        mock_user.return_value = []
        mock_team.return_value = []
        mock_project.return_value = ['drawing_spec_comparison']

        result = is_drawing_spec_comparison_active(self.user, self.team, self.project)
        self.assertTrue(result)

    @patch('apps.utils.feature_flags.get_active_flags_for_user')
    @patch('apps.utils.feature_flags.get_active_flags_for_team')
    @patch('apps.utils.feature_flags.get_active_flags_for_project')
    @override_settings(DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME='drawing_spec_comparison')
    def test_returns_false_when_no_flag(self, mock_project, mock_team, mock_user):
        mock_user.return_value = []
        mock_team.return_value = []
        mock_project.return_value = []

        result = is_drawing_spec_comparison_active(self.user, self.team, self.project)
        self.assertFalse(result)

    @patch('apps.utils.feature_flags.get_active_flags_for_user')
    @patch('apps.utils.feature_flags.get_active_flags_for_team')
    @override_settings(DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME='drawing_spec_comparison')
    def test_works_without_project(self, mock_team, mock_user):
        mock_user.return_value = ['drawing_spec_comparison']
        mock_team.return_value = []

        result = is_drawing_spec_comparison_active(self.user, self.team, project=None)
        self.assertTrue(result)
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.utils.tests.test_spec_comparison_feature_flag -v 2`
Expected: FAIL (function doesn't exist)

**Step 3: Add feature flag helper to feature_flags.py**

Add to `apps/utils/feature_flags.py`:

```python
def is_drawing_spec_comparison_active(user, team, project=None):
    """
    Check if the drawing spec comparison feature flag is active.

    Args:
        user: User object
        team: Team object
        project: Optional Project object

    Returns:
        bool: True if flag is active, False otherwise
    """
    return (
        settings.DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or
        settings.DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME in get_active_flags_for_team(team) or
        (project and settings.DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME in get_active_flags_for_project(project))
    )
```

**Step 4: Add settings to settings.py**

Add to `the_link/settings.py` near other feature flag settings:

```python
# Drawing Spec Comparison Feature
DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME = "drawing_spec_comparison"

SPEC_COMPARISON_LAMBDA_FUNCTION_URL = os.environ.get(
    "SPEC_COMPARISON_LAMBDA_FUNCTION_URL",
    ""
)

BACKEND_SPEC_COMPARISON_CALLBACK_URL = BACKEND_BASE_URL + "/api/deliverables/webhooks/spec-comparison/"

# Shared secret for webhook HMAC authentication (generate with: python -c "import secrets; print(secrets.token_hex(32))")
SPEC_COMPARISON_WEBHOOK_SECRET = os.environ.get(
    "SPEC_COMPARISON_WEBHOOK_SECRET",
    ""
)
```

**Step 5: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.utils.tests.test_spec_comparison_feature_flag -v 2`
Expected: PASS

**Step 6: Commit**

```bash
git add apps/utils/feature_flags.py apps/utils/tests/test_spec_comparison_feature_flag.py the_link/settings.py
git commit -m "$(cat <<'EOF'
feat: add drawing spec comparison feature flag and settings

- Add is_drawing_spec_comparison_active() helper
- Add DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME setting
- Add SPEC_COMPARISON_LAMBDA_FUNCTION_URL setting
- Add BACKEND_SPEC_COMPARISON_CALLBACK_URL setting

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add Admin Registration

**Files:**
- Modify: `apps/deliverables/admin.py`

**Step 1: Add admin registrations**

Add to `apps/deliverables/admin.py`:

```python
from .models import (
    SpecComparison,
    SpecComparisonWebhookEvent,
    SpecConflict,
    SkippedNote,
)


@admin.register(SpecComparison)
class SpecComparisonAdmin(admin.ModelAdmin):
    list_display = ['id', 'project', 'status', 'triggered_by', 'notes_processed', 'created_at', 'completed_at']
    list_filter = ['status', 'project']
    search_fields = ['project__name', 'event_id']
    raw_id_fields = ['project', 'project_version', 'triggered_by']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(SpecComparisonWebhookEvent)
class SpecComparisonWebhookEventAdmin(admin.ModelAdmin):
    list_display = ['id', 'event_id', 'comparison', 'new_status', 'created_at']
    list_filter = ['new_status']
    search_fields = ['event_id']
    raw_id_fields = ['comparison']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(SpecConflict)
class SpecConflictAdmin(admin.ModelAdmin):
    list_display = ['id', 'comparison', 'note_id_from_lambda', 'spec_masterformat_number', 'confidence', 'created_at']
    list_filter = ['comparison__status']
    search_fields = ['note_text', 'spec_text', 'note_id_from_lambda']
    raw_id_fields = ['comparison', 'note']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(SkippedNote)
class SkippedNoteAdmin(admin.ModelAdmin):
    list_display = ['id', 'comparison', 'note_id_from_lambda', 'reason', 'sheet_discipline', 'created_at']
    list_filter = ['reason', 'comparison__status']
    search_fields = ['note_id_from_lambda', 'detail']
    raw_id_fields = ['comparison', 'note']
    readonly_fields = ['created_at', 'updated_at']
```

**Step 2: Verify admin loads without errors**

Run: `docker-compose exec web python manage.py check`
Expected: System check identified no issues

**Step 3: Commit**

```bash
git add apps/deliverables/admin.py
git commit -m "$(cat <<'EOF'
feat: register SpecComparison models in Django admin

- Add SpecComparisonAdmin with filtering and search
- Add SpecComparisonWebhookEventAdmin for debugging
- Add SpecConflictAdmin with note/spec search
- Add SkippedNoteAdmin with reason filtering

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add Webhook Payload Serializers

**Files:**
- Create: `apps/deliverables/serializers/spec_comparison_serializers.py`

**Step 1: Write serializer tests**

Create `apps/deliverables/tests/test_spec_comparison_serializers.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_spec_comparison_serializers -v 2`
Expected: FAIL (serializers don't exist)

**Step 3: Create serializers file**

Create `apps/deliverables/serializers/spec_comparison_serializers.py`:

```python
import boto3
from django.conf import settings
from rest_framework import serializers

from ..models import (
    SpecComparison,
    SpecComparisonStatus,
    SpecConflict,
    SkippedNote,
    SkipReason,
)


# Initialize S3 client at module level (matches existing pattern)
s3 = boto3.client(
    "s3",
    region_name=settings.AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
)


# --- Webhook Payload Serializers (for validating incoming lambda data) ---


class PdfLocationSerializer(serializers.Serializer):
    """Validates PDF bounding box location data"""
    page_no = serializers.IntegerField()
    x = serializers.FloatField()
    y = serializers.FloatField()
    width = serializers.FloatField()
    height = serializers.FloatField()


class SpecConflictPayloadSerializer(serializers.Serializer):
    """Validates conflict data from lambda webhook payload"""
    note_id = serializers.CharField()
    note_text = serializers.CharField()
    spec_text = serializers.CharField()
    spec_source_file = serializers.CharField()
    spec_page_number = serializers.IntegerField(min_value=1)
    spec_masterformat_number = serializers.CharField()
    confidence = serializers.FloatField(min_value=0.0, max_value=1.0)
    reason = serializers.CharField()
    pdf_locations = PdfLocationSerializer(many=True, required=False, default=list)

    def validate_spec_source_file(self, value):
        """Enforce s3://{bucket}/{key} URI format and validate bucket matches our bucket."""
        if not value.startswith('s3://'):
            raise serializers.ValidationError(
                f"spec_source_file must be an s3:// URI, got: {value[:50]}"
            )
        # Validate format: s3://bucket/key (must have bucket AND key)
        parts = value[5:].split('/', 1)  # Remove 's3://'
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise serializers.ValidationError(
                f"spec_source_file must be s3://bucket/key format, got: {value[:50]}"
            )
        # Security: validate bucket matches our expected bucket (skip if S3_BUCKET not configured)
        bucket = parts[0]
        if settings.S3_BUCKET and bucket != settings.S3_BUCKET:
            raise serializers.ValidationError(
                f"spec_source_file bucket must be {settings.S3_BUCKET}, got: {bucket}"
            )
        return value


class SkippedNotePayloadSerializer(serializers.Serializer):
    """Validates skipped note data from lambda webhook payload"""
    note_id = serializers.CharField()
    disciplines = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list
    )
    sheet_discipline = serializers.CharField(required=False, allow_null=True)
    reason = serializers.ChoiceField(choices=SkipReason.choices)
    detail = serializers.CharField(required=False, allow_null=True)


class SpecComparisonWebhookSerializer(serializers.Serializer):
    """Validates the complete webhook payload from lambda"""
    event_id = serializers.CharField(required=True, allow_blank=False)
    comparison_id = serializers.IntegerField(required=True)
    status = serializers.ChoiceField(choices=[
        SpecComparisonStatus.SUCCESS,
        SpecComparisonStatus.PARTIAL_SUCCESS,
        SpecComparisonStatus.FAILED,
    ])  # Only terminal statuses allowed
    conflicts = SpecConflictPayloadSerializer(many=True, required=False, default=list)
    skipped_notes = SkippedNotePayloadSerializer(many=True, required=False, default=list)
    notes_processed = serializers.IntegerField(required=False, default=0, min_value=0)
    notes_skipped = serializers.IntegerField(required=False, default=0, min_value=0)
    spec_files_processed = serializers.IntegerField(required=False, default=0, min_value=0)
    notes_with_mismatch = serializers.IntegerField(required=False, default=0, min_value=0)
    error_message = serializers.CharField(required=False, allow_null=True)


# --- Read Serializers (for API responses) ---


class SpecComparisonSummarySerializer(serializers.ModelSerializer):
    """Lightweight serializer for comparison metadata in responses"""

    class Meta:
        model = SpecComparison
        fields = ['id', 'status', 'completed_at']


class SpecConflictReadSerializer(serializers.ModelSerializer):
    """Serializer for reading conflict data via API"""
    note_id = serializers.SerializerMethodField()
    spec_file_url = serializers.SerializerMethodField()

    class Meta:
        model = SpecConflict
        fields = [
            'id',
            'note_id',
            'note_id_from_lambda',
            'note_text',
            'spec_text',
            'spec_file_s3_key',
            'spec_file_url',
            'spec_page_number',
            'spec_masterformat_number',
            'confidence',
            'reason',
            'pdf_locations',
        ]

    def get_note_id(self, obj):
        """Return note.id if FK exists, otherwise fall back to note_id_from_lambda."""
        if obj.note:
            return obj.note.id
        # Fall back to lambda-provided ID (may be string for non-integer IDs)
        return obj.note_id_from_lambda

    def get_spec_file_url(self, obj):
        """Generate presigned S3 URL for spec file access."""
        # Memoize URLs per s3_key within request context to avoid redundant S3 calls
        context = self.context
        cache_key = f'presigned_urls'
        if cache_key not in context:
            context[cache_key] = {}

        s3_key = obj.spec_file_s3_key
        if s3_key not in context[cache_key]:
            context[cache_key][s3_key] = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': settings.S3_BUCKET, 'Key': s3_key},
                ExpiresIn=3600,
            )
        return context[cache_key][s3_key]


class SkippedNoteReadSerializer(serializers.ModelSerializer):
    """Serializer for reading skipped note data via API"""
    note_id = serializers.SerializerMethodField()

    class Meta:
        model = SkippedNote
        fields = [
            'id',
            'note_id',
            'note_id_from_lambda',
            'disciplines',
            'sheet_discipline',
            'reason',
            'detail',
        ]

    def get_note_id(self, obj):
        """Return note.id if FK exists, otherwise fall back to note_id_from_lambda."""
        if obj.note:
            return obj.note.id
        return obj.note_id_from_lambda


class SpecComparisonListSerializer(serializers.ModelSerializer):
    """Serializer for listing comparison runs"""
    triggered_by = serializers.SerializerMethodField()
    conflict_count = serializers.SerializerMethodField()

    class Meta:
        model = SpecComparison
        fields = [
            'id',
            'status',
            'event_id',
            'created_at',
            'started_at',
            'completed_at',
            'triggered_by',
            'notes_processed',
            'notes_skipped',
            'spec_files_processed',
            'conflict_count',
        ]

    def get_triggered_by(self, obj):
        if obj.triggered_by:
            return {'display_name': obj.triggered_by.get_full_name() or obj.triggered_by.email}
        return None

    def get_conflict_count(self, obj):
        # Use annotated count if available (from queryset with annotate),
        # otherwise fall back to counting (less efficient)
        if hasattr(obj, 'conflict_count_annotated'):
            return obj.conflict_count_annotated
        return obj.conflicts.count()


class TriggerSpecComparisonSerializer(serializers.Serializer):
    """Serializer for trigger endpoint request"""
    project_version_id = serializers.IntegerField(required=True)


class TriggerSpecComparisonResponseSerializer(serializers.ModelSerializer):
    """Serializer for trigger endpoint response"""
    triggered_by = serializers.SerializerMethodField()

    class Meta:
        model = SpecComparison
        fields = [
            'id',
            'status',
            'event_id',
            'created_at',
            'started_at',
            'triggered_by',
        ]

    def get_triggered_by(self, obj):
        if obj.triggered_by:
            return {
                'id': obj.triggered_by.id,
                'display_name': obj.triggered_by.get_full_name() or obj.triggered_by.email,
            }
        return None
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_spec_comparison_serializers -v 2`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/serializers/spec_comparison_serializers.py apps/deliverables/tests/test_spec_comparison_serializers.py
git commit -m "$(cat <<'EOF'
feat: add SpecComparison serializers for webhook and API

- Add PdfLocationSerializer for bounding box validation
- Add SpecConflictPayloadSerializer with s3:// URI validation
- Add SkippedNotePayloadSerializer with reason validation
- Add SpecComparisonWebhookSerializer for lambda payload
- Add read serializers for API responses
- Add trigger request/response serializers

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add Webhook Endpoint

**Files:**
- Create: `apps/deliverables/views/spec_comparison_views.py`
- Modify: `apps/deliverables/urls.py`

**Step 1: Write webhook endpoint tests**

Create `apps/deliverables/tests/test_spec_comparison_webhook.py`:

```python
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


@override_settings(S3_BUCKET='bucket', SPEC_COMPARISON_WEBHOOK_SECRET='', DEBUG=True)
class TestSpecComparisonWebhook(APITestCase):
    """Test the spec comparison webhook endpoint"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
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

    def test_success_webhook_creates_conflicts(self):
        """Test successful webhook creates conflict records"""
        payload = {
            'event_id': 'test-event-id-123',
            'comparison_id': self.comparison.id,
            'status': 'SUCCESS',
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
            'spec_files_processed': 10,
            'notes_with_mismatch': 3,
        }

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
        payload = {
            'event_id': 'test-event-id-123',
            'comparison_id': self.comparison.id,
            'status': 'SUCCESS',
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
            'spec_files_processed': 5,
            'notes_with_mismatch': 0,
        }

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
        payload = {
            'event_id': 'test-event-id-123',
            'comparison_id': self.comparison.id,
            'status': 'FAILED',
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
        payload = {
            'event_id': 'test-event-id-123',
            'comparison_id': self.comparison.id,
            'status': 'SUCCESS',
            'conflicts': [],
            'skipped_notes': [],
            'notes_processed': 100,
        }

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
        payload = {
            'event_id': 'wrong-event-id',
            'comparison_id': self.comparison.id,
            'status': 'SUCCESS',
        }

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Event ID mismatch', response.data['error'])

    def test_comparison_not_found_returns_404(self):
        """Test non-existent comparison returns 404"""
        payload = {
            'event_id': 'some-event-id',
            'comparison_id': 99999,
            'status': 'SUCCESS',
        }

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
        }

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_spec_source_file_returns_400(self):
        """Test invalid spec_source_file format returns 400"""
        payload = {
            'event_id': 'test-event-id-123',
            'comparison_id': self.comparison.id,
            'status': 'SUCCESS',
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

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_note_fk_null_when_not_found(self):
        """Test note FK is null when note_id not found"""
        payload = {
            'event_id': 'test-event-id-123',
            'comparison_id': self.comparison.id,
            'status': 'SUCCESS',
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
        payload = {
            'event_id': 'test-event-id-123',
            'comparison_id': self.comparison.id,
            'status': 'SUCCESS',
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
        payload = {
            'event_id': 'test-event-id-123',
            'comparison_id': self.comparison.id,
            'status': 'PARTIAL_SUCCESS',
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

    @override_settings(SPEC_COMPARISON_WEBHOOK_SECRET='test-secret-key')
    def test_invalid_signature_returns_401(self):
        """Test invalid HMAC signature returns 401"""
        payload = {
            'event_id': 'test-event-id-123',
            'comparison_id': self.comparison.id,
            'status': 'SUCCESS',
        }

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_WEBHOOK_SIGNATURE='sha256=invalid-signature'
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(SPEC_COMPARISON_WEBHOOK_SECRET='test-secret-key')
    def test_missing_signature_returns_401(self):
        """Test missing HMAC signature returns 401"""
        payload = {
            'event_id': 'test-event-id-123',
            'comparison_id': self.comparison.id,
            'status': 'SUCCESS',
        }

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
            # No X-Webhook-Signature header
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(SPEC_COMPARISON_WEBHOOK_SECRET='test-secret-key')
    def test_valid_signature_accepted(self):
        """Test valid HMAC signature is accepted"""
        import hmac
        import hashlib

        payload = json.dumps({
            'event_id': 'test-event-id-123',
            'comparison_id': self.comparison.id,
            'status': 'SUCCESS',
            'notes_processed': 10,
        })

        signature = hmac.new(
            b'test-secret-key',
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        response = self.client.post(
            self.webhook_url,
            data=payload,
            content_type='application/json',
            HTTP_X_WEBHOOK_SIGNATURE=f'sha256={signature}'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_spec_comparison_webhook -v 2`
Expected: FAIL (view doesn't exist, URL not configured)

**Step 3: Create the webhook view**

Create `apps/deliverables/views/spec_comparison_views.py`:

```python
import logging
from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ..models import (
    SpecComparison,
    SpecComparisonStatus,
    SpecComparisonWebhookEvent,
    SpecConflict,
    SkippedNote,
    DrawingNote,
)
from ..serializers.spec_comparison_serializers import (
    SpecComparisonWebhookSerializer,
)

logger = logging.getLogger(__name__)


def parse_s3_uri_to_key(s3_uri: str) -> str:
    """Extract S3 key from s3://bucket/key URI.

    Only accepts s3:// URIs (validated by serializer).
    """
    # s3://bucket/path/to/file.pdf -> path/to/file.pdf
    parts = s3_uri[5:].split('/', 1)  # Remove 's3://'
    if len(parts) > 1:
        return parts[1]
    raise ValueError(f"Invalid S3 URI format: {s3_uri}")


def safe_int(value: str) -> int | None:
    """Safely convert string to int, return None if invalid."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def verify_webhook_signature(request) -> bool:
    """Verify HMAC signature from lambda webhook.

    Lambda should send signature in X-Webhook-Signature header as:
    sha256=<hex_digest>

    The signature is computed as HMAC-SHA256 of the request body using
    SPEC_COMPARISON_WEBHOOK_SECRET as the key.

    SECURITY: Fails closed in production (DEBUG=False) when secret is not configured.
    """
    import hmac
    import hashlib

    secret = settings.SPEC_COMPARISON_WEBHOOK_SECRET
    if not secret:
        # Fail closed in production - require secret to be configured
        if not settings.DEBUG:
            logger.error("SPEC_COMPARISON_WEBHOOK_SECRET not set in production - rejecting webhook")
            return False
        # In development (DEBUG=True), allow requests but warn
        logger.warning("SPEC_COMPARISON_WEBHOOK_SECRET not set - webhook authentication disabled (dev only)")
        return True

    signature_header = request.headers.get('X-Webhook-Signature', '')
    if not signature_header.startswith('sha256='):
        return False

    expected_signature = signature_header[7:]  # Remove 'sha256=' prefix
    body = request.body

    computed_signature = hmac.new(
        secret.encode('utf-8'),
        body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_signature, expected_signature)


@api_view(['POST'])
@permission_classes([AllowAny])
def spec_comparison_webhook(request):
    """
    Webhook endpoint for receiving spec comparison results from AWS Lambda.
    Idempotent: duplicate event_ids are ignored.
    Atomic: all changes within a single transaction.
    Authenticated: HMAC signature verified if SPEC_COMPARISON_WEBHOOK_SECRET is set.
    """
    # Verify webhook signature (HMAC authentication)
    if not verify_webhook_signature(request):
        return Response(
            {"error": "Invalid webhook signature"},
            status=status.HTTP_401_UNAUTHORIZED
        )

    # Validate payload
    serializer = SpecComparisonWebhookSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"error": "Invalid payload", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    data = serializer.validated_data
    event_id = data['event_id']
    comparison_id = data['comparison_id']
    new_status = data['status']

    with transaction.atomic():
        # Lock comparison row to prevent races
        try:
            comparison = SpecComparison.objects.select_for_update().get(id=comparison_id)
        except SpecComparison.DoesNotExist:
            return Response(
                {"error": "Comparison not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Verify event_id matches
        if comparison.event_id != event_id:
            return Response(
                {"error": "Event ID mismatch"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create webhook event for idempotency (unique constraint on event_id)
        try:
            SpecComparisonWebhookEvent.objects.create(
                comparison=comparison,
                event_id=event_id,
                new_status=new_status,
            )
        except IntegrityError:
            # Duplicate event_id - already processed
            return Response({"status": "already_processed"}, status=status.HTTP_200_OK)

        # Update comparison metadata
        comparison.status = new_status
        comparison.notes_processed = data['notes_processed']
        comparison.notes_skipped = data['notes_skipped']
        comparison.spec_files_processed = data['spec_files_processed']
        comparison.notes_with_mismatch = data['notes_with_mismatch']
        comparison.completed_at = timezone.now()

        if new_status == SpecComparisonStatus.FAILED:
            comparison.error_message = data.get('error_message')
            comparison.save()
            # FAILED: Do not store conflicts/skipped notes (no partial data)
            return Response({"status": "processed"}, status=status.HTTP_200_OK)

        comparison.save()

        # SUCCESS/PARTIAL_SUCCESS: Store conflicts and skipped notes

        # Build note ID lookup for FK linking (safely handle non-integer IDs)
        conflict_note_ids = [c['note_id'] for c in data['conflicts']]
        skipped_note_ids = [s['note_id'] for s in data['skipped_notes']]
        all_note_ids_raw = set(conflict_note_ids + skipped_note_ids)

        # Safely convert to integers, filtering out invalid IDs
        valid_note_ids = [safe_int(nid) for nid in all_note_ids_raw]
        valid_note_ids = [nid for nid in valid_note_ids if nid is not None]

        notes_by_id = {}
        if valid_note_ids:
            # Scope note lookup to the comparison's project/version for security
            notes_by_id = {
                str(n.id): n
                for n in DrawingNote.objects.filter(
                    id__in=valid_note_ids,
                    section__page__extraction__drawing_file__project=comparison.project,
                    section__page__extraction__drawing_file__project_version=comparison.project_version,
                )
            }

        # Create conflicts (with batch_size for large lists)
        if data['conflicts']:
            conflicts_to_create = [
                SpecConflict(
                    comparison=comparison,
                    note=notes_by_id.get(c['note_id']),
                    note_id_from_lambda=c['note_id'],
                    note_text=c['note_text'],
                    spec_text=c['spec_text'],
                    spec_file_s3_key=parse_s3_uri_to_key(c['spec_source_file']),
                    spec_page_number=c['spec_page_number'],
                    spec_masterformat_number=c['spec_masterformat_number'],
                    confidence=c['confidence'],
                    reason=c['reason'],
                    pdf_locations=c.get('pdf_locations', []),
                )
                for c in data['conflicts']
            ]
            SpecConflict.objects.bulk_create(conflicts_to_create, batch_size=500)

        # Create skipped notes (with batch_size for large lists)
        if data['skipped_notes']:
            skipped_to_create = [
                SkippedNote(
                    comparison=comparison,
                    note=notes_by_id.get(s['note_id']),
                    note_id_from_lambda=s['note_id'],
                    disciplines=s.get('disciplines', []),
                    sheet_discipline=s.get('sheet_discipline'),
                    reason=s['reason'],
                    detail=s.get('detail'),
                )
                for s in data['skipped_notes']
            ]
            SkippedNote.objects.bulk_create(skipped_to_create, batch_size=500)

    return Response({"status": "processed"}, status=status.HTTP_200_OK)
```

**Step 4: Add URL route**

Add to `apps/deliverables/urls.py`:

```python
from .views.spec_comparison_views import spec_comparison_webhook

# Add to urlpatterns:
path('webhooks/spec-comparison/', spec_comparison_webhook, name='spec-comparison-webhook'),
```

**Step 5: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_spec_comparison_webhook -v 2`
Expected: PASS

**Step 6: Commit**

```bash
git add apps/deliverables/views/spec_comparison_views.py apps/deliverables/tests/test_spec_comparison_webhook.py apps/deliverables/urls.py
git commit -m "$(cat <<'EOF'
feat: add spec comparison webhook endpoint

- Add POST /webhooks/spec-comparison/ endpoint
- Implement idempotency via unique event_id constraint
- Use select_for_update for race-safe processing
- Store conflicts and skipped notes on SUCCESS/PARTIAL_SUCCESS
- Handle FAILED status without storing partial data
- Gracefully handle non-integer note IDs

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Add Trigger Endpoint

**Files:**
- Modify: `apps/deliverables/views/spec_comparison_views.py`
- Modify: `apps/deliverables/urls.py`

**Step 1: Write trigger endpoint tests**

Create `apps/deliverables/tests/test_spec_comparison_trigger.py`:

```python
import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status

from apps.deliverables.models import (
    Project,
    ProjectMembership,
    SpecComparison,
    SpecComparisonStatus,
    SpecSection,
    MasterFormatSection,
    UploadedFile,
    DrawingFile,
    DrawingExtraction,
    DrawingExtractionStatus,
    DrawingPage,
    DrawingNoteSection,
    DrawingNote,
)
from apps.teams.models import Team

User = get_user_model()


class TestTriggerSpecComparison(APITestCase):
    """Test the trigger spec comparison endpoint"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
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
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role='project_member'
        )

        # Create drawing notes
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

        # Create spec sections
        self.masterformat = MasterFormatSection.objects.create(
            masterformat_number='220500',
            masterformat_description='Common Work Results'
        )
        self.uploaded_file = UploadedFile.objects.create(
            project=self.project,
            project_version=self.project_version,
            document_path='specs/test.pdf',
            name='test.pdf',
            md5='def456',
            processing_status='PROCESSED',
        )
        self.spec_section = SpecSection.objects.create(
            masterformat_section=self.masterformat,
            document=self.uploaded_file,
            file_s3_key='specs/test.pdf',
        )

        self.client.force_authenticate(user=self.user)
        self.trigger_url = reverse(
            'deliverables:trigger-spec-comparison',
            kwargs={'project_id': self.project.id}
        )

    def test_missing_project_version_id_returns_400(self):
        """Test 400 when project_version_id is not provided"""
        response = self.client.post(self.trigger_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('project_version_id', str(response.data))

    @patch('apps.deliverables.views.spec_comparison_views.is_drawing_spec_comparison_active')
    @patch('apps.deliverables.views.spec_comparison_views.invoke_spec_comparison_lambda')
    @patch('apps.deliverables.views.spec_comparison_views.upload_payload_to_s3')
    def test_successful_trigger(self, mock_upload, mock_invoke, mock_flag):
        """Test successful comparison trigger"""
        mock_flag.return_value = True
        mock_upload.return_value = 'spec-comparisons/1/payload.json'
        mock_invoke.return_value = None

        response = self.client.post(
            self.trigger_url,
            data={'project_version_id': self.project_version.id},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], SpecComparisonStatus.PROCESSING)
        self.assertIn('event_id', response.data)

        # Verify comparison created
        comparison = SpecComparison.objects.get(id=response.data['id'])
        self.assertEqual(comparison.project, self.project)
        self.assertEqual(comparison.project_version, self.project_version)
        self.assertEqual(comparison.status, SpecComparisonStatus.PROCESSING)
        self.assertIsNotNone(comparison.started_at)

    @patch('apps.deliverables.views.spec_comparison_views.is_drawing_spec_comparison_active')
    def test_feature_flag_disabled_returns_403(self, mock_flag):
        """Test 403 when feature flag is disabled"""
        mock_flag.return_value = False

        response = self.client.post(
            self.trigger_url,
            data={'project_version_id': self.project_version.id},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.deliverables.views.spec_comparison_views.is_drawing_spec_comparison_active')
    def test_no_notes_returns_400(self, mock_flag):
        """Test 400 when no drawing notes exist"""
        mock_flag.return_value = True
        DrawingNote.objects.all().delete()

        response = self.client.post(
            self.trigger_url,
            data={'project_version_id': self.project_version.id},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('No drawing notes', response.data['error'])

    @patch('apps.deliverables.views.spec_comparison_views.is_drawing_spec_comparison_active')
    def test_no_specs_returns_400(self, mock_flag):
        """Test 400 when no spec sections exist"""
        mock_flag.return_value = True
        SpecSection.objects.all().delete()

        response = self.client.post(
            self.trigger_url,
            data={'project_version_id': self.project_version.id},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('No spec sections', response.data['error'])

    def test_unauthenticated_returns_403(self):
        """Test 403 for unauthenticated requests"""
        self.client.force_authenticate(user=None)

        response = self.client.post(self.trigger_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_member_returns_403(self):
        """Test 403 for non-project members"""
        other_user = User.objects.create_user(
            email='other@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=other_user)

        response = self.client.post(self.trigger_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.deliverables.views.spec_comparison_views.is_drawing_spec_comparison_active')
    @patch('apps.deliverables.views.spec_comparison_views.invoke_spec_comparison_lambda')
    @patch('apps.deliverables.views.spec_comparison_views.upload_payload_to_s3')
    def test_lambda_invoke_failure_sets_failed_status(self, mock_upload, mock_invoke, mock_flag):
        """Test that lambda invoke failure sets FAILED status"""
        mock_flag.return_value = True
        mock_upload.return_value = 'spec-comparisons/1/payload.json'
        mock_invoke.side_effect = Exception('Lambda timeout')

        response = self.client.post(
            self.trigger_url,
            data={'project_version_id': self.project_version.id},
            format='json'
        )

        # Should still return 201 but with FAILED status
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], SpecComparisonStatus.FAILED)

        # Verify comparison has error
        comparison = SpecComparison.objects.get(id=response.data['id'])
        self.assertEqual(comparison.status, SpecComparisonStatus.FAILED)
        self.assertIn('Lambda timeout', comparison.error_message)
        self.assertIsNotNone(comparison.completed_at)

    @patch('apps.deliverables.views.spec_comparison_views.is_drawing_spec_comparison_active')
    def test_invalid_project_version_id_returns_400(self, mock_flag):
        """Test 400 for invalid project_version_id"""
        mock_flag.return_value = True

        response = self.client.post(
            self.trigger_url,
            data={'project_version_id': 99999},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Project version not found', response.data['error'])

    def test_project_not_found_returns_404(self):
        """Test 404 for non-existent project"""
        url = reverse(
            'deliverables:trigger-spec-comparison',
            kwargs={'project_id': 99999}
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_spec_comparison_trigger -v 2`
Expected: FAIL (view and URL don't exist)

**Step 3: Add trigger view to spec_comparison_views.py**

Add to `apps/deliverables/views/spec_comparison_views.py`:

```python
import json
import uuid
import requests
from django.conf import settings
from django.db.models import Subquery, OuterRef, Count
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import (
    Project,
    ProjectVersion,
    SpecComparison,
    SpecComparisonStatus,
    DrawingNote,
    DrawingExtraction,
    DrawingExtractionStatus,
    SpecSection,
)
from ..serializers.spec_comparison_serializers import (
    TriggerSpecComparisonSerializer,
    TriggerSpecComparisonResponseSerializer,
)
from apps.utils.feature_flags import is_drawing_spec_comparison_active

# Import S3 client (reuse from drawing_serializers pattern)
import boto3
s3 = boto3.client(
    "s3",
    region_name=settings.AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
)


def get_notes_queryset(project, project_version):
    """Get notes from the latest successful extraction per drawing file.

    Includes both SUCCESS and PARTIAL_SUCCESS extractions to match
    the DrawingExtractionStatus enum.
    """
    # Subquery: latest successful extraction ID per drawing file
    latest_extraction_subquery = DrawingExtraction.objects.filter(
        drawing_file=OuterRef('section__page__extraction__drawing_file'),
        drawing_file__project=project,
        drawing_file__project_version=project_version,
        status__in=[DrawingExtractionStatus.SUCCESS, DrawingExtractionStatus.PARTIAL_SUCCESS],
    ).order_by('-created_at').values('id')[:1]

    return DrawingNote.objects.filter(
        section__page__extraction__drawing_file__project=project,
        section__page__extraction__drawing_file__project_version=project_version,
        section__page__extraction__id=Subquery(latest_extraction_subquery),
    ).select_related('section__page')


def get_specs_queryset(project, project_version):
    """Get spec sections with valid S3 keys."""
    return SpecSection.objects.filter(
        document__project=project,
        document__project_version=project_version,
        file_s3_key__isnull=False,
    ).exclude(
        file_s3_key=''
    ).select_related('masterformat_section')


def build_comparison_payload(project, project_version, comparison_id, event_id):
    """Build the payload to send to lambda."""
    drawing_notes = get_notes_queryset(project, project_version)
    spec_sections = get_specs_queryset(project, project_version)

    payload = {
        "comparison_id": comparison_id,
        "event_id": event_id,
        "notes": [
            {
                "id": str(note.id),
                "text": note.text,
                "disciplines": note.disciplines or [],
                "sheet_discipline": note.section.page.sheet_discipline,
                "sheet_number": note.section.page.sheet_number,
                "sheet_title": note.section.page.sheet_title,
            }
            for note in drawing_notes
        ],
        "spec_files": [
            {
                "s3_uri": f"s3://{settings.S3_BUCKET}/{spec.file_s3_key}",
                "s3_key": spec.file_s3_key,
                "masterformat_number": spec.masterformat_section.masterformat_number,
            }
            for spec in spec_sections
        ],
        "callback_url": settings.BACKEND_SPEC_COMPARISON_CALLBACK_URL,
    }

    return payload


def upload_payload_to_s3(payload, comparison_id):
    """Upload payload JSON to S3 and return the key."""
    payload_s3_key = f"spec-comparisons/{comparison_id}/payload.json"
    s3.put_object(
        Bucket=settings.S3_BUCKET,
        Key=payload_s3_key,
        Body=json.dumps(payload),
        ContentType='application/json',
    )
    return payload_s3_key


def invoke_spec_comparison_lambda(payload_s3_key, comparison_id, event_id):
    """Invoke the lambda function with S3 pointer.

    Raises exception if lambda returns non-2xx status or times out unexpectedly.
    ReadTimeout is expected for large payloads as lambda processes asynchronously.
    """
    if not settings.SPEC_COMPARISON_LAMBDA_FUNCTION_URL:
        raise ValueError("SPEC_COMPARISON_LAMBDA_FUNCTION_URL is not set")

    lambda_payload = {
        "payload_s3_uri": f"s3://{settings.S3_BUCKET}/{payload_s3_key}",
        "callback_url": settings.BACKEND_SPEC_COMPARISON_CALLBACK_URL,
        "comparison_id": comparison_id,
        "event_id": event_id,
    }

    try:
        response = requests.post(
            settings.SPEC_COMPARISON_LAMBDA_FUNCTION_URL,
            json=lambda_payload,
            timeout=2
        )
        # Check for non-2xx status codes (lambda invocation errors)
        response.raise_for_status()
    except requests.exceptions.ReadTimeout:
        # If we timed out, the lambda is processing - this is expected
        pass
    except requests.exceptions.HTTPError as e:
        # Lambda returned an error status code
        raise Exception(f"Lambda invocation failed: {e.response.status_code} - {e.response.text[:200]}")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_spec_comparison(request, project_id):
    """
    Trigger a new spec comparison for a project.

    POST /api/deliverables/projects/{project_id}/trigger-spec-comparison/
    """
    # Get project
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return Response(
            {"error": "Project not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    # Check project membership
    if not request.user.is_member_of_project(project_id):
        return Response(
            {"error": "Not authorized to access this project"},
            status=status.HTTP_403_FORBIDDEN
        )

    # Check feature flag
    if not is_drawing_spec_comparison_active(request.user, project.team, project):
        return Response(
            {"error": "Feature not enabled for this project"},
            status=status.HTTP_403_FORBIDDEN
        )

    # Parse request body
    serializer = TriggerSpecComparisonSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"error": "Invalid request", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Resolve project version (required parameter)
    project_version_id = serializer.validated_data['project_version_id']
    try:
        project_version = ProjectVersion.objects.get(
            id=project_version_id,
            project=project
        )
    except ProjectVersion.DoesNotExist:
        return Response(
            {"error": "Project version not found or does not belong to this project"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Pre-validate: count notes and specs
    notes_count = get_notes_queryset(project, project_version).count()
    specs_count = get_specs_queryset(project, project_version).count()

    if notes_count == 0:
        return Response(
            {"error": "No drawing notes found for comparison"},
            status=status.HTTP_400_BAD_REQUEST
        )
    if specs_count == 0:
        return Response(
            {"error": "No spec sections found for comparison"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Create comparison with server-generated event_id
    # Set PROCESSING status BEFORE invoking lambda to prevent race condition
    # where webhook returns before we update status
    event_id = str(uuid.uuid4())
    comparison = SpecComparison.objects.create(
        project=project,
        project_version=project_version,
        triggered_by=request.user,
        status=SpecComparisonStatus.PROCESSING,  # Start as PROCESSING, not PENDING
        event_id=event_id,
        started_at=timezone.now(),
    )

    try:
        # Build and upload payload
        payload = build_comparison_payload(project, project_version, comparison.id, event_id)
        payload_s3_key = upload_payload_to_s3(payload, comparison.id)
        comparison.payload_s3_key = payload_s3_key
        comparison.save()

        # Invoke lambda (status already PROCESSING)
        invoke_spec_comparison_lambda(payload_s3_key, comparison.id, event_id)

    except Exception as e:
        comparison.status = SpecComparisonStatus.FAILED
        comparison.error_message = str(e)
        comparison.completed_at = timezone.now()
        comparison.save()
        logger.error(f"Failed to trigger spec comparison {comparison.id}: {e}")

    response_serializer = TriggerSpecComparisonResponseSerializer(comparison)
    return Response(response_serializer.data, status=status.HTTP_201_CREATED)
```

**Step 4: Add URL route**

Add to `apps/deliverables/urls.py`:

```python
from .views.spec_comparison_views import spec_comparison_webhook, trigger_spec_comparison

# Add to urlpatterns (within projects path):
path('projects/<int:project_id>/trigger-spec-comparison/', trigger_spec_comparison, name='trigger-spec-comparison'),
```

**Step 5: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_spec_comparison_trigger -v 2`
Expected: PASS

**Step 6: Commit**

```bash
git add apps/deliverables/views/spec_comparison_views.py apps/deliverables/tests/test_spec_comparison_trigger.py apps/deliverables/urls.py
git commit -m "$(cat <<'EOF'
feat: add trigger spec comparison endpoint

- Add POST /projects/{id}/trigger-spec-comparison/ endpoint
- Validate feature flag, project membership, notes/specs existence
- Build payload with notes and spec files
- Upload payload to S3 for large payloads
- Invoke lambda and handle failures gracefully
- Support optional project_version_id parameter

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Add Read Endpoints

**Files:**
- Modify: `apps/deliverables/views/spec_comparison_views.py`
- Modify: `apps/deliverables/urls.py`

**Step 1: Write read endpoint tests**

Create `apps/deliverables/tests/test_spec_comparison_read.py`:

```python
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from unittest.mock import patch

from apps.deliverables.models import (
    Project,
    ProjectMembership,
    SpecComparison,
    SpecComparisonStatus,
    SpecConflict,
    SkippedNote,
    SkipReason,
)
from apps.teams.models import Team

User = get_user_model()


class TestSpecConflictsEndpoint(APITestCase):
    """Test GET /projects/{id}/spec-conflicts/ endpoint"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
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
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role='project_member'
        )

        # Create a successful comparison with conflicts
        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event-1',
            completed_at='2026-02-02T10:00:00Z',
        )
        self.conflict1 = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='1',
            note_text='Note 1',
            spec_text='Spec 1',
            spec_file_s3_key='specs/plumbing.pdf',
            spec_page_number=15,
            spec_masterformat_number='220500',
            confidence=0.85,
            reason='Conflict 1',
        )
        self.conflict2 = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='2',
            note_text='Note 2',
            spec_text='Spec 2',
            spec_file_s3_key='specs/mechanical.pdf',
            spec_page_number=20,
            spec_masterformat_number='230500',
            confidence=0.75,
            reason='Conflict 2',
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse(
            'deliverables:spec-conflicts',
            kwargs={'project_id': self.project.id}
        )

    def test_missing_project_version_id_returns_400(self):
        """Test 400 when project_version_id is not provided"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('project_version_id', response.data['error'])

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_returns_conflicts_from_latest_successful(self, mock_presigned):
        """Test returns conflicts from latest successful comparison"""
        mock_presigned.return_value = 'https://presigned-url.com/file.pdf'

        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['comparison']['id'], self.comparison.id)
        self.assertEqual(len(response.data['results']), 2)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_excludes_failed_comparisons_from_latest(self, mock_presigned):
        """Test 'latest' excludes FAILED comparisons"""
        mock_presigned.return_value = 'https://presigned-url.com/file.pdf'

        # Create a newer FAILED comparison
        SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.FAILED,
            event_id='test-event-2',
            completed_at='2026-02-02T11:00:00Z',  # Newer
        )

        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        # Should still return the successful comparison
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['comparison']['id'], self.comparison.id)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_by_comparison_id(self, mock_presigned):
        """Test filtering by comparison_id"""
        mock_presigned.return_value = 'https://presigned-url.com/file.pdf'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'comparison_id': self.comparison.id
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['comparison']['id'], self.comparison.id)

    def test_comparison_id_wrong_project_returns_404(self):
        """Test comparison_id from different project returns 404"""
        other_project = Project.objects.create(
            name='Other Project',
            project_number='P-OTHER',
            team=self.team,
            created_by=self.user
        )
        other_comparison = SpecComparison.objects.create(
            project=other_project,
            project_version=other_project.versions.first(),
            status=SpecComparisonStatus.SUCCESS,
            event_id='other-event',
        )

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'comparison_id': other_comparison.id
        })

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_returns_403(self):
        """Test 403 for unauthenticated requests"""
        self.client.force_authenticate(user=None)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_member_returns_403(self):
        """Test 403 for non-project members"""
        other_user = User.objects.create_user(
            email='other@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=other_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_empty_results_when_no_comparisons(self):
        """Test empty results when no comparisons exist"""
        SpecComparison.objects.all().delete()

        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)
        self.assertIsNone(response.data['comparison'])

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_pagination(self, mock_presigned):
        """Test pagination works correctly"""
        mock_presigned.return_value = 'https://presigned-url.com/file.pdf'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'limit': 1
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertIsNotNone(response.data['next'])

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_deterministic_ordering(self, mock_presigned):
        """Test results are ordered by id for deterministic pagination"""
        mock_presigned.return_value = 'https://presigned-url.com/file.pdf'

        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        results = response.data['results']
        self.assertEqual(results[0]['id'], self.conflict1.id)
        self.assertEqual(results[1]['id'], self.conflict2.id)


class TestSkippedNotesEndpoint(APITestCase):
    """Test GET /projects/{id}/skipped-notes/ endpoint"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
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
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role='project_member'
        )

        # Create a successful comparison with skipped notes
        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event-1',
            completed_at='2026-02-02T10:00:00Z',
        )
        self.skipped1 = SkippedNote.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='1',
            disciplines=['plumbing'],
            sheet_discipline='mechanical',
            reason=SkipReason.NO_MATCHING_SPECS,
            detail='Division 22 has no specs',
        )
        self.skipped2 = SkippedNote.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='2',
            reason=SkipReason.UNKNOWN_DISCIPLINE,
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse(
            'deliverables:skipped-notes',
            kwargs={'project_id': self.project.id}
        )

    def test_missing_project_version_id_returns_400(self):
        """Test 400 when project_version_id is not provided"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('project_version_id', response.data['error'])

    def test_returns_skipped_notes(self):
        """Test returns skipped notes from latest successful comparison"""
        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)

    def test_filter_by_reason(self):
        """Test filtering by reason"""
        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'reason': 'no_matching_specs'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['reason'], 'no_matching_specs')


class TestSpecComparisonsListEndpoint(APITestCase):
    """Test GET /projects/{id}/spec-comparisons/ endpoint"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
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
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role='project_member'
        )

        self.comparison1 = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            triggered_by=self.user,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event-1',
            notes_processed=100,
        )
        self.comparison2 = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.FAILED,
            event_id='test-event-2',
            error_message='Lambda timeout',
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse(
            'deliverables:spec-comparisons-list',
            kwargs={'project_id': self.project.id}
        )

    def test_lists_all_comparisons(self):
        """Test lists all comparisons for project"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)

    def test_includes_triggered_by(self):
        """Test includes triggered_by info"""
        response = self.client.get(self.url)

        results = response.data['results']
        # Find the comparison with triggered_by
        comparison_with_user = next(
            (r for r in results if r['id'] == self.comparison1.id),
            None
        )
        self.assertIsNotNone(comparison_with_user)
        self.assertIsNotNone(comparison_with_user['triggered_by'])
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_spec_comparison_read -v 2`
Expected: FAIL (views and URLs don't exist)

**Step 3: Add read views**

Add to `apps/deliverables/views/spec_comparison_views.py`:

```python
from rest_framework.pagination import PageNumberPagination

from ..serializers.spec_comparison_serializers import (
    SpecComparisonSummarySerializer,
    SpecConflictReadSerializer,
    SkippedNoteReadSerializer,
    SpecComparisonListSerializer,
)


class SpecComparisonPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'limit'  # Use 'limit' for consistency with DrawingNotePagination
    max_page_size = 100


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_spec_conflicts(request, project_id):
    """
    Get spec conflicts from the latest successful comparison.

    GET /api/deliverables/projects/{project_id}/spec-conflicts/
    Query params:
        - comparison_id: Filter to specific comparison
        - project_version_id: Required - the version to query
        - page, limit: Pagination
    """
    # Get project and check access
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return Response(
            {"error": "Project not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    if not request.user.is_member_of_project(project_id):
        return Response(
            {"error": "Not authorized to access this project"},
            status=status.HTTP_403_FORBIDDEN
        )

    # Get version filter (required)
    project_version_id = request.query_params.get('project_version_id')
    if not project_version_id:
        return Response(
            {"error": "project_version_id is required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    try:
        project_version = ProjectVersion.objects.get(
            id=int(project_version_id),
            project=project
        )
    except (ValueError, ProjectVersion.DoesNotExist):
        return Response(
            {"error": "Invalid project_version_id"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Get comparison
    comparison_id = request.query_params.get('comparison_id')
    if comparison_id:
        try:
            comparison_id_int = int(comparison_id)
        except (ValueError, TypeError):
            return Response(
                {"error": "comparison_id must be an integer"},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            comparison = SpecComparison.objects.get(
                id=comparison_id_int,
                project=project,
                project_version=project_version
            )
        except SpecComparison.DoesNotExist:
            return Response(
                {"error": "Comparison not found or does not belong to this project/version"},
                status=status.HTTP_404_NOT_FOUND
            )
    else:
        # Get latest successful comparison for this version
        comparison = SpecComparison.objects.filter(
            project=project,
            project_version=project_version,
            status__in=[SpecComparisonStatus.SUCCESS, SpecComparisonStatus.PARTIAL_SUCCESS],
        ).order_by('-completed_at').first()

    if not comparison:
        return Response({
            'count': 0,
            'next': None,
            'previous': None,
            'comparison': None,
            'results': [],
        })

    # Get conflicts with pagination (select_related to avoid N+1 on note access)
    conflicts = SpecConflict.objects.filter(comparison=comparison).select_related('note').order_by('id')

    paginator = SpecComparisonPagination()
    page = paginator.paginate_queryset(conflicts, request)

    serializer = SpecConflictReadSerializer(page, many=True, context={'request': request})

    response = paginator.get_paginated_response(serializer.data)
    response.data['comparison'] = SpecComparisonSummarySerializer(comparison).data

    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_skipped_notes(request, project_id):
    """
    Get skipped notes from the latest successful comparison.

    GET /api/deliverables/projects/{project_id}/skipped-notes/
    Query params:
        - comparison_id: Filter to specific comparison
        - project_version_id: Required - the version to query
        - reason: Filter by skip reason
        - page, limit: Pagination
    """
    # Get project and check access
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return Response(
            {"error": "Project not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    if not request.user.is_member_of_project(project_id):
        return Response(
            {"error": "Not authorized to access this project"},
            status=status.HTTP_403_FORBIDDEN
        )

    # Get version filter (required)
    project_version_id = request.query_params.get('project_version_id')
    if not project_version_id:
        return Response(
            {"error": "project_version_id is required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    try:
        project_version = ProjectVersion.objects.get(
            id=int(project_version_id),
            project=project
        )
    except (ValueError, ProjectVersion.DoesNotExist):
        return Response(
            {"error": "Invalid project_version_id"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Get comparison
    comparison_id = request.query_params.get('comparison_id')
    if comparison_id:
        try:
            comparison_id_int = int(comparison_id)
        except (ValueError, TypeError):
            return Response(
                {"error": "comparison_id must be an integer"},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            comparison = SpecComparison.objects.get(
                id=comparison_id_int,
                project=project,
                project_version=project_version
            )
        except SpecComparison.DoesNotExist:
            return Response(
                {"error": "Comparison not found or does not belong to this project/version"},
                status=status.HTTP_404_NOT_FOUND
            )
    else:
        # Get latest successful comparison for this version
        comparison = SpecComparison.objects.filter(
            project=project,
            project_version=project_version,
            status__in=[SpecComparisonStatus.SUCCESS, SpecComparisonStatus.PARTIAL_SUCCESS],
        ).order_by('-completed_at').first()

    if not comparison:
        return Response({
            'count': 0,
            'next': None,
            'previous': None,
            'results': [],
        })

    # Get skipped notes with optional reason filter (select_related to avoid N+1 on note access)
    skipped_notes = SkippedNote.objects.filter(comparison=comparison).select_related('note').order_by('id')

    reason_filter = request.query_params.get('reason')
    if reason_filter:
        skipped_notes = skipped_notes.filter(reason=reason_filter)

    paginator = SpecComparisonPagination()
    page = paginator.paginate_queryset(skipped_notes, request)

    serializer = SkippedNoteReadSerializer(page, many=True)

    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_spec_comparisons(request, project_id):
    """
    List all spec comparisons for a project.

    GET /api/deliverables/projects/{project_id}/spec-comparisons/
    """
    # Get project and check access
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return Response(
            {"error": "Project not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    if not request.user.is_member_of_project(project_id):
        return Response(
            {"error": "Not authorized to access this project"},
            status=status.HTTP_403_FORBIDDEN
        )

    comparisons = SpecComparison.objects.filter(
        project=project
    ).order_by('-created_at').annotate(
        conflict_count_annotated=Count('conflicts')
    ).select_related('triggered_by')

    paginator = SpecComparisonPagination()
    page = paginator.paginate_queryset(comparisons, request)

    serializer = SpecComparisonListSerializer(page, many=True)

    return paginator.get_paginated_response(serializer.data)
```

**Step 4: Add URL routes**

Add to `apps/deliverables/urls.py`:

```python
from .views.spec_comparison_views import (
    spec_comparison_webhook,
    trigger_spec_comparison,
    get_spec_conflicts,
    get_skipped_notes,
    list_spec_comparisons,
)

# Add to urlpatterns:
path('projects/<int:project_id>/spec-conflicts/', get_spec_conflicts, name='spec-conflicts'),
path('projects/<int:project_id>/skipped-notes/', get_skipped_notes, name='skipped-notes'),
path('projects/<int:project_id>/spec-comparisons/', list_spec_comparisons, name='spec-comparisons-list'),
```

**Step 5: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_spec_comparison_read -v 2`
Expected: PASS

**Step 6: Commit**

```bash
git add apps/deliverables/views/spec_comparison_views.py apps/deliverables/tests/test_spec_comparison_read.py apps/deliverables/urls.py
git commit -m "$(cat <<'EOF'
feat: add spec comparison read endpoints

- Add GET /projects/{id}/spec-conflicts/ endpoint
- Add GET /projects/{id}/skipped-notes/ endpoint
- Add GET /projects/{id}/spec-comparisons/ endpoint
- Include pagination, filtering, and project access checks
- Generate presigned URLs for spec files
- Use latest successful comparison by default

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Run Full Test Suite and Final Verification

**Step 1: Run all spec comparison tests**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_spec_comparison_models apps.deliverables.tests.test_spec_comparison_serializers apps.deliverables.tests.test_spec_comparison_webhook apps.deliverables.tests.test_spec_comparison_trigger apps.deliverables.tests.test_spec_comparison_read apps.utils.tests.test_spec_comparison_feature_flag -v 2`
Expected: All tests PASS

**Step 2: Run system check**

Run: `docker-compose exec web python manage.py check`
Expected: System check identified no issues

**Step 3: Run migrations check**

Run: `docker-compose exec web python manage.py makemigrations --check --dry-run`
Expected: No changes detected

**Step 4: Final commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
feat: complete drawing spec comparison feature

This commit completes the backend implementation for comparing drawing
notes against project specifications to detect conflicts.

Features:
- SpecComparison model to track comparison runs
- SpecConflict model to store detected conflicts
- SkippedNote model to track skipped notes with reasons
- Webhook endpoint for receiving lambda results
- Trigger endpoint to initiate comparisons
- Read endpoints for conflicts, skipped notes, and history
- Feature flag support at user/team/project level
- Idempotent webhook processing with select_for_update
- S3 payload upload for large payloads

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

This implementation plan covers:

1. **Task 1**: Models and enums (SpecComparison, SpecConflict, SkippedNote, etc.)
2. **Task 2**: Feature flag helper and settings configuration
3. **Task 3**: Django admin registration
4. **Task 4**: Webhook payload serializers with validation
5. **Task 5**: Webhook endpoint with idempotency
6. **Task 6**: Trigger endpoint with payload building and lambda invocation
7. **Task 7**: Read endpoints for conflicts, skipped notes, and comparison history
8. **Task 8**: Final verification and test suite run

Each task follows TDD with explicit test-first steps, exact file paths, and commit messages.

---

**v1**: Addressed review 0:
- Fixed test fixtures: Team requires `slug` (not `created_by`), Project requires `project_number`
- Added Prerequisites section noting dependency on PR #238 (discipline fields)
- Fixed race condition: set PROCESSING status before invoking lambda, not after
- Fixed note selection: include PARTIAL_SUCCESS extractions (not just SUCCESS)
- Added bucket validation: serializer validates spec_source_file bucket matches S3_BUCKET
- Added note scoping: webhook scopes note FK lookups to comparison's project/version for security

**v2**: Addressed review 1:
- Added HMAC webhook authentication: verify_webhook_signature() with X-Webhook-Signature header
- Added SPEC_COMPARISON_WEBHOOK_SECRET setting for webhook auth
- Added tests for invalid/missing/valid webhook signatures
- Added @override_settings(S3_BUCKET='bucket') to test class to fix bucket validation in tests
- Added lambda response status checking: response.raise_for_status() for non-2xx errors
- Added comparison_id type validation: return 400 for non-integer IDs
- Added note_id fallback: read serializers fall back to note_id_from_lambda when FK is null
- Added confidence range validation: min_value=0.0, max_value=1.0
- Added spec_page_number validation: min_value=1
- Fixed N+1 queries: use annotate(Count('conflicts')) instead of obj.conflicts.count()
- Added choices to SpecComparisonWebhookEvent.new_status field
- Note: kept versions.first() instead of current_version (doesn't exist in codebase)

**v3**: Addressed review 2:
- Added `from django.conf import settings` import to webhook view file (was missing)
- Fixed bucket validation to skip when S3_BUCKET is empty: `if settings.S3_BUCKET and bucket != settings.S3_BUCKET:`
- Added unit tests for parse_s3_uri_to_key() function (valid URI, nested path, invalid no-path)
- Added unit tests for safe_int() function (valid integers, invalid strings, None input)
- Added count field validation: min_value=0 on notes_processed, notes_skipped, spec_files_processed, notes_with_mismatch

**v4**: Addressed review 3:
- Added version-scoped reads: read endpoints now accept `project_version_id` param and default to current version
- Added webhook auth fail-closed: verify_webhook_signature() now rejects requests in production (DEBUG=False) when secret is not configured
- Changed pagination param from `page_size` to `limit` for consistency with DrawingNotePagination
- Added `@override_settings(S3_BUCKET='bucket')` to serializer tests for CI stability
- Increased spec_masterformat_number max_length from 32 to 256 to match MasterFormatSection
- Added `select_related('note')` to conflict/skipped-note querysets to avoid N+1 on note access

**v5**: Addressed review 4:
- Fixed version selection: changed from `project.versions.first()` (oldest) to latest non-archived version using `ProjectVersion.objects.filter(project=project, is_archived=False).order_by('-created_at').first()` to match pattern in main_views.py
- Fixed pagination test: changed `page_size` to `limit` in test_pagination test
- Fixed missing project_number in test_comparison_id_wrong_project_returns_404 fixture
- Added DEBUG=True to webhook test class override_settings to prevent 401 in CI when secret is empty

**v6**: User feedback - require explicit version selection:
- Made `project_version_id` required on trigger endpoint (TriggerSpecComparisonSerializer.project_version_id now required=True)
- Made `project_version_id` required on read endpoints (get_spec_conflicts, get_skipped_notes) - returns 400 if not provided
- Removed all default version selection logic - no more falling back to latest version
- Updated all endpoint tests to pass `project_version_id` parameter
- Added test_missing_project_version_id_returns_400 tests for trigger, conflicts, and skipped-notes endpoints
- Removed test_optional_project_version_id test (no longer optional)
