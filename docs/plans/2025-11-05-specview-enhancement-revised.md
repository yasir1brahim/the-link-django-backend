# SpecView Enhancement Implementation Plan (REVISED)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert AiGeneratedLog JSON data to ExtractedData model instances and build CRUD endpoints for user-created extractions via Apryse highlights

**Architecture:** Create ExtractedData model to normalize JSON rows, run data migration via Django migration file for automatic deployment, update all views/serializers to use the new model while maintaining backwards compatibility, then add extraction CRUD endpoints for Apryse highlight workflow

**Tech Stack:** Django 4.2, Django REST Framework, PostgreSQL, pytest, openpyxl (for Excel export)

**Key Concept:** Users create highlights in Apryse webviewer and select a type (submittal, inspection, owner deliverable, etc.). This creates an ExtractedData entry with source=HUMAN. There is NO separate "annotation" layer - the highlighting IS the extraction.

---

## Phase 1: Create ExtractedData Model and Tests ✅ COMPLETED

### Task 1: Create ExtractedData Model with Tests ✅ COMPLETED

**Status:** ✅ Completed - Migration 0065 created, tests passing

**What was built:**
- Added `created_by` field to `AiGeneratedLog`
- Created `ExtractionSource` enum (AI vs HUMAN)
- Created `ExtractionItemType` enum for categorization
- Created `ExtractedData` model with source tracking
- NO annotation fields (is_annotated, annotation_notes, annotated_by, etc.)
- Tests confirm AI and HUMAN source entries work correctly

---

## Phase 2: Model Relationships and Admin

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

    # Human-created via highlight
    human_extracted = ExtractedData.objects.create(
        project=self.project,
        project_version=self.version,
        spec_section_number="02 1000",
        spec_section_name="Existing",
        extraction_type="submittal",
        item_type="submittal",
        requirement_text="Human created via Apryse highlight",
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

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extracted_data_model::TestExtractedDataModel::test_created_by_relationship --verbosity=2`
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
            'extraction_type', 'source', 'created_by', 'created_at'
        ]
        self.assertEqual(list(admin.list_display), expected)

    def test_admin_list_filter(self):
        """Test admin filter options"""
        admin = ExtractedDataAdmin(ExtractedData, site)
        expected = [
            'source', 'extraction_type', 'item_type', 'project'
        ]
        self.assertEqual(list(admin.list_filter), expected)
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extracted_data_admin --verbosity=2`
Expected: FAIL with "ImportError: cannot import name 'ExtractedDataAdmin'"

**Step 3: Add ExtractedData admin**

```python
# apps/deliverables/admin.py (add after AiGeneratedLogAdmin, around line 407)

@admin.register(ExtractedData)
class ExtractedDataAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'spec_section_number', 'spec_section_name',
        'extraction_type', 'source', 'created_by', 'created_at'
    ]
    list_filter = [
        'source', 'extraction_type', 'item_type', 'project'
    ]
    search_fields = [
        'spec_section_number', 'spec_section_name',
        'requirement_text'
    ]
    readonly_fields = ['created_at', 'updated_at']

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
                'requirement_text', 'responsible_party', 'metadata'
            )
        }),
        ('PDF Data', {
            'fields': ('pdf_locations',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'ai_generated_log', 'project', 'project_version',
            'spec_section', 'created_by'
        )
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extracted_data_admin --verbosity=2`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/admin.py
git add apps/deliverables/tests/test_extracted_data_admin.py
git commit -m "feat: add ExtractedData admin interface with source tracking"
```

---

## Phase 3: Data Migration

### Task 4: Create Data Migration for ExtractedData

**Files:**
- Create: `apps/deliverables/migrations/0066_migrate_ai_log_data_to_extracted.py`

**Step 1: Create data migration**

Run: `docker-compose exec web python manage.py makemigrations --empty deliverables --name migrate_ai_log_data_to_extracted`

**Step 2: Write migration code**

```python
# apps/deliverables/migrations/0066_migrate_ai_log_data_to_extracted.py
from django.db import migrations, transaction
import logging

logger = logging.getLogger(__name__)

def migrate_ai_log_data(apps, schema_editor):
    """Migrate data from AiGeneratedLog.log_data to ExtractedData model"""
    AiGeneratedLog = apps.get_model('deliverables', 'AiGeneratedLog')
    ExtractedData = apps.get_model('deliverables', 'ExtractedData')

    text_field_map = {
        'inspection_log': 'Inspection Type And Requirements',
        'owner_deliverables_log': 'Exact Requirement Text',
        'qa_planner': 'Requirement Text',
    }

    # Process each AI log
    for ai_log in AiGeneratedLog.objects.filter(log_status='SUCCESS').iterator(chunk_size=100):
        if not ai_log.log_data:
            continue

        extracted_items = []

        try:
            with transaction.atomic():
                for item in ai_log.log_data:
                    text_field = text_field_map.get(ai_log.log_type)

                    extracted_data = {
                        'ai_generated_log': ai_log,
                        'project': ai_log.project,
                        'project_version': ai_log.project_version,
                        'extraction_type': ai_log.log_type,
                        'source': 'AI',
                        'metadata': {},
                    }

                    if hasattr(ai_log, 'created_by'):
                        extracted_data['created_by'] = ai_log.created_by

                    extracted_data['spec_section_number'] = item.get('Spec Section #', '')
                    extracted_data['spec_section_name'] = item.get('Spec Section Name', '')
                    extracted_data['responsible_party'] = item.get('Responsible Party')
                    extracted_data['pdf_locations'] = item.get('pdf_locations')

                    if text_field:
                        extracted_data['requirement_text'] = item.get(text_field, '')
                        extracted_data['metadata']['original_text_key'] = text_field
                    else:
                        extracted_data['requirement_text'] = str(item)
                        extracted_data['metadata']['original_text_key'] = None

                    if ai_log.log_type == 'inspection_log':
                        extracted_data['metadata'].update({
                            'inspection_frequency': item.get('Inspection Frequency'),
                            'when_due': item.get('Inspection Frequency'),
                        })

                    elif ai_log.log_type == 'owner_deliverables_log':
                        extracted_data['metadata'].update({
                            'deliverable_type': item.get('Deliverable Type'),
                            'when_due': item.get('When Due'),
                        })

                    elif ai_log.log_type == 'qa_planner':
                        extracted_data['item_type'] = item.get('item_type')
                        extracted_data['paragraph_number'] = item.get('Paragraph Number')
                        extracted_data['metadata'].update({
                            'when_due': item.get('When Due'),
                        })

                    extracted_data['metadata']['raw_item'] = item

                    extracted_items.append(ExtractedData(**extracted_data))

                # Bulk create for efficiency
                if extracted_items:
                    ExtractedData.objects.bulk_create(extracted_items, batch_size=100)
                    logger.info(f"Migrated {len(extracted_items)} items from AiGeneratedLog {ai_log.id}")

        except Exception as e:
            logger.error(f"Error migrating AiGeneratedLog {ai_log.id}: {e}")
            continue

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
        ('deliverables', '0065_aigeneratedlog_created_by_extracteddata'),
    ]

    operations = [
        migrations.RunPython(
            migrate_ai_log_data,
            reverse_migration,
            elidable=False
        ),
    ]
```

**Step 3: Run migration**

Run: `docker-compose exec web python manage.py migrate deliverables`
Expected: Migration runs successfully, logs show records migrated

**Step 4: Verify migration**

Run: `docker-compose exec web python manage.py shell -c "from apps.deliverables.models import ExtractedData; print(f'Total ExtractedData: {ExtractedData.objects.count()}')"`

**Step 5: Commit**

```bash
git add apps/deliverables/migrations/0066_migrate_ai_log_data_to_extracted.py
git commit -m "feat: add data migration from log_data to ExtractedData with source tracking"
```

---

## Phase 4: Update Webhook

### Task 5: Update Webhook to Create ExtractedData

**Files:**
- Modify: `apps/deliverables/views/specgpt_views.py:317-437`

**Step 1: Locate webhook function**

The webhook is at `ai_log_generation_webhook()` around line 317.

**Step 2: Update webhook to create ExtractedData**

Add after the `ai_log.log_data = log_data` line:

```python
# Also create ExtractedData records
if log_data:
    extracted_items = []
    created_by = getattr(ai_log, 'created_by', None)
    text_field_map = {
        'inspection_log': 'Inspection Type And Requirements',
        'owner_deliverables_log': 'Exact Requirement Text',
        'qa_planner': 'Requirement Text',
    }
    text_field = text_field_map.get(ai_log.log_type)

    for item in log_data:
        extracted_data = {
            'ai_generated_log': ai_log,
            'project': ai_log.project,
            'project_version': ai_log.project_version,
            'extraction_type': ai_log.log_type,
            'source': 'AI',
            'created_by': created_by,
            'spec_section_number': item.get('Spec Section #', ''),
            'spec_section_name': item.get('Spec Section Name', ''),
            'responsible_party': item.get('Responsible Party'),
            'pdf_locations': item.get('pdf_locations'),
            'metadata': {
                'original_text_key': text_field,
                'raw_item': item,
            },
        }

        if text_field:
            extracted_data['requirement_text'] = item.get(text_field, '')
        else:
            extracted_data['requirement_text'] = str(item)

        # Handle different log types
        if ai_log.log_type == 'inspection_log':
            extracted_data['metadata'].update({
                'inspection_frequency': item.get('Inspection Frequency'),
                'when_due': item.get('Inspection Frequency'),
            })
        elif ai_log.log_type == 'owner_deliverables_log':
            extracted_data['metadata'].update({
                'deliverable_type': item.get('Deliverable Type'),
                'when_due': item.get('When Due'),
            })
        elif ai_log.log_type == 'qa_planner':
            extracted_data['item_type'] = item.get('item_type')
            extracted_data['paragraph_number'] = item.get('Paragraph Number')
            extracted_data['metadata'].update({
                'when_due': item.get('When Due'),
            })

        extracted_items.append(ExtractedData(**extracted_data))

    # Bulk create ExtractedData records
    if extracted_items:
        with transaction.atomic():
            ai_log.extracted_items.all().delete()
            ExtractedData.objects.bulk_create(extracted_items, batch_size=100)
```

**Step 3: Add import at top of file**

```python
from apps.deliverables.models import ExtractedData
from django.db import transaction
```

**Step 4: Test manually (if possible) or write integration test**

**Step 5: Commit**

```bash
git add apps/deliverables/views/specgpt_views.py
git commit -m "feat: update webhook to create ExtractedData with source tracking"
```

---

## Phase 5: CRUD API for ExtractedData

### Task 6: Create ExtractedData Serializers

**Files:**
- Create: `apps/deliverables/serializers/extracted_data.py`

**Step 1: Create serializers**

```python
# apps/deliverables/serializers/extracted_data.py
from rest_framework import serializers
from apps.deliverables.models import ExtractedData, ExtractionItemType, ExtractionSource
from apps.accounts.serializers import UserSerializer
from django.contrib.auth import get_user_model

User = get_user_model()

class ExtractedDataListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views"""
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True,
        allow_null=True
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
            'responsible_party', 'metadata',
            'source', 'source_display', 'created_by_name', 'created_at'
        ]
        read_only_fields = fields


class ExtractedDataSerializer(serializers.ModelSerializer):
    """Full serializer for detail views and updates"""
    created_by = UserSerializer(read_only=True)
    source_display = serializers.CharField(
        source='get_source_display',
        read_only=True
    )

    class Meta:
        model = ExtractedData
        fields = [
            'id', 'ai_generated_log', 'spec_section_number',
            'spec_section_name', 'extraction_type', 'item_type',
            'requirement_text', 'responsible_party', 'metadata',
            'pdf_locations', 'paragraph_number',
            'source', 'source_display', 'created_by',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'ai_generated_log', 'spec_section_number',
            'spec_section_name', 'extraction_type', 'item_type',
            'requirement_text', 'responsible_party', 'metadata',
            'pdf_locations', 'paragraph_number',
            'source', 'created_by', 'created_at', 'updated_at'
        ]


class ExtractedDataCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new ExtractedData (human-sourced via Apryse highlights)"""

    class Meta:
        model = ExtractedData
        fields = [
            'project', 'project_version', 'spec_section',
            'spec_section_number', 'spec_section_name',
            'extraction_type', 'item_type', 'paragraph_number',
            'requirement_text', 'responsible_party', 'metadata',
            'pdf_locations'
        ]

    def create(self, validated_data):
        """Set created_by and source from request context"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user

        # Always HUMAN source for manual creation
        validated_data['source'] = ExtractionSource.HUMAN

        return super().create(validated_data)
```

**Step 2: Commit**

```bash
git add apps/deliverables/serializers/extracted_data.py
git commit -m "feat: add ExtractedData serializers for CRUD operations"
```

### Task 7: Create ExtractedData ViewSet

**Files:**
- Create: `apps/deliverables/views/extracted_data_views.py`
- Modify: `apps/deliverables/urls.py`

**Step 1: Create viewset**

```python
# apps/deliverables/views/extracted_data_views.py
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count

from apps.deliverables.models import ExtractedData, Project, ExtractionSource
from apps.deliverables.serializers.extracted_data import (
    ExtractedDataSerializer,
    ExtractedDataListSerializer,
    ExtractedDataCreateSerializer
)
from apps.deliverables.permissions import ProjectAccessPermissions


class ExtractedDataViewSet(viewsets.ModelViewSet):
    """ViewSet for ExtractedData CRUD operations"""
    permission_classes = [IsAuthenticated, ProjectAccessPermissions]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    # Filtering
    filterset_fields = [
        'source', 'extraction_type', 'item_type',
        'spec_section_number', 'ai_generated_log',
        'project_version', 'created_by'
    ]

    # Search
    search_fields = [
        'spec_section_number', 'spec_section_name',
        'requirement_text'
    ]

    # Ordering
    ordering_fields = [
        'spec_section_number', 'created_at', 'updated_at',
        'extraction_type', 'source'
    ]
    ordering = ['spec_section_number', 'id']

    def get_queryset(self):
        """Filter by project and optimize queries"""
        project_id = self.kwargs.get('project_pk')
        queryset = ExtractedData.objects.filter(project_id=project_id)

        # Optimize based on action
        if self.action == 'list':
            queryset = queryset.select_related('created_by', 'ai_generated_log')
        elif self.action in ['retrieve', 'update', 'partial_update']:
            queryset = queryset.select_related(
                'created_by', 'ai_generated_log',
                'project', 'project_version', 'spec_section'
            )

        return queryset

    def get_serializer_class(self):
        """Use different serializers for different actions"""
        if self.action == 'list':
            return ExtractedDataListSerializer
        elif self.action == 'create':
            return ExtractedDataCreateSerializer
        return ExtractedDataSerializer

    def perform_create(self, serializer):
        """Ensure created_by is set for human-sourced entries"""
        serializer.save(
            created_by=self.request.user,
            source=ExtractionSource.HUMAN
        )

    def perform_destroy(self, instance):
        """Only allow deletion of HUMAN-sourced extractions"""
        if instance.source == ExtractionSource.AI:
            raise serializers.ValidationError(
                "Cannot delete AI-generated extractions. Delete the source AI log instead."
            )
        instance.delete()

    @action(detail=False, methods=['get'])
    def summary(self, request, project_pk=None):
        """Get summary of extractions for the project"""
        queryset = self.get_queryset()

        # Group by source
        source_stats = queryset.values('source').annotate(
            total=Count('id')
        )

        # Group by extraction type
        type_stats = queryset.values('extraction_type', 'item_type').annotate(
            count=Count('id')
        ).order_by('extraction_type', 'item_type')

        total = queryset.count()

        return Response({
            'total_items': total,
            'by_source': {
                item['source']: item['total']
                for item in source_stats
            },
            'by_type': [
                {
                    'extraction_type': item['extraction_type'],
                    'item_type': item['item_type'],
                    'count': item['count']
                }
                for item in type_stats
            ]
        })

    @action(detail=False, methods=['get'])
    def by_spec_section(self, request, project_pk=None):
        """Get extractions grouped by spec section"""
        queryset = self.get_queryset()
        spec_number = request.query_params.get('spec_section_number')

        if spec_number:
            queryset = queryset.filter(spec_section_number=spec_number)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
```

**Step 2: Update URLs**

```python
# Modify apps/deliverables/urls.py
from apps.deliverables.views import extracted_data_views

# Add after ai-generated-logs router
extracted_data_router = routers.NestedDefaultRouter(
    project_router, 'projects', lookup='project'
)
extracted_data_router.register(
    r'extracted-data',
    extracted_data_views.ExtractedDataViewSet,
    basename='extracteddata'
)

# At the end of urlpatterns, add:
urlpatterns += extracted_data_router.urls
```

**Step 3: Commit**

```bash
git add apps/deliverables/views/extracted_data_views.py
git add apps/deliverables/urls.py
git commit -m "feat: add ExtractedData viewset with CRUD operations"
```

### Task 8: Add Advanced Filtering

**Files:**
- Create: `apps/deliverables/filters.py`
- Modify: `apps/deliverables/views/extracted_data_views.py`

**Step 1: Create filter class**

```python
# apps/deliverables/filters.py
import django_filters
from apps.deliverables.models import ExtractedData, ExtractionItemType, ExtractionSource


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

    # Text filters
    spec_section_contains = django_filters.CharFilter(
        field_name='spec_section_number',
        lookup_expr='icontains'
    )
    requirement_contains = django_filters.CharFilter(
        field_name='requirement_text',
        lookup_expr='icontains'
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
            'source', 'extraction_type', 'item_type',
            'spec_section_number', 'ai_generated_log',
            'project_version', 'created_by', 'responsible_party'
        ]
```

**Step 2: Update viewset to use filter**

```python
# Update apps/deliverables/views/extracted_data_views.py
from apps.deliverables.filters import ExtractedDataFilter

class ExtractedDataViewSet(viewsets.ModelViewSet):
    # ... existing code ...
    filterset_class = ExtractedDataFilter
    # ... rest of the class ...
```

**Step 3: Commit**

```bash
git add apps/deliverables/filters.py
git add apps/deliverables/views/extracted_data_views.py
git commit -m "feat: add advanced filtering for ExtractedData"
```

---

## Phase 6: Update SpecView Integration

### Task 9: Update SpecSectionContentSerializer to Use ExtractedData

**Files:**
- Modify: `apps/deliverables/serializers/spec_centric_serializers.py:146-200`

**Step 1: Update get_ai_log_highlights method**

Replace the existing `get_ai_log_highlights` method with:

```python
def get_ai_log_highlights(self, obj):
    """Get highlights from ExtractedData model (both AI and human-created)"""
    request = self.context.get('request')
    project_id = self.context.get('project_id')
    project_version_id = self.context.get('project_version_id')

    if not project_id:
        return []

    spec_section_number = obj.spec_section_number
    if not spec_section_number:
        return []

    # Query ExtractedData directly instead of AiGeneratedLog
    extracted_items = ExtractedData.objects.filter(
        project_id=project_id,
        pdf_locations__isnull=False  # Only items with PDF locations
    ).select_related('created_by')

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
        metadata = item.metadata or {}
        result = {
            'id': item.id,
            'extraction_type': item.extraction_type,
            'item_type': item.item_type,
            'spec_section_number': item.spec_section_number,
            'spec_section_name': item.spec_section_name,
            'requirement_text': item.requirement_text,
            'responsible_party': item.responsible_party,
            'metadata': metadata,
            'pdf_locations': item.pdf_locations,

            # Include source information
            'source': item.source,
            'source_display': item.get_source_display(),
            'created_by': item.created_by.get_full_name() if item.created_by else None,
            'created_by_id': item.created_by.id if item.created_by else None,
            'created_at': item.created_at
        }

        # Add type-specific convenience fields for backwards compatibility
        if item.extraction_type == 'inspection_log':
            result['inspection_frequency'] = metadata.get('inspection_frequency')
        elif item.extraction_type == 'owner_deliverables_log':
            result['deliverable_type'] = metadata.get('deliverable_type')
        elif item.extraction_type == 'qa_planner':
            result['paragraph_number'] = item.paragraph_number

        # Expose shared metadata convenience fields
        result['when_due'] = metadata.get('when_due')

        results.append(result)

    return results
```