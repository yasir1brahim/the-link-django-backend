# AiGeneratedLogSerializer Update Plan

> **Context:** This plan updates the existing plan in `docs/plans/2025-11-05-specview-enhancement-revised.md` to focus on verifying and optimizing the AiGeneratedLogViewSet to use ExtractedData while maintaining backward compatibility.

**Goal:** Ensure AiGeneratedLogViewSet returns data sourced from ExtractedData model objects while maintaining the exact same response shape for frontend compatibility.

**Current State Analysis:**

The serializer already has support for ExtractedData:
- `build_structured_rows()` (line 48-58) checks for `extracted_items` and uses them when available
- `_format_extracted_item()` (line 60-94) converts ExtractedData back to legacy row format
- `to_representation()` (line 124-212) uses `build_structured_rows()` to populate `log_data`
- ViewSet (line 632) already does `.prefetch_related('extracted_items')`

**What Needs To Be Done:**
1. Verify the existing implementation works correctly
2. Add comprehensive tests to ensure backward compatibility
3. Optimize queryset to always prefer ExtractedData when available
4. Document the fallback behavior (ExtractedData → log_data JSON)

---

## Phase: Verify and Test AiGeneratedLog → ExtractedData Integration

### Task 1: Add Tests for ExtractedData Serialization

**Files:**
- Create: `apps/deliverables/tests/test_ai_generated_log_serializer_extracted_data.py`

**Step 1: Write test for serializer with ExtractedData**

```python
# apps/deliverables/tests/test_ai_generated_log_serializer_extracted_data.py
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from apps.deliverables.models import (
    Project, ProjectVersion, AiGeneratedLog, ExtractedData,
    ExtractionSource, Team
)
from apps.deliverables.serializers.specgpt import AiGeneratedLogSerializer

User = get_user_model()


class TestAiGeneratedLogSerializerWithExtractedData(TestCase):
    """Test that AiGeneratedLogSerializer properly uses ExtractedData when available"""

    def setUp(self):
        self.user = User.objects.create_user('test@example.com')
        self.team = Team.objects.create(name='Test Team')
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team
        )
        self.version = ProjectVersion.objects.create(
            project=self.project,
            version_number='1.0'
        )

    def test_serializer_uses_extracted_data_when_available(self):
        """Test that serializer uses ExtractedData instead of log_data when available"""
        # Create AI log with log_data
        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='inspection_log',
            log_status='SUCCESS',
            created_by=self.user,
            log_data=[
                {
                    'Spec Section #': '01 1000',
                    'Spec Section Name': 'General',
                    'Inspection Type And Requirements': 'Old data from JSON',
                    'Inspection Frequency': 'Daily',
                    'Responsible Party': 'Contractor',
                }
            ]
        )

        # Create ExtractedData that should override log_data
        ExtractedData.objects.create(
            ai_generated_log=ai_log,
            project=self.project,
            project_version=self.version,
            spec_section_number='01 1000',
            spec_section_name='General',
            extraction_type='inspection_log',
            requirement_text='New data from ExtractedData model',
            responsible_party='Contractor',
            source=ExtractionSource.AI,
            created_by=self.user,
            metadata={
                'inspection_frequency': 'Daily',
                'raw_item': {
                    'Inspection Frequency': 'Daily',
                }
            }
        )

        # Serialize with ExtractedData prefetched
        ai_log_with_prefetch = AiGeneratedLog.objects.prefetch_related(
            'extracted_items'
        ).get(id=ai_log.id)

        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user
        request.team = self.team

        serializer = AiGeneratedLogSerializer(
            ai_log_with_prefetch,
            context={'request': request}
        )
        data = serializer.data

        # Verify that data comes from ExtractedData, not log_data
        self.assertEqual(len(data['log_data']), 1)
        row = data['log_data'][0]
        self.assertEqual(
            row['Inspection Type And Requirements'],
            'New data from ExtractedData model'
        )
        self.assertEqual(row['Spec Section #'], '01 1000')
        self.assertEqual(row['Inspection Frequency'], 'Daily')

    def test_serializer_falls_back_to_log_data_when_no_extracted_data(self):
        """Test that serializer falls back to log_data when ExtractedData is not available"""
        # Create AI log with only log_data (no ExtractedData)
        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='inspection_log',
            log_status='SUCCESS',
            created_by=self.user,
            log_data=[
                {
                    'Spec Section #': '01 1000',
                    'Spec Section Name': 'General',
                    'Inspection Type And Requirements': 'From JSON fallback',
                    'Inspection Frequency': 'Weekly',
                }
            ]
        )

        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user
        request.team = self.team

        serializer = AiGeneratedLogSerializer(
            ai_log,
            context={'request': request}
        )
        data = serializer.data

        # Verify data comes from log_data JSON field
        self.assertEqual(len(data['log_data']), 1)
        row = data['log_data'][0]
        self.assertEqual(
            row['Inspection Type And Requirements'],
            'From JSON fallback'
        )

    def test_extracted_data_format_matches_legacy_format(self):
        """Test that ExtractedData is formatted exactly like legacy log_data"""
        legacy_row = {
            'Spec Section #': '01 1000',
            'Spec Section Name': 'General Requirements',
            'Inspection Type And Requirements': 'Verify installation',
            'Inspection Frequency': 'Daily',
            'Responsible Party': 'Contractor',
            'pdf_locations': [{'page': 5, 'bbox': [100, 200, 300, 250]}]
        }

        # Create AI log with legacy format
        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='inspection_log',
            log_status='SUCCESS',
            created_by=self.user,
            log_data=[legacy_row]
        )

        # Create matching ExtractedData
        ExtractedData.objects.create(
            ai_generated_log=ai_log,
            project=self.project,
            project_version=self.version,
            spec_section_number='01 1000',
            spec_section_name='General Requirements',
            extraction_type='inspection_log',
            requirement_text='Verify installation',
            responsible_party='Contractor',
            pdf_locations=[{'page': 5, 'bbox': [100, 200, 300, 250]}],
            source=ExtractionSource.AI,
            created_by=self.user,
            metadata={
                'inspection_frequency': 'Daily',
                'raw_item': legacy_row
            }
        )

        # Get with prefetch
        ai_log_with_prefetch = AiGeneratedLog.objects.prefetch_related(
            'extracted_items'
        ).get(id=ai_log.id)

        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user
        request.team = self.team

        serializer = AiGeneratedLogSerializer(
            ai_log_with_prefetch,
            context={'request': request}
        )
        data = serializer.data

        # Verify format matches exactly
        row = data['log_data'][0]
        self.assertEqual(row['Spec Section #'], legacy_row['Spec Section #'])
        self.assertEqual(row['Spec Section Name'], legacy_row['Spec Section Name'])
        self.assertEqual(
            row['Inspection Type And Requirements'],
            legacy_row['Inspection Type And Requirements']
        )
        self.assertEqual(row['Inspection Frequency'], legacy_row['Inspection Frequency'])
        self.assertEqual(row['Responsible Party'], legacy_row['Responsible Party'])
        self.assertEqual(row['pdf_locations'], legacy_row['pdf_locations'])

    def test_qa_planner_extracted_data_format(self):
        """Test QA Planner extraction type formatting"""
        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='qa_planner',
            log_status='SUCCESS',
            created_by=self.user
        )

        ExtractedData.objects.create(
            ai_generated_log=ai_log,
            project=self.project,
            project_version=self.version,
            spec_section_number='03 3000',
            spec_section_name='Concrete',
            extraction_type='qa_planner',
            item_type='product',
            paragraph_number='3.1.A',
            requirement_text='Use Type II cement',
            responsible_party='Contractor',
            source=ExtractionSource.AI,
            created_by=self.user,
            metadata={
                'when_due': 'Prior to placement',
                'raw_item': {
                    'Paragraph Number': '3.1.A',
                    'item_type': 'product',
                    'When Due': 'Prior to placement'
                }
            }
        )

        ai_log_with_prefetch = AiGeneratedLog.objects.prefetch_related(
            'extracted_items'
        ).get(id=ai_log.id)

        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user
        request.team = self.team

        serializer = AiGeneratedLogSerializer(
            ai_log_with_prefetch,
            context={'request': request}
        )
        data = serializer.data

        row = data['log_data'][0]
        self.assertEqual(row['Requirement Text'], 'Use Type II cement')
        self.assertEqual(row['item_type'], 'product')
        self.assertEqual(row['Paragraph Number'], '3.1.A')
        self.assertEqual(row['When Due'], 'Prior to placement')

    def test_owner_deliverables_extracted_data_format(self):
        """Test Owner Deliverables extraction type formatting"""
        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='owner_deliverables_log',
            log_status='SUCCESS',
            created_by=self.user
        )

        ExtractedData.objects.create(
            ai_generated_log=ai_log,
            project=self.project,
            project_version=self.version,
            spec_section_number='01 7800',
            spec_section_name='Closeout Submittals',
            extraction_type='owner_deliverables_log',
            requirement_text='Provide as-built drawings',
            responsible_party='Contractor',
            source=ExtractionSource.AI,
            created_by=self.user,
            metadata={
                'deliverable_type': 'Drawing',
                'when_due': 'Prior to final payment',
                'raw_item': {
                    'Deliverable Type': 'Drawing',
                    'When Due': 'Prior to final payment'
                }
            }
        )

        ai_log_with_prefetch = AiGeneratedLog.objects.prefetch_related(
            'extracted_items'
        ).get(id=ai_log.id)

        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user
        request.team = self.team

        serializer = AiGeneratedLogSerializer(
            ai_log_with_prefetch,
            context={'request': request}
        )
        data = serializer.data

        row = data['log_data'][0]
        self.assertEqual(row['Exact Requirement Text'], 'Provide as-built drawings')
        self.assertEqual(row['Deliverable Type'], 'Drawing')
        self.assertEqual(row['When Due'], 'Prior to final payment')
```

**Step 2: Run tests to verify they pass**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_ai_generated_log_serializer_extracted_data --verbosity=2`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add apps/deliverables/tests/test_ai_generated_log_serializer_extracted_data.py
git commit -m "test: verify AiGeneratedLogSerializer uses ExtractedData with backward compatibility"
```

---

### Task 2: Add Integration Tests for ViewSet

**Files:**
- Modify: `apps/deliverables/tests/test_ai_generated_log_views.py`

**Step 1: Add test for viewset endpoint with ExtractedData**

```python
# Add to apps/deliverables/tests/test_ai_generated_log_views.py

def test_list_endpoint_uses_extracted_data(self):
    """Test that list endpoint returns data from ExtractedData when available"""
    # Create AI log with both log_data and ExtractedData
    ai_log = AiGeneratedLog.objects.create(
        project=self.project,
        project_version=self.version,
        log_type='inspection_log',
        log_status='SUCCESS',
        created_by=self.user,
        log_data=[
            {
                'Spec Section #': '01 1000',
                'Inspection Type And Requirements': 'Old JSON data',
            }
        ]
    )

    # ExtractedData should take precedence
    ExtractedData.objects.create(
        ai_generated_log=ai_log,
        project=self.project,
        project_version=self.version,
        spec_section_number='01 1000',
        spec_section_name='General',
        extraction_type='inspection_log',
        requirement_text='New ExtractedData model data',
        source='AI',
        created_by=self.user,
        metadata={'inspection_frequency': 'Daily', 'raw_item': {}}
    )

    url = reverse('aigeneratedlog-list', kwargs={'project_id': self.project.id})
    response = self.client.get(url, {
        'project_version_id': self.version.id,
        'log_type': 'inspection_log'
    })

    self.assertEqual(response.status_code, 200)
    results = response.json()['results']
    self.assertEqual(len(results), 1)

    # Verify data comes from ExtractedData
    log_data = results[0]['log_data']
    self.assertEqual(len(log_data), 1)
    self.assertEqual(
        log_data[0]['Inspection Type And Requirements'],
        'New ExtractedData model data'
    )
```

**Step 2: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_ai_generated_log_views.TestAiGeneratedLogViewSet.test_list_endpoint_uses_extracted_data --verbosity=2`
Expected: PASS

**Step 3: Commit**

```bash
git add apps/deliverables/tests/test_ai_generated_log_views.py
git commit -m "test: verify viewset endpoint uses ExtractedData over log_data JSON"
```

---

### Task 3: Update Documentation

**Files:**
- Create: `docs/EXTRACTED_DATA_MIGRATION.md`

**Step 1: Create migration documentation**

```markdown
# ExtractedData Model Migration

## Overview

The `ExtractedData` model normalizes data previously stored in the `AiGeneratedLog.log_data` JSON field. This provides:

1. **Proper database indexing** for faster queries
2. **Foreign key relationships** for data integrity
3. **Source tracking** (AI vs HUMAN created extractions)
4. **CRUD operations** for user-created highlights

## Backward Compatibility

The `AiGeneratedLogSerializer` maintains complete backward compatibility:

### Data Source Priority
1. **If `ExtractedData` records exist:** Use them (via `extracted_items` relationship)
2. **If no `ExtractedData` records:** Fall back to `log_data` JSON field

### Response Format
The response format is **identical** whether data comes from `ExtractedData` or `log_data`:

```json
{
  "id": 123,
  "log_type": "inspection_log",
  "log_data": [
    {
      "Spec Section #": "01 1000",
      "Spec Section Name": "General",
      "Inspection Type And Requirements": "...",
      "Inspection Frequency": "Daily",
      "Responsible Party": "Contractor",
      "pdf_locations": [...]
    }
  ],
  "pagination": {...}
}
```

### How It Works

1. **ViewSet** (line 632 of `specgpt_views.py`):
   ```python
   return queryset.prefetch_related('extracted_items')
   ```

2. **Serializer** (line 48-58 of `specgpt.py`):
   ```python
   def build_structured_rows(self, instance):
       """Return structured rows using ExtractedData when available."""
       extracted_items = list(getattr(instance, 'extracted_items', []).all())
       if extracted_items:
           return [self._format_extracted_item(item) for item in extracted_items]
       # Fallback to log_data JSON
       return instance.log_data
   ```

3. **Formatter** (line 60-94 of `specgpt.py`):
   ```python
   def _format_extracted_item(self, item):
       """Convert ExtractedData instance to legacy row format."""
       # Reconstructs the exact format expected by frontend
   ```

## Migration Status

- ✅ Model created (migration 0065)
- ✅ Data migration script (migration 0066)
- ✅ Webhook updated to create ExtractedData
- ✅ Serializer supports ExtractedData with fallback
- ✅ ViewSet prefetches ExtractedData
- ✅ New CRUD endpoints for human-created extractions

## Frontend Changes Required

**None!** The frontend continues to use the same endpoints and receives the same response format.

## New Capabilities

### 1. Human-Created Extractions
Users can now create extractions via Apryse highlights:

```
POST /api/projects/{project_id}/extracted-data/
{
  "spec_section_number": "01 1000",
  "extraction_type": "submittal",
  "item_type": "product",
  "requirement_text": "...",
  "pdf_locations": [...]
}
```

### 2. Better Querying
Direct database queries instead of JSON traversal:

```python
# Old way (slow, no indexes)
logs = AiGeneratedLog.objects.filter(log_type='inspection_log')
# Then parse JSON in Python

# New way (fast, indexed)
items = ExtractedData.objects.filter(
    extraction_type='inspection_log',
    spec_section_number='01 1000'
).select_related('project', 'created_by')
```

### 3. Source Tracking
Know whether extraction came from AI or human:

```python
ai_items = ExtractedData.objects.filter(source=ExtractionSource.AI)
human_items = ExtractedData.objects.filter(source=ExtractionSource.HUMAN)
```
```

**Step 2: Commit**

```bash
git add docs/EXTRACTED_DATA_MIGRATION.md
git commit -m "docs: document ExtractedData migration and backward compatibility"
```

---

## Summary

**Key Points:**
1. ✅ Serializer already uses ExtractedData when available (no changes needed)
2. ✅ ViewSet already prefetches ExtractedData (no changes needed)
3. ✅ Response format is identical (backward compatible)
4. 📝 Added comprehensive tests to verify behavior
5. 📝 Added documentation for future reference

**Frontend Impact:** Zero - same endpoints, same response format

**Backend Benefits:**
- Proper database normalization
- Better query performance
- Source tracking (AI vs HUMAN)
- CRUD operations for highlights
