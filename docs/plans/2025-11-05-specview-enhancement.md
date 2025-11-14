# SpecView Enhancement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert AiGeneratedLog JSON data to ExtractedData model instances and build CRUD endpoints for annotations

**Architecture:** Create ExtractedData model to normalize JSON rows, run data migration via Django migration file for automatic deployment, update all views/serializers to use the new model while maintaining backwards compatibility, then add annotation CRUD endpoints with proper permissions

**Tech Stack:** Django 4.2, Django REST Framework, PostgreSQL, pytest, openpyxl (for Excel export)

**Command Convention:** Run Django management commands and tests with `docker-compose exec web <command>` unless explicitly noted otherwise.

---

## Phase 1: Create ExtractedData Model and Tests

### Task 1: Create ExtractedData Model with Tests

**Files:**
- Create: `apps/deliverables/tests/test_extracted_data_model.py`
- Modify: `apps/deliverables/models.py:433` (after AiGeneratedLog)

**Step 1: Write failing test for ExtractedData model**

```python
# apps/deliverables/tests/test_extracted_data_model.py
import pytest
from django.test import TestCase
from apps.deliverables.models import ExtractedData, AiGeneratedLog, Project, ProjectVersion, ExtractionSource
from django.contrib.auth import get_user_model

User = get_user_model()

class TestExtractedDataModel(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('test@example.com')
        self.project = Project.objects.create(name="Test Project")
        self.version = ProjectVersion.objects.create(
            project=self.project, name="v1"
        )
        self.ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type="inspection_log",
            log_status="SUCCESS"
        )

    def test_extracted_data_creation(self):
        """Test basic ExtractedData model creation"""
        extracted = ExtractedData.objects.create(
            ai_generated_log=self.ai_log,
            project=self.project,
            project_version=self.version,
            spec_section_number="03 3000",
            spec_section_name="Concrete",
            extraction_type="inspection_log",
            requirement_text="Visual inspection of formwork",
            responsible_party="QC Inspector",
            when_due="Daily",
            inspection_frequency="Daily",
            source="AI",
            created_by=self.user
        )

        self.assertEqual(extracted.spec_section_number, "03 3000")
        self.assertEqual(extracted.extraction_type, "inspection_log")
        self.assertEqual(extracted.source, "AI")
        self.assertEqual(extracted.created_by, self.user)
        self.assertFalse(extracted.is_annotated)

    def test_human_created_extraction(self):
        """Test human-created extraction"""
        extracted = ExtractedData.objects.create(
            project=self.project,
            project_version=self.version,
            spec_section_number="05 1000",
            spec_section_name="Metals",
            extraction_type="owner_deliverables_log",
            requirement_text="Manual entry by user",
            source="HUMAN",
            created_by=self.user
        )

        self.assertEqual(extracted.source, "HUMAN")
        self.assertIsNone(extracted.ai_generated_log)  # No AI log for human entries
        self.assertEqual(extracted.created_by, self.user)

    def test_annotation_fields(self):
        """Test annotation-specific fields"""
        extracted = ExtractedData.objects.create(
            ai_generated_log=self.ai_log,
            project=self.project,
            project_version=self.version,
            spec_section_number="01 1000",
            spec_section_name="General",
            extraction_type="owner_deliverables_log",
            requirement_text="Submit documentation",
            annotation_type="submittal",
            is_annotated=True,
            annotation_notes="Marked as submittal by user",
            source="AI",
            created_by=self.user,
            annotated_by=self.user
        )

        self.assertEqual(extracted.annotation_type, "submittal")
        self.assertTrue(extracted.is_annotated)
        self.assertEqual(extracted.annotated_by, self.user)
        self.assertIn("submittal", extracted.annotation_notes)
```

**Step 2: Run test to verify it fails**

Run: `pytest apps/deliverables/tests/test_extracted_data_model.py -v`
Expected: FAIL with "ImportError: cannot import name 'ExtractedData'"

**Step 3: Add nullable `created_by` to `AiGeneratedLog`**

```python
# apps/deliverables/models.py (inside the AiGeneratedLog model)
class AiGeneratedLog(BaseModel):
    project = models.ForeignKey("Project", on_delete=models.CASCADE)
    project_version = models.ForeignKey("ProjectVersion", on_delete=models.CASCADE)
    log_type = models.CharField(max_length=256)
    log_status = models.CharField(max_length=256)
    log_table = models.TextField(blank=True, null=True)
    log_data = models.JSONField(blank=True, null=True, help_text="Structured data for inspection logs and owner deliverables logs")
    qa_options_selected = models.JSONField(blank=True, null=True, help_text="Selected QA options for qa_planner log type")
    completion_status = models.JSONField(blank=True, null=True, help_text="Status of each QA option processing")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_generated_logs',
        help_text="User who triggered this AI log (null when automated)"
    )
```

Add a migration to backfill the new field with `NULL` so existing rows remain valid.

**Step 4: Create ExtractedData model**

```python
# apps/deliverables/models.py (add after AiGeneratedLog class, around line 433)

class ExtractionSource(models.TextChoices):
    """Source of the extracted data"""
    AI = "AI", "AI Generated"
    HUMAN = "HUMAN", "Human Created"

class AnnotationType(models.TextChoices):
    """Types of annotations users can apply to extracted data"""
    SUBMITTAL = "submittal", "Submittal"
    INSPECTION = "inspection", "Inspection"
    OWNER_DELIVERABLE = "owner_deliverable", "Owner Deliverable"
    QA_INSPECTION = "qa_inspection", "QA Inspection"
    QA_WARRANTY = "qa_warranty", "QA Warranty"
    QA_CERTIFICATE = "qa_certificate", "QA Certificate"
    QA_CLOSEOUT = "qa_closeout", "QA Closeout"
    QA_TEST_REPORT = "qa_test_report", "QA Test Report"
    QA_COMMISSIONING = "qa_commissioning", "QA Commissioning"
    QA_DELEGATED_DESIGN = "qa_delegated_design", "QA Delegated Design"
    QA_MOCKUP = "qa_mockup", "QA Mock-up/Sample"
    QA_PRE_INSTALL = "qa_pre_install", "QA Pre-Installation Meeting"

class ExtractedData(BaseModel):
    """Individual row extracted from AI-generated logs or manually created"""

    # Foreign keys
    ai_generated_log = models.ForeignKey(
        'AiGeneratedLog',
        on_delete=models.CASCADE,
        related_name='extracted_items',
        null=True,
        blank=True,
        help_text="AI log this was extracted from (null for human-created)"
    )
    project = models.ForeignKey('Project', on_delete=models.CASCADE)
    project_version = models.ForeignKey('ProjectVersion', on_delete=models.CASCADE)
    spec_section = models.ForeignKey(
        'SpecSection',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Creation metadata
    source = models.CharField(
        max_length=10,
        choices=ExtractionSource.choices,
        default=ExtractionSource.AI,
        help_text="Whether this was AI-generated or human-created"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_extractions',
        help_text="User who created this extraction (for HUMAN source) or triggered AI generation"
    )

    # Core data fields
    spec_section_number = models.CharField(max_length=256)
    spec_section_name = models.CharField(max_length=512)
    paragraph_number = models.CharField(max_length=256, blank=True, null=True)

    # Type classification
    extraction_type = models.CharField(
        max_length=256,
        help_text="Original log type: inspection_log, owner_deliverables_log, qa_planner"
    )
    item_type = models.CharField(
        max_length=256,
        blank=True,
        null=True,
        help_text="For QA planner subtypes"
    )

    # Content fields
    requirement_text = models.TextField()
    responsible_party = models.CharField(max_length=512, blank=True, null=True)
    when_due = models.CharField(max_length=512, blank=True, null=True)

    # Inspection-specific
    inspection_frequency = models.CharField(max_length=256, blank=True, null=True)

    # Owner deliverables-specific
    deliverable_type = models.CharField(max_length=256, blank=True, null=True)

    # PDF location data
    pdf_locations = models.JSONField(
        blank=True,
        null=True,
        help_text="PDF coordinate data for highlighting"
    )

    # Annotation metadata
    annotation_type = models.CharField(
        max_length=256,
        choices=AnnotationType.choices,
        blank=True,
        null=True,
        help_text="User-defined classification of this item"
    )
    is_annotated = models.BooleanField(default=False)
    annotation_notes = models.TextField(blank=True, null=True)
    annotated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='annotated_extractions'
    )
    annotated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'deliverables_extracted_data'
        indexes = [
            models.Index(fields=['project', 'project_version']),
            models.Index(fields=['spec_section_number']),
            models.Index(fields=['extraction_type', 'item_type']),
            models.Index(fields=['is_annotated']),
            models.Index(fields=['annotation_type']),
            models.Index(fields=['source']),
            models.Index(fields=['created_by']),
        ]
        ordering = ['spec_section_number', 'id']

    def __str__(self):
        return f"{self.spec_section_number} - {self.requirement_text[:50]}"

    def save(self, *args, **kwargs):
        """Override save to set created_by for AI sources from request context"""
        if self.source == ExtractionSource.AI and not self.created_by_id:
            # Try to get user from ai_generated_log if available
            if self.ai_generated_log and hasattr(self.ai_generated_log, 'created_by'):
                self.created_by = self.ai_generated_log.created_by

        super().save(*args, **kwargs)
```

**Step 5: Create and run migration**

Run: `python manage.py makemigrations deliverables`
Expected: Creates `apps/deliverables/migrations/0XXX_add_extracteddata_model.py`

Run: `python manage.py migrate`
Expected: SUCCESS

**Step 6: Run test to verify it passes**

Run: `pytest apps/deliverables/tests/test_extracted_data_model.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add apps/deliverables/models.py
git add apps/deliverables/tests/test_extracted_data_model.py
git add apps/deliverables/migrations/0XXX_add_extracteddata_model.py
git commit -m "feat: add ExtractedData model with source tracking for AI/human entries"
```

### Task 2: Add Model Relationships Tests

**Files:**
- Modify: `apps/deliverables/tests/test_extracted_data_model.py`

**Step 1: Write test for model relationships**

```python
# Add to apps/deliverables/tests/test_extracted_data_model.py

def test_ai_log_relationship(self):
    """Test relationship between AiGeneratedLog and ExtractedData"""
    # Create multiple extracted items
    for i in range(3):
        ExtractedData.objects.create(
            ai_generated_log=self.ai_log,
            project=self.project,
            project_version=self.version,
            spec_section_number=f"0{i} 1000",
            spec_section_name=f"Section {i}",
            extraction_type="inspection_log",
            requirement_text=f"Requirement {i}",
            source="AI",
            created_by=self.user
        )

    # Test reverse relationship
    self.assertEqual(self.ai_log.extracted_items.count(), 3)

    # Test cascade delete
    log_id = self.ai_log.id
    self.ai_log.delete()
    self.assertFalse(
        ExtractedData.objects.filter(ai_generated_log_id=log_id).exists()
    )

def test_spec_section_relationship(self):
    """Test optional SpecSection relationship"""
    spec_section = SpecSection.objects.create(
        project=self.project,
        project_version=self.version,
        spec_section_number="03 3000",
        spec_section_name="Concrete"
    )

    extracted = ExtractedData.objects.create(
        ai_generated_log=self.ai_log,
        project=self.project,
        project_version=self.version,
        spec_section=spec_section,
        spec_section_number="03 3000",
        spec_section_name="Concrete",
        extraction_type="inspection_log",
        requirement_text="Test requirement",
        source="AI"
    )

    self.assertEqual(extracted.spec_section, spec_section)

    # Test SET_NULL on delete
    spec_section.delete()
    extracted.refresh_from_db()
    self.assertIsNone(extracted.spec_section)

def test_created_by_relationship(self):
    """Test created_by user relationship"""
    user2 = User.objects.create_user('user2@example.com')

    # AI-created with created_by
    ai_extracted = ExtractedData.objects.create(
        ai_generated_log=self.ai_log,
        project=self.project,
        project_version=self.version,
        spec_section_number="01 1000",
        spec_section_name="General",
        extraction_type="inspection_log",
        requirement_text="AI generated",
        source="AI",
        created_by=self.user
    )

    # Human-created
    human_extracted = ExtractedData.objects.create(
        project=self.project,
        project_version=self.version,
        spec_section_number="02 1000",
        spec_section_name="Existing",
        extraction_type="inspection_log",
        requirement_text="Human created",
        source="HUMAN",
        created_by=user2
    )

    # Check relationships
    self.assertEqual(self.user.created_extractions.count(), 1)
    self.assertEqual(user2.created_extractions.count(), 1)

    # Test SET_NULL on user delete
    user2.delete()
    human_extracted.refresh_from_db()
    self.assertIsNone(human_extracted.created_by)
```

**Step 2: Run test to verify it passes**

Run: `pytest apps/deliverables/tests/test_extracted_data_model.py::TestExtractedDataModel::test_created_by_relationship -v`
Expected: PASS

**Step 3: Commit**

```bash
git add apps/deliverables/tests/test_extracted_data_model.py
git commit -m "test: add ExtractedData relationship tests including source tracking"
```

### Task 3: Create ExtractedData Admin Interface

**Files:**
- Create: `apps/deliverables/tests/test_extracted_data_admin.py`
- Modify: `apps/deliverables/admin.py:407` (after AiGeneratedLogAdmin)

**Step 1: Write test for admin interface**

```python
# apps/deliverables/tests/test_extracted_data_admin.py
from django.test import TestCase
from django.contrib.admin.sites import site
from apps.deliverables.models import ExtractedData
from apps.deliverables.admin import ExtractedDataAdmin

class TestExtractedDataAdmin(TestCase):
    def test_admin_registered(self):
        """Test ExtractedData is registered in admin"""
        self.assertIn(ExtractedData, site._registry)

    def test_admin_list_display(self):
        """Test admin list display fields"""
        admin = ExtractedDataAdmin(ExtractedData, site)
        expected = [
            'id', 'spec_section_number', 'spec_section_name',
            'extraction_type', 'source', 'created_by',
            'annotation_type', 'is_annotated', 'created_at'
        ]
        self.assertEqual(list(admin.list_display), expected)

    def test_admin_list_filter(self):
        """Test admin filter options"""
        admin = ExtractedDataAdmin(ExtractedData, site)
        expected = [
            'source', 'extraction_type', 'item_type',
            'annotation_type', 'is_annotated', 'project'
        ]
        self.assertEqual(list(admin.list_filter), expected)
```

**Step 2: Run test to verify it fails**

Run: `pytest apps/deliverables/tests/test_extracted_data_admin.py -v`
Expected: FAIL with "ImportError: cannot import name 'ExtractedDataAdmin'"

**Step 3: Add ExtractedData admin**

```python
# apps/deliverables/admin.py (add after AiGeneratedLogAdmin, around line 407)

@admin.register(ExtractedData)
class ExtractedDataAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'spec_section_number', 'spec_section_name',
        'extraction_type', 'source', 'created_by',
        'annotation_type', 'is_annotated', 'created_at'
    ]
    list_filter = [
        'source', 'extraction_type', 'item_type',
        'annotation_type', 'is_annotated', 'project'
    ]
    search_fields = [
        'spec_section_number', 'spec_section_name',
        'requirement_text', 'annotation_notes'
    ]
    readonly_fields = ['created_at', 'updated_at', 'annotated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'source', 'created_by', 'ai_generated_log',
                'project', 'project_version', 'spec_section',
                'spec_section_number', 'spec_section_name'
            )
        }),
        ('Extraction Details', {
            'fields': (
                'extraction_type', 'item_type', 'paragraph_number',
                'requirement_text', 'responsible_party', 'when_due',
                'inspection_frequency', 'deliverable_type'
            )
        }),
        ('PDF Data', {
            'fields': ('pdf_locations',),
            'classes': ('collapse',)
        }),
        ('Annotation', {
            'fields': (
                'annotation_type', 'is_annotated', 'annotation_notes',
                'annotated_by', 'annotated_at'
            )
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'ai_generated_log', 'project', 'project_version',
            'spec_section', 'created_by', 'annotated_by'
        )
```

**Step 4: Run test to verify it passes**

Run: `pytest apps/deliverables/tests/test_extracted_data_admin.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/admin.py
git add apps/deliverables/tests/test_extracted_data_admin.py
git commit -m "feat: add ExtractedData admin interface with source tracking"
```

---

## Phase 2: Data Migration via Django Migration

### Task 4: Create Data Migration for ExtractedData

**Files:**
- Create: `apps/deliverables/tests/test_extracted_data_migration.py`
- Create: `apps/deliverables/migrations/0XXX_migrate_ai_log_data_to_extracted.py`

**Step 1: Write test for data migration**

```python
# apps/deliverables/tests/test_extracted_data_migration.py
from django.test import TestCase, TransactionTestCase
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from apps.deliverables.models import AiGeneratedLog, ExtractedData, Project, ProjectVersion
from django.contrib.auth import get_user_model

User = get_user_model()

class TestExtractedDataMigration(TransactionTestCase):
    migrate_from = '0XXX_add_extracteddata_model'  # Previous migration
    migrate_to = '0XXX_migrate_ai_log_data_to_extracted'  # Our data migration

    def setUp(self):
        # Start at the previous migration
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([('deliverables', self.migrate_from)])

        # Create test data using old structure
        Project = self.executor.loader.project_state([('deliverables', self.migrate_from)]).apps.get_model('deliverables', 'Project')
        ProjectVersion = self.executor.loader.project_state([('deliverables', self.migrate_from)]).apps.get_model('deliverables', 'ProjectVersion')
        AiGeneratedLog = self.executor.loader.project_state([('deliverables', self.migrate_from)]).apps.get_model('deliverables', 'AiGeneratedLog')
        User = self.executor.loader.project_state([('deliverables', self.migrate_from)]).apps.get_model('accounts', 'User')

        # Create user for created_by tracking
        self.user = User.objects.create(email='test@example.com')

        project = Project.objects.create(name="Test Project")
        version = ProjectVersion.objects.create(project=project, name="v1")

        # Create inspection log with created_by
        self.inspection_log = AiGeneratedLog.objects.create(
            project=project,
            project_version=version,
            log_type='inspection_log',
            log_status='SUCCESS',
            created_by=self.user,  # Assuming AiGeneratedLog has created_by field
            log_data=[
                {
                    'Spec Section #': '03 3000',
                    'Spec Section Name': 'Concrete',
                    'Inspection Type And Requirements': 'Visual inspection',
                    'Inspection Frequency': 'Daily',
                    'Responsible Party': 'QC Inspector',
                    'pdf_locations': [{'page': 1, 'x': 100, 'y': 200}]
                },
                {
                    'Spec Section #': '04 2000',
                    'Spec Section Name': 'Masonry',
                    'Inspection Type And Requirements': 'Block inspection',
                    'Inspection Frequency': 'Weekly',
                    'Responsible Party': 'Inspector'
                }
            ]
        )

        # Create owner deliverables log
        self.owner_log = AiGeneratedLog.objects.create(
            project=project,
            project_version=version,
            log_type='owner_deliverables_log',
            log_status='SUCCESS',
            log_data=[
                {
                    'Spec Section #': '01 2000',
                    'Spec Section Name': 'Existing Conditions',
                    'Deliverable Type': 'Submittals',
                    'When Due': 'Before construction',
                    'Responsible Party': 'General Contractor',
                    'Exact Requirement Text': 'Submit documentation'
                }
            ]
        )

        # Create QA planner log
        self.qa_log = AiGeneratedLog.objects.create(
            project=project,
            project_version=version,
            log_type='qa_planner',
            log_status='SUCCESS',
            log_data=[
                {
                    'Spec Section #': '01 1000',
                    'Spec Section Name': 'General Requirements',
                    'Paragraph Number': '1.1',
                    'item_type': 'inspections',
                    'Requirement Text': 'Comply with codes',
                    'Responsible Party': 'Contractor',
                    'When Due': 'Before start'
                }
            ]
        )

    def test_migration_creates_extracted_data(self):
        """Test that migration creates ExtractedData records with source"""
        # Run the migration
        self.executor.migrate([('deliverables', self.migrate_to)])

        # Get the new models
        ExtractedData = self.executor.loader.project_state([('deliverables', self.migrate_to)]).apps.get_model('deliverables', 'ExtractedData')

        # Check inspection log migration
        inspection_items = ExtractedData.objects.filter(
            ai_generated_log_id=self.inspection_log.id
        )
        self.assertEqual(inspection_items.count(), 2)

        # Check first inspection item
        item = inspection_items.first()
        self.assertEqual(item.spec_section_number, '03 3000')
        self.assertEqual(item.spec_section_name, 'Concrete')
        self.assertEqual(item.extraction_type, 'inspection_log')
        self.assertEqual(item.requirement_text, 'Visual inspection')
        self.assertEqual(item.inspection_frequency, 'Daily')
        self.assertEqual(item.responsible_party, 'QC Inspector')
        self.assertEqual(item.source, 'AI')  # Should be set to AI
        self.assertEqual(item.created_by_id, self.user.id)  # Should inherit from log
        self.assertIsNotNone(item.pdf_locations)

        # Check owner deliverables migration
        owner_items = ExtractedData.objects.filter(
            ai_generated_log_id=self.owner_log.id
        )
        self.assertEqual(owner_items.count(), 1)

        item = owner_items.first()
        self.assertEqual(item.deliverable_type, 'Submittals')
        self.assertEqual(item.requirement_text, 'Submit documentation')
        self.assertEqual(item.source, 'AI')

        # Check QA planner migration
        qa_items = ExtractedData.objects.filter(
            ai_generated_log_id=self.qa_log.id
        )
        self.assertEqual(qa_items.count(), 1)

        item = qa_items.first()
        self.assertEqual(item.item_type, 'inspections')
        self.assertEqual(item.paragraph_number, '1.1')
        self.assertEqual(item.source, 'AI')
```

**Step 2: Run test to verify it fails**

Run: `pytest apps/deliverables/tests/test_extracted_data_migration.py -v`
Expected: FAIL (migration doesn't exist yet)

**Step 3: Create data migration**

```python
# apps/deliverables/migrations/0XXX_migrate_ai_log_data_to_extracted.py
from django.db import migrations, transaction
import logging

logger = logging.getLogger(__name__)

def migrate_ai_log_data(apps, schema_editor):
    """Migrate data from AiGeneratedLog.log_data to ExtractedData model"""
    AiGeneratedLog = apps.get_model('deliverables', 'AiGeneratedLog')
    ExtractedData = apps.get_model('deliverables', 'ExtractedData')

    # Process each AI log
    for ai_log in AiGeneratedLog.objects.filter(log_status='SUCCESS').iterator(chunk_size=100):
        if not ai_log.log_data:
            continue

        extracted_items = []

        try:
            with transaction.atomic():
                for item in ai_log.log_data:
                    extracted_data = {
                        'ai_generated_log': ai_log,
                        'project': ai_log.project,
                        'project_version': ai_log.project_version,
                        'extraction_type': ai_log.log_type,
                        'source': 'AI',  # All migrated data is AI-generated
                    }

                    # Try to get created_by from the AI log if it has that field
                    if hasattr(ai_log, 'created_by'):
                        extracted_data['created_by'] = ai_log.created_by

                    # Common fields
                    extracted_data['spec_section_number'] = item.get('Spec Section #', '')
                    extracted_data['spec_section_name'] = item.get('Spec Section Name', '')
                    extracted_data['responsible_party'] = item.get('Responsible Party')
                    extracted_data['pdf_locations'] = item.get('pdf_locations')

                    # Handle different log types
                    if ai_log.log_type == 'inspection_log':
                        extracted_data['requirement_text'] = item.get('Inspection Type And Requirements', '')
                        extracted_data['inspection_frequency'] = item.get('Inspection Frequency')
                        extracted_data['when_due'] = item.get('Inspection Frequency')  # Use frequency as when_due

                    elif ai_log.log_type == 'owner_deliverables_log':
                        extracted_data['requirement_text'] = item.get('Exact Requirement Text', '')
                        extracted_data['deliverable_type'] = item.get('Deliverable Type')
                        extracted_data['when_due'] = item.get('When Due')

                    elif ai_log.log_type == 'qa_planner':
                        extracted_data['requirement_text'] = item.get('Requirement Text', '')
                        extracted_data['item_type'] = item.get('item_type')
                        extracted_data['paragraph_number'] = item.get('Paragraph Number')
                        extracted_data['when_due'] = item.get('When Due')

                    else:
                        # Unknown log type - store as-is
                        extracted_data['requirement_text'] = str(item)

                    # Create ExtractedData instance
                    extracted_items.append(ExtractedData(**extracted_data))

                # Bulk create for efficiency
                if extracted_items:
                    ExtractedData.objects.bulk_create(extracted_items, batch_size=100)
                    logger.info(f"Migrated {len(extracted_items)} items from AiGeneratedLog {ai_log.id}")

        except Exception as e:
            logger.error(f"Error migrating AiGeneratedLog {ai_log.id}: {e}")
            # Continue with next log rather than failing entire migration
            continue

    # Log summary
    total_count = ExtractedData.objects.count()
    logger.info(f"Migration complete. Total ExtractedData records: {total_count}")

def reverse_migration(apps, schema_editor):
    """Reverse the migration by deleting ExtractedData records"""
    ExtractedData = apps.get_model('deliverables', 'ExtractedData')
    count = ExtractedData.objects.count()
    ExtractedData.objects.all().delete()
    logger.info(f"Deleted {count} ExtractedData records")

class Migration(migrations.Migration):
    dependencies = [
        ('deliverables', '0XXX_add_extracteddata_model'),
    ]

    operations = [
        migrations.RunPython(
            migrate_ai_log_data,
            reverse_migration,
            elidable=False  # This migration modifies data and should not be elided
        ),
    ]
```

**Step 4: Run migration**

Run: `python manage.py migrate deliverables`
Expected: Migration runs successfully

**Step 5: Run test to verify it passes**

Run: `pytest apps/deliverables/tests/test_extracted_data_migration.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add apps/deliverables/migrations/0XXX_migrate_ai_log_data_to_extracted.py
git add apps/deliverables/tests/test_extracted_data_migration.py
git commit -m "feat: add data migration from log_data to ExtractedData with source tracking"
```

---

## Phase 3: Update Code to Use ExtractedData

### Task 5: Update Webhook to Create ExtractedData

**Files:**
- Modify: `apps/deliverables/tests/test_inspection_log_data_tables.py`
- Modify: `apps/deliverables/views/specgpt_views.py:317-437`

**Step 1: Write test for webhook ExtractedData creation**

```python
# Add to apps/deliverables/tests/test_inspection_log_data_tables.py

def test_webhook_creates_extracted_data_with_source(self):
    """Test webhook creates ExtractedData records with source and created_by"""
    url = reverse('ai-log-generation-webhook')

    # Assume the AI log has a created_by field
    self.processing_log.created_by = self.user
    self.processing_log.save()

    webhook_data = {
        'ai_generated_log_id': str(self.processing_log.id),
        'status': 'SUCCESS',
        'log_data': [
            {
                'Spec Section #': '03 3000',
                'Spec Section Name': 'Concrete',
                'Inspection Type And Requirements': 'Visual inspection',
                'Inspection Frequency': 'Daily',
                'Responsible Party': 'QC Inspector'
            },
            {
                'Spec Section #': '04 2000',
                'Spec Section Name': 'Masonry',
                'Inspection Type And Requirements': 'Block inspection',
                'Inspection Frequency': 'Weekly',
                'Responsible Party': 'Inspector'
            }
        ]
    }

    response = self.client.post(
        url,
        data=webhook_data,
        content_type='application/json',
        HTTP_AUTHORIZATION=f'Bearer {settings.LAMBDA_SECRET_KEY}'
    )

    self.assertEqual(response.status_code, 200)

    # Check log_data is still populated (backwards compatibility)
    self.processing_log.refresh_from_db()
    self.assertEqual(len(self.processing_log.log_data), 2)

    # Check ExtractedData records were created
    extracted_items = ExtractedData.objects.filter(
        ai_generated_log=self.processing_log
    )
    self.assertEqual(extracted_items.count(), 2)

    # Verify first item has correct source and created_by
    first_item = extracted_items.first()
    self.assertEqual(first_item.spec_section_number, '03 3000')
    self.assertEqual(first_item.extraction_type, 'inspection_log')
    self.assertEqual(first_item.requirement_text, 'Visual inspection')
    self.assertEqual(first_item.source, 'AI')
    self.assertEqual(first_item.created_by, self.user)
```

**Step 2: Run test to verify it fails**

Run: `pytest apps/deliverables/tests/test_inspection_log_data_tables.py::test_webhook_creates_extracted_data_with_source -v`
Expected: FAIL (ExtractedData not created)

**Step 3: Update webhook to create ExtractedData**

```python
# Modify apps/deliverables/views/specgpt_views.py (ai_log_generation_webhook function, around line 317)

@csrf_exempt
def ai_log_generation_webhook(request):
    """Webhook to update AI log generation status from Lambda"""
    # ... existing authentication code ...

    try:
        data = json.loads(request.body)
        ai_log_id = data.get('ai_generated_log_id')
        status = data.get('status')
        log_data = data.get('log_data', [])

        # ... existing validation ...

        # Update the log
        ai_log = AiGeneratedLog.objects.get(id=ai_log_id)
        ai_log.log_status = status

        if log_data:
            # Still populate log_data for backwards compatibility
            ai_log.log_data = log_data

            # Also create ExtractedData records
            extracted_items = []

            # Get created_by from the AI log if available
            created_by = getattr(ai_log, 'created_by', None)

            for item in log_data:
                extracted_data = {
                    'ai_generated_log': ai_log,
                    'project': ai_log.project,
                    'project_version': ai_log.project_version,
                    'extraction_type': ai_log.log_type,
                    'source': 'AI',  # Mark as AI-generated
                    'created_by': created_by,  # User who triggered the AI generation
                    'spec_section_number': item.get('Spec Section #', ''),
                    'spec_section_name': item.get('Spec Section Name', ''),
                    'responsible_party': item.get('Responsible Party'),
                    'pdf_locations': item.get('pdf_locations'),
                }

                # Handle different log types
                if ai_log.log_type == 'inspection_log':
                    extracted_data.update({
                        'requirement_text': item.get('Inspection Type And Requirements', ''),
                        'inspection_frequency': item.get('Inspection Frequency'),
                        'when_due': item.get('Inspection Frequency'),
                    })

                elif ai_log.log_type == 'owner_deliverables_log':
                    extracted_data.update({
                        'requirement_text': item.get('Exact Requirement Text', ''),
                        'deliverable_type': item.get('Deliverable Type'),
                        'when_due': item.get('When Due'),
                    })

                elif ai_log.log_type == 'qa_planner':
                    extracted_data.update({
                        'requirement_text': item.get('Requirement Text', ''),
                        'item_type': item.get('item_type'),
                        'paragraph_number': item.get('Paragraph Number'),
                        'when_due': item.get('When Due'),
                    })

                extracted_items.append(ExtractedData(**extracted_data))

            # Bulk create ExtractedData records
            if extracted_items:
                with transaction.atomic():
                    # Delete any existing extracted items for this log (in case of retry)
                    ai_log.extracted_items.all().delete()
                    # Create new ones
                    ExtractedData.objects.bulk_create(extracted_items, batch_size=100)

        # Handle other status fields...
        if status == 'PARTIAL_SUCCESS' and ai_log.log_type == 'qa_planner':
            ai_log.completion_status = data.get('completion_status', {})

        ai_log.save()

        return JsonResponse({'status': 'success'})

    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)
```

**Step 4: Run test to verify it passes**

Run: `pytest apps/deliverables/tests/test_inspection_log_data_tables.py::test_webhook_creates_extracted_data_with_source -v`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/views/specgpt_views.py
git add apps/deliverables/tests/test_inspection_log_data_tables.py
git commit -m "feat: update webhook to create ExtractedData with source tracking"
```

---

## Phase 4: CRUD API for ExtractedData

### Task 6: Create ExtractedData Serializer

**Files:**
- Create: `apps/deliverables/tests/test_extracted_data_serializer.py`
- Create: `apps/deliverables/serializers/extracted_data.py`

**Step 1: Write test for serializer**

```python
# apps/deliverables/tests/test_extracted_data_serializer.py
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from apps.deliverables.models import ExtractedData, AiGeneratedLog, Project, ProjectVersion
from apps.deliverables.serializers.extracted_data import (
    ExtractedDataSerializer,
    ExtractedDataListSerializer,
    ExtractedDataCreateSerializer
)
from django.contrib.auth import get_user_model

User = get_user_model()

class TestExtractedDataSerializer(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user('test@example.com')
        self.project = Project.objects.create(name="Test Project")
        self.version = ProjectVersion.objects.create(project=self.project, name="v1")
        self.ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type="inspection_log",
            log_status="SUCCESS"
        )
        self.extracted = ExtractedData.objects.create(
            ai_generated_log=self.ai_log,
            project=self.project,
            project_version=self.version,
            spec_section_number="03 3000",
            spec_section_name="Concrete",
            extraction_type="inspection_log",
            requirement_text="Visual inspection",
            annotation_type="inspection",
            is_annotated=True,
            source="AI",
            created_by=self.user,
            annotated_by=self.user
        )

    def test_serializer_fields(self):
        """Test serializer returns expected fields"""
        serializer = ExtractedDataSerializer(self.extracted)
        data = serializer.data

        expected_fields = {
            'id', 'ai_generated_log', 'spec_section_number',
            'spec_section_name', 'extraction_type', 'item_type',
            'requirement_text', 'responsible_party', 'when_due',
            'annotation_type', 'is_annotated', 'annotation_notes',
            'annotated_by', 'annotated_at', 'source', 'created_by',
            'created_at'
        }

        self.assertEqual(set(data.keys()), expected_fields)
        self.assertEqual(data['spec_section_number'], '03 3000')
        self.assertEqual(data['annotation_type'], 'inspection')
        self.assertEqual(data['source'], 'AI')

    def test_list_serializer_minimal_fields(self):
        """Test list serializer returns minimal fields"""
        serializer = ExtractedDataListSerializer(self.extracted)
        data = serializer.data

        # List view should have fewer fields for performance
        self.assertIn('id', data)
        self.assertIn('spec_section_number', data)
        self.assertIn('requirement_text', data)
        self.assertIn('annotation_type', data)
        self.assertIn('source', data)
        self.assertNotIn('pdf_locations', data)  # Excluded from list view

    def test_create_serializer_human_source(self):
        """Test creating human-sourced extraction"""
        data = {
            'project': self.project.id,
            'project_version': self.version.id,
            'spec_section_number': '05 1000',
            'spec_section_name': 'Metals',
            'extraction_type': 'inspection_log',
            'requirement_text': 'Manual inspection entry',
            'source': 'HUMAN'
        }

        request = self.factory.post('/')
        request.user = self.user

        serializer = ExtractedDataCreateSerializer(
            data=data,
            context={'request': request}
        )

        self.assertTrue(serializer.is_valid())
        instance = serializer.save()

        self.assertEqual(instance.source, 'HUMAN')
        self.assertEqual(instance.created_by, self.user)
        self.assertIsNone(instance.ai_generated_log)
```

**Step 2: Run test to verify it fails**

Run: `pytest apps/deliverables/tests/test_extracted_data_serializer.py -v`
Expected: FAIL with ImportError

**Step 3: Create serializers**

```python
# apps/deliverables/serializers/extracted_data.py
from rest_framework import serializers
from apps.deliverables.models import ExtractedData, AnnotationType, ExtractionSource
from apps.accounts.serializers import UserSerializer
from django.utils import timezone

class ExtractedDataListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views"""
    annotated_by_name = serializers.CharField(
        source='annotated_by.get_full_name',
        read_only=True
    )
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True
    )
    source_display = serializers.CharField(
        source='get_source_display',
        read_only=True
    )

    class Meta:
        model = ExtractedData
        fields = [
            'id', 'spec_section_number', 'spec_section_name',
            'extraction_type', 'item_type', 'requirement_text',
            'annotation_type', 'is_annotated', 'annotated_by_name',
            'source', 'source_display', 'created_by_name', 'created_at'
        ]
        read_only_fields = fields

class ExtractedDataSerializer(serializers.ModelSerializer):
    """Full serializer for detail views and updates"""
    annotated_by = UserSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    annotated_by_id = serializers.PrimaryKeyRelatedField(
        source='annotated_by',
        queryset=User.objects.all(),
        write_only=True,
        required=False,
        allow_null=True
    )
    annotation_type_display = serializers.CharField(
        source='get_annotation_type_display',
        read_only=True
    )
    source_display = serializers.CharField(
        source='get_source_display',
        read_only=True
    )

    class Meta:
        model = ExtractedData
        fields = [
            'id', 'ai_generated_log', 'spec_section_number',
            'spec_section_name', 'extraction_type', 'item_type',
            'requirement_text', 'responsible_party', 'when_due',
            'inspection_frequency', 'deliverable_type',
            'pdf_locations', 'paragraph_number',
            'annotation_type', 'annotation_type_display',
            'is_annotated', 'annotation_notes',
            'annotated_by', 'annotated_by_id', 'annotated_at',
            'source', 'source_display', 'created_by',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'ai_generated_log', 'spec_section_number',
            'spec_section_name', 'extraction_type', 'item_type',
            'requirement_text', 'responsible_party', 'when_due',
            'inspection_frequency', 'deliverable_type',
            'pdf_locations', 'paragraph_number',
            'source', 'created_by', 'created_at', 'updated_at',
            'annotated_at'
        ]

    def validate_annotation_type(self, value):
        """Validate annotation type is valid"""
        if value and value not in AnnotationType.values:
            raise serializers.ValidationError(
                f"Invalid annotation type. Must be one of: {', '.join(AnnotationType.values)}"
            )
        return value

    def update(self, instance, validated_data):
        """Update annotation fields and track metadata"""
        # Auto-set annotation metadata when annotating
        if 'annotation_type' in validated_data and validated_data['annotation_type']:
            validated_data['is_annotated'] = True
            validated_data['annotated_at'] = timezone.now()

            # Set annotated_by from request context if not provided
            if 'annotated_by' not in validated_data:
                request = self.context.get('request')
                if request and request.user.is_authenticated:
                    validated_data['annotated_by'] = request.user

        # Clear annotation if type is removed
        elif 'annotation_type' in validated_data and not validated_data['annotation_type']:
            validated_data['is_annotated'] = False
            validated_data['annotated_at'] = None
            validated_data['annotated_by'] = None

        return super().update(instance, validated_data)

class ExtractedDataCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new ExtractedData (human-sourced)"""

    class Meta:
        model = ExtractedData
        fields = [
            'project', 'project_version', 'spec_section',
            'spec_section_number', 'spec_section_name',
            'extraction_type', 'item_type', 'paragraph_number',
            'requirement_text', 'responsible_party', 'when_due',
            'inspection_frequency', 'deliverable_type',
            'pdf_locations', 'source'
        ]

    def validate_source(self, value):
        """Ensure only HUMAN source for manual creation"""
        if value != ExtractionSource.HUMAN:
            raise serializers.ValidationError(
                "Only HUMAN source is allowed for manual creation. AI sources come from webhooks."
            )
        return value

    def create(self, validated_data):
        """Set created_by from request context"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user

        # Ensure source is HUMAN for manual creation
        validated_data['source'] = ExtractionSource.HUMAN

        return super().create(validated_data)

class BulkAnnotationSerializer(serializers.Serializer):
    """Serializer for bulk annotation operations"""
    ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        max_length=100,
        help_text="List of ExtractedData IDs to annotate"
    )
    annotation_type = serializers.ChoiceField(
        choices=AnnotationType.choices,
        allow_null=True,
        help_text="Annotation type to apply (null to clear)"
    )
    annotation_notes = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional notes for all items"
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest apps/deliverables/tests/test_extracted_data_serializer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/serializers/extracted_data.py
git add apps/deliverables/tests/test_extracted_data_serializer.py
git commit -m "feat: add ExtractedData serializers with source tracking"
```

### Task 7: Create ExtractedData ViewSet

**Files:**
- Create: `apps/deliverables/tests/test_extracted_data_views.py`
- Create: `apps/deliverables/views/extracted_data_views.py`
- Modify: `apps/deliverables/urls.py:43`

**Step 1: Write test for viewset**

```python
# apps/deliverables/tests/test_extracted_data_views.py
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from apps.deliverables.models import ExtractedData, AiGeneratedLog, Project, ProjectVersion
from django.contrib.auth import get_user_model

User = get_user_model()

class TestExtractedDataViewSet(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('test@example.com')
        self.project = Project.objects.create(name="Test Project")
        self.version = ProjectVersion.objects.create(project=self.project, name="v1")
        self.ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type="inspection_log",
            log_status="SUCCESS"
        )

        # Create AI-sourced test data
        for i in range(3):
            ExtractedData.objects.create(
                ai_generated_log=self.ai_log,
                project=self.project,
                project_version=self.version,
                spec_section_number=f"0{i} 1000",
                spec_section_name=f"Section {i}",
                extraction_type="inspection_log",
                requirement_text=f"Requirement {i}",
                source="AI",
                created_by=self.user
            )

        # Create human-sourced test data
        for i in range(2):
            ExtractedData.objects.create(
                project=self.project,
                project_version=self.version,
                spec_section_number=f"1{i} 1000",
                spec_section_name=f"Manual Section {i}",
                extraction_type="inspection_log",
                requirement_text=f"Manual Requirement {i}",
                source="HUMAN",
                created_by=self.user
            )

        self.client.force_authenticate(user=self.user)

    def test_list_extracted_data(self):
        """Test listing extracted data with pagination"""
        url = reverse(
            'deliverables:extracteddata-list',
            kwargs={'project_id': self.project.id}
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 5)

    def test_filter_by_source(self):
        """Test filtering by source (AI vs HUMAN)"""
        url = reverse(
            'deliverables:extracteddata-list',
            kwargs={'project_id': self.project.id}
        )

        # Filter for AI-sourced only
        response = self.client.get(url, {'source': 'AI'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)

        # Filter for HUMAN-sourced only
        response = self.client.get(url, {'source': 'HUMAN'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_create_human_extraction(self):
        """Test creating a human-sourced extraction"""
        url = reverse(
            'deliverables:extracteddata-list',
            kwargs={'project_id': self.project.id}
        )

        data = {
            'project': self.project.id,
            'project_version': self.version.id,
            'spec_section_number': '20 1000',
            'spec_section_name': 'New Manual Entry',
            'extraction_type': 'inspection_log',
            'requirement_text': 'Manual inspection requirement',
            'source': 'HUMAN'
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify the created extraction
        created = ExtractedData.objects.get(id=response.data['id'])
        self.assertEqual(created.source, 'HUMAN')
        self.assertEqual(created.created_by, self.user)
        self.assertIsNone(created.ai_generated_log)

    def test_cannot_create_ai_extraction_via_api(self):
        """Test that AI source cannot be created via API"""
        url = reverse(
            'deliverables:extracteddata-list',
            kwargs={'project_id': self.project.id}
        )

        data = {
            'project': self.project.id,
            'project_version': self.version.id,
            'spec_section_number': '21 1000',
            'spec_section_name': 'Invalid Entry',
            'extraction_type': 'inspection_log',
            'requirement_text': 'Should fail',
            'source': 'AI'  # This should be rejected
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('source', response.data)

    def test_update_annotation(self):
        """Test updating annotation fields"""
        item = ExtractedData.objects.first()
        url = reverse(
            'deliverables:extracteddata-detail',
            kwargs={'project_id': self.project.id, 'pk': item.id}
        )

        data = {
            'annotation_type': 'submittal',
            'annotation_notes': 'Marked as submittal for review'
        }

        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        item.refresh_from_db()
        self.assertEqual(item.annotation_type, 'submittal')
        self.assertTrue(item.is_annotated)
        self.assertEqual(item.annotated_by, self.user)
```

**Step 2: Run test to verify it fails**

Run: `pytest apps/deliverables/tests/test_extracted_data_views.py -v`
Expected: FAIL (viewset doesn't exist)

**Step 3: Create viewset**

```python
# apps/deliverables/views/extracted_data_views.py
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count
from django.utils import timezone

from apps.deliverables.models import ExtractedData, Project, ExtractionSource
from apps.deliverables.serializers.extracted_data import (
    ExtractedDataSerializer,
    ExtractedDataListSerializer,
    ExtractedDataCreateSerializer,
    BulkAnnotationSerializer
)
from apps.deliverables.permissions import ProjectAccessPermissions

class ExtractedDataViewSet(viewsets.ModelViewSet):
    """ViewSet for ExtractedData CRUD operations and annotations"""
    permission_classes = [IsAuthenticated, ProjectAccessPermissions]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    # Filtering
    filterset_fields = [
        'source', 'extraction_type', 'item_type', 'annotation_type',
        'is_annotated', 'spec_section_number', 'ai_generated_log',
        'project_version', 'created_by'
    ]

    # Search
    search_fields = [
        'spec_section_number', 'spec_section_name',
        'requirement_text', 'annotation_notes'
    ]

    # Ordering
    ordering_fields = [
        'spec_section_number', 'created_at', 'updated_at',
        'annotation_type', 'is_annotated', 'source'
    ]
    ordering = ['spec_section_number', 'id']

    def get_queryset(self):
        """Filter by project and optimize queries"""
        project_id = self.kwargs.get('project_id')
        queryset = ExtractedData.objects.filter(project_id=project_id)

        # Optimize based on action
        if self.action == 'list':
            queryset = queryset.select_related(
                'annotated_by', 'created_by', 'ai_generated_log'
            )
        elif self.action in ['retrieve', 'update', 'partial_update']:
            queryset = queryset.select_related(
                'annotated_by', 'created_by', 'ai_generated_log',
                'project', 'project_version', 'spec_section'
            )

        return queryset

    def get_serializer_class(self):
        """Use different serializers for different actions"""
        if self.action == 'list':
            return ExtractedDataListSerializer
        elif self.action == 'create':
            return ExtractedDataCreateSerializer
        elif self.action == 'bulk_annotate':
            return BulkAnnotationSerializer
        return ExtractedDataSerializer

    def perform_create(self, serializer):
        """Ensure created_by is set for human-sourced entries"""
        serializer.save(
            created_by=self.request.user,
            source=ExtractionSource.HUMAN
        )

    @action(detail=False, methods=['post'], url_path='bulk-annotate')
    def bulk_annotate(self, request, project_id=None):
        """Bulk annotate multiple extracted data items"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ids = serializer.validated_data['ids']
        annotation_type = serializer.validated_data.get('annotation_type')
        annotation_notes = serializer.validated_data.get('annotation_notes', '')

        # Get items to update
        items = self.get_queryset().filter(id__in=ids)
        if not items.exists():
            return Response(
                {'error': 'No valid items found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Prepare update data
        update_data = {
            'annotation_type': annotation_type,
            'annotation_notes': annotation_notes,
            'annotated_by': request.user,
            'annotated_at': timezone.now() if annotation_type else None,
            'is_annotated': bool(annotation_type)
        }

        # Bulk update
        updated_count = items.update(**update_data)

        return Response({
            'updated': updated_count,
            'annotation_type': annotation_type,
            'message': f'Successfully updated {updated_count} items'
        })

    @action(detail=False, methods=['get'], url_path='by-spec-section/(?P<spec_number>[^/]+)')
    def by_spec_section(self, request, project_id=None, spec_number=None):
        """Get all extracted data for a specific spec section"""
        # Normalize spec number (handle variations like "03 3000" vs "033000")
        normalized = spec_number.replace(' ', '').replace('-', '')

        queryset = self.get_queryset().filter(
            Q(spec_section_number=spec_number) |
            Q(spec_section_number__icontains=normalized)
        )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def annotation_summary(self, request, project_id=None):
        """Get summary of annotations for the project"""
        queryset = self.get_queryset()

        # Group by source and annotation status
        source_stats = queryset.values('source').annotate(
            total=Count('id'),
            annotated=Count('id', filter=Q(is_annotated=True))
        )

        # Group by annotation type
        type_stats = queryset.values('annotation_type').annotate(
            count=Count('id')
        ).order_by('annotation_type')

        total = queryset.count()
        annotated = queryset.filter(is_annotated=True).count()

        return Response({
            'total_items': total,
            'annotated_items': annotated,
            'unannotated_items': total - annotated,
            'by_source': {
                item['source']: {
                    'total': item['total'],
                    'annotated': item['annotated']
                }
                for item in source_stats
            },
            'by_type': {
                item['annotation_type'] or 'unannotated': item['count']
                for item in type_stats
            }
        })

    @action(detail=False, methods=['get'])
    def created_by_summary(self, request, project_id=None):
        """Get summary of who created extractions"""
        queryset = self.get_queryset()

        creator_stats = queryset.values(
            'created_by__email',
            'source'
        ).annotate(
            count=Count('id')
        ).order_by('created_by__email')

        return Response({
            'by_creator': [
                {
                    'email': item['created_by__email'] or 'System',
                    'source': item['source'],
                    'count': item['count']
                }
                for item in creator_stats
            ]
        })
```

**Step 4: Update URLs**

```python
# Modify apps/deliverables/urls.py (add after line 43, after ai-generated-logs registration)

# Import the new views
from apps.deliverables.views import extracted_data_views

# ExtractedData endpoints
extracted_data_router = routers.NestedDefaultRouter(
    project_router, 'projects', lookup='project'
)
extracted_data_router.register(
    r'extracted-data',
    extracted_data_views.ExtractedDataViewSet,
    basename='extracteddata'
)

# ... at the end of urlpatterns, add:
urlpatterns += extracted_data_router.urls
```

**Step 5: Run test to verify it passes**

Run: `pytest apps/deliverables/tests/test_extracted_data_views.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add apps/deliverables/views/extracted_data_views.py
git add apps/deliverables/tests/test_extracted_data_views.py
git add apps/deliverables/urls.py
git commit -m "feat: add ExtractedData viewset with source filtering and human creation"
```

### Task 8: Add Advanced Filtering and Permissions

**Files:**
- Create: `apps/deliverables/tests/test_extracted_data_permissions.py`
- Modify: `apps/deliverables/permissions.py`
- Create: `apps/deliverables/filters.py`

**Step 1: Write test for permissions**

```python
# apps/deliverables/tests/test_extracted_data_permissions.py
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from apps.deliverables.models import ExtractedData, Project, Team
from django.contrib.auth import get_user_model

User = get_user_model()

class TestExtractedDataPermissions(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create users
        self.owner = User.objects.create_user('owner@example.com')
        self.member = User.objects.create_user('member@example.com')
        self.non_member = User.objects.create_user('other@example.com')

        # Create team and project
        self.team = Team.objects.create(name="Test Team")
        self.team.members.add(self.owner, self.member)
        self.project = Project.objects.create(
            name="Test Project",
            team=self.team,
            created_by=self.owner
        )

        # Create test data with different sources
        self.ai_extracted = ExtractedData.objects.create(
            project=self.project,
            spec_section_number="01 1000",
            extraction_type="inspection_log",
            requirement_text="AI Test",
            source="AI",
            created_by=self.owner
        )

        self.human_extracted = ExtractedData.objects.create(
            project=self.project,
            spec_section_number="02 1000",
            extraction_type="inspection_log",
            requirement_text="Human Test",
            source="HUMAN",
            created_by=self.member
        )

    def test_team_member_can_access(self):
        """Test team members can access extracted data"""
        self.client.force_authenticate(user=self.member)
        url = f'/api/deliverables/projects/{self.project.id}/extracted-data/'

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_non_member_cannot_access(self):
        """Test non-team members cannot access extracted data"""
        self.client.force_authenticate(user=self.non_member)
        url = f'/api/deliverables/projects/{self.project.id}/extracted-data/'

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_only_authenticated_can_annotate(self):
        """Test only authenticated users can update annotations"""
        self.client.force_authenticate(user=self.member)
        url = f'/api/deliverables/projects/{self.project.id}/extracted-data/{self.ai_extracted.id}/'

        response = self.client.patch(url, {'annotation_type': 'submittal'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test unauthenticated
        self.client.force_authenticate(user=None)
        response = self.client.patch(url, {'annotation_type': 'inspection'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_member_can_create_human_extraction(self):
        """Test team members can create human-sourced extractions"""
        self.client.force_authenticate(user=self.member)
        url = f'/api/deliverables/projects/{self.project.id}/extracted-data/'

        data = {
            'project': self.project.id,
            'project_version': self.version.id,
            'spec_section_number': '03 1000',
            'spec_section_name': 'Test',
            'extraction_type': 'inspection_log',
            'requirement_text': 'New manual entry',
            'source': 'HUMAN'
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        created = ExtractedData.objects.get(id=response.data['id'])
        self.assertEqual(created.created_by, self.member)
        self.assertEqual(created.source, 'HUMAN')
```

**Step 2: Run test to verify permissions work**

Run: `pytest apps/deliverables/tests/test_extracted_data_permissions.py -v`
Expected: May pass or fail depending on existing permissions

**Step 3: Create custom filter**

```python
# apps/deliverables/filters.py
import django_filters
from apps.deliverables.models import ExtractedData, AnnotationType, ExtractionSource

class ExtractedDataFilter(django_filters.FilterSet):
    """Advanced filtering for ExtractedData"""

    # Date range filters
    created_after = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='gte'
    )
    created_before = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='lte'
    )

    # Annotation filters
    annotated_by = django_filters.NumberFilter(
        field_name='annotated_by__id'
    )
    annotated_after = django_filters.DateTimeFilter(
        field_name='annotated_at',
        lookup_expr='gte'
    )

    # Text filters
    spec_section_contains = django_filters.CharFilter(
        field_name='spec_section_number',
        lookup_expr='icontains'
    )
    requirement_contains = django_filters.CharFilter(
        field_name='requirement_text',
        lookup_expr='icontains'
    )

    # Multiple choice filters
    annotation_types = django_filters.MultipleChoiceFilter(
        field_name='annotation_type',
        choices=AnnotationType.choices
    )

    # Source filter
    source = django_filters.ChoiceFilter(
        field_name='source',
        choices=ExtractionSource.choices
    )

    # Created by filter
    created_by = django_filters.NumberFilter(
        field_name='created_by__id'
    )

    class Meta:
        model = ExtractedData
        fields = [
            'source', 'extraction_type', 'item_type', 'annotation_type',
            'is_annotated', 'spec_section_number', 'ai_generated_log',
            'project_version', 'annotated_by', 'responsible_party',
            'created_by'
        ]
```

**Step 4: Update viewset to use filter**

```python
# Update apps/deliverables/views/extracted_data_views.py
from apps.deliverables.filters import ExtractedDataFilter

class ExtractedDataViewSet(viewsets.ModelViewSet):
    # ... existing code ...
    filterset_class = ExtractedDataFilter  # Add this line
    # ... rest of the class ...
```

**Step 5: Run tests**

Run: `pytest apps/deliverables/tests/test_extracted_data_permissions.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add apps/deliverables/permissions.py
git add apps/deliverables/filters.py
git add apps/deliverables/tests/test_extracted_data_permissions.py
git commit -m "feat: add permissions and advanced filtering with source tracking"
```

---

## Phase 5: Update SpecView Integration

### Task 9: Update SpecSectionContentSerializer to Use ExtractedData

**Files:**
- Modify: `apps/deliverables/tests/test_spec_centric_views.py`
- Modify: `apps/deliverables/serializers/spec_centric_serializers.py:146-200`

**Step 1: Write test for updated serializer**

```python
# Add to apps/deliverables/tests/test_spec_centric_views.py

def test_spec_section_uses_extracted_data_with_source(self):
    """Test SpecSectionContentSerializer uses ExtractedData with source info"""
    # Create AI-sourced ExtractedData
    ExtractedData.objects.create(
        ai_generated_log=self.ai_log,
        project=self.project,
        project_version=self.version,
        spec_section_number="03 3000",
        spec_section_name="Concrete",
        extraction_type="inspection_log",
        requirement_text="AI Visual inspection",
        pdf_locations=[{'page': 1, 'x': 100, 'y': 200}],
        annotation_type="inspection",
        is_annotated=True,
        source="AI",
        created_by=self.user
    )

    # Create human-sourced ExtractedData
    ExtractedData.objects.create(
        project=self.project,
        project_version=self.version,
        spec_section_number="03 3000",
        spec_section_name="Concrete",
        extraction_type="owner_deliverables_log",
        requirement_text="Manual concrete submittal",
        annotation_type="submittal",
        is_annotated=True,
        source="HUMAN",
        created_by=self.user
    )

    url = reverse(
        'deliverables:spec-section-detail',
        kwargs={
            'project_id': self.project.id,
            'pk': self.spec_section.id
        }
    )

    response = self.client.get(url)
    self.assertEqual(response.status_code, status.HTTP_200_OK)

    # Check that highlights come from ExtractedData
    highlights = response.data.get('ai_log_highlights', [])
    self.assertEqual(len(highlights), 2)

    # Verify source and annotation data is included
    for highlight in highlights:
        self.assertIn('annotation_type', highlight)
        self.assertIn('is_annotated', highlight)
        self.assertIn('source', highlight)
        self.assertIn('created_by', highlight)

        # Check specific items
        if 'AI Visual' in highlight['requirement_text']:
            self.assertEqual(highlight['source'], 'AI')
        elif 'Manual concrete' in highlight['requirement_text']:
            self.assertEqual(highlight['source'], 'HUMAN')
```

**Step 2: Run test to verify it fails**

Run: `pytest apps/deliverables/tests/test_spec_centric_views.py::test_spec_section_uses_extracted_data_with_source -v`
Expected: FAIL (still using log_data)

**Step 3: Update serializer to use ExtractedData**

```python
# Modify apps/deliverables/serializers/spec_centric_serializers.py (get_ai_log_highlights method, around line 146)

def get_ai_log_highlights(self, obj):
    """Get AI log highlights from ExtractedData model"""
    request = self.context.get('request')
    project_id = self.context.get('project_id')
    project_version_id = self.context.get('project_version_id')

    if not project_id:
        return []

    # Get the spec section number
    spec_section_number = obj.spec_section_number
    if not spec_section_number:
        return []

    # Query ExtractedData directly instead of AiGeneratedLog
    extracted_items = ExtractedData.objects.filter(
        project_id=project_id,
        pdf_locations__isnull=False  # Only items with PDF locations
    ).select_related('created_by', 'annotated_by')

    # Filter by project version if provided
    if project_version_id:
        extracted_items = extracted_items.filter(
            project_version_id=project_version_id
        )

    # Filter by spec section using fuzzy matching
    matching_items = []
    for item in extracted_items:
        if self.fuzzy_match_spec_section_number(
            spec_section_number,
            item.spec_section_number
        ):
            matching_items.append(item)

    # Format results
    results = []
    for item in matching_items:
        # Normalize item type for display
        item_type = self._normalize_item_type(
            item.extraction_type,
            item.item_type
        )

        result = {
            'id': item.id,
            'log_type': item.extraction_type,
            'item_type': item_type,
            'spec_section_number': item.spec_section_number,
            'spec_section_name': item.spec_section_name,
            'requirement_text': item.requirement_text,
            'responsible_party': item.responsible_party,
            'when_due': item.when_due,
            'pdf_locations': item.pdf_locations,

            # Include source information
            'source': item.source,
            'source_display': item.get_source_display(),
            'created_by': item.created_by.get_full_name() if item.created_by else None,
            'created_by_id': item.created_by.id if item.created_by else None,

            # Include annotation data
            'annotation_type': item.annotation_type,
            'annotation_type_display': item.get_annotation_type_display() if item.annotation_type else None,
            'is_annotated': item.is_annotated,
            'annotation_notes': item.annotation_notes,
            'annotated_by': item.annotated_by.get_full_name() if item.annotated_by else None,
            'annotated_at': item.annotated_at
        }

        # Add type-specific fields
        if item.extraction_type == 'inspection_log':
            result['inspection_frequency'] = item.inspection_frequency
        elif item.extraction_type == 'owner_deliverables_log':
            result['deliverable_type'] = item.deliverable_type
        elif item.extraction_type == 'qa_planner':
            result['paragraph_number'] = item.paragraph_number

        results.append(result)

    return results

def _normalize_item_type(self, extraction_type, item_type):
    """Normalize item type for consistent display"""
    if extraction_type == 'inspection_log':
        return 'inspections'
    elif extraction_type == 'owner_deliverables_log':
        return 'owner_deliverables'
    elif extraction_type == 'qa_planner' and item_type:
        # Map QA planner item types to display names
        type_map = {
            'inspections': 'inspections',
            'mock_ups_sample_construction': 'mockups',
            'pre_installation_meetings': 'pre_installation',
            'warranties': 'warranties',
            'certificates': 'certificates',
            'closeout_submittals': 'closeout',
            'test_reports': 'test_reports',
            'commissioning': 'commissioning',
            'delegated_design': 'delegated_design'
        }
        return type_map.get(item_type, item_type)
    return item_type or extraction_type
```

**Step 4: Run test to verify it passes**

Run: `pytest apps/deliverables/tests/test_spec_centric_views.py::test_spec_section_uses_extracted_data_with_source -v`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/serializers/spec_centric_serializers.py
git add apps/deliverables/tests/test_spec_centric_views.py
git commit -m "feat: update SpecView to use ExtractedData with source tracking"
```

---

## Phase 6: Integration and Performance Testing

### Task 10: End-to-End Integration Test

**Files:**
- Create: `apps/deliverables/tests/test_extracted_data_e2e.py`

**Step 1: Write comprehensive E2E test**

```python
# apps/deliverables/tests/test_extracted_data_e2e.py
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from apps.deliverables.models import (
    ExtractedData, AiGeneratedLog, Project,
    ProjectVersion, Team, SpecSection
)
import json

User = get_user_model()

class TestExtractedDataE2E(TransactionTestCase):
    """End-to-end test for complete ExtractedData workflow"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('test@example.com')
        self.user2 = User.objects.create_user('test2@example.com')
        self.team = Team.objects.create(name="Test Team")
        self.team.members.add(self.user, self.user2)
        self.project = Project.objects.create(
            name="Test Project",
            team=self.team
        )
        self.version = ProjectVersion.objects.create(
            project=self.project,
            name="v1"
        )
        self.client.force_authenticate(user=self.user)

    def test_complete_workflow(self):
        """Test complete workflow from webhook to annotation with mixed sources"""

        # Step 1: Simulate Lambda webhook creating AI log with ExtractedData
        webhook_url = '/api/deliverables/webhooks/ai-log-generation/'

        # Create processing log first with created_by
        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='inspection_log',
            log_status='PROCESSING',
            created_by=self.user  # Track who triggered AI generation
        )

        webhook_data = {
            'ai_generated_log_id': str(ai_log.id),
            'status': 'SUCCESS',
            'log_data': [
                {
                    'Spec Section #': '03 3000',
                    'Spec Section Name': 'Concrete',
                    'Inspection Type And Requirements': 'Visual inspection of formwork',
                    'Inspection Frequency': 'Daily',
                    'Responsible Party': 'QC Inspector',
                    'pdf_locations': [{'page': 1, 'x': 100, 'y': 200}]
                },
                {
                    'Spec Section #': '04 2000',
                    'Spec Section Name': 'Masonry',
                    'Inspection Type And Requirements': 'Block inspection',
                    'Inspection Frequency': 'Weekly',
                    'Responsible Party': 'Site Engineer'
                }
            ]
        }

        # Use Lambda secret key for webhook
        response = self.client.post(
            webhook_url,
            data=json.dumps(webhook_data),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {settings.LAMBDA_SECRET_KEY}'
        )

        self.assertEqual(response.status_code, 200)

        # Verify ExtractedData was created with AI source
        ai_items = ExtractedData.objects.filter(
            ai_generated_log=ai_log,
            source='AI'
        )
        self.assertEqual(ai_items.count(), 2)

        # Verify created_by is set
        for item in ai_items:
            self.assertEqual(item.created_by, self.user)

        # Step 2: Create human-sourced extraction
        self.client.force_authenticate(user=self.user2)

        create_url = f'/api/deliverables/projects/{self.project.id}/extracted-data/'
        human_data = {
            'project': self.project.id,
            'project_version': self.version.id,
            'spec_section_number': '03 3000',
            'spec_section_name': 'Concrete',
            'extraction_type': 'inspection_log',
            'requirement_text': 'Additional manual inspection requirement',
            'responsible_party': 'Project Manager',
            'source': 'HUMAN'
        }

        response = self.client.post(create_url, human_data)
        self.assertEqual(response.status_code, 201)

        human_item = ExtractedData.objects.get(id=response.data['id'])
        self.assertEqual(human_item.source, 'HUMAN')
        self.assertEqual(human_item.created_by, self.user2)

        # Step 3: List and filter by source
        list_url = f'/api/deliverables/projects/{self.project.id}/extracted-data/'

        # All items
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 3)

        # AI-sourced only
        response = self.client.get(list_url, {'source': 'AI'})
        self.assertEqual(len(response.data['results']), 2)

        # Human-sourced only
        response = self.client.get(list_url, {'source': 'HUMAN'})
        self.assertEqual(len(response.data['results']), 1)

        # Step 4: Annotate items
        item = ai_items.first()
        detail_url = f'/api/deliverables/projects/{self.project.id}/extracted-data/{item.id}/'

        annotation_data = {
            'annotation_type': 'inspection',
            'annotation_notes': 'Critical inspection point'
        }

        response = self.client.patch(detail_url, annotation_data)
        self.assertEqual(response.status_code, 200)

        item.refresh_from_db()
        self.assertEqual(item.annotation_type, 'inspection')
        self.assertTrue(item.is_annotated)
        self.assertEqual(item.annotated_by, self.user2)

        # Step 5: Bulk annotate remaining items
        bulk_url = f'/api/deliverables/projects/{self.project.id}/extracted-data/bulk-annotate/'

        all_ids = list(ExtractedData.objects.filter(
            project=self.project
        ).values_list('id', flat=True))

        bulk_data = {
            'ids': all_ids,
            'annotation_type': 'submittal',
            'annotation_notes': 'Bulk marked as submittal'
        }

        response = self.client.post(bulk_url, bulk_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['updated'], 3)

        # Step 6: Get annotation summary with source breakdown
        summary_url = f'/api/deliverables/projects/{self.project.id}/extracted-data/annotation-summary/'

        response = self.client.get(summary_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_items'], 3)
        self.assertEqual(response.data['annotated_items'], 3)
        self.assertIn('by_source', response.data)
        self.assertEqual(response.data['by_source']['AI']['total'], 2)
        self.assertEqual(response.data['by_source']['HUMAN']['total'], 1)

        # Step 7: Get created_by summary
        creator_url = f'/api/deliverables/projects/{self.project.id}/extracted-data/created_by-summary/'

        response = self.client.get(creator_url)
        self.assertEqual(response.status_code, 200)
        creators = response.data['by_creator']

        # Should have entries for both users
        emails = [c['email'] for c in creators]
        self.assertIn(self.user.email, emails)
        self.assertIn(self.user2.email, emails)

        # Step 8: Access via SpecView
        spec_section = SpecSection.objects.create(
            project=self.project,
            project_version=self.version,
            spec_section_number='03 3000',
            spec_section_name='Concrete'
        )

        spec_url = f'/api/deliverables/projects/{self.project.id}/spec-sections/{spec_section.id}/'

        response = self.client.get(spec_url)
        self.assertEqual(response.status_code, 200)

        # Verify highlights include both AI and human sources
        highlights = response.data.get('ai_log_highlights', [])
        self.assertGreater(len(highlights), 0)

        sources = [h['source'] for h in highlights]
        self.assertIn('AI', sources)
        self.assertIn('HUMAN', sources)

        for highlight in highlights:
            self.assertEqual(highlight['annotation_type'], 'submittal')
            self.assertTrue(highlight['is_annotated'])
            self.assertIsNotNone(highlight['created_by'])
```

**Step 2: Run E2E test**

Run: `pytest apps/deliverables/tests/test_extracted_data_e2e.py -v -s`
Expected: PASS

**Step 3: Commit**

```bash
git add apps/deliverables/tests/test_extracted_data_e2e.py
git commit -m "test: add end-to-end test for ExtractedData with source tracking"
```

### Task 11: Performance Optimization Test

**Files:**
- Create: `apps/deliverables/tests/test_extracted_data_performance.py`

**Step 1: Write performance test**

```python
# apps/deliverables/tests/test_extracted_data_performance.py
from django.test import TestCase
from django.test.utils import override_settings
from django.db import connection
from django.test import TransactionTestCase
import time

class TestExtractedDataPerformance(TransactionTestCase):
    """Test performance of ExtractedData queries"""

    def setUp(self):
        # Create large dataset
        self.project = Project.objects.create(name="Test")
        self.version = ProjectVersion.objects.create(
            project=self.project, name="v1"
        )
        self.user = User.objects.create_user('test@example.com')

        # Create 10 AI logs with 100 items each = 1000 ExtractedData records
        for log_num in range(10):
            ai_log = AiGeneratedLog.objects.create(
                project=self.project,
                project_version=self.version,
                log_type='inspection_log',
                log_status='SUCCESS',
                created_by=self.user
            )

            items = []
            for item_num in range(100):
                # Mix AI and HUMAN sources
                source = 'AI' if item_num < 80 else 'HUMAN'
                items.append(ExtractedData(
                    ai_generated_log=ai_log if source == 'AI' else None,
                    project=self.project,
                    project_version=self.version,
                    spec_section_number=f"{log_num:02d} {item_num:04d}",
                    spec_section_name=f"Section {log_num}-{item_num}",
                    extraction_type='inspection_log',
                    requirement_text=f"Requirement {item_num}",
                    source=source,
                    created_by=self.user
                ))

            ExtractedData.objects.bulk_create(items)

    @override_settings(DEBUG=True)
    def test_query_performance(self):
        """Test that queries use indexes efficiently"""
        from django.db import reset_queries

        reset_queries()

        # Test indexed queries
        start_time = time.time()

        # Query by spec section (indexed)
        results = ExtractedData.objects.filter(
            spec_section_number='05 0050'
        ).select_related('annotated_by', 'created_by')
        list(results)  # Force evaluation

        # Query by source (indexed)
        results = ExtractedData.objects.filter(
            source='AI'
        )
        self.assertEqual(results.count(), 800)  # 80% are AI

        results = ExtractedData.objects.filter(
            source='HUMAN'
        )
        self.assertEqual(results.count(), 200)  # 20% are HUMAN

        # Query by created_by (indexed)
        results = ExtractedData.objects.filter(
            created_by=self.user
        )[:100]
        list(results)

        # Query by annotation type (indexed)
        results = ExtractedData.objects.filter(
            annotation_type='submittal'
        )
        list(results)

        # Query by project and version (indexed)
        results = ExtractedData.objects.filter(
            project=self.project,
            project_version=self.version
        )[:100]  # Limit for pagination
        list(results)

        elapsed = time.time() - start_time

        # Check performance
        self.assertLess(elapsed, 1.0, "Queries took too long")

        # Check query count
        self.assertLess(len(connection.queries), 15, "Too many queries")

        # Verify indexes are used (check EXPLAIN on one query)
        with connection.cursor() as cursor:
            cursor.execute(
                "EXPLAIN SELECT * FROM deliverables_extracted_data "
                "WHERE source = %s",
                ['AI']
            )
            explain = cursor.fetchall()
            # Check that an index is mentioned in the explain plan
            explain_text = str(explain)
            self.assertIn('index', explain_text.lower())
```

**Step 2: Run performance test**

Run: `pytest apps/deliverables/tests/test_extracted_data_performance.py -v`
Expected: PASS

**Step 3: Final commit**

```bash
git add apps/deliverables/tests/test_extracted_data_performance.py
git commit -m "test: add performance tests for ExtractedData with source indexing"

# Create comprehensive commit for the feature
git add .
git commit -m "feat: complete SpecView enhancement with ExtractedData model

- Created ExtractedData model with source (AI/HUMAN) and created_by tracking
- Added Django migration to convert existing data automatically
- Updated webhook to create ExtractedData records with source tracking
- Built full CRUD API with annotation capabilities and human entry support
- Added filtering by source and created_by user
- Integrated with SpecView for highlighting with source information
- Added comprehensive test coverage including E2E and performance tests
- Optimized with database indexes on source and created_by fields"
```

---

## Summary

This plan provides a complete backend implementation for the SpecView enhancement feature with:

1. **ExtractedData Model**: Normalized storage with source tracking (AI vs HUMAN) and created_by field
2. **Data Migration**: Automatic conversion via Django migration file (not management command)
3. **Dual Support**: Maintains backwards compatibility with log_data
4. **CRUD API**: Full REST API with filtering by source, search, and bulk operations
5. **Human Entry Support**: Users can manually create ExtractedData entries marked as HUMAN source
6. **Annotation System**: User tracking for both creation and annotation with timestamps
7. **SpecView Integration**: Seamless replacement using ExtractedData with source information
8. **No Feature Flag**: Direct implementation for simpler deployment
9. **Comprehensive Testing**: Model, API, permissions, E2E, and performance tests
10. **Source Tracking**: Clear distinction between AI-generated and human-created data

**Total Tasks**: 11 bite-sized tasks with TDD approach
**Deployment**: Migration runs automatically on deploy
**Backwards Compatible**: Maintains log_data during transition
**Audit Trail**: Full tracking of who created and annotated each item