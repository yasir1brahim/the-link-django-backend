# Discipline Classification Backend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add discipline classification fields to the drawing extraction pipeline, enabling filtering of notes by construction trade.

**Architecture:** Extend existing `DrawingPage` and `DrawingNote` models with discipline fields. Update the webhook handler to extract these from Lambda payloads. Expose in API with filtering support.

**Tech Stack:** Django 4.x, PostgreSQL ArrayField, Django REST Framework

---

## Task 1: Add Discipline Enums to Models

**Files:**
- Modify: `apps/deliverables/models.py:834-854` (after existing enums)

**Step 1: Write the failing test**

Create test file `apps/deliverables/tests/test_discipline_enums.py`:

```python
# apps/deliverables/tests/test_discipline_enums.py
from django.test import TestCase
from apps.deliverables.models import Discipline, DisciplineConfidence


class TestDisciplineEnum(TestCase):
    def test_discipline_enum_has_all_ncs_codes(self):
        """Test Discipline enum contains all 21 NCS discipline codes"""
        expected_values = {
            "general", "hazardous_materials", "survey_mapping", "geotechnical",
            "civil", "landscape", "structural", "architectural", "interiors",
            "equipment", "fire_protection", "plumbing", "process", "mechanical",
            "electrical", "distributed_energy", "telecommunications", "resource",
            "other", "contractor_shop", "operations"
        }
        actual_values = {choice.value for choice in Discipline}
        self.assertEqual(actual_values, expected_values)

    def test_discipline_confidence_enum_has_levels(self):
        """Test DisciplineConfidence enum has high/medium/low"""
        expected_values = {"high", "medium", "low"}
        actual_values = {choice.value for choice in DisciplineConfidence}
        self.assertEqual(actual_values, expected_values)
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_discipline_enums -v 2`

Expected: FAIL with `ImportError: cannot import name 'Discipline'`

**Step 3: Write minimal implementation**

In `apps/deliverables/models.py`, add after line 854 (after `DrawingPageExtractionStatus`):

```python
class Discipline(models.TextChoices):
    """NCS (US National CAD Standard) discipline designators"""
    GENERAL = "general", "General"
    HAZARDOUS_MATERIALS = "hazardous_materials", "Hazardous Materials"
    SURVEY_MAPPING = "survey_mapping", "Survey/Mapping"
    GEOTECHNICAL = "geotechnical", "Geotechnical"
    CIVIL = "civil", "Civil"
    LANDSCAPE = "landscape", "Landscape"
    STRUCTURAL = "structural", "Structural"
    ARCHITECTURAL = "architectural", "Architectural"
    INTERIORS = "interiors", "Interiors"
    EQUIPMENT = "equipment", "Equipment"
    FIRE_PROTECTION = "fire_protection", "Fire Protection"
    PLUMBING = "plumbing", "Plumbing"
    PROCESS = "process", "Process"
    MECHANICAL = "mechanical", "Mechanical"
    ELECTRICAL = "electrical", "Electrical"
    DISTRIBUTED_ENERGY = "distributed_energy", "Distributed Energy"
    TELECOMMUNICATIONS = "telecommunications", "Telecommunications"
    RESOURCE = "resource", "Resource"
    OTHER = "other", "Other"
    CONTRACTOR_SHOP = "contractor_shop", "Contractor/Shop"
    OPERATIONS = "operations", "Operations"


class DisciplineConfidence(models.TextChoices):
    """Confidence level of discipline classification"""
    HIGH = "high", "High"
    MEDIUM = "medium", "Medium"
    LOW = "low", "Low"
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_discipline_enums -v 2`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/models.py apps/deliverables/tests/test_discipline_enums.py
git commit -m "feat: add Discipline and DisciplineConfidence enums"
```

---

## Task 2: Add Discipline Fields to DrawingPage Model

**Files:**
- Modify: `apps/deliverables/models.py:933-982` (DrawingPage class)
- Create: `apps/deliverables/migrations/0077_add_discipline_fields.py`

**Step 1: Write the failing test**

Add to `apps/deliverables/tests/test_discipline_enums.py`:

```python
from apps.deliverables.models import (
    DrawingPage, DrawingFile, DrawingExtraction, DrawingExtractionStatus,
    DrawingPageType, DrawingPageExtractionStatus, Discipline, DisciplineConfidence,
    Project,
)
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class TestDrawingPageDisciplineFields(TestCase):
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

    def test_drawing_page_has_sheet_discipline_field(self):
        """Test DrawingPage can store sheet_discipline"""
        page = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=1,
            page_type=DrawingPageType.DRAWING,
            extraction_status=DrawingPageExtractionStatus.SUCCESS,
            sheet_discipline=Discipline.MECHANICAL,
            sheet_discipline_confidence=DisciplineConfidence.HIGH,
        )
        page.refresh_from_db()
        self.assertEqual(page.sheet_discipline, Discipline.MECHANICAL)
        self.assertEqual(page.sheet_discipline_confidence, DisciplineConfidence.HIGH)

    def test_drawing_page_discipline_fields_nullable(self):
        """Test discipline fields are nullable"""
        page = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=1,
            page_type=DrawingPageType.DRAWING,
            extraction_status=DrawingPageExtractionStatus.SUCCESS,
            sheet_discipline=None,
            sheet_discipline_confidence=None,
        )
        page.refresh_from_db()
        self.assertIsNone(page.sheet_discipline)
        self.assertIsNone(page.sheet_discipline_confidence)
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_discipline_enums.TestDrawingPageDisciplineFields -v 2`

Expected: FAIL with `TypeError: DrawingPage() got unexpected keyword arguments: 'sheet_discipline'`

**Step 3: Write minimal implementation**

In `apps/deliverables/models.py`, add to `DrawingPage` class after `sheet_title` field (around line 975):

```python
    sheet_discipline = models.CharField(
        max_length=32,
        choices=Discipline.choices,
        null=True,
        blank=True,
        help_text="Primary discipline of the sheet based on sheet number prefix (e.g., M-101 → mechanical)",
    )
    sheet_discipline_confidence = models.CharField(
        max_length=16,
        choices=DisciplineConfidence.choices,
        null=True,
        blank=True,
        help_text="Confidence level of the discipline classification",
    )
```

**Step 4: Create and run migration**

Run: `docker-compose exec web python manage.py makemigrations deliverables --name add_discipline_fields_to_drawing_page`

Run: `docker-compose exec web python manage.py migrate`

**Step 5: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_discipline_enums.TestDrawingPageDisciplineFields -v 2`

Expected: PASS

**Step 6: Commit**

```bash
git add apps/deliverables/models.py apps/deliverables/migrations/
git commit -m "feat: add sheet_discipline fields to DrawingPage model"
```

---

## Task 3: Add Disciplines Field to DrawingNote Model

**Files:**
- Modify: `apps/deliverables/models.py:1005-1033` (DrawingNote class)
- Modify: `apps/deliverables/migrations/0077_*.py` (same migration or new one)

**Step 1: Write the failing test**

Add to `apps/deliverables/tests/test_discipline_enums.py`:

```python
from apps.deliverables.models import DrawingNote, DrawingNoteSection


class TestDrawingNoteDisciplineFields(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('test2@example.com')
        self.team = Team.objects.create(name="Test Team 2", slug="test-team-2")
        self.project = Project.objects.create(
            name="Test Project",
            project_number="P-002",
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

    def test_drawing_note_has_disciplines_array_field(self):
        """Test DrawingNote can store multiple disciplines"""
        note = DrawingNote.objects.create(
            section=self.section,
            note_number=1,
            category="GENERAL NOTES",
            text="Coordinate with mechanical and electrical.",
            disciplines=["mechanical", "electrical"],
            discipline_confidence=DisciplineConfidence.HIGH,
        )
        note.refresh_from_db()
        self.assertEqual(note.disciplines, ["mechanical", "electrical"])
        self.assertEqual(note.discipline_confidence, DisciplineConfidence.HIGH)

    def test_drawing_note_disciplines_default_empty_list(self):
        """Test disciplines field defaults to empty list"""
        note = DrawingNote.objects.create(
            section=self.section,
            note_number=1,
            category="GENERAL NOTES",
            text="Some note",
        )
        note.refresh_from_db()
        self.assertEqual(note.disciplines, [])

    def test_drawing_note_discipline_confidence_nullable(self):
        """Test discipline_confidence is nullable"""
        note = DrawingNote.objects.create(
            section=self.section,
            note_number=1,
            category="GENERAL NOTES",
            text="Some note",
            discipline_confidence=None,
        )
        note.refresh_from_db()
        self.assertIsNone(note.discipline_confidence)
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_discipline_enums.TestDrawingNoteDisciplineFields -v 2`

Expected: FAIL with `TypeError: DrawingNote() got unexpected keyword arguments: 'disciplines'`

**Step 3: Write minimal implementation**

At the top of `apps/deliverables/models.py`, add the ArrayField import (around line 1):

```python
from django.contrib.postgres.fields import ArrayField
```

In `apps/deliverables/models.py`, add to `DrawingNote` class after `drawing_references` field (around line 1022):

```python
    disciplines = ArrayField(
        models.CharField(max_length=32, choices=Discipline.choices),
        default=list,
        blank=True,
        help_text="List of disciplines this note relates to (can be multiple)",
    )
    discipline_confidence = models.CharField(
        max_length=16,
        choices=DisciplineConfidence.choices,
        null=True,
        blank=True,
        help_text="Confidence level of the discipline classification",
    )
```

**Step 4: Create and run migration**

Run: `docker-compose exec web python manage.py makemigrations deliverables --name add_discipline_fields_to_drawing_note`

Run: `docker-compose exec web python manage.py migrate`

**Step 5: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_discipline_enums.TestDrawingNoteDisciplineFields -v 2`

Expected: PASS

**Step 6: Commit**

```bash
git add apps/deliverables/models.py apps/deliverables/migrations/
git commit -m "feat: add disciplines ArrayField to DrawingNote model"
```

---

## Task 4: Update Webhook Handler to Extract Discipline Fields

**Files:**
- Modify: `apps/deliverables/views/drawing_views.py:139-231` (_create_drawing_records function)
- Test: `apps/deliverables/tests/test_drawing_extraction_webhook.py`

**Step 1: Write the failing test**

Add to `apps/deliverables/tests/test_drawing_extraction_webhook.py`:

```python
class TestDrawingExtractionWebhookDisciplineFields(TestCase):
    """Tests for discipline field extraction from webhook payload"""

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

    def test_sheet_discipline_extracted(self):
        """Test that sheet_discipline and confidence are extracted from payload"""
        from apps.deliverables.models import DrawingPage

        payload = {
            "event_id": "evt_disc_001",
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
                        "sheet_number": "M-101",
                        "sheet_discipline": "mechanical",
                        "sheet_discipline_confidence": "high",
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

        page = DrawingPage.objects.get(extraction=self.extraction)
        self.assertEqual(page.sheet_discipline, "mechanical")
        self.assertEqual(page.sheet_discipline_confidence, "high")

    def test_note_disciplines_extracted(self):
        """Test that note disciplines array and confidence are extracted"""
        from apps.deliverables.models import DrawingNote

        payload = {
            "event_id": "evt_disc_002",
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
                        "note_sections": [
                            {
                                "header": "GENERAL NOTES:",
                                "notes": [
                                    {
                                        "note_number": 1,
                                        "category": "GENERAL NOTES",
                                        "text": "Coordinate with electrical and plumbing.",
                                        "disciplines": ["mechanical", "electrical", "plumbing"],
                                        "discipline_confidence": "high",
                                    }
                                ]
                            }
                        ],
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

        note = DrawingNote.objects.get(section__page__extraction=self.extraction)
        self.assertEqual(note.disciplines, ["mechanical", "electrical", "plumbing"])
        self.assertEqual(note.discipline_confidence, "high")

    def test_missing_discipline_fields_default_gracefully(self):
        """Test webhook handles missing discipline fields gracefully"""
        from apps.deliverables.models import DrawingPage, DrawingNote

        payload = {
            "event_id": "evt_disc_003",
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
                        # No discipline fields
                        "note_sections": [
                            {
                                "header": "NOTES:",
                                "notes": [
                                    {
                                        "note_number": 1,
                                        "category": "NOTES",
                                        "text": "Some note",
                                        # No discipline fields
                                    }
                                ]
                            }
                        ],
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

        page = DrawingPage.objects.get(extraction=self.extraction)
        self.assertIsNone(page.sheet_discipline)
        self.assertIsNone(page.sheet_discipline_confidence)

        note = DrawingNote.objects.get(section__page__extraction=self.extraction)
        self.assertEqual(note.disciplines, [])
        self.assertIsNone(note.discipline_confidence)
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_extraction_webhook.TestDrawingExtractionWebhookDisciplineFields -v 2`

Expected: FAIL - discipline fields will be None/empty because webhook doesn't extract them yet

**Step 3: Write minimal implementation**

In `apps/deliverables/views/drawing_views.py`, update `_create_drawing_records()`:

In the DrawingPage creation block (around line 167-181), add the discipline fields:

```python
        page_objects.append(DrawingPage(
            drawing_file=extraction.drawing_file,
            extraction=extraction,
            page_number=page_data['page_number'],
            page_type=page_data['page_type'],
            rotation=page_data.get('rotation', 0),
            rotated_width=page_data.get('rotated_page_width'),
            rotated_height=page_data.get('rotated_page_height'),
            unrotated_width=page_data.get('unrotated_page_width'),
            unrotated_height=page_data.get('unrotated_page_height'),
            extraction_status=_normalize_page_extraction_status(page_data['extraction_status']),
            spec_content=page_data.get('spec_content'),
            sheet_number=page_data.get('sheet_number'),
            sheet_title=page_data.get('sheet_title'),
            sheet_discipline=page_data.get('sheet_discipline'),
            sheet_discipline_confidence=page_data.get('sheet_discipline_confidence'),
        ))
```

In the DrawingNote creation block (around line 218-229), add the discipline fields:

```python
            note_objects.append(DrawingNote(
                section=section,
                note_number=note_data['note_number'],
                category=note_data['category'],
                text=note_data['text'],
                bounding_box=note_data.get('unrotated_bounding_box') or note_data.get('bounding_box'),
                raw_bounding_box=note_data.get('rotated_bounding_box') or note_data.get('raw_bounding_box') or note_data.get('bounding_box'),
                rotated_bounding_box=note_data.get('rotated_bounding_box'),
                unrotated_bounding_box=note_data.get('unrotated_bounding_box'),
                source_blocks=note_data.get('source_blocks'),
                drawing_references=note_data.get('drawing_references'),
                disciplines=note_data.get('disciplines', []),
                discipline_confidence=note_data.get('discipline_confidence'),
            ))
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_extraction_webhook.TestDrawingExtractionWebhookDisciplineFields -v 2`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/views/drawing_views.py apps/deliverables/tests/test_drawing_extraction_webhook.py
git commit -m "feat: extract discipline fields in webhook handler"
```

---

## Task 5: Update Serializer to Expose Discipline Fields

**Files:**
- Modify: `apps/deliverables/serializers/drawing_serializers.py`
- Test: `apps/deliverables/tests/test_drawing_note_serializers.py`

**Step 1: Write the failing test**

Add to `apps/deliverables/tests/test_drawing_note_serializers.py`:

```python
class TestDrawingNoteSerializerDisciplineFields(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('test2@example.com')
        self.team = Team.objects.create(name="Test Team 2", slug="test-team-2")
        self.project = Project.objects.create(
            name="Test Project",
            project_number="P-002",
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
            sheet_discipline="mechanical",
            sheet_discipline_confidence="high",
        )
        self.section = DrawingNoteSection.objects.create(
            page=self.page,
            header="GENERAL NOTES:",
        )
        self.note = DrawingNote.objects.create(
            section=self.section,
            note_number=1,
            category="GENERAL NOTES",
            text="Coordinate with electrical.",
            disciplines=["mechanical", "electrical"],
            discipline_confidence="high",
        )

    def test_serializer_includes_sheet_discipline(self):
        """Test serializer includes sheet_discipline from page"""
        serializer = DrawingNoteReadSerializer(self.note)
        data = serializer.data

        self.assertIn('sheet_discipline', data)
        self.assertEqual(data['sheet_discipline'], "mechanical")

    def test_serializer_includes_disciplines_array(self):
        """Test serializer includes disciplines array from note"""
        serializer = DrawingNoteReadSerializer(self.note)
        data = serializer.data

        self.assertIn('disciplines', data)
        self.assertEqual(data['disciplines'], ["mechanical", "electrical"])

    def test_serializer_handles_null_sheet_discipline(self):
        """Test serializer handles null sheet_discipline"""
        self.page.sheet_discipline = None
        self.page.save()

        serializer = DrawingNoteReadSerializer(self.note)
        data = serializer.data

        self.assertIn('sheet_discipline', data)
        self.assertIsNone(data['sheet_discipline'])

    def test_serializer_handles_empty_disciplines(self):
        """Test serializer handles empty disciplines array"""
        self.note.disciplines = []
        self.note.save()

        serializer = DrawingNoteReadSerializer(self.note)
        data = serializer.data

        self.assertIn('disciplines', data)
        self.assertEqual(data['disciplines'], [])
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_note_serializers.TestDrawingNoteSerializerDisciplineFields -v 2`

Expected: FAIL with `KeyError: 'sheet_discipline'`

**Step 3: Write minimal implementation**

In `apps/deliverables/serializers/drawing_serializers.py`, update `DrawingNoteReadSerializer`:

Add the field declaration (around line 35, after `section_unrotated_header_bbox`):

```python
    sheet_discipline = serializers.SerializerMethodField()
```

Add the method (around line 77, after `get_page_extraction_failed`):

```python
    def get_sheet_discipline(self, obj):
        return obj.section.page.sheet_discipline
```

Update the `fields` list in `Meta` class to include the new fields (add after 'page_extraction_failed'):

```python
            'sheet_discipline',
            'disciplines',
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_note_serializers.TestDrawingNoteSerializerDisciplineFields -v 2`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/serializers/drawing_serializers.py apps/deliverables/tests/test_drawing_note_serializers.py
git commit -m "feat: expose discipline fields in DrawingNote serializer"
```

---

## Task 6: Add Discipline Filtering to ViewSet

**Files:**
- Modify: `apps/deliverables/views/drawing_views.py:300-356` (get_queryset method)
- Test: `apps/deliverables/tests/test_drawing_note_viewset.py`

**Step 1: Write the failing test**

Add to `apps/deliverables/tests/test_drawing_note_viewset.py`:

```python
class TestDrawingNoteViewSetDisciplineFiltering(TestCase):
    """Tests for discipline filtering in DrawingNoteViewSet"""

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
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ROLE_PROJECT_MEMBER
        )

        # Create drawing file
        self.drawing_file = DrawingFile.objects.create(
            project=self.project,
            project_version=self.project_version,
            file_name="Mixed.pdf",
            file_s3_key="drawings/mixed.pdf",
            md5="abc123",
        )
        self.extraction = DrawingExtraction.objects.create(
            drawing_file=self.drawing_file,
            status=DrawingExtractionStatus.SUCCESS,
        )

        # Create mechanical page with notes
        self.mech_page = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=1,
            page_type=DrawingPageType.DRAWING,
            extraction_status=DrawingPageExtractionStatus.SUCCESS,
            sheet_discipline="mechanical",
        )
        self.mech_section = DrawingNoteSection.objects.create(
            page=self.mech_page, header="MECHANICAL NOTES:"
        )
        self.mech_note = DrawingNote.objects.create(
            section=self.mech_section,
            note_number=1,
            category="MECHANICAL",
            text="Mechanical note",
            disciplines=["mechanical"],
        )

        # Create electrical page with notes
        self.elec_page = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=2,
            page_type=DrawingPageType.DRAWING,
            extraction_status=DrawingPageExtractionStatus.SUCCESS,
            sheet_discipline="electrical",
        )
        self.elec_section = DrawingNoteSection.objects.create(
            page=self.elec_page, header="ELECTRICAL NOTES:"
        )
        self.elec_note = DrawingNote.objects.create(
            section=self.elec_section,
            note_number=1,
            category="ELECTRICAL",
            text="Electrical note",
            disciplines=["electrical"],
        )

        # Create cross-discipline note (on mechanical page, references plumbing)
        self.cross_note = DrawingNote.objects.create(
            section=self.mech_section,
            note_number=2,
            category="COORDINATION",
            text="Coordinate with plumbing",
            disciplines=["mechanical", "plumbing"],
        )

        self.client.force_authenticate(user=self.user)

    def test_filter_by_sheet_discipline(self):
        """Test filtering by sheet_discipline"""
        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url, {'sheet_discipline': 'mechanical'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)  # Both notes on mech page
        for note in response.data['results']:
            self.assertEqual(note['sheet_discipline'], 'mechanical')

    def test_filter_by_disciplines_contains(self):
        """Test filtering notes that contain a specific discipline"""
        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url, {'disciplines': 'plumbing'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['text'], "Coordinate with plumbing")

    def test_filter_by_disciplines_returns_cross_discipline_notes(self):
        """Test that filtering by discipline returns notes with multiple disciplines"""
        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url, {'disciplines': 'mechanical'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return mech_note and cross_note (both have mechanical in disciplines)
        self.assertEqual(len(response.data['results']), 2)
        texts = {r['text'] for r in response.data['results']}
        self.assertIn("Mechanical note", texts)
        self.assertIn("Coordinate with plumbing", texts)

    def test_disciplines_field_in_response(self):
        """Test that disciplines array appears in API response"""
        url = reverse('deliverables:drawing-note-list', kwargs={'project_id': self.project.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data['results']) > 0)

        # Find the cross-discipline note
        cross_note = next(
            r for r in response.data['results']
            if r['text'] == "Coordinate with plumbing"
        )
        self.assertEqual(cross_note['disciplines'], ["mechanical", "plumbing"])
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_note_viewset.TestDrawingNoteViewSetDisciplineFiltering -v 2`

Expected: FAIL - filtering returns all notes instead of filtered results

**Step 3: Write minimal implementation**

In `apps/deliverables/views/drawing_views.py`, update `get_queryset()` in `DrawingNoteViewSet`.

Add after the `search` filter block (around line 352):

```python
        # Filter by sheet_discipline
        sheet_discipline = self.request.query_params.get('sheet_discipline')
        if sheet_discipline:
            queryset = queryset.filter(section__page__sheet_discipline=sheet_discipline)

        # Filter by disciplines (notes containing this discipline)
        disciplines = self.request.query_params.get('disciplines')
        if disciplines:
            queryset = queryset.filter(disciplines__contains=[disciplines])
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_note_viewset.TestDrawingNoteViewSetDisciplineFiltering -v 2`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/views/drawing_views.py apps/deliverables/tests/test_drawing_note_viewset.py
git commit -m "feat: add discipline filtering to DrawingNoteViewSet"
```

---

## Task 7: Run Full Test Suite and Verify

**Step 1: Run all drawing-related tests**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_drawing_extraction_webhook apps.deliverables.tests.test_drawing_note_viewset apps.deliverables.tests.test_drawing_note_serializers apps.deliverables.tests.test_discipline_enums -v 2`

Expected: All tests PASS

**Step 2: Run the full deliverables test suite**

Run: `docker-compose exec web python manage.py test apps.deliverables -v 2`

Expected: All tests PASS

**Step 3: Commit any fixes if needed**

If any tests fail, fix them and commit.

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add Discipline enums | models.py, test_discipline_enums.py |
| 2 | Add fields to DrawingPage | models.py, migration |
| 3 | Add fields to DrawingNote | models.py, migration |
| 4 | Update webhook handler | drawing_views.py, test_drawing_extraction_webhook.py |
| 5 | Update serializer | drawing_serializers.py, test_drawing_note_serializers.py |
| 6 | Add API filtering | drawing_views.py, test_drawing_note_viewset.py |
| 7 | Full test suite verification | - |
