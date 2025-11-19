# Extraction Notes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add text-based notes to ExtractedData highlights with inline API responses and author-only editing

**Architecture:** Create ExtractionNote model with CASCADE delete to ExtractedData, embed notes in ExtractedData serializers as read-only nested field, provide separate CRUD endpoints for note management, optimize queries with prefetch_related

**Tech Stack:** Django 4.2, Django REST Framework, PostgreSQL, pytest

---

## Phase 1: Model & Basic Tests

### Task 1: Create ExtractionNote Model

**Files:**
- Create: `apps/deliverables/tests/test_extraction_note_model.py`
- Modify: `apps/deliverables/models.py` (after ExtractedData model, around line 602)

**Step 1: Write failing test for model creation**

```python
# apps/deliverables/tests/test_extraction_note_model.py
import pytest
from django.test import TestCase
from apps.deliverables.models import ExtractedData, ExtractionNote, AiGeneratedLog, Project, ProjectVersion, ExtractionSource
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class TestExtractionNoteModel(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('test@example.com')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(name="Test Project", team=self.team, created_by=self.user)
        self.version = self.project.versions.first()
        self.extracted_data = ExtractedData.objects.create(
            project=self.project,
            project_version=self.version,
            spec_section_number="01 1000",
            spec_section_name="General Requirements",
            extraction_type="custom_highlights",
            requirement_text="Test requirement",
            source=ExtractionSource.HUMAN,
            created_by=self.user
        )

    def test_note_creation(self):
        """Test basic note creation"""
        note = ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="This is a test note",
            created_by=self.user
        )

        self.assertEqual(note.text, "This is a test note")
        self.assertEqual(note.created_by, self.user)
        self.assertEqual(note.extracted_data, self.extracted_data)
        self.assertIsNotNone(note.created_at)
        self.assertIsNotNone(note.updated_at)
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_model::TestExtractionNoteModel::test_note_creation --verbosity=2`

Expected: FAIL with "ImportError: cannot import name 'ExtractionNote'"

**Step 3: Create ExtractionNote model**

Add to `apps/deliverables/models.py` after ExtractedData model (around line 602):

```python
class ExtractionNote(BaseModel):
    """Text notes attached to ExtractedData highlights"""

    extracted_data = models.ForeignKey(
        'ExtractedData',
        on_delete=models.CASCADE,
        related_name='notes',
        help_text="The highlight this note is attached to"
    )

    text = models.TextField(
        help_text="Note content"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='extraction_notes',
        help_text="User who created this note"
    )

    class Meta:
        db_table = 'deliverables_extraction_note'
        indexes = [
            models.Index(fields=['extracted_data', 'created_at']),
            models.Index(fields=['created_by']),
        ]
        ordering = ['created_at']

    def __str__(self):
        preview = self.text[:50] + '...' if len(self.text) > 50 else self.text
        return f"Note on {self.extracted_data.spec_section_number}: {preview}"
```

**Step 4: Update models __init__ exports**

Check if `apps/deliverables/models.py` has an `__all__` export list. If so, add `'ExtractionNote'` to it.

**Step 5: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_model::TestExtractionNoteModel::test_note_creation --verbosity=2`

Expected: PASS

**Step 6: Commit**

```bash
git add apps/deliverables/models.py apps/deliverables/tests/test_extraction_note_model.py
git commit -m "feat: add ExtractionNote model for text notes on highlights"
```

---

### Task 2: Test Model Relationships

**Files:**
- Modify: `apps/deliverables/tests/test_extraction_note_model.py`

**Step 1: Write test for multiple notes**

Add to `TestExtractionNoteModel` class:

```python
def test_multiple_notes_per_extraction(self):
    """Test that ExtractedData can have multiple notes"""
    note1 = ExtractionNote.objects.create(
        extracted_data=self.extracted_data,
        text="First note",
        created_by=self.user
    )
    note2 = ExtractionNote.objects.create(
        extracted_data=self.extracted_data,
        text="Second note",
        created_by=self.user
    )

    notes = self.extracted_data.notes.all()
    self.assertEqual(notes.count(), 2)
    self.assertEqual(notes[0].text, "First note")
    self.assertEqual(notes[1].text, "Second note")
```

**Step 2: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_model::TestExtractionNoteModel::test_multiple_notes_per_extraction --verbosity=2`

Expected: PASS

**Step 3: Write test for cascade delete**

Add to `TestExtractionNoteModel` class:

```python
def test_cascade_delete_with_extracted_data(self):
    """Test that notes are deleted when ExtractedData is deleted"""
    note = ExtractionNote.objects.create(
        extracted_data=self.extracted_data,
        text="Will be deleted",
        created_by=self.user
    )
    note_id = note.id

    self.extracted_data.delete()

    self.assertFalse(ExtractionNote.objects.filter(id=note_id).exists())
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_model::TestExtractionNoteModel::test_cascade_delete_with_extracted_data --verbosity=2`

Expected: PASS

**Step 5: Write test for user deletion**

Add to `TestExtractionNoteModel` class:

```python
def test_set_null_on_user_delete(self):
    """Test that notes persist when user is deleted"""
    note = ExtractionNote.objects.create(
        extracted_data=self.extracted_data,
        text="Note from deleted user",
        created_by=self.user
    )
    note_id = note.id

    self.user.delete()

    note.refresh_from_db()
    self.assertIsNone(note.created_by)
    self.assertEqual(note.text, "Note from deleted user")
```

**Step 6: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_model::TestExtractionNoteModel::test_set_null_on_user_delete --verbosity=2`

Expected: PASS

**Step 7: Write test for ordering**

Add to `TestExtractionNoteModel` class:

```python
def test_notes_ordered_by_created_at(self):
    """Test that notes are ordered chronologically"""
    import time
    note1 = ExtractionNote.objects.create(
        extracted_data=self.extracted_data,
        text="First",
        created_by=self.user
    )
    time.sleep(0.01)  # Ensure different timestamps
    note2 = ExtractionNote.objects.create(
        extracted_data=self.extracted_data,
        text="Second",
        created_by=self.user
    )
    time.sleep(0.01)
    note3 = ExtractionNote.objects.create(
        extracted_data=self.extracted_data,
        text="Third",
        created_by=self.user
    )

    notes = list(self.extracted_data.notes.all())
    self.assertEqual(len(notes), 3)
    self.assertEqual(notes[0].text, "First")
    self.assertEqual(notes[1].text, "Second")
    self.assertEqual(notes[2].text, "Third")
```

**Step 8: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_model::TestExtractionNoteModel::test_notes_ordered_by_created_at --verbosity=2`

Expected: PASS

**Step 9: Commit**

```bash
git add apps/deliverables/tests/test_extraction_note_model.py
git commit -m "test: add relationship tests for ExtractionNote model"
```

---

## Phase 2: Serializers

### Task 3: Create ExtractionNote Serializers

**Files:**
- Create: `apps/deliverables/serializers/extraction_note.py`
- Create: `apps/deliverables/tests/test_extraction_note_serializers.py`

**Step 1: Write failing test for note serializer**

```python
# apps/deliverables/tests/test_extraction_note_serializers.py
from django.test import TestCase
from apps.deliverables.models import ExtractedData, ExtractionNote, Project, ProjectVersion, ExtractionSource
from apps.deliverables.serializers.extraction_note import ExtractionNoteSerializer, ExtractionNoteCreateUpdateSerializer
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class TestExtractionNoteSerializer(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('test@example.com', first_name='Test', last_name='User')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(name="Test Project", team=self.team, created_by=self.user)
        self.version = self.project.versions.first()
        self.extracted_data = ExtractedData.objects.create(
            project=self.project,
            project_version=self.version,
            spec_section_number="01 1000",
            spec_section_name="General Requirements",
            extraction_type="custom_highlights",
            requirement_text="Test requirement",
            source=ExtractionSource.HUMAN,
            created_by=self.user
        )
        self.note = ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="Test note content",
            created_by=self.user
        )

    def test_serializer_includes_all_fields(self):
        """Test that serializer includes required fields"""
        serializer = ExtractionNoteSerializer(self.note)
        data = serializer.data

        self.assertIn('id', data)
        self.assertIn('text', data)
        self.assertIn('created_by_id', data)
        self.assertIn('created_by_name', data)
        self.assertIn('created_at', data)
        self.assertIn('updated_at', data)

        self.assertEqual(data['text'], "Test note content")
        self.assertEqual(data['created_by_id'], self.user.id)
        self.assertEqual(data['created_by_name'], "Test User")

    def test_serializer_with_null_user(self):
        """Test serializer handles deleted user (null created_by)"""
        self.note.created_by = None
        self.note.save()

        serializer = ExtractionNoteSerializer(self.note)
        data = serializer.data

        self.assertIsNone(data['created_by_id'])
        self.assertIsNone(data['created_by_name'])
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_serializers --verbosity=2`

Expected: FAIL with "ImportError: cannot import name 'ExtractionNoteSerializer'"

**Step 3: Create serializers**

```python
# apps/deliverables/serializers/extraction_note.py
from rest_framework import serializers
from apps.deliverables.models import ExtractionNote
from django.contrib.auth import get_user_model

User = get_user_model()


class ExtractionNoteSerializer(serializers.ModelSerializer):
    """Full serializer for note CRUD"""
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True,
        allow_null=True
    )
    created_by_id = serializers.IntegerField(
        source='created_by.id',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = ExtractionNote
        fields = [
            'id', 'text', 'created_by_id', 'created_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_by_id', 'created_by_name', 'created_at', 'updated_at']


class ExtractionNoteCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating notes"""
    class Meta:
        model = ExtractionNote
        fields = ['text']

    def validate_text(self, value):
        """Ensure text is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Text cannot be empty.")
        return value.strip()
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_serializers --verbosity=2`

Expected: PASS

**Step 5: Write test for create/update serializer**

Add to `TestExtractionNoteSerializer`:

```python
def test_create_update_serializer_validation(self):
    """Test that create/update serializer validates text"""
    # Valid data
    serializer = ExtractionNoteCreateUpdateSerializer(data={'text': 'Valid note'})
    self.assertTrue(serializer.is_valid())
    self.assertEqual(serializer.validated_data['text'], 'Valid note')

    # Empty text
    serializer = ExtractionNoteCreateUpdateSerializer(data={'text': ''})
    self.assertFalse(serializer.is_valid())
    self.assertIn('text', serializer.errors)

    # Whitespace only
    serializer = ExtractionNoteCreateUpdateSerializer(data={'text': '   '})
    self.assertFalse(serializer.is_valid())
    self.assertIn('text', serializer.errors)

def test_create_update_serializer_strips_whitespace(self):
    """Test that serializer strips leading/trailing whitespace"""
    serializer = ExtractionNoteCreateUpdateSerializer(data={'text': '  Note with spaces  '})
    self.assertTrue(serializer.is_valid())
    self.assertEqual(serializer.validated_data['text'], 'Note with spaces')
```

**Step 6: Run tests to verify they pass**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_serializers --verbosity=2`

Expected: PASS

**Step 7: Commit**

```bash
git add apps/deliverables/serializers/extraction_note.py apps/deliverables/tests/test_extraction_note_serializers.py
git commit -m "feat: add ExtractionNote serializers with validation"
```

---

## Phase 3: ViewSet & Permissions

### Task 4: Create ExtractionNote ViewSet

**Files:**
- Create: `apps/deliverables/views/extraction_note_views.py`
- Create: `apps/deliverables/tests/test_extraction_note_viewset.py`

**Step 1: Write failing test for note creation endpoint**

```python
# apps/deliverables/tests/test_extraction_note_viewset.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.deliverables.models import ExtractedData, ExtractionNote, Project, ProjectVersion, ExtractionSource
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class TestExtractionNoteViewSet(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('test@example.com', password='testpass123')
        self.other_user = User.objects.create_user('other@example.com', password='testpass123')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(name="Test Project", team=self.team, created_by=self.user)
        self.version = self.project.versions.first()

        # Add user to project
        from apps.deliverables.models import ProjectMembership, ROLE_PROJECT_MEMBER
        ProjectMembership.objects.create(project=self.project, user=self.user, role=ROLE_PROJECT_MEMBER)

        self.extracted_data = ExtractedData.objects.create(
            project=self.project,
            project_version=self.version,
            spec_section_number="01 1000",
            spec_section_name="General Requirements",
            extraction_type="custom_highlights",
            requirement_text="Test requirement",
            source=ExtractionSource.HUMAN,
            created_by=self.user
        )

        self.client.force_authenticate(user=self.user)

    def test_create_note(self):
        """Test creating a note on an ExtractedData"""
        url = reverse('extractionnote-list', kwargs={
            'project_pk': self.project.id,
            'extracteddata_pk': self.extracted_data.id
        })
        data = {'text': 'This is a new note'}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ExtractionNote.objects.count(), 1)
        note = ExtractionNote.objects.first()
        self.assertEqual(note.text, 'This is a new note')
        self.assertEqual(note.created_by, self.user)
        self.assertEqual(note.extracted_data, self.extracted_data)
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_viewset::TestExtractionNoteViewSet::test_create_note --verbosity=2`

Expected: FAIL (either ImportError or 404/endpoint not found)

**Step 3: Add dedicated permission class**

Add to `apps/deliverables/permissions.py` (near `ProjectAccessPermissions`):

```python
class ExtractionNoteAccessPermissions(permissions.BasePermission):
    """
    Ensure only project members can access notes and that only the author (or notes without an author)
    can be modified.
    """

    def _get_project_id(self, view):
        project_pk = view.kwargs.get('project_pk')
        if project_pk:
            return project_pk
        extracted_data = getattr(view, 'kwargs', {}).get('extracteddata_pk')
        if extracted_data:
            from apps.deliverables.models import ExtractedData
            try:
                return ExtractedData.objects.only('project_id').get(id=extracted_data).project_id
            except ExtractedData.DoesNotExist:
                return None
        return None

    def has_permission(self, request, view):
        project_id = self._get_project_id(view)
        return (
            request.user.is_authenticated
            and project_id is not None
            and request.user.is_member_of_project(project_id)
        )

    def has_object_permission(self, request, view, obj):
        project = obj.extracted_data.project
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_member_of_project(project)
        return obj.created_by is None or obj.created_by_id == request.user.id
```

**Step 4: Create viewset**

```python
# apps/deliverables/views/extraction_note_views.py
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from apps.deliverables.models import ExtractionNote, ExtractedData
from apps.deliverables.serializers.extraction_note import (
    ExtractionNoteSerializer,
    ExtractionNoteCreateUpdateSerializer
)
from apps.deliverables.permissions import ExtractionNoteAccessPermissions


class ExtractionNoteViewSet(viewsets.ModelViewSet):
    """ViewSet for ExtractionNote CRUD operations"""
    permission_classes = [IsAuthenticated, ExtractionNoteAccessPermissions]

    def get_queryset(self):
        """Filter by extracted_data and project, optimize queries"""
        project_id = self.kwargs.get('project_pk')
        extracted_data_id = self.kwargs.get('extracteddata_pk')

        return ExtractionNote.objects.filter(
            extracted_data_id=extracted_data_id,
            extracted_data__project_id=project_id
        ).select_related('created_by', 'extracted_data').order_by('created_at')

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ExtractionNoteCreateUpdateSerializer
        return ExtractionNoteSerializer

    def perform_create(self, serializer):
        """Set created_by and extracted_data from context"""
        project_id = self.kwargs.get('project_pk')
        extracted_data_id = self.kwargs.get('extracteddata_pk')

        # Verify ExtractedData exists and belongs to project
        extracted_data = get_object_or_404(
            ExtractedData,
            id=extracted_data_id,
            project_id=project_id
        )

        serializer.save(
            created_by=self.request.user,
            extracted_data=extracted_data
        )

    def check_object_permissions(self, request, obj):
        """Only note author can edit/delete"""
        super().check_object_permissions(request, obj)

        if self.action in ['update', 'partial_update', 'destroy']:
            if obj.created_by and obj.created_by != request.user:
                raise PermissionDenied("You can only modify notes you created.")
```

**Step 5: Update URLs**

Modify `apps/deliverables/urls.py` to add nested router. Find where `single_project_router` is defined and add after the extracted-data registration:

```python
# Add import at top
from rest_framework_nested import routers
from apps.deliverables.views import extraction_note_views

# After single_project_router.register for extracted-data (around line 76)
extraction_note_router = routers.NestedDefaultRouter(
    single_project_router, 'extracted-data', lookup='extracteddata'
)
extraction_note_router.register(
    r'notes',
    extraction_note_views.ExtractionNoteViewSet,
    basename='extractionnote'
)

# At the end of urlpatterns (around line 141), add:
urlpatterns += extraction_note_router.urls
```

**Step 6: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_viewset::TestExtractionNoteViewSet::test_create_note --verbosity=2`

Expected: PASS

**Step 7: Commit**

```bash
git add apps/deliverables/views/extraction_note_views.py apps/deliverables/urls.py apps/deliverables/tests/test_extraction_note_viewset.py
git commit -m "feat: add ExtractionNote viewset with create endpoint"
```

---

### Task 5: Add ViewSet Permission Tests

**Files:**
- Modify: `apps/deliverables/tests/test_extraction_note_viewset.py`

**Step 1: Write test for list notes**

Add to `TestExtractionNoteViewSet`:

```python
def test_list_notes(self):
    """Test listing all notes for an ExtractedData"""
    ExtractionNote.objects.create(
        extracted_data=self.extracted_data,
        text="First note",
        created_by=self.user
    )
    ExtractionNote.objects.create(
        extracted_data=self.extracted_data,
        text="Second note",
        created_by=self.user
    )

    url = reverse('extractionnote-list', kwargs={
        'project_pk': self.project.id,
        'extracteddata_pk': self.extracted_data.id
    })

    response = self.client.get(url)

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(len(response.data), 2)
    self.assertEqual(response.data[0]['text'], 'First note')
    self.assertEqual(response.data[1]['text'], 'Second note')
```

**Step 2: Run test**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_viewset::TestExtractionNoteViewSet::test_list_notes --verbosity=2`

Expected: PASS

**Step 3: Write test for list notes as non-member**

Add to `TestExtractionNoteViewSet`:

```python
def test_list_notes_for_non_member(self):
    """Non-project members should not see notes"""
    url = reverse('extractionnote-list', kwargs={
        'project_pk': self.project.id,
        'extracteddata_pk': self.extracted_data.id
    })

    self.client.force_authenticate(user=self.other_user)
    response = self.client.get(url)

    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
```

**Step 4: Run test**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_viewset::TestExtractionNoteViewSet::test_list_notes_for_non_member --verbosity=2`

Expected: PASS

**Step 5: Write test for create note as non-member**

Add to `TestExtractionNoteViewSet`:

```python
def test_create_note_as_non_member(self):
    """Non-project members cannot create notes"""
    url = reverse('extractionnote-list', kwargs={
        'project_pk': self.project.id,
        'extracteddata_pk': self.extracted_data.id
    })

    self.client.force_authenticate(user=self.other_user)
    response = self.client.post(url, {'text': 'Nope'}, format='json')

    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    self.assertEqual(ExtractionNote.objects.count(), 0)
```

**Step 6: Run test**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_viewset::TestExtractionNoteViewSet::test_create_note_as_non_member --verbosity=2`

Expected: PASS

**Step 7: Write test for update note (author)**

Add to `TestExtractionNoteViewSet`:

```python
def test_update_note_as_author(self):
    """Test that author can update their note"""
    note = ExtractionNote.objects.create(
        extracted_data=self.extracted_data,
        text="Original text",
        created_by=self.user
    )

    url = reverse('extractionnote-detail', kwargs={
        'project_pk': self.project.id,
        'extracteddata_pk': self.extracted_data.id,
        'pk': note.id
    })
    data = {'text': 'Updated text'}

    response = self.client.patch(url, data, format='json')

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    note.refresh_from_db()
    self.assertEqual(note.text, 'Updated text')
```

**Step 8: Run test**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_viewset::TestExtractionNoteViewSet::test_update_note_as_author --verbosity=2`

Expected: PASS

**Step 9: Write test for update note (non-author)**

Add to `TestExtractionNoteViewSet`:

```python
def test_update_note_as_non_author(self):
    """Test that non-author cannot update a note"""
    note = ExtractionNote.objects.create(
        extracted_data=self.extracted_data,
        text="Original text",
        created_by=self.user
    )

    # Add other_user to project
    from apps.deliverables.models import ProjectMembership, ROLE_PROJECT_MEMBER
    ProjectMembership.objects.create(project=self.project, user=self.other_user, role=ROLE_PROJECT_MEMBER)

    # Switch to other user
    self.client.force_authenticate(user=self.other_user)

    url = reverse('extractionnote-detail', kwargs={
        'project_pk': self.project.id,
        'extracteddata_pk': self.extracted_data.id,
        'pk': note.id
    })
    data = {'text': 'Attempted update'}

    response = self.client.patch(url, data, format='json')

    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    note.refresh_from_db()
    self.assertEqual(note.text, 'Original text')  # Unchanged
```

**Step 10: Run test**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_viewset::TestExtractionNoteViewSet::test_update_note_as_non_author --verbosity=2`

Expected: PASS

**Step 11: Write test for delete note (author)**

Add to `TestExtractionNoteViewSet`:

```python
def test_delete_note_as_author(self):
    """Test that author can delete their note"""
    note = ExtractionNote.objects.create(
        extracted_data=self.extracted_data,
        text="To be deleted",
        created_by=self.user
    )
    note_id = note.id

    url = reverse('extractionnote-detail', kwargs={
        'project_pk': self.project.id,
        'extracteddata_pk': self.extracted_data.id,
        'pk': note.id
    })

    response = self.client.delete(url)

    self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
    self.assertFalse(ExtractionNote.objects.filter(id=note_id).exists())
```

**Step 12: Run test**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_viewset::TestExtractionNoteViewSet::test_delete_note_as_author --verbosity=2`

Expected: PASS

**Step 13: Write test for delete note (non-author)**

Add to `TestExtractionNoteViewSet`:

```python
def test_delete_note_as_non_author(self):
    """Test that non-author cannot delete a note"""
    note = ExtractionNote.objects.create(
        extracted_data=self.extracted_data,
        text="Cannot delete",
        created_by=self.user
    )

    # Add other_user to project
    from apps.deliverables.models import ProjectMembership, ROLE_PROJECT_MEMBER
    ProjectMembership.objects.create(project=self.project, user=self.other_user, role=ROLE_PROJECT_MEMBER)

    # Switch to other user
    self.client.force_authenticate(user=self.other_user)

    url = reverse('extractionnote-detail', kwargs={
        'project_pk': self.project.id,
        'extracteddata_pk': self.extracted_data.id,
        'pk': note.id
    })

    response = self.client.delete(url)

    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    self.assertTrue(ExtractionNote.objects.filter(id=note.id).exists())
```

**Step 14: Run test**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_viewset::TestExtractionNoteViewSet::test_delete_note_as_non_author --verbosity=2`

Expected: PASS

**Step 15: Write test for unauthenticated access**

Add to `TestExtractionNoteViewSet`:

```python
def test_unauthenticated_access_denied(self):
    """Test that unauthenticated users cannot access notes"""
    self.client.force_authenticate(user=None)

    url = reverse('extractionnote-list', kwargs={
        'project_pk': self.project.id,
        'extracteddata_pk': self.extracted_data.id
    })

    response = self.client.get(url)
    self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
```

**Step 16: Run test**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_viewset::TestExtractionNoteViewSet::test_unauthenticated_access_denied --verbosity=2`

Expected: PASS

**Step 17: Run all viewset tests**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_viewset --verbosity=2`

Expected: All tests PASS

**Step 18: Commit**

```bash
git add apps/deliverables/tests/test_extraction_note_viewset.py
git commit -m "test: add comprehensive permission tests for ExtractionNote viewset"
```

---

## Phase 4: Inline Notes in ExtractedData

### Task 6: Update ExtractedData Serializers

**Files:**
- Modify: `apps/deliverables/serializers/extracted_data.py`
- Modify: `apps/deliverables/tests/test_extraction_note_serializers.py`

**Step 1: Write test for notes in ExtractedData serializer**

Add to `apps/deliverables/tests/test_extraction_note_serializers.py`:

```python
class TestExtractedDataWithNotes(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('test@example.com', first_name='Test', last_name='User')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(name="Test Project", team=self.team, created_by=self.user)
        self.version = self.project.versions.first()
        self.extracted_data = ExtractedData.objects.create(
            project=self.project,
            project_version=self.version,
            spec_section_number="01 1000",
            spec_section_name="General Requirements",
            extraction_type="custom_highlights",
            requirement_text="Test requirement",
            source=ExtractionSource.HUMAN,
            created_by=self.user
        )

    def test_extracted_data_includes_notes(self):
        """Test that ExtractedData serializer includes notes"""
        from apps.deliverables.serializers.extracted_data import ExtractedDataSerializer

        # Create notes
        ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="First note",
            created_by=self.user
        )
        ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="Second note",
            created_by=self.user
        )

        serializer = ExtractedDataSerializer(self.extracted_data)
        data = serializer.data

        self.assertIn('notes', data)
        self.assertEqual(len(data['notes']), 2)
        self.assertEqual(data['notes'][0]['text'], 'First note')
        self.assertEqual(data['notes'][1]['text'], 'Second note')

    def test_extracted_data_with_no_notes(self):
        """Test ExtractedData with no notes returns empty array"""
        from apps.deliverables.serializers.extracted_data import ExtractedDataSerializer

        serializer = ExtractedDataSerializer(self.extracted_data)
        data = serializer.data

        self.assertIn('notes', data)
        self.assertEqual(len(data['notes']), 0)
        self.assertEqual(data['notes'], [])

    def test_extracted_data_list_serializer_includes_notes(self):
        """Test that list serializer also includes notes"""
        from apps.deliverables.serializers.extracted_data import ExtractedDataListSerializer

        ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="Note in list",
            created_by=self.user
        )

        serializer = ExtractedDataListSerializer(self.extracted_data)
        data = serializer.data

        self.assertIn('notes', data)
        self.assertEqual(len(data['notes']), 1)
        self.assertEqual(data['notes'][0]['text'], 'Note in list')
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_serializers::TestExtractedDataWithNotes --verbosity=2`

Expected: FAIL (notes field not present or KeyError)

**Step 3: Update ExtractedData serializers**

In `apps/deliverables/serializers/extracted_data.py`, add import at top:

```python
from apps.deliverables.serializers.extraction_note import ExtractionNoteSerializer
```

Update `ExtractedDataListSerializer`:

```python
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
    custom_item_type = serializers.SerializerMethodField()
    notes = ExtractionNoteSerializer(many=True, read_only=True)  # NEW

    class Meta:
        model = ExtractedData
        fields = [
            'id', 'spec_section_number', 'spec_section_name',
            'extraction_type', 'item_type', 'requirement_text',
            'responsible_party', 'metadata', 'custom_item_type',
            'source', 'source_display', 'created_by_name', 'created_at',
            'notes'  # NEW
        ]
        read_only_fields = fields
```

Update `ExtractedDataSerializer`:

```python
class ExtractedDataSerializer(serializers.ModelSerializer):
    """Full serializer for detail views and updates"""
    created_by = CustomUserSerializer(read_only=True)
    source_display = serializers.CharField(
        source='get_source_display',
        read_only=True
    )
    custom_item_type = serializers.SerializerMethodField()
    custom_item_type_id = serializers.PrimaryKeyRelatedField(
        source='custom_item_type',
        queryset=CustomItemType.objects.filter(is_active=True),
        write_only=True,
        required=False,
        allow_null=True,
    )
    notes = ExtractionNoteSerializer(many=True, read_only=True)  # NEW

    class Meta:
        model = ExtractedData
        fields = [
            'id', 'ai_generated_log', 'spec_section_number',
            'spec_section_name', 'extraction_type', 'item_type',
            'requirement_text', 'responsible_party', 'metadata',
            'pdf_locations', 'paragraph_number',
            'custom_item_type', 'custom_item_type_id',
            'source', 'source_display', 'created_by',
            'created_at', 'updated_at',
            'notes'  # NEW
        ]
        read_only_fields = [
            'id', 'ai_generated_log', 'spec_section_number',
            'spec_section_name', 'extraction_type', 'item_type',
            'requirement_text', 'responsible_party', 'metadata',
            'pdf_locations', 'paragraph_number',
            'custom_item_type',
            'source', 'created_by', 'created_at', 'updated_at',
            'notes'  # NEW
        ]
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_serializers::TestExtractedDataWithNotes --verbosity=2`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/serializers/extracted_data.py apps/deliverables/tests/test_extraction_note_serializers.py
git commit -m "feat: add inline notes to ExtractedData serializers"
```

---

### Task 7: Optimize ExtractedData Queries

**Files:**
- Modify: `apps/deliverables/views/extracted_data_views.py`
- Create: `apps/deliverables/tests/test_extraction_note_performance.py`

**Step 1: Write test for N+1 query prevention**

```python
# apps/deliverables/tests/test_extraction_note_performance.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.test.utils import CaptureQueriesContext
from django.db import connection
from apps.deliverables.models import (
    ExtractedData,
    ExtractionNote,
    Project,
    ExtractionSource,
    ProjectMembership,
    ROLE_PROJECT_MEMBER,
)
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class TestExtractionNotePerformance(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('test@example.com')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(name="Test Project", team=self.team, created_by=self.user)
        self.version = self.project.versions.first()
        ProjectMembership.objects.create(project=self.project, user=self.user, role=ROLE_PROJECT_MEMBER)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_no_n_plus_1_queries_with_notes(self):
        """Test that fetching multiple ExtractedData with notes doesn't cause N+1 queries"""
        # Create 5 ExtractedData items with notes
        for i in range(5):
            extracted = ExtractedData.objects.create(
                project=self.project,
                project_version=self.version,
                spec_section_number=f"0{i} 1000",
                spec_section_name=f"Section {i}",
                extraction_type="custom_highlights",
                requirement_text=f"Requirement {i}",
                source=ExtractionSource.HUMAN,
                created_by=self.user
            )
            # Add 3 notes to each
            for j in range(3):
                ExtractionNote.objects.create(
                    extracted_data=extracted,
                    text=f"Note {j} for item {i}",
                    created_by=self.user
                )

        list_url = reverse('extracted-data-list', kwargs={'project_pk': self.project.id})

        with CaptureQueriesContext(connection) as context:
            response = self.client.get(list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(len(payload), 5)
        for item in payload:
            self.assertIn('notes', item)

        # Should be approximately 3 queries:
        # 1. ExtractedData select
        # 2. Prefetch notes
        # 3. Prefetch note creators
        # Allow some tolerance for database setup queries
        self.assertLess(len(context.captured_queries), 8,
            f"Too many queries: {len(context.captured_queries)}. Possible N+1 issue.")
```

**Step 2: Run test to verify current state**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_performance --verbosity=2`

Expected: May PASS or FAIL depending on whether prefetch is already in place

**Step 3: Update ExtractedDataViewSet for prefetching**

In `apps/deliverables/views/extracted_data_views.py`, update the `get_queryset` method:

```python
def get_queryset(self):
    """Filter by project and optimize queries"""
    project_id = self.kwargs.get('project_pk')
    queryset = ExtractedData.objects.filter(project_id=project_id)

    # Optimize based on action
    if self.action == 'list':
        queryset = queryset.select_related('created_by', 'ai_generated_log')
        queryset = queryset.prefetch_related('notes__created_by')  # NEW
    elif self.action in ['retrieve', 'update', 'partial_update']:
        queryset = queryset.select_related(
            'created_by', 'ai_generated_log',
            'project', 'project_version', 'spec_section'
        )
        queryset = queryset.prefetch_related('notes__created_by')  # NEW

    return queryset
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_performance --verbosity=2`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/views/extracted_data_views.py apps/deliverables/tests/test_extraction_note_performance.py
git commit -m "perf: add prefetch_related for notes to prevent N+1 queries"
```

---

## Phase 5: Admin Interface

### Task 8: Create Admin Interface

**Files:**
- Modify: `apps/deliverables/admin.py`
- Create: `apps/deliverables/tests/test_extraction_note_admin.py`

**Step 1: Write test for admin registration**

```python
# apps/deliverables/tests/test_extraction_note_admin.py
from django.test import TestCase
from django.contrib.admin.sites import site
from apps.deliverables.models import ExtractionNote
from apps.deliverables.admin import ExtractionNoteAdmin


class TestExtractionNoteAdmin(TestCase):
    def test_admin_registered(self):
        """Test ExtractionNote is registered in admin"""
        self.assertIn(ExtractionNote, site._registry)
        self.assertIsInstance(site._registry[ExtractionNote], ExtractionNoteAdmin)

    def test_admin_list_display(self):
        """Test admin list display fields"""
        admin = ExtractionNoteAdmin(ExtractionNote, site)
        expected = ['id', 'extracted_data', 'text_preview', 'created_by', 'created_at']
        self.assertEqual(list(admin.list_display), expected)

    def test_admin_list_filter(self):
        """Test admin filter options"""
        admin = ExtractionNoteAdmin(ExtractionNote, site)
        self.assertIn('created_at', admin.list_filter)

    def test_admin_search_fields(self):
        """Test admin search fields"""
        admin = ExtractionNoteAdmin(ExtractionNote, site)
        self.assertIn('text', admin.search_fields)
        self.assertIn('created_by__email', admin.search_fields)
        self.assertIn('extracted_data__spec_section_number', admin.search_fields)
```

**Step 2: Run test to verify it fails**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_admin --verbosity=2`

Expected: FAIL with "ImportError: cannot import name 'ExtractionNoteAdmin'"

**Step 3: Add admin class**

In `apps/deliverables/admin.py`, add after the CustomItemType admin (search for `@admin.register(CustomItemType)` and add after that class):

```python
@admin.register(ExtractionNote)
class ExtractionNoteAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'extracted_data', 'text_preview', 'created_by', 'created_at'
    ]
    list_filter = [
        'created_at',
        ('extracted_data__project', admin.RelatedOnlyFieldListFilter)
    ]
    search_fields = [
        'text', 'created_by__email', 'extracted_data__spec_section_number'
    ]
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['extracted_data', 'created_by']

    fieldsets = (
        ('Note Information', {
            'fields': ('extracted_data', 'text', 'created_by')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def text_preview(self, obj):
        """Show truncated text in list view"""
        return obj.text[:75] + '...' if len(obj.text) > 75 else obj.text
    text_preview.short_description = 'Text'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'extracted_data', 'created_by'
        )
```

Add import at top of file if not already present:

```python
from apps.deliverables.models import ExtractionNote
```

**Step 4: Run test to verify it passes**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_admin --verbosity=2`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/deliverables/admin.py apps/deliverables/tests/test_extraction_note_admin.py
git commit -m "feat: add ExtractionNote admin interface with optimized queries"
```

---

## Phase 6: Database Migration

### Task 9: Create and Run Migration

**Files:**
- Create: `apps/deliverables/migrations/00XX_add_extraction_note.py`

**Step 1: Create migration**

Run: `docker-compose exec web python manage.py makemigrations deliverables --name add_extraction_note`

Expected: Migration file created

**Step 2: Review migration file**

Run: `cat apps/deliverables/migrations/00XX_add_extraction_note.py` (use actual migration number)

Expected: Should show CreateModel for ExtractionNote with indexes

**Step 3: Run migration**

Run: `docker-compose exec web python manage.py migrate deliverables`

Expected: Migration applies successfully

**Step 4: Verify model in database**

Run: `docker-compose exec web python manage.py shell -c "from apps.deliverables.models import ExtractionNote; print(f'ExtractionNote table exists: {ExtractionNote.objects.model._meta.db_table}')"`

Expected: Prints table name without error

**Step 5: Commit**

```bash
git add apps/deliverables/migrations/
git commit -m "feat: add database migration for ExtractionNote model"
```

---

## Phase 7: Integration Testing

### Task 10: End-to-End Integration Test

**Files:**
- Create: `apps/deliverables/tests/test_extraction_note_integration.py`

**Step 1: Write integration test**

```python
# apps/deliverables/tests/test_extraction_note_integration.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.deliverables.models import (
    ExtractedData, ExtractionNote, Project, ProjectVersion,
    ExtractionSource, ProjectMembership, ROLE_PROJECT_MEMBER
)
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class TestExtractionNoteIntegration(TestCase):
    """End-to-end integration tests for the complete notes workflow"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('test@example.com', password='testpass123', first_name='Test', last_name='User')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(name="Test Project", team=self.team, created_by=self.user)
        self.version = self.project.versions.first()

        ProjectMembership.objects.create(project=self.project, user=self.user, role=ROLE_PROJECT_MEMBER)

        self.extracted_data = ExtractedData.objects.create(
            project=self.project,
            project_version=self.version,
            spec_section_number="01 1000",
            spec_section_name="General Requirements",
            extraction_type="custom_highlights",
            requirement_text="Test requirement",
            source=ExtractionSource.HUMAN,
            created_by=self.user
        )

        self.client.force_authenticate(user=self.user)

    def test_complete_note_workflow(self):
        """Test complete workflow: create extracted data, add notes, fetch with notes, update, delete"""

        # Step 1: Create first note
        create_url = reverse('extractionnote-list', kwargs={
            'project_pk': self.project.id,
            'extracteddata_pk': self.extracted_data.id
        })
        response = self.client.post(create_url, {'text': 'First note'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        first_note_id = response.data['id']

        # Step 2: Create second note
        response = self.client.post(create_url, {'text': 'Second note'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        second_note_id = response.data['id']

        # Step 3: Fetch ExtractedData and verify notes are inline
        extracted_data_url = reverse('extracted-data-detail', kwargs={
            'project_pk': self.project.id,
            'pk': self.extracted_data.id
        })
        response = self.client.get(extracted_data_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('notes', response.data)
        self.assertEqual(len(response.data['notes']), 2)
        self.assertEqual(response.data['notes'][0]['text'], 'First note')
        self.assertEqual(response.data['notes'][1]['text'], 'Second note')

        # Step 4: Update first note
        update_url = reverse('extractionnote-detail', kwargs={
            'project_pk': self.project.id,
            'extracteddata_pk': self.extracted_data.id,
            'pk': first_note_id
        })
        response = self.client.patch(update_url, {'text': 'Updated first note'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Step 5: Verify update
        response = self.client.get(extracted_data_url)
        self.assertEqual(response.data['notes'][0]['text'], 'Updated first note')

        # Step 6: Delete second note
        delete_url = reverse('extractionnote-detail', kwargs={
            'project_pk': self.project.id,
            'extracteddata_pk': self.extracted_data.id,
            'pk': second_note_id
        })
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Step 7: Verify deletion
        response = self.client.get(extracted_data_url)
        self.assertEqual(len(response.data['notes']), 1)
        self.assertEqual(response.data['notes'][0]['text'], 'Updated first note')

    def test_notes_included_in_list_view(self):
        """Test that notes are included when fetching list of ExtractedData"""
        # Create multiple ExtractedData with notes
        for i in range(3):
            extracted = ExtractedData.objects.create(
                project=self.project,
                project_version=self.version,
                spec_section_number=f"0{i} 1000",
                spec_section_name=f"Section {i}",
                extraction_type="custom_highlights",
                requirement_text=f"Requirement {i}",
                source=ExtractionSource.HUMAN,
                created_by=self.user
            )
            ExtractionNote.objects.create(
                extracted_data=extracted,
                text=f"Note for item {i}",
                created_by=self.user
            )

        # Fetch list
        list_url = reverse('extracted-data-list', kwargs={'project_pk': self.project.id})
        response = self.client.get(list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should have 4 items total (setUp + 3 new)
        self.assertEqual(len(response.data), 4)

        # Verify all have notes field
        for item in response.data:
            self.assertIn('notes', item)
```

**Step 2: Run integration test**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note_integration --verbosity=2`

Expected: PASS

**Step 3: Commit**

```bash
git add apps/deliverables/tests/test_extraction_note_integration.py
git commit -m "test: add end-to-end integration tests for notes workflow"
```

---

## Phase 8: Final Verification

### Task 11: Run Full Test Suite

**Step 1: Run all extraction note tests**

Run: `docker-compose exec web python manage.py test apps.deliverables.tests.test_extraction_note --verbosity=2`

Expected: All tests PASS

**Step 2: Run all deliverables tests to ensure no regressions**

Run: `docker-compose exec web python manage.py test apps.deliverables --verbosity=2`

Expected: All tests PASS (may take a while)

**Step 3: Check for any migrations needed**

Run: `docker-compose exec web python manage.py makemigrations --dry-run`

Expected: "No changes detected"

**Step 4: Verify admin interface manually (optional)**

1. Start server: `docker-compose up`
2. Navigate to `/admin/deliverables/extractionnote/`
3. Verify list display, filters, and search work
4. Create a test note through admin
5. Verify it appears in API

**Step 5: Final commit if any cleanup needed**

```bash
git add .
git commit -m "chore: final cleanup for extraction notes feature"
```

---

## Implementation Complete!

**Verification Checklist:**

- ✅ ExtractionNote model created with proper relationships
- ✅ CASCADE delete on ExtractedData
- ✅ SET_NULL on user deletion
- ✅ Notes ordered by created_at
- ✅ Serializers with validation
- ✅ ViewSet with CRUD operations
- ✅ Author-only edit/delete permissions
- ✅ Notes inline in ExtractedData responses
- ✅ Prefetch optimization to prevent N+1
- ✅ Admin interface
- ✅ Database migration
- ✅ Comprehensive test coverage

**API Summary:**

```
# Create note
POST /api/deliverables/projects/{project_id}/extracted-data/{extracted_data_id}/notes/
Body: {"text": "Note content"}

# List notes
GET /api/deliverables/projects/{project_id}/extracted-data/{extracted_data_id}/notes/

# Update note (author only)
PATCH /api/deliverables/projects/{project_id}/extracted-data/{extracted_data_id}/notes/{note_id}/
Body: {"text": "Updated content"}

# Delete note (author only)
DELETE /api/deliverables/projects/{project_id}/extracted-data/{extracted_data_id}/notes/{note_id}/

# Fetch ExtractedData with inline notes
GET /api/deliverables/projects/{project_id}/extracted-data/{extracted_data_id}/
# Response includes "notes": [...] array
```

**Next Steps:**

- Frontend can now integrate notes using these endpoints
- Notes automatically appear in ExtractedData responses
- Position data inherited from `pdf_locations` field
- Frontend can render using any Apryse annotation type
