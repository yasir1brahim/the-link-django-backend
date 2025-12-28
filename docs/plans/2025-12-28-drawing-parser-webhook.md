# Drawing Parser Webhook Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement webhook system to receive parsed drawing data from AWS extraction service and display extracted notes via API.

**Architecture:** Create DrawingFile/DrawingExtraction/DrawingPage/DrawingNoteSection/DrawingNote models with CASCADE relationships, implement idempotent webhook endpoint for AWS callbacks with status state machine, provide read-only list API mirroring SubmittalItemViewSet pattern with pagination and filtering.

**Tech Stack:** Django 4.2, Django REST Framework, PostgreSQL (tests via Django test runner: `docker-compose exec web python manage.py test ...`)

---

## Phase 0: Feature Flag Setup

### Task 1: Add Drawings Feature Flag

**Files:**
- Modify: `the_link/settings.py` (add after line 633)
- Modify: `apps/utils/feature_flags.py`
- Create: `apps/utils/tests/test_drawings_feature_flag.py`

**Step 1: Write failing test for feature flag**

```python
# apps/utils/tests/test_drawings_feature_flag.py
from django.conf import settings
from django.test import TestCase

from apps.users.models import CustomUser
from apps.teams.models import Team, Flag
from apps.deliverables.models import Project
from apps.utils.feature_flags import is_drawings_feature_flag_active


class DrawingsFeatureFlagTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(username="test", password="test")
        self.team = Team.objects.create(name="test", slug="test-team")
        self.team.members.add(self.user)
        self.project = Project.objects.create(
            name="Test Project",
            project_number="P-001",
            team=self.team,
            created_by=self.user
        )
        self.flag: Flag = Flag.objects.create(name=settings.DRAWINGS_FEATURE_FLAG_NAME)

    def test_is_drawings_feature_flag_active_returns_false_when_not_set(self):
        self.assertFalse(is_drawings_feature_flag_active(self.user, self.team, self.project))

    def test_is_drawings_feature_flag_active_returns_true_when_set_for_superusers(self):
        self.user.is_superuser = True
        self.user.save()
        self.flag.superusers = True
        self.flag.save()
        self.assertTrue(is_drawings_feature_flag_active(self.user, self.team, self.project))
        self.user.is_superuser = False
        self.user.save()
        self.assertFalse(is_drawings_feature_flag_active(self.user, self.team, self.project))

    def test_is_drawings_feature_flag_active_returns_true_when_set_for_user(self):
        self.assertFalse(is_drawings_feature_flag_active(self.user, self.team, self.project))
        self.flag.users.add(self.user)
        self.flag.save()
        self.assertTrue(is_drawings_feature_flag_active(self.user, self.team, self.project))

    def test_is_drawings_feature_flag_active_returns_true_when_set_for_team(self):
        self.assertFalse(is_drawings_feature_flag_active(self.user, self.team, self.project))
        self.flag.teams.add(self.team)
        self.flag.save()
        self.assertTrue(is_drawings_feature_flag_active(self.user, self.team, self.project))

    def test_is_drawings_feature_flag_active_returns_true_when_set_for_project(self):
        self.assertFalse(is_drawings_feature_flag_active(self.user, self.team, self.project))
        self.flag.projects.add(self.project)
        self.flag.save()
        self.assertTrue(is_drawings_feature_flag_active(self.user, self.team, self.project))
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.utils.tests.test_drawings_feature_flag --verbosity=2`

Expected: FAIL with "AttributeError: module 'django.conf.settings' has no attribute 'DRAWINGS_FEATURE_FLAG_NAME'"

**Step 3: Add settings constant**

Add to `the_link/settings.py` after line 633 (after `LANGCHAIN_UPDATE_FEATURE_FLAG_NAME`):

```python
DRAWINGS_FEATURE_FLAG_NAME = 'drawings'
```

**Step 4: Run test again**

Run: `docker-compose exec web python manage.py test apps.utils.tests.test_drawings_feature_flag --verbosity=2`

Expected: FAIL with "ImportError: cannot import name 'is_drawings_feature_flag_active'"

**Step 5: Add feature flag function**

Add to `apps/utils/feature_flags.py` at the end of the file:

```python
def is_drawings_feature_flag_active(user, team, project=None):
    """
    Check if the drawings feature flag is active for the given user/team/project.
    This flag enables the drawing parser webhook and notes display features.

    Args:
        user: User object
        team: Team object
        project: Optional Project object

    Returns:
        bool: True if flag is active, False otherwise
    """
    return (settings.DRAWINGS_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or
            settings.DRAWINGS_FEATURE_FLAG_NAME in get_active_flags_for_team(team) or
            (project and settings.DRAWINGS_FEATURE_FLAG_NAME in get_active_flags_for_project(project)))
```

**Step 6: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.utils.tests.test_drawings_feature_flag --verbosity=2`

Expected: All tests PASS

**Step 7: Commit**

```bash
git add the_link/settings.py apps/utils/feature_flags.py apps/utils/tests/test_drawings_feature_flag.py
git commit -m "$(cat <<'EOF'
feat: add drawings feature flag

Adds 'drawings' feature flag to control access to drawing parser
webhook and notes display features. Follows existing pattern with
user/team/project level activation.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 1: Enums & Core Models

### Task 2: Create DrawingFile Model and Enums

**Files:**
- Create: `apps/deliverables/tests/test_drawing_parser_models.py`
- Modify: `apps/deliverables/models.py` (add after ExtractionNote model, around line 650+)

**Step 1: Write failing test for enums and DrawingFile model**

```python
# apps/deliverables/tests/test_drawing_parser_models.py
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
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_parser_models.TestDrawingFileModel --verbosity=2`

Expected: FAIL with "ImportError: cannot import name 'DrawingFile'"

**Step 3: Create enums and DrawingFile model**

Add to `apps/deliverables/models.py` after ExtractionNote model:

```python
# Drawing Parser Models
class DrawingExtractionStatus(models.TextChoices):
    """Status of a drawing extraction run"""
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    SUCCESS = "SUCCESS", "Success"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS", "Partial Success"
    FAILED = "FAILED", "Failed"


class DrawingPageType(models.TextChoices):
    """Type of page in a drawing"""
    DRAWING = "drawing", "Drawing"
    SPEC = "spec", "Specification"


class DrawingPageExtractionStatus(models.TextChoices):
    """Extraction status for individual pages"""
    SUCCESS = "success", "Success"
    NO_NOTES_FOUND = "no_notes_found", "No Notes Found"
    FAILED = "failed", "Failed"


class DrawingFile(BaseModel):
    """Uploaded drawing document (e.g., mechanical drawings PDF)"""

    project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        related_name="drawing_files"
    )
    project_version = models.ForeignKey(
        "ProjectVersion",
        on_delete=models.CASCADE,
        related_name="drawing_files"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_drawing_files"
    )

    file_name = models.CharField(max_length=512)
    file_s3_key = models.CharField(max_length=1024)
    md5 = models.CharField(max_length=64)
    total_pages = models.IntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['project', 'project_version']),
        ]

    def __str__(self):
        return f"{self.file_name} ({self.project.name})"

    @property
    def latest_extraction(self):
        return self.extractions.order_by('-created_at').first()

    @property
    def extraction_status(self):
        extraction = self.latest_extraction
        return extraction.status if extraction else None
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_parser_models.TestDrawingFileModel --verbosity=2`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/models.py apps/deliverables/tests/test_drawing_parser_models.py
git commit -m "$(cat <<'EOF'
feat: add DrawingFile model and extraction status enums

Add core model for drawing file uploads with enums for tracking
extraction status, page types, and page-level extraction status.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Create DrawingExtraction Model

**Files:**
- Modify: `apps/deliverables/tests/test_drawing_parser_models.py`
- Modify: `apps/deliverables/models.py`

**Step 1: Write failing test for DrawingExtraction**

Add to `apps/deliverables/tests/test_drawing_parser_models.py`:

```python
from apps.deliverables.models import DrawingExtraction
from django.utils import timezone


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
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_parser_models.TestDrawingExtractionModel --verbosity=2`

Expected: FAIL with "ImportError: cannot import name 'DrawingExtraction'"

**Step 3: Create DrawingExtraction model**

Add to `apps/deliverables/models.py` after DrawingFile:

```python
class DrawingExtraction(BaseModel):
    """Tracks each extraction attempt for a drawing file"""

    drawing_file = models.ForeignKey(
        "DrawingFile",
        on_delete=models.CASCADE,
        related_name="extractions"
    )

    status = models.CharField(
        max_length=32,
        choices=DrawingExtractionStatus.choices,
        default=DrawingExtractionStatus.PENDING
    )

    # Processing metadata
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    model_version = models.CharField(max_length=128, null=True, blank=True)
    processing_time_ms = models.IntegerField(null=True, blank=True)
    output_s3_key = models.CharField(max_length=1024, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    failure_summary = models.CharField(max_length=256, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['drawing_file', 'status']),
        ]

    def __str__(self):
        return f"Extraction {self.id} for {self.drawing_file.file_name} ({self.status})"
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_parser_models.TestDrawingExtractionModel --verbosity=2`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/models.py apps/deliverables/tests/test_drawing_parser_models.py
git commit -m "$(cat <<'EOF'
feat: add DrawingExtraction model for tracking extraction attempts

Tracks status, timing, and metadata for each drawing extraction run.
Supports multiple extraction attempts per DrawingFile.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Create DrawingPage Model

**Files:**
- Modify: `apps/deliverables/tests/test_drawing_parser_models.py`
- Modify: `apps/deliverables/models.py`

**Step 1: Write failing test for DrawingPage**

Add to `apps/deliverables/tests/test_drawing_parser_models.py`:

```python
from apps.deliverables.models import DrawingPage


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

```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_parser_models.TestDrawingPageModel --verbosity=2`

Expected: FAIL with "ImportError: cannot import name 'DrawingPage'"

**Step 3: Create DrawingPage model**

Add to `apps/deliverables/models.py` after DrawingExtraction:

```python
class DrawingPage(BaseModel):
    """Individual page from a drawing file"""

    drawing_file = models.ForeignKey(
        "DrawingFile",
        on_delete=models.CASCADE,
        related_name="pages"
    )
    extraction = models.ForeignKey(
        "DrawingExtraction",
        on_delete=models.CASCADE,
        related_name="pages"
    )

    page_number = models.IntegerField()
    page_type = models.CharField(
        max_length=32,
        choices=DrawingPageType.choices
    )
    extraction_status = models.CharField(
        max_length=32,
        choices=DrawingPageExtractionStatus.choices
    )
    spec_content = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['page_number']

    def __str__(self):
        return f"Page {self.page_number} of {self.drawing_file.file_name}"
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_parser_models.TestDrawingPageModel --verbosity=2`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/models.py apps/deliverables/tests/test_drawing_parser_models.py
git commit -m "$(cat <<'EOF'
feat: add DrawingPage model for individual pages

Stores page-level extraction results with support for both
drawing and spec page types.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Create DrawingNoteSection and DrawingNote Models

**Files:**
- Modify: `apps/deliverables/tests/test_drawing_parser_models.py`
- Modify: `apps/deliverables/models.py`

**Step 1: Write failing test for DrawingNoteSection and DrawingNote**

Add to `apps/deliverables/tests/test_drawing_parser_models.py`:

```python
from apps.deliverables.models import DrawingNoteSection, DrawingNote


class TestDrawingNoteSectionModel(TestCase):
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
            page_number=1,
            page_type=DrawingPageType.DRAWING,
            extraction_status=DrawingPageExtractionStatus.SUCCESS,
        )

    def test_note_section_creation(self):
        """Test DrawingNoteSection creation"""
        section = DrawingNoteSection.objects.create(
            page=self.page,
            header="GENERAL NOTES:",
            header_bbox=[100.0, 200.0, 300.0, 250.0],
        )

        self.assertEqual(section.header, "GENERAL NOTES:")
        self.assertEqual(section.header_bbox, [100.0, 200.0, 300.0, 250.0])
        self.assertEqual(section.page, self.page)


class TestDrawingNoteModel(TestCase):
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
            page_number=1,
            page_type=DrawingPageType.DRAWING,
            extraction_status=DrawingPageExtractionStatus.SUCCESS,
        )
        self.section = DrawingNoteSection.objects.create(
            page=self.page,
            header="GENERAL NOTES:",
        )

    def test_note_creation(self):
        """Test DrawingNote creation"""
        note = DrawingNote.objects.create(
            section=self.section,
            note_number=1,
            category="GENERAL NOTES",
            text="All work shall comply with applicable codes.",
            bounding_box=[100.0, 300.0, 500.0, 350.0],
            source_blocks=[[100.0, 300.0, 250.0, 325.0], [250.0, 325.0, 500.0, 350.0]],
            drawing_references=[
                {"reference_text": "DETAIL 04/M702", "drawing_id": "M702", "detail_number": "04"}
            ],
        )

        self.assertEqual(note.note_number, 1)
        self.assertEqual(note.category, "GENERAL NOTES")
        self.assertEqual(note.text, "All work shall comply with applicable codes.")
        self.assertEqual(len(note.drawing_references), 1)
        self.assertEqual(note.drawing_references[0]["drawing_id"], "M702")

    def test_notes_ordered_by_note_number(self):
        """Test notes are ordered by note_number"""
        DrawingNote.objects.create(
            section=self.section,
            note_number=3,
            category="GENERAL",
            text="Third note",
        )
        DrawingNote.objects.create(
            section=self.section,
            note_number=1,
            category="GENERAL",
            text="First note",
        )

        notes = list(DrawingNote.objects.filter(section=self.section))
        self.assertEqual(notes[0].note_number, 1)
        self.assertEqual(notes[1].note_number, 3)

    def test_cascade_delete_from_page(self):
        """Test notes are deleted when page is deleted"""
        DrawingNote.objects.create(
            section=self.section,
            note_number=1,
            category="GENERAL",
            text="Test note",
        )

        self.assertEqual(DrawingNote.objects.count(), 1)
        self.page.delete()
        self.assertEqual(DrawingNote.objects.count(), 0)
        self.assertEqual(DrawingNoteSection.objects.count(), 0)
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_parser_models.TestDrawingNoteSectionModel apps.deliverables.tests.test_drawing_parser_models.TestDrawingNoteModel --verbosity=2`

Expected: FAIL with "ImportError: cannot import name 'DrawingNoteSection'"

**Step 3: Create DrawingNoteSection and DrawingNote models**

Add to `apps/deliverables/models.py` after DrawingPage:

```python
class DrawingNoteSection(BaseModel):
    """A section header containing notes on a drawing page (e.g., 'GENERAL NOTES:')"""

    page = models.ForeignKey(
        "DrawingPage",
        on_delete=models.CASCADE,
        related_name="note_sections"
    )

    header = models.CharField(max_length=512)
    header_bbox = models.JSONField(null=True, blank=True)  # [x1, y1, x2, y2]

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.header} (Page {self.page.page_number})"


class DrawingNote(BaseModel):
    """Individual note extracted from a drawing"""

    section = models.ForeignKey(
        "DrawingNoteSection",
        on_delete=models.CASCADE,
        related_name="notes"
    )

    note_number = models.IntegerField()
    category = models.CharField(max_length=256)
    text = models.TextField()
    bounding_box = models.JSONField(null=True, blank=True)
    source_blocks = models.JSONField(null=True, blank=True)
    drawing_references = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['note_number']
        indexes = [
            models.Index(fields=['category']),
        ]

    def __str__(self):
        preview = self.text[:50] + '...' if len(self.text) > 50 else self.text
        return f"Note {self.note_number}: {preview}"
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_parser_models.TestDrawingNoteSectionModel apps.deliverables.tests.test_drawing_parser_models.TestDrawingNoteModel --verbosity=2`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/models.py apps/deliverables/tests/test_drawing_parser_models.py
git commit -m "$(cat <<'EOF'
feat: add DrawingNoteSection and DrawingNote models

Complete the drawing note hierarchy with section headers
and individual notes with bounding boxes and drawing references.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Create DrawingExtractionWebhookEvent Model

**Files:**
- Modify: `apps/deliverables/tests/test_drawing_parser_models.py`
- Modify: `apps/deliverables/models.py`

**Step 1: Write failing test for webhook event idempotency**

Add to `apps/deliverables/tests/test_drawing_parser_models.py`:

```python
from apps.deliverables.models import DrawingExtractionWebhookEvent
from django.db import IntegrityError


class TestDrawingExtractionWebhookEventModel(TestCase):
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
            status=DrawingExtractionStatus.PENDING,
        )

    def test_webhook_event_creation(self):
        """Test webhook event creation"""
        event = DrawingExtractionWebhookEvent.objects.create(
            extraction=self.extraction,
            event_id="evt_12345",
            new_status=DrawingExtractionStatus.PROCESSING,
            payload={"test": "data"},
        )

        self.assertEqual(event.event_id, "evt_12345")
        self.assertEqual(event.new_status, DrawingExtractionStatus.PROCESSING)

    def test_event_id_uniqueness(self):
        """Test event_id must be unique for idempotency"""
        DrawingExtractionWebhookEvent.objects.create(
            extraction=self.extraction,
            event_id="evt_12345",
            new_status=DrawingExtractionStatus.PROCESSING,
        )

        with self.assertRaises(IntegrityError):
            DrawingExtractionWebhookEvent.objects.create(
                extraction=self.extraction,
                event_id="evt_12345",  # Same event_id
                new_status=DrawingExtractionStatus.SUCCESS,
            )
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_parser_models.TestDrawingExtractionWebhookEventModel --verbosity=2`

Expected: FAIL with "ImportError: cannot import name 'DrawingExtractionWebhookEvent'"

**Step 3: Create DrawingExtractionWebhookEvent model**

Add to `apps/deliverables/models.py` after DrawingNote:

```python
class DrawingExtractionWebhookEvent(BaseModel):
    """
    Store each webhook delivery for idempotency and retry safety.
    The unique event_id ensures duplicate deliveries are ignored.
    """

    extraction = models.ForeignKey(
        "DrawingExtraction",
        on_delete=models.CASCADE,
        related_name="webhook_events",
    )

    # Provided by the caller; unique per webhook delivery
    event_id = models.CharField(max_length=128, unique=True)

    # Helps debug ordering/retries without storing entire payload forever
    new_status = models.CharField(max_length=32)
    output_s3_key = models.CharField(max_length=1024, null=True, blank=True)
    payload = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["extraction", "new_status"]),
        ]

    def __str__(self):
        return f"Webhook {self.event_id} -> {self.new_status}"
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_parser_models.TestDrawingExtractionWebhookEventModel --verbosity=2`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/models.py apps/deliverables/tests/test_drawing_parser_models.py
git commit -m "$(cat <<'EOF'
feat: add DrawingExtractionWebhookEvent for idempotency

Ensures webhook callbacks can be safely retried by tracking
unique event IDs and preventing duplicate processing.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Create and Run Migration

**Files:**
- Create: `apps/deliverables/migrations/00XX_add_drawing_parser_models.py` (auto-generated)

**Step 1: Generate migration**

Run: `docker-compose exec web python manage.py makemigrations deliverables --name add_drawing_parser_models`

Expected: Migration file created

**Step 2: Run migration**

Run: `docker-compose exec web python manage.py migrate deliverables`

Expected: Migration applied successfully

**Step 3: Run all model tests to verify**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_parser_models --verbosity=2`

Expected: All tests PASS

**Step 4: Commit**

```bash
git add apps/deliverables/migrations/
git commit -m "$(cat <<'EOF'
chore: add migration for drawing parser models

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 1.5: Upload Flow Integration

### Task 7.5: Update Upload Logic and Trigger Extraction

**Files:**
- Modify: `apps/deliverables/serializers/__init__.py`
- Modify: `apps/deliverables/views/main_views.py`
- Create: `apps/deliverables/tests/test_drawing_upload.py`

**Step 1: Write failing test for drawing upload**

```python
# apps/deliverables/tests/test_drawing_upload.py
from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status
from apps.deliverables.models import Project, ProjectVersion, DrawingFile, DrawingExtraction, DrawingExtractionStatus
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()

class DrawingUploadTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('test@example.com', password='testpass')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(
            name="Test Project",
            project_number="P-001",
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        self.team.members.add(self.user)
        self.client.force_authenticate(user=self.user)

    def test_upload_drawing_file(self):
        """Test uploading a file with file_type='drawing'"""
        pdf_content = b"%PDF-1.4 test content"
        drawing_file = SimpleUploadedFile("mechanical.pdf", pdf_content, content_type="application/pdf")

        url = reverse('deliverables:upload-file')
        data = {
            'files': [drawing_file],
            'project_id': self.project.id,
            'project_version_id': self.project_version.id,
            'file_type': 'drawing'
        }

        response = self.client.post(url, data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify DrawingFile was created
        self.assertEqual(DrawingFile.objects.count(), 1)
        df = DrawingFile.objects.first()
        self.assertEqual(df.file_name, "mechanical.pdf")
        
        # Verify DrawingExtraction was created
        self.assertEqual(DrawingExtraction.objects.count(), 1)
        ext = DrawingExtraction.objects.first()
        self.assertEqual(ext.drawing_file, df)
        self.assertEqual(ext.status, DrawingExtractionStatus.PENDING)

    def test_upload_duplicate_drawing_reuses_file_record(self):
        """Test that uploading the same drawing reuses the DrawingFile record but creates new Extraction"""
        pdf_content = b"%PDF-1.4 unique content"
        file1 = SimpleUploadedFile("mechanical.pdf", pdf_content, content_type="application/pdf")
        
        url = reverse('deliverables:upload-file')
        
        # First upload
        self.client.post(url, {
            'files': [file1],
            'project_id': self.project.id,
            'project_version_id': self.project_version.id,
            'file_type': 'drawing'
        }, format='multipart')
        
        self.assertEqual(DrawingFile.objects.count(), 1)
        self.assertEqual(DrawingExtraction.objects.count(), 1)
        
        # Second upload of same file
        file2 = SimpleUploadedFile("mechanical.pdf", pdf_content, content_type="application/pdf")
        self.client.post(url, {
            'files': [file2],
            'project_id': self.project.id,
            'project_version_id': self.project_version.id,
            'file_type': 'drawing'
        }, format='multipart')
        
        # Should still be 1 DrawingFile but 2 Extractions
        self.assertEqual(DrawingFile.objects.count(), 1)
        self.assertEqual(DrawingExtraction.objects.count(), 2)
```

**Step 2: Update Serializer**

Add `file_type` to `FileUploadSerializer` in `apps/deliverables/serializers/__init__.py`:

```python
class FileUploadSerializer(serializers.Serializer):
    files = serializers.ListField(child=serializers.FileField())
    project_id = serializers.IntegerField()
    project_version_id = serializers.IntegerField(required=False)
    extract_notices = serializers.BooleanField(required=False)
    full_spec_processing = serializers.BooleanField(required=False)
    file_type = serializers.ChoiceField(
        choices=['spec', 'drawing'],
        default='spec',
        required=False
    )
```

**Step 3: Update View Logic**

Modify `upload_file` in `apps/deliverables/views/main_views.py` to handle `file_type == 'drawing'`:
- Use separate S3 prefix: `drawings/`
- Check MD5 uniqueness for `DrawingFile` within same version.
- Create `DrawingExtraction`.
- Trigger AWS Lambda (placeholder for actual trigger call).

**Step 4: Run tests to verify**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_upload --verbosity=2`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/serializers/__init__.py apps/deliverables/views/main_views.py apps/deliverables/tests/test_drawing_upload.py
git commit -m "$(cat <<'EOF'
feat: integrate drawing upload into main upload flow

Updates FileUploadSerializer and upload_file view to support 
drawings, including duplicate detection and extraction triggering.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Phase 2: Webhook Endpoint

### Task 8: Create Webhook View File and Basic Endpoint

**Files:**
- Create: `apps/deliverables/tests/test_drawing_extraction_webhook.py`
- Create: `apps/deliverables/views/drawing_views.py`
- Modify: `apps/deliverables/urls.py`

**Step 1: Write failing test for webhook endpoint existence**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_extraction_webhook.TestDrawingExtractionWebhookBasic.test_webhook_accepts_post_without_auth --verbosity=2`

Expected: FAIL with "NoReverseMatch: 'drawing-extraction-webhook'"

**Step 3: Create view and URL**

Create `apps/deliverables/views/drawing_views.py`:

```python
from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from ..models import (
    DrawingExtraction,
    DrawingExtractionStatus,
    DrawingExtractionWebhookEvent,
    DrawingPage,
    DrawingNoteSection,
    DrawingNote,
)


@api_view(['POST'])
@permission_classes([AllowAny])
def drawing_extraction_webhook(request):
    """
    Webhook endpoint for receiving drawing extraction results from AWS Lambda.

    Idempotent: duplicate event_ids are ignored.
    Atomic: all changes within a single transaction.
    """
    payload = request.data
    event_id = payload.get('event_id')
    extraction_id = payload.get('extraction_id')
    new_status_str = payload.get('new_status')

    if not all([event_id, extraction_id, new_status_str]):
        return Response(
            {"error": "Missing required fields: event_id, extraction_id, new_status"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        new_status = DrawingExtractionStatus(new_status_str)
    except ValueError:
        return Response(
            {"error": f"Invalid status: {new_status_str}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    with transaction.atomic():
        try:
            extraction = DrawingExtraction.objects.select_for_update().get(id=extraction_id)
        except DrawingExtraction.DoesNotExist:
            return Response(
                {"error": f"Extraction {extraction_id} not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Try to record the webhook event for idempotency
        try:
            DrawingExtractionWebhookEvent.objects.create(
                extraction=extraction,
                event_id=event_id,
                new_status=new_status.value,
                output_s3_key=payload.get("output_s3_key"),
                payload=payload,
            )
        except IntegrityError:
            # Duplicate event_id - already processed
            return Response(status=status.HTTP_200_OK)

        # Status transition validation
        allowed_next_statuses = {
            DrawingExtractionStatus.PENDING: {
                DrawingExtractionStatus.PROCESSING,
                DrawingExtractionStatus.FAILED
            },
            DrawingExtractionStatus.PROCESSING: {
                DrawingExtractionStatus.SUCCESS,
                DrawingExtractionStatus.PARTIAL_SUCCESS,
                DrawingExtractionStatus.FAILED,
            },
            DrawingExtractionStatus.SUCCESS: set(),
            DrawingExtractionStatus.PARTIAL_SUCCESS: set(),
            DrawingExtractionStatus.FAILED: set(),
        }

        if new_status not in allowed_next_statuses.get(extraction.status, set()):
            # Ignore invalid transitions (e.g., PROCESSING after SUCCESS)
            return Response(status=status.HTTP_200_OK)

        # Process based on new status
        if new_status == DrawingExtractionStatus.PROCESSING:
            extraction.status = DrawingExtractionStatus.PROCESSING
            extraction.started_at = timezone.now()
            extraction.save()

        elif new_status in {DrawingExtractionStatus.SUCCESS, DrawingExtractionStatus.PARTIAL_SUCCESS}:
            extraction.status = new_status
            extraction.completed_at = timezone.now()
            extraction.model_version = payload.get('model_version')
            extraction.processing_time_ms = payload.get('processing_time_ms')
            extraction.output_s3_key = payload.get('output_s3_key')
            extraction.failure_summary = payload.get('failure_summary')
            extraction.save()

            # Update drawing file total_pages
            data = payload.get('data', {})
            if data.get('total_pages'):
                extraction.drawing_file.total_pages = data['total_pages']
                extraction.drawing_file.save()

            # Clear existing pages and recreate (idempotent)
            DrawingPage.objects.filter(extraction=extraction).delete()
            _create_drawing_records(extraction, data)

        elif new_status == DrawingExtractionStatus.FAILED:
            extraction.status = DrawingExtractionStatus.FAILED
            extraction.completed_at = timezone.now()
            extraction.error_message = payload.get('error_message')
            extraction.failure_summary = payload.get('failure_summary')
            extraction.save()

    return Response(status=status.HTTP_200_OK)


def _create_drawing_records(extraction, data):
    """
    Bulk create DrawingPage, DrawingNoteSection, and DrawingNote records.
    Uses bulk_create for performance on large PDFs.
    """
    pages_data = data.get('pages', [])

    # First pass: create all pages
    page_objects = []
    for page_data in pages_data:
        page_objects.append(DrawingPage(
            drawing_file=extraction.drawing_file,
            extraction=extraction,
            page_number=page_data['page_number'],
            page_type=page_data['page_type'],
            extraction_status=page_data['extraction_status'],
            spec_content=page_data.get('spec_content'),
        ))

    created_pages = DrawingPage.objects.bulk_create(page_objects)

    # Build page_number -> page mapping
    page_map = {p.page_number: p for p in created_pages}

    # Second pass: create all note sections
    section_objects = []
    section_notes_map = []  # Track (section_index, notes_data) for later

    for page_data in pages_data:
        page = page_map[page_data['page_number']]
        for section_data in page_data.get('note_sections', []):
            section_index = len(section_objects)
            section_objects.append(DrawingNoteSection(
                page=page,
                header=section_data['header'],
                header_bbox=section_data.get('header_bbox'),
            ))
            section_notes_map.append((section_index, section_data.get('notes', [])))

    created_sections = DrawingNoteSection.objects.bulk_create(section_objects)

    # Third pass: create all notes
    note_objects = []
    for section_index, notes_data in section_notes_map:
        section = created_sections[section_index]
        for note_data in notes_data:
            note_objects.append(DrawingNote(
                section=section,
                note_number=note_data['note_number'],
                category=note_data['category'],
                text=note_data['text'],
                bounding_box=note_data.get('bounding_box'),
                source_blocks=note_data.get('source_blocks'),
                drawing_references=note_data.get('drawing_references'),
            ))

    DrawingNote.objects.bulk_create(note_objects)
```

Add to `apps/deliverables/urls.py` (add import and URL):

```python
# Add import at top
from .views import drawing_views

# Add URL in urlpatterns list
path('webhooks/drawing-extraction/', drawing_views.drawing_extraction_webhook, name='drawing-extraction-webhook'),
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_extraction_webhook.TestDrawingExtractionWebhookBasic.test_webhook_accepts_post_without_auth --verbosity=2`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/views/drawing_views.py apps/deliverables/urls.py apps/deliverables/tests/test_drawing_extraction_webhook.py
git commit -m "$(cat <<'EOF'
feat: add drawing extraction webhook endpoint

Implements idempotent webhook handler with:
- Status state machine validation
- Atomic transactions
- Bulk record creation for performance

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Test Webhook Status Transitions

**Files:**
- Modify: `apps/deliverables/tests/test_drawing_extraction_webhook.py`

**Step 1: Write tests for status transitions**

Add to `apps/deliverables/tests/test_drawing_extraction_webhook.py`:

```python
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
```

**Step 2: Run all webhook tests**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_extraction_webhook --verbosity=2`

Expected: All tests PASS

**Step 3: Commit**

```bash
git add apps/deliverables/tests/test_drawing_extraction_webhook.py
git commit -m "$(cat <<'EOF'
test: add comprehensive webhook status transition tests

Covers all valid transitions, invalid transition handling,
idempotency, and data creation on success.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 3: API Endpoints

### Task 10: Create DrawingNote Serializer

**Files:**
- Create: `apps/deliverables/serializers/drawing_serializers.py`
- Create: `apps/deliverables/tests/test_drawing_note_serializers.py`

**Step 1: Write failing test for serializer**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_note_serializers.TestDrawingNoteReadSerializer --verbosity=2`

Expected: FAIL with "ImportError: cannot import name 'DrawingNoteReadSerializer'"

**Step 3: Create serializer**

Create `apps/deliverables/serializers/drawing_serializers.py`:

```python
import boto3
from django.conf import settings
from rest_framework import serializers
from ..models import DrawingNote, DrawingPageExtractionStatus


s3 = boto3.client(
    "s3",
    region_name=settings.AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
)


class DrawingNoteReadSerializer(serializers.ModelSerializer):
    """
    Flattened serializer for DrawingNote table display.
    Includes related fields from section, page, and drawing file.
    """
    # Flattened fields for table display
    drawing_file_id = serializers.IntegerField(source='section.page.drawing_file.id')
    drawing_file_name = serializers.CharField(source='section.page.drawing_file.file_name')
    drawing_file_url = serializers.SerializerMethodField()
    page_number = serializers.IntegerField(source='section.page.page_number')
    section_header = serializers.CharField(source='section.header')

    # Extraction status for error display
    page_extraction_status = serializers.CharField(source='section.page.extraction_status')
    page_extraction_failed = serializers.SerializerMethodField()

    class Meta:
        model = DrawingNote
        fields = [
            'id',
            'drawing_file_id',
            'drawing_file_name',
            'drawing_file_url',
            'page_number',
            'section_header',
            'note_number',
            'category',
            'text',
            'drawing_references',
            'bounding_box',
            'page_extraction_status',
            'page_extraction_failed',
        ]

    def get_drawing_file_url(self, obj):
        """Generate a presigned URL for the drawing file PDF."""
        s3_key = obj.section.page.drawing_file.file_s3_key
        return s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.S3_BUCKET, 'Key': s3_key},
            ExpiresIn=3600
        )

    def get_page_extraction_failed(self, obj):
        return obj.section.page.extraction_status == DrawingPageExtractionStatus.FAILED
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_note_serializers.TestDrawingNoteReadSerializer --verbosity=2`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/serializers/drawing_serializers.py apps/deliverables/tests/test_drawing_note_serializers.py
git commit -m "$(cat <<'EOF'
feat: add DrawingNoteReadSerializer with flattened fields

Provides table-friendly representation of drawing notes with
nested relationships flattened for efficient frontend display.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Create DrawingNote Permission Class

**Files:**
- Modify: `apps/deliverables/permissions.py`
- Create: `apps/deliverables/tests/test_drawing_note_permissions.py`

**Step 1: Write failing test for permissions**

```python
# apps/deliverables/tests/test_drawing_note_permissions.py
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from apps.teams.models import Team
from apps.deliverables.models import (
    Project, ProjectMembership, ROLE_PROJECT_MEMBER,
)
from apps.deliverables.permissions import DrawingNoteAccessPermissions

User = get_user_model()


class TestDrawingNoteAccessPermissions(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user('test@example.com')
        self.other_user = User.objects.create_user('other@example.com')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(
            name="Test Project",
            project_number="P-001",
            team=self.team,
            created_by=self.user
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ROLE_PROJECT_MEMBER
        )
        self.permission = DrawingNoteAccessPermissions()

    def test_member_has_permission(self):
        """Test project member has access"""
        request = self.factory.get('/')
        request.user = self.user

        class MockView:
            kwargs = {'project_id': self.project.id}

        self.assertTrue(self.permission.has_permission(request, MockView()))

    def test_non_member_denied(self):
        """Test non-member is denied access"""
        request = self.factory.get('/')
        request.user = self.other_user

        class MockView:
            kwargs = {'project_id': self.project.id}

        self.assertFalse(self.permission.has_permission(request, MockView()))
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_note_permissions.TestDrawingNoteAccessPermissions --verbosity=2`

Expected: FAIL with "AttributeError: type object 'DrawingNoteAccessPermissions' has no attribute..."

**Step 3: Add permission class**

Add to `apps/deliverables/permissions.py`:

```python
class DrawingNoteAccessPermissions(permissions.BasePermission):
    """
    Permission to only allow members of a project to access drawing notes.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        project_id = view.kwargs.get('project_id')
        if project_id:
            return request.user.is_member_of_project(project_id)
        return False
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_note_permissions.TestDrawingNoteAccessPermissions --verbosity=2`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/permissions.py apps/deliverables/tests/test_drawing_note_permissions.py
git commit -m "$(cat <<'EOF'
feat: add DrawingNoteAccessPermissions

Simple permission class ensuring only project members
can access drawing notes.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: Create DrawingNote ViewSet

**Files:**
- Modify: `apps/deliverables/views/drawing_views.py`
- Modify: `apps/deliverables/urls.py`
- Create: `apps/deliverables/tests/test_drawing_note_viewset.py`

**Step 1: Write failing test for list endpoint**

```python
# apps/deliverables/tests/test_drawing_note_viewset.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.deliverables.models import (
    Project, ProjectMembership, ROLE_PROJECT_MEMBER,
    DrawingFile, DrawingExtraction, DrawingPage, DrawingNoteSection, DrawingNote,
    DrawingExtractionStatus, DrawingPageType, DrawingPageExtractionStatus,
)
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class TestDrawingNoteViewSet(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('test@example.com', password='testpass')
        self.other_user = User.objects.create_user('other@example.com', password='testpass')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(
            name="Test Project",
            project_number="P-001",
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ROLE_PROJECT_MEMBER
        )

        # Create drawing data
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
            page_number=1,
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
            text="Test note content",
        )

        self.client.force_authenticate(user=self.user)

    def test_list_notes(self):
        """Test listing drawing notes for a project"""
        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['text'], "Test note content")

    def test_list_notes_unauthenticated_denied(self):
        """Test unauthenticated access is denied"""
        self.client.logout()
        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_notes_non_member_denied(self):
        """Test non-member access is denied"""
        self.client.force_authenticate(user=self.other_user)
        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_filter_by_project_version(self):
        """Test filtering by project_version_id"""
        # Create note in different version
        version2 = self.project.versions.create(version_number=2, version_name="V2")
        drawing_file2 = DrawingFile.objects.create(
            project=self.project,
            project_version=version2,
            file_name="Electrical.pdf",
            file_s3_key="drawings/test2.pdf",
            md5="def456",
        )
        extraction2 = DrawingExtraction.objects.create(
            drawing_file=drawing_file2,
            status=DrawingExtractionStatus.SUCCESS,
        )
        page2 = DrawingPage.objects.create(
            drawing_file=drawing_file2,
            extraction=extraction2,
            page_number=1,
            page_type=DrawingPageType.DRAWING,
            extraction_status=DrawingPageExtractionStatus.SUCCESS,
        )
        section2 = DrawingNoteSection.objects.create(page=page2, header="ELECTRICAL:")
        DrawingNote.objects.create(
            section=section2,
            note_number=1,
            category="ELECTRICAL",
            text="Electrical note",
        )

        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})

        # Filter by first version
        response = self.client.get(url, {'project_version_id': self.project_version.id})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['category'], "GENERAL NOTES")

        # Filter by second version
        response = self.client.get(url, {'project_version_id': version2.id})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['category'], "ELECTRICAL")

    def test_filter_by_category(self):
        """Test filtering by category"""
        # Create note with different category
        DrawingNote.objects.create(
            section=self.section,
            note_number=2,
            category="MECHANICAL",
            text="Mechanical note",
        )

        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url, {'category': 'MECHANICAL'})

        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['category'], "MECHANICAL")

    def test_all_filter_vals_returned(self):
        """Test that filter options are returned in response"""
        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url)

        self.assertIn('all_filter_vals', response.data)
        self.assertIn('category', response.data['all_filter_vals'])
        self.assertIn('drawing_file', response.data['all_filter_vals'])

    def test_processing_status_returned(self):
        """Test that processing_status is included in response"""
        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url)

        self.assertIn('processing_status', response.data)
        status_data = response.data['processing_status']
        self.assertIn('is_processing', status_data)
        self.assertIn('files_processing', status_data)
        self.assertIn('files_completed', status_data)
        self.assertIn('files_failed', status_data)
        self.assertIn('files', status_data)

    def test_processing_status_shows_processing_files(self):
        """Test processing_status correctly shows files being processed"""
        # Create a file that is still processing
        processing_file = DrawingFile.objects.create(
            project=self.project,
            project_version=self.project_version,
            file_name="Electrical.pdf",
            file_s3_key="drawings/electrical.pdf",
            md5="def456",
        )
        DrawingExtraction.objects.create(
            drawing_file=processing_file,
            status=DrawingExtractionStatus.PROCESSING,
        )

        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url)

        status_data = response.data['processing_status']
        self.assertTrue(status_data['is_processing'])
        self.assertEqual(status_data['files_processing'], 1)
        self.assertEqual(status_data['files_completed'], 1)  # Original file
        self.assertEqual(len(status_data['files']), 1)
        self.assertEqual(status_data['files'][0]['name'], "Electrical.pdf")
        self.assertEqual(status_data['files'][0]['status'], "PROCESSING")
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_note_viewset.TestDrawingNoteViewSet.test_list_notes --verbosity=2`

Expected: FAIL with "NoReverseMatch: 'drawing-note-list'"

**Step 3: Create ViewSet and add URL**

Add to `apps/deliverables/views/drawing_views.py`:

```python
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django.db.models import OuterRef, Subquery

from ..models import DrawingNote, DrawingFile, DrawingExtraction, DrawingExtractionStatus
from ..serializers.drawing_serializers import DrawingNoteReadSerializer
from ..permissions import DrawingNoteAccessPermissions


class DrawingNotePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'limit'
    max_page_size = 100


class DrawingNoteViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for listing drawing notes.
    Mirrors SubmittalItemViewSet pattern with filtering and pagination.
    """
    permission_classes = [IsAuthenticated, DrawingNoteAccessPermissions]
    pagination_class = DrawingNotePagination
    serializer_class = DrawingNoteReadSerializer

    def get_queryset(self):
        project_id = self.kwargs['project_id']
        queryset = DrawingNote.objects.filter(
            section__page__drawing_file__project_id=project_id
        ).select_related(
            'section__page__drawing_file',
            'section__page__extraction',
        )

        # Filter by project_version_id
        version_id = self.request.query_params.get('project_version_id')
        if version_id:
            queryset = queryset.filter(
                section__page__drawing_file__project_version_id=version_id
            )

        # Filter by category
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)

        # Filter by drawing_file_id
        drawing_file_id = self.request.query_params.get('drawing_file_id')
        if drawing_file_id:
            queryset = queryset.filter(
                section__page__drawing_file_id=drawing_file_id
            )

        # Search in text (case-insensitive substring)
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(text__icontains=search)

        return queryset

    def _get_processing_status(self, project_id, version_id=None):
        """
        Get processing status for all drawing files in the project/version.
        Returns status object with file counts and details for files still processing.
        """
        # Get all drawing files for this project/version
        files_qs = DrawingFile.objects.filter(project_id=project_id)
        if version_id:
            files_qs = files_qs.filter(project_version_id=version_id)

        # Annotate with latest extraction status
        latest_extraction = DrawingExtraction.objects.filter(
            drawing_file=OuterRef('pk')
        ).order_by('-created_at')

        files_with_status = files_qs.annotate(
            latest_status=Subquery(latest_extraction.values('status')[:1])
        )

        # Count by status
        files_processing = 0
        files_completed = 0
        files_failed = 0
        processing_files = []

        for f in files_with_status:
            status = f.latest_status
            if status in [DrawingExtractionStatus.PENDING, DrawingExtractionStatus.PROCESSING]:
                files_processing += 1
                processing_files.append({
                    'id': f.id,
                    'name': f.file_name,
                    'status': status or DrawingExtractionStatus.PENDING,
                })
            elif status in [DrawingExtractionStatus.SUCCESS, DrawingExtractionStatus.PARTIAL_SUCCESS]:
                files_completed += 1
            elif status == DrawingExtractionStatus.FAILED:
                files_failed += 1
            elif status is None:
                # No extraction yet - treat as pending
                files_processing += 1
                processing_files.append({
                    'id': f.id,
                    'name': f.file_name,
                    'status': DrawingExtractionStatus.PENDING,
                })

        return {
            'is_processing': files_processing > 0,
            'files_processing': files_processing,
            'files_completed': files_completed,
            'files_failed': files_failed,
            'files': processing_files,
        }

    def list(self, request, *args, **kwargs):
        project_id = self.kwargs['project_id']
        version_id = request.query_params.get('project_version_id')

        queryset = self.filter_queryset(self.get_queryset())

        # Get filter values for UI dropdowns
        all_filter_vals = {
            'category': list(queryset.values_list('category', flat=True).distinct()),
            'drawing_file': list(queryset.values_list(
                'section__page__drawing_file__file_name', flat=True
            ).distinct()),
        }

        # Get processing status
        processing_status = self._get_processing_status(project_id, version_id)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data['all_filter_vals'] = all_filter_vals
            response.data['total_count'] = queryset.count()
            response.data['processing_status'] = processing_status
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'all_filter_vals': all_filter_vals,
            'total_count': queryset.count(),
            'processing_status': processing_status,
        })
```

Update `apps/deliverables/urls.py`:

```python
# Add import
from .views.drawing_views import DrawingNoteViewSet

# Add to single_project_router registrations (after existing registrations)
single_project_router.register(
    'drawing-notes',
    DrawingNoteViewSet,
    basename='drawing-note',
)
```

**Step 4: Run tests to verify they pass**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_note_viewset --verbosity=2`

Expected: All tests PASS

**Step 5: Commit**

```bash
git add apps/deliverables/views/drawing_views.py apps/deliverables/urls.py apps/deliverables/tests/test_drawing_note_viewset.py
git commit -m "$(cat <<'EOF'
feat: add DrawingNoteViewSet with filtering and pagination

Read-only API for listing drawing notes with:
- Project version, category, and drawing file filters
- Text search
- Pagination matching SubmittalItemViewSet pattern

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 4: Admin and Finishing Touches

### Task 13: Add Admin Classes

**Files:**
- Modify: `apps/deliverables/admin.py`

**Step 1: Add admin classes**

Add to `apps/deliverables/admin.py`:

```python
# Add imports at top
from .models import (
    # ... existing imports ...
    DrawingFile, DrawingExtraction, DrawingPage, DrawingNoteSection,
    DrawingNote, DrawingExtractionWebhookEvent,
)


@admin.register(DrawingFile)
class DrawingFileAdmin(admin.ModelAdmin):
    list_display = ['id', 'file_name', 'project', 'project_version', 'total_pages', 'created_at']
    list_filter = ['project', 'project_version']
    search_fields = ['file_name', 'project__name']
    raw_id_fields = ['project', 'project_version', 'uploaded_by']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(DrawingExtraction)
class DrawingExtractionAdmin(admin.ModelAdmin):
    list_display = ['id', 'drawing_file', 'status', 'started_at', 'completed_at', 'created_at']
    list_filter = ['status']
    search_fields = ['drawing_file__file_name']
    raw_id_fields = ['drawing_file']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(DrawingPage)
class DrawingPageAdmin(admin.ModelAdmin):
    list_display = ['id', 'drawing_file', 'page_number', 'page_type', 'extraction_status']
    list_filter = ['page_type', 'extraction_status']
    search_fields = ['drawing_file__file_name']
    raw_id_fields = ['drawing_file', 'extraction']


@admin.register(DrawingNoteSection)
class DrawingNoteSectionAdmin(admin.ModelAdmin):
    list_display = ['id', 'header', 'page']
    search_fields = ['header']
    raw_id_fields = ['page']


@admin.register(DrawingNote)
class DrawingNoteAdmin(admin.ModelAdmin):
    list_display = ['id', 'note_number', 'category', 'text_preview', 'section']
    list_filter = ['category']
    search_fields = ['text', 'category']
    raw_id_fields = ['section']

    def text_preview(self, obj):
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    text_preview.short_description = 'Text'


@admin.register(DrawingExtractionWebhookEvent)
class DrawingExtractionWebhookEventAdmin(admin.ModelAdmin):
    list_display = ['id', 'event_id', 'extraction', 'new_status', 'created_at']
    list_filter = ['new_status']
    search_fields = ['event_id']
    raw_id_fields = ['extraction']
    readonly_fields = ['created_at', 'updated_at']
```

**Step 2: Verify admin site loads**

Run: `docker-compose exec web python manage.py check`

Expected: System check identifies no issues

**Step 3: Commit**

```bash
git add apps/deliverables/admin.py
git commit -m "$(cat <<'EOF'
feat: add admin classes for drawing parser models

Enables debugging and inspection of drawing extraction
data through the Django admin interface.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 14: Run Full Test Suite

**Step 1: Run all drawing parser tests**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_parser_models apps.deliverables.tests.test_drawing_extraction_webhook apps.deliverables.tests.test_drawing_note_serializers apps.deliverables.tests.test_drawing_note_permissions apps.deliverables.tests.test_drawing_note_viewset --verbosity=2`

Expected: All tests PASS

**Step 2: Run full deliverables test suite to check for regressions**

Run: `docker-compose exec web python manage.py test apps.deliverables --verbosity=1`

Expected: All tests PASS

**Step 3: Commit any fixes if needed**

---

### Task 15: Final Documentation Update

**Files:**
- Modify: `.the_link/drawing_parser_webhook_design.md` (if needed)

**Step 1: Verify implementation matches design**

Review the design document and confirm all specified components were implemented:
- [x] DrawingExtractionStatus enum
- [x] DrawingPageType enum
- [x] DrawingPageExtractionStatus enum
- [x] DrawingFile model
- [x] DrawingExtraction model
- [x] DrawingPage model
- [x] DrawingNoteSection model
- [x] DrawingNote model
- [x] DrawingExtractionWebhookEvent model
- [x] Upload flow integration (Task 7.5)
- [x] Webhook endpoint with idempotency
- [x] DrawingNote list endpoint with filtering
- [x] Admin classes

**Step 2: Commit final state**

```bash
git add -A
git commit -m "$(cat <<'EOF'
feat: complete drawing parser webhook implementation

Full implementation of webhook system for receiving parsed
drawing data from AWS extraction service including:

- 6 new models with proper relationships
- Main upload flow integration with duplicate detection
- Idempotent webhook endpoint with status state machine
- Read-only API with pagination and filtering
- Admin interface for debugging

Closes: TBL-XXX

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

This plan implements the drawing parser webhook system in **16 tasks across 6 phases**:

| Phase | Tasks | Description |
|-------|-------|-------------|
| **Phase 0** | 1 | Add "drawings" feature flag with TDD |
| **Phase 1** | 2-7 | Create models and enums with TDD |
| **Phase 1.5** | 7.5 | Integrate drawing upload into main upload flow |
| **Phase 2** | 8-9 | Implement webhook endpoint with idempotency |
| **Phase 3** | 10-12 | Create API serializer, permissions, and ViewSet |
| **Phase 4** | 13-15 | Add admin, run tests, finalize |

Each task follows strict TDD: write failing test, implement, verify pass, commit.
