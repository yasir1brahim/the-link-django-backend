# Spec Conflicts API Enhancements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance the spec conflicts API with drawing PDF fields, server-side sorting/filtering, filter options, and Excel export.

**Architecture:** Extend `SpecConflictReadSerializer` with drawing-related fields by traversing the `note.section.page.drawing_file` relationship. Add query parameter handling in the view for sorting and filtering. Create a new export endpoint using openpyxl (following existing patterns in `main_views.py`).

**Tech Stack:** Django REST Framework, openpyxl, boto3 (S3 presigned URLs)

---

## Task 1: Add Drawing Fields to Serializer

**Files:**
- Modify: `apps/deliverables/serializers/spec_comparison_serializers.py`
- Modify: `apps/deliverables/tests/test_spec_comparison_serializers.py`

**Step 1: Write tests for new serializer fields**

Add to `apps/deliverables/tests/test_spec_comparison_serializers.py`:

```python
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
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


@override_settings(S3_BUCKET='bucket')
class TestSpecConflictReadSerializerDrawingFields(TestCase):
    """Test drawing-related fields in SpecConflictReadSerializer"""

    def setUp(self):
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

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_includes_sheet_number(self, mock_presigned):
        """Test serializer includes sheet_number from drawing page"""
        mock_presigned.return_value = 'https://presigned-url.com'
        from apps.deliverables.serializers.spec_comparison_serializers import SpecConflictReadSerializer

        serializer = SpecConflictReadSerializer(self.conflict, context={})
        self.assertEqual(serializer.data['sheet_number'], 'P-201')

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_includes_sheet_title(self, mock_presigned):
        """Test serializer includes sheet_title from drawing page"""
        mock_presigned.return_value = 'https://presigned-url.com'
        from apps.deliverables.serializers.spec_comparison_serializers import SpecConflictReadSerializer

        serializer = SpecConflictReadSerializer(self.conflict, context={})
        self.assertEqual(serializer.data['sheet_title'], 'Plumbing Riser Diagram')

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_includes_drawing_file_url(self, mock_presigned):
        """Test serializer includes presigned drawing file URL"""
        mock_presigned.return_value = 'https://presigned-url.com/drawing.pdf'
        from apps.deliverables.serializers.spec_comparison_serializers import SpecConflictReadSerializer

        serializer = SpecConflictReadSerializer(self.conflict, context={})
        self.assertEqual(serializer.data['drawing_file_url'], 'https://presigned-url.com/drawing.pdf')

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_includes_drawing_page_number(self, mock_presigned):
        """Test serializer includes drawing page number"""
        mock_presigned.return_value = 'https://presigned-url.com'
        from apps.deliverables.serializers.spec_comparison_serializers import SpecConflictReadSerializer

        serializer = SpecConflictReadSerializer(self.conflict, context={})
        self.assertEqual(serializer.data['drawing_page_number'], 3)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_includes_drawing_bounding_box(self, mock_presigned):
        """Test serializer includes drawing bounding box"""
        mock_presigned.return_value = 'https://presigned-url.com'
        from apps.deliverables.serializers.spec_comparison_serializers import SpecConflictReadSerializer

        serializer = SpecConflictReadSerializer(self.conflict, context={})
        self.assertEqual(serializer.data['drawing_bounding_box'], [120.5, 340.2, 280.0, 360.8])

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_drawing_fields_null_when_note_missing(self, mock_presigned):
        """Test drawing fields are null when note FK is null"""
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
```

**Step 2: Run tests to verify they fail**

Run: `docker-compose exec -T web python manage.py test apps.deliverables.tests.test_spec_comparison_serializers.TestSpecConflictReadSerializerDrawingFields -v 2`
Expected: FAIL (fields don't exist)

**Step 3: Update SpecConflictReadSerializer**

Modify `apps/deliverables/serializers/spec_comparison_serializers.py`:

```python
class SpecConflictReadSerializer(serializers.ModelSerializer):
    """Serializer for reading conflict data via API"""
    note_id = serializers.SerializerMethodField()
    spec_file_url = serializers.SerializerMethodField()
    # New drawing-related fields
    sheet_number = serializers.SerializerMethodField()
    sheet_title = serializers.SerializerMethodField()
    drawing_file_url = serializers.SerializerMethodField()
    drawing_page_number = serializers.SerializerMethodField()
    drawing_bounding_box = serializers.SerializerMethodField()

    class Meta:
        model = SpecConflict
        fields = [
            'id',
            'note_id',
            'note_id_from_lambda',
            'note_text',
            # Drawing fields
            'sheet_number',
            'sheet_title',
            'drawing_file_url',
            'drawing_page_number',
            'drawing_bounding_box',
            # Spec fields
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
        return obj.note_id_from_lambda

    def get_sheet_number(self, obj):
        """Get sheet number from the drawing page."""
        if obj.note and obj.note.section and obj.note.section.page:
            return obj.note.section.page.sheet_number
        return None

    def get_sheet_title(self, obj):
        """Get sheet title from the drawing page."""
        if obj.note and obj.note.section and obj.note.section.page:
            return obj.note.section.page.sheet_title
        return None

    def get_drawing_file_url(self, obj):
        """Generate presigned S3 URL for drawing file access."""
        if not obj.note or not obj.note.section or not obj.note.section.page:
            return None

        drawing_file = obj.note.section.page.drawing_file
        s3_key = drawing_file.file_s3_key

        # Memoize URLs per s3_key within request context
        context = self.context
        cache_key = 'presigned_urls'
        if cache_key not in context:
            context[cache_key] = {}

        if s3_key not in context[cache_key]:
            context[cache_key][s3_key] = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': settings.S3_BUCKET, 'Key': s3_key},
                ExpiresIn=3600,
            )
        return context[cache_key][s3_key]

    def get_drawing_page_number(self, obj):
        """Get page number from the drawing page."""
        if obj.note and obj.note.section and obj.note.section.page:
            return obj.note.section.page.page_number
        return None

    def get_drawing_bounding_box(self, obj):
        """Get bounding box for the note in the drawing."""
        if obj.note:
            # Prefer unrotated_bounding_box, fall back to bounding_box
            return obj.note.unrotated_bounding_box or obj.note.bounding_box
        return None

    def get_spec_file_url(self, obj):
        """Generate presigned S3 URL for spec file access."""
        context = self.context
        cache_key = 'presigned_urls'
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
```

**Step 4: Run tests to verify they pass**

Run: `docker-compose exec -T web python manage.py test apps.deliverables.tests.test_spec_comparison_serializers -v 2`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/serializers/spec_comparison_serializers.py apps/deliverables/tests/test_spec_comparison_serializers.py
git commit -m "$(cat <<'EOF'
feat: add drawing fields to SpecConflictReadSerializer

- Add sheet_number, sheet_title from drawing page
- Add drawing_file_url with presigned S3 URL
- Add drawing_page_number for PDF viewer navigation
- Add drawing_bounding_box for highlighting
- Handle null note FK gracefully

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add Server-Side Sorting

**Files:**
- Modify: `apps/deliverables/views/spec_comparison_views.py`
- Modify: `apps/deliverables/tests/test_spec_comparison_read.py`

**Step 1: Write sorting tests**

Add to `apps/deliverables/tests/test_spec_comparison_read.py`:

```python
class TestSpecConflictsSorting(APITestCase):
    """Test sorting on spec conflicts endpoint"""

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
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role='project_member'
        )

        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event',
        )

        # Create conflicts with different values for sorting
        self.conflict_a = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='1',
            note_text='Alpha note',
            spec_text='Spec A',
            spec_file_s3_key='specs/a.pdf',
            spec_page_number=1,
            spec_masterformat_number='220500',
            confidence=0.9,
            reason='Reason A',
        )
        self.conflict_b = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='2',
            note_text='Beta note',
            spec_text='Spec B',
            spec_file_s3_key='specs/b.pdf',
            spec_page_number=2,
            spec_masterformat_number='230500',
            confidence=0.8,
            reason='Reason B',
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse('deliverables:spec-conflicts', kwargs={'project_id': self.project.id})

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_sort_by_note_text_asc(self, mock_presigned):
        """Test sorting by note_text ascending"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'sort_column': 'note_text',
            'sort_direction': 'asc'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(results[0]['note_text'], 'Alpha note')
        self.assertEqual(results[1]['note_text'], 'Beta note')

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_sort_by_note_text_desc(self, mock_presigned):
        """Test sorting by note_text descending"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'sort_column': 'note_text',
            'sort_direction': 'desc'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(results[0]['note_text'], 'Beta note')
        self.assertEqual(results[1]['note_text'], 'Alpha note')

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_sort_by_spec_masterformat_number(self, mock_presigned):
        """Test sorting by spec_masterformat_number"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'sort_column': 'spec_masterformat_number',
            'sort_direction': 'asc'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(results[0]['spec_masterformat_number'], '220500')
        self.assertEqual(results[1]['spec_masterformat_number'], '230500')

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_invalid_sort_column_ignored(self, mock_presigned):
        """Test invalid sort column is ignored (falls back to default)"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'sort_column': 'invalid_column',
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
```

**Step 2: Run tests to verify they fail**

Run: `docker-compose exec -T web python manage.py test apps.deliverables.tests.test_spec_comparison_read.TestSpecConflictsSorting -v 2`
Expected: FAIL (sorting not implemented)

**Step 3: Add sorting to get_spec_conflicts view**

Modify the `get_spec_conflicts` function in `apps/deliverables/views/spec_comparison_views.py`:

```python
# Add these constants at module level
SORTABLE_COLUMNS = {
    'sheet_number': 'note__section__page__sheet_number',
    'note_text': 'note_text',
    'spec_text': 'spec_text',
    'spec_masterformat_number': 'spec_masterformat_number',
    'reason': 'reason',
}

# In get_spec_conflicts, replace the conflicts query with:
    # Get conflicts with pagination
    conflicts = SpecConflict.objects.filter(comparison=comparison).select_related(
        'note__section__page__drawing_file'
    )

    # Apply sorting
    sort_column = request.query_params.get('sort_column')
    sort_direction = request.query_params.get('sort_direction', 'asc')

    if sort_column and sort_column in SORTABLE_COLUMNS:
        order_field = SORTABLE_COLUMNS[sort_column]
        if sort_direction == 'desc':
            order_field = f'-{order_field}'
        conflicts = conflicts.order_by(order_field, 'id')  # Secondary sort by id for stability
    else:
        conflicts = conflicts.order_by('id')
```

**Step 4: Run tests to verify they pass**

Run: `docker-compose exec -T web python manage.py test apps.deliverables.tests.test_spec_comparison_read.TestSpecConflictsSorting -v 2`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/views/spec_comparison_views.py apps/deliverables/tests/test_spec_comparison_read.py
git commit -m "$(cat <<'EOF'
feat: add server-side sorting to spec conflicts endpoint

- Support sort_column: sheet_number, note_text, spec_text, spec_masterformat_number, reason
- Support sort_direction: asc (default), desc
- Invalid sort columns are ignored
- Secondary sort by id for stable pagination

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add Server-Side Filtering

**Files:**
- Modify: `apps/deliverables/views/spec_comparison_views.py`
- Modify: `apps/deliverables/tests/test_spec_comparison_read.py`

**Step 1: Write filtering tests**

Add to `apps/deliverables/tests/test_spec_comparison_read.py`:

```python
class TestSpecConflictsFiltering(APITestCase):
    """Test filtering on spec conflicts endpoint"""

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
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role='project_member'
        )

        # Create drawing structures for sheet_number filtering
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
        self.page1 = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=1,
            page_type='drawing',
            extraction_status='success',
            sheet_number='P-201',
        )
        self.page2 = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=2,
            page_type='drawing',
            extraction_status='success',
            sheet_number='M-101',
        )
        self.section1 = DrawingNoteSection.objects.create(page=self.page1, header='NOTES')
        self.section2 = DrawingNoteSection.objects.create(page=self.page2, header='NOTES')
        self.note1 = DrawingNote.objects.create(
            section=self.section1, note_number=1, category='general', text='Valve note'
        )
        self.note2 = DrawingNote.objects.create(
            section=self.section2, note_number=1, category='general', text='Duct note'
        )

        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event',
        )

        self.conflict1 = SpecConflict.objects.create(
            comparison=self.comparison,
            note=self.note1,
            note_id_from_lambda='1',
            note_text='Ball valve required',
            spec_text='Gate valve specified',
            spec_file_s3_key='specs/plumbing.pdf',
            spec_page_number=1,
            spec_masterformat_number='220500',
            confidence=0.9,
            reason='Valve type mismatch',
        )
        self.conflict2 = SpecConflict.objects.create(
            comparison=self.comparison,
            note=self.note2,
            note_id_from_lambda='2',
            note_text='Duct size 12 inch',
            spec_text='Duct size 10 inch',
            spec_file_s3_key='specs/mechanical.pdf',
            spec_page_number=2,
            spec_masterformat_number='230500',
            confidence=0.8,
            reason='Dimension mismatch',
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse('deliverables:spec-conflicts', kwargs={'project_id': self.project.id})

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_by_search_in_note_text(self, mock_presigned):
        """Test search filter matches note_text"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'search': 'valve'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['note_text'], 'Ball valve required')

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_by_search_in_spec_text(self, mock_presigned):
        """Test search filter matches spec_text"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'search': 'Gate'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_by_search_in_reason(self, mock_presigned):
        """Test search filter matches reason"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'search': 'Dimension'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertIn('Dimension', response.data['results'][0]['reason'])

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_by_sheet_number(self, mock_presigned):
        """Test filtering by exact sheet_number"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'sheet_number': 'P-201'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['sheet_number'], 'P-201')

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_by_spec_masterformat_number(self, mock_presigned):
        """Test filtering by exact spec_masterformat_number"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'spec_masterformat_number': '220500'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_by_reason(self, mock_presigned):
        """Test filtering by exact reason"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'reason': 'Valve type mismatch'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_combined_filters(self, mock_presigned):
        """Test combining multiple filters"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'sheet_number': 'P-201',
            'search': 'valve'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
```

**Step 2: Run tests to verify they fail**

Run: `docker-compose exec -T web python manage.py test apps.deliverables.tests.test_spec_comparison_read.TestSpecConflictsFiltering -v 2`
Expected: FAIL (filtering not implemented)

**Step 3: Add filtering to get_spec_conflicts view**

Add filtering logic after the sorting in `get_spec_conflicts`:

```python
from django.db.models import Q

# In get_spec_conflicts, after getting conflicts queryset:

    # Apply filters
    search = request.query_params.get('search')
    if search:
        conflicts = conflicts.filter(
            Q(note_text__icontains=search) |
            Q(spec_text__icontains=search) |
            Q(reason__icontains=search)
        )

    sheet_number_filter = request.query_params.get('sheet_number')
    if sheet_number_filter:
        conflicts = conflicts.filter(note__section__page__sheet_number=sheet_number_filter)

    spec_masterformat_filter = request.query_params.get('spec_masterformat_number')
    if spec_masterformat_filter:
        conflicts = conflicts.filter(spec_masterformat_number=spec_masterformat_filter)

    reason_filter = request.query_params.get('reason')
    if reason_filter:
        conflicts = conflicts.filter(reason=reason_filter)
```

**Step 4: Run tests to verify they pass**

Run: `docker-compose exec -T web python manage.py test apps.deliverables.tests.test_spec_comparison_read.TestSpecConflictsFiltering -v 2`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/views/spec_comparison_views.py apps/deliverables/tests/test_spec_comparison_read.py
git commit -m "$(cat <<'EOF'
feat: add server-side filtering to spec conflicts endpoint

- Add search filter across note_text, spec_text, reason (case-insensitive)
- Add sheet_number exact filter
- Add spec_masterformat_number exact filter
- Add reason exact filter
- Filters can be combined

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add Filter Options to Response

**Files:**
- Modify: `apps/deliverables/views/spec_comparison_views.py`
- Modify: `apps/deliverables/tests/test_spec_comparison_read.py`

**Step 1: Write filter options tests**

Add to `apps/deliverables/tests/test_spec_comparison_read.py`:

```python
class TestSpecConflictsFilterOptions(APITestCase):
    """Test filter_options in spec conflicts response"""

    def setUp(self):
        # Same setup as TestSpecConflictsFiltering
        self.user = User.objects.create_user('test@example.com', password='testpass123')
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

        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event',
        )

        # Create drawing structures
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
        page1 = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=1,
            page_type='drawing',
            extraction_status='success',
            sheet_number='P-201',
        )
        page2 = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=2,
            page_type='drawing',
            extraction_status='success',
            sheet_number='M-101',
        )
        section1 = DrawingNoteSection.objects.create(page=page1, header='NOTES')
        section2 = DrawingNoteSection.objects.create(page=page2, header='NOTES')
        note1 = DrawingNote.objects.create(section=section1, note_number=1, category='general', text='Note 1')
        note2 = DrawingNote.objects.create(section=section2, note_number=1, category='general', text='Note 2')

        SpecConflict.objects.create(
            comparison=self.comparison,
            note=note1,
            note_id_from_lambda='1',
            note_text='Note 1',
            spec_text='Spec 1',
            spec_file_s3_key='specs/a.pdf',
            spec_page_number=1,
            spec_masterformat_number='220500',
            confidence=0.9,
            reason='Reason A',
        )
        SpecConflict.objects.create(
            comparison=self.comparison,
            note=note2,
            note_id_from_lambda='2',
            note_text='Note 2',
            spec_text='Spec 2',
            spec_file_s3_key='specs/b.pdf',
            spec_page_number=2,
            spec_masterformat_number='230500',
            confidence=0.8,
            reason='Reason B',
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse('deliverables:spec-conflicts', kwargs={'project_id': self.project.id})

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_includes_filter_options(self, mock_presigned):
        """Test response includes filter_options"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('filter_options', response.data)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_options_contains_sheet_numbers(self, mock_presigned):
        """Test filter_options includes unique sheet numbers"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        sheet_numbers = response.data['filter_options']['sheet_numbers']
        self.assertIn('P-201', sheet_numbers)
        self.assertIn('M-101', sheet_numbers)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_options_contains_spec_masterformat_numbers(self, mock_presigned):
        """Test filter_options includes unique spec masterformat numbers"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        spec_numbers = response.data['filter_options']['spec_masterformat_numbers']
        self.assertIn('220500', spec_numbers)
        self.assertIn('230500', spec_numbers)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_options_contains_reasons(self, mock_presigned):
        """Test filter_options includes unique reasons"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        reasons = response.data['filter_options']['reasons']
        self.assertIn('Reason A', reasons)
        self.assertIn('Reason B', reasons)
```

**Step 2: Run tests to verify they fail**

Run: `docker-compose exec -T web python manage.py test apps.deliverables.tests.test_spec_comparison_read.TestSpecConflictsFilterOptions -v 2`
Expected: FAIL

**Step 3: Add filter_options to response**

Modify `get_spec_conflicts` to include filter_options:

```python
# After getting comparison, before applying filters, get all filter options:

    # Get filter options from unfiltered queryset (for dropdown population)
    all_conflicts = SpecConflict.objects.filter(comparison=comparison).select_related(
        'note__section__page'
    )

    filter_options = {
        'sheet_numbers': sorted(list(
            all_conflicts.exclude(note__section__page__sheet_number__isnull=True)
            .values_list('note__section__page__sheet_number', flat=True)
            .distinct()
        )),
        'spec_masterformat_numbers': sorted(list(
            all_conflicts.values_list('spec_masterformat_number', flat=True).distinct()
        )),
        'reasons': sorted(list(
            all_conflicts.values_list('reason', flat=True).distinct()
        )),
    }

# Then at the end of the function, add filter_options to response:
    response = paginator.get_paginated_response(serializer.data)
    response.data['comparison'] = SpecComparisonSummarySerializer(comparison).data
    response.data['filter_options'] = filter_options

    return response
```

**Step 4: Run tests to verify they pass**

Run: `docker-compose exec -T web python manage.py test apps.deliverables.tests.test_spec_comparison_read.TestSpecConflictsFilterOptions -v 2`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/views/spec_comparison_views.py apps/deliverables/tests/test_spec_comparison_read.py
git commit -m "$(cat <<'EOF'
feat: add filter_options to spec conflicts response

- Include sheet_numbers array for dropdown population
- Include spec_masterformat_numbers array
- Include reasons array
- Values are sorted and deduplicated

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add Excel Export Endpoint

**Files:**
- Modify: `apps/deliverables/views/spec_comparison_views.py`
- Modify: `apps/deliverables/urls.py`
- Create: `apps/deliverables/tests/test_spec_comparison_export.py`

**Step 1: Write export endpoint tests**

Create `apps/deliverables/tests/test_spec_comparison_export.py`:

```python
from io import BytesIO
from unittest.mock import patch
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
import openpyxl

from apps.deliverables.models import (
    Project,
    ProjectMembership,
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

User = get_user_model()


class TestSpecConflictsExport(APITestCase):
    """Test GET /projects/{id}/spec-conflicts/export/ endpoint"""

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
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role='project_member'
        )

        # Create drawing structures
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
            sheet_number='P-201',
            sheet_title='Plumbing Plan',
        )
        self.section = DrawingNoteSection.objects.create(page=self.page, header='NOTES')
        self.note = DrawingNote.objects.create(
            section=self.section,
            note_number=1,
            category='general',
            text='Test note'
        )

        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event',
        )
        self.conflict = SpecConflict.objects.create(
            comparison=self.comparison,
            note=self.note,
            note_id_from_lambda='1',
            note_text='Ball valve required',
            spec_text='Gate valve specified',
            spec_file_s3_key='specs/plumbing.pdf',
            spec_page_number=15,
            spec_masterformat_number='220500',
            confidence=0.85,
            reason='Valve type mismatch',
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse('deliverables:spec-conflicts-export', kwargs={'project_id': self.project.id})

    def test_returns_xlsx_content_type(self):
        """Test export returns correct content type"""
        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    def test_returns_attachment_disposition(self):
        """Test export returns attachment disposition"""
        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('spec_conflicts.xlsx', response['Content-Disposition'])

    def test_xlsx_contains_headers(self):
        """Test exported file contains correct headers"""
        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        workbook = openpyxl.load_workbook(BytesIO(response.content))
        worksheet = workbook.active

        expected_headers = [
            'Drawing #', 'Sheet Title', 'Drawing Content', 'Related Spec Content',
            'Spec Section', 'Spec Page', 'Reason', 'Confidence'
        ]
        actual_headers = [cell.value for cell in worksheet[1]]

        self.assertEqual(actual_headers, expected_headers)

    def test_xlsx_contains_data(self):
        """Test exported file contains conflict data"""
        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        workbook = openpyxl.load_workbook(BytesIO(response.content))
        worksheet = workbook.active

        # Check data row (row 2)
        self.assertEqual(worksheet.cell(2, 1).value, 'P-201')  # Drawing #
        self.assertEqual(worksheet.cell(2, 2).value, 'Plumbing Plan')  # Sheet Title
        self.assertEqual(worksheet.cell(2, 3).value, 'Ball valve required')  # Drawing Content
        self.assertEqual(worksheet.cell(2, 4).value, 'Gate valve specified')  # Spec Content
        self.assertEqual(worksheet.cell(2, 5).value, '220500')  # Spec Section
        self.assertEqual(worksheet.cell(2, 6).value, 15)  # Spec Page
        self.assertEqual(worksheet.cell(2, 7).value, 'Valve type mismatch')  # Reason
        self.assertEqual(worksheet.cell(2, 8).value, '85%')  # Confidence

    def test_respects_filters(self):
        """Test export respects filter parameters"""
        # Create another conflict that should be filtered out
        SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='2',
            note_text='Other note',
            spec_text='Other spec',
            spec_file_s3_key='specs/other.pdf',
            spec_page_number=1,
            spec_masterformat_number='230500',
            confidence=0.7,
            reason='Different reason',
        )

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'spec_masterformat_number': '220500'
        })

        workbook = openpyxl.load_workbook(BytesIO(response.content))
        worksheet = workbook.active

        # Should only have header + 1 data row
        self.assertEqual(worksheet.max_row, 2)

    def test_missing_project_version_id_returns_400(self):
        """Test 400 when project_version_id is missing"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_returns_403(self):
        """Test 403 for unauthenticated requests"""
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
```

**Step 2: Run tests to verify they fail**

Run: `docker-compose exec -T web python manage.py test apps.deliverables.tests.test_spec_comparison_export -v 2`
Expected: FAIL (endpoint doesn't exist)

**Step 3: Add export view**

Add to `apps/deliverables/views/spec_comparison_views.py`:

```python
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from django.http import HttpResponse


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_spec_conflicts(request, project_id):
    """
    Export spec conflicts to Excel file.

    GET /api/deliverables/projects/{project_id}/spec-conflicts/export/
    Query params: Same as get_spec_conflicts (filters apply)
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
            comparison = SpecComparison.objects.get(
                id=int(comparison_id),
                project=project,
                project_version=project_version
            )
        except (ValueError, SpecComparison.DoesNotExist):
            return Response(
                {"error": "Comparison not found"},
                status=status.HTTP_404_NOT_FOUND
            )
    else:
        comparison = SpecComparison.objects.filter(
            project=project,
            project_version=project_version,
            status__in=[SpecComparisonStatus.SUCCESS, SpecComparisonStatus.PARTIAL_SUCCESS],
        ).order_by('-completed_at').first()

    if not comparison:
        # Return empty Excel file
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.title = "Spec Conflicts"
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename=spec_conflicts.xlsx'
        workbook.save(response)
        return response

    # Get conflicts with filters
    conflicts = SpecConflict.objects.filter(comparison=comparison).select_related(
        'note__section__page__drawing_file'
    )

    # Apply filters (same as get_spec_conflicts)
    search = request.query_params.get('search')
    if search:
        conflicts = conflicts.filter(
            Q(note_text__icontains=search) |
            Q(spec_text__icontains=search) |
            Q(reason__icontains=search)
        )

    sheet_number_filter = request.query_params.get('sheet_number')
    if sheet_number_filter:
        conflicts = conflicts.filter(note__section__page__sheet_number=sheet_number_filter)

    spec_masterformat_filter = request.query_params.get('spec_masterformat_number')
    if spec_masterformat_filter:
        conflicts = conflicts.filter(spec_masterformat_number=spec_masterformat_filter)

    reason_filter = request.query_params.get('reason')
    if reason_filter:
        conflicts = conflicts.filter(reason=reason_filter)

    conflicts = conflicts.order_by('id')

    # Create workbook
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "Spec Conflicts"

    # Define styles
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='202a44', end_color='202a44', fill_type='solid')
    header_alignment = Alignment(wrap_text=True, vertical='center')
    text_alignment = Alignment(wrap_text=True, vertical='center')

    # Headers
    headers = [
        'Drawing #', 'Sheet Title', 'Drawing Content', 'Related Spec Content',
        'Spec Section', 'Spec Page', 'Reason', 'Confidence'
    ]
    for col, header in enumerate(headers, start=1):
        cell = worksheet.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment

    # Data rows
    for row_idx, conflict in enumerate(conflicts, start=2):
        # Get drawing info
        sheet_number = None
        sheet_title = None
        if conflict.note and conflict.note.section and conflict.note.section.page:
            page = conflict.note.section.page
            sheet_number = page.sheet_number
            sheet_title = page.sheet_title

        row_data = [
            sheet_number,
            sheet_title,
            conflict.note_text,
            conflict.spec_text,
            conflict.spec_masterformat_number,
            conflict.spec_page_number,
            conflict.reason,
            f"{int(conflict.confidence * 100)}%",
        ]

        for col, value in enumerate(row_data, start=1):
            cell = worksheet.cell(row=row_idx, column=col, value=value)
            cell.alignment = text_alignment

    # Set column widths
    column_widths = [15, 30, 50, 50, 15, 12, 40, 12]
    for col, width in enumerate(column_widths, start=1):
        worksheet.column_dimensions[openpyxl.utils.get_column_letter(col)].width = width

    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=spec_conflicts.xlsx'
    workbook.save(response)

    return response
```

**Step 4: Add URL route**

Add to `apps/deliverables/urls.py`:

```python
from .views.spec_comparison_views import (
    spec_comparison_webhook,
    trigger_spec_comparison,
    get_spec_conflicts,
    get_skipped_notes,
    list_spec_comparisons,
    export_spec_conflicts,
)

# Add to urlpatterns:
path('projects/<int:project_id>/spec-conflicts/export/', export_spec_conflicts, name='spec-conflicts-export'),
```

**Step 5: Run tests to verify they pass**

Run: `docker-compose exec -T web python manage.py test apps.deliverables.tests.test_spec_comparison_export -v 2`
Expected: PASS

**Step 6: Commit**

```bash
git add apps/deliverables/views/spec_comparison_views.py apps/deliverables/urls.py apps/deliverables/tests/test_spec_comparison_export.py
git commit -m "$(cat <<'EOF'
feat: add spec conflicts Excel export endpoint

- Add GET /projects/{id}/spec-conflicts/export/ endpoint
- Export to XLSX with styled headers
- Include all required columns per frontend spec
- Respect all filter parameters
- Format confidence as percentage

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Update select_related for Performance

**Files:**
- Modify: `apps/deliverables/views/spec_comparison_views.py`

**Step 1: Update get_spec_conflicts select_related**

Ensure all related objects are fetched efficiently:

```python
# In get_spec_conflicts, update the conflicts queryset:
conflicts = SpecConflict.objects.filter(comparison=comparison).select_related(
    'note__section__page__drawing_file'
)
```

**Step 2: Run full test suite**

Run: `docker-compose exec -T web python manage.py test apps.deliverables.tests.test_spec_comparison_read apps.deliverables.tests.test_spec_comparison_export -v 2`
Expected: PASS

**Step 3: Commit**

```bash
git add apps/deliverables/views/spec_comparison_views.py
git commit -m "$(cat <<'EOF'
perf: optimize select_related for spec conflicts queries

- Add note__section__page__drawing_file to select_related
- Prevents N+1 queries when accessing drawing fields

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Run Full Test Suite and Update API Documentation

**Step 1: Run all related tests**

Run: `docker-compose exec -T web python manage.py test apps.deliverables.tests.test_spec_comparison_models apps.deliverables.tests.test_spec_comparison_serializers apps.deliverables.tests.test_spec_comparison_webhook apps.deliverables.tests.test_spec_comparison_trigger apps.deliverables.tests.test_spec_comparison_read apps.deliverables.tests.test_spec_comparison_export apps.utils.tests.test_spec_comparison_feature_flag -v 2`
Expected: All tests PASS

**Step 2: Run system check**

Run: `docker-compose exec -T web python manage.py check`
Expected: No issues

**Step 3: Update API documentation**

Update `docs/drawing-spec-comparison-api.md` to reflect the new fields, sorting, filtering, filter_options, and export endpoint.

**Step 4: Final commit**

```bash
git add docs/drawing-spec-comparison-api.md
git commit -m "$(cat <<'EOF'
docs: update API documentation with new features

- Document new drawing fields in conflict response
- Document sorting parameters
- Document filtering parameters
- Document filter_options in response
- Document Excel export endpoint

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

| Task | Description | Files Modified |
|------|-------------|----------------|
| 1 | Add drawing fields to serializer | serializers, tests |
| 2 | Add server-side sorting | views, tests |
| 3 | Add server-side filtering | views, tests |
| 4 | Add filter_options to response | views, tests |
| 5 | Add Excel export endpoint | views, urls, tests |
| 6 | Optimize select_related | views |
| 7 | Full test suite and docs | docs |

Each task follows TDD with explicit test-first steps.
