# Extraction Notes API Modification

## Overview

This document describes a required modification to the ExtractedData creation endpoint to support creating an initial note during highlight creation.

## Background

The frontend needs to support creating a highlight with an optional note in a single user action. To provide the best UX (atomic operation, single API call, no race conditions), we need the backend to accept an optional `note_text` field during ExtractedData creation.

## Required Changes

### Endpoint

**`POST /api/deliverables/projects/{project_id}/extracted-data/`**

### Request Body Modification

Add an optional `note_text` field to the existing request payload:

```json
{
  "project": 123,
  "project_version": 456,
  "spec_section": 789,
  "spec_section_number": "01 1000",
  "spec_section_name": "General Requirements",
  "extraction_type": "custom_highlights",
  "item_type": "custom_77",
  "requirement_text": "All materials shall be tested...",
  "pdf_locations": [
    {
      "page_no": 5,
      "x": 100,
      "y": 200,
      "width": 300,
      "height": 20
    }
  ],
  "custom_item_type_id": 77,
  "note_text": "This requirement applies to phase 2 only"  // NEW OPTIONAL FIELD
}
```

**Field Specification:**
- **Field name:** `note_text`
- **Type:** String
- **Required:** No (optional)
- **Validation:**
  - If provided and non-empty (after trimming whitespace), create an ExtractionNote
  - If null, empty string, or only whitespace, do not create a note
  - Should apply the same validation as the ExtractionNote serializer (text cannot be empty)

### Backend Implementation

**Locations:**
- `apps/deliverables/serializers/extracted_data.py`
- `apps/deliverables/views/extracted_data_views.py`

**Serializer Updates (`ExtractedDataCreateSerializer`):**

```python
class ExtractedDataCreateSerializer(serializers.ModelSerializer):
    note_text = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True
    )
    # ... existing fields ...

    def validate_note_text(self, value):
        trimmed = value.strip()
        if value and not trimmed:
            raise serializers.ValidationError('Text cannot be empty.')
        return trimmed

    def create(self, validated_data):
        note_text = validated_data.pop('note_text', None)
        request = self.context.get('request')
        user = request.user if request and request.user.is_authenticated else None
        if user:
            validated_data['created_by'] = user
        validated_data['source'] = ExtractionSource.HUMAN

        with transaction.atomic():
            extracted_data = super().create(validated_data)
            if note_text and user:
                ExtractionNote.objects.create(
                    extracted_data=extracted_data,
                    text=note_text,
                    created_by=user
                )
        return extracted_data
```

> Note: add the necessary imports (`from django.db import transaction` and `from apps.deliverables.models import ExtractionNote`) at the top of the serializer module.

**View Updates:**

```python
def perform_create(self, serializer):
    serializer.save()
```

**Important Notes:**
1. Serializer-level `transaction.atomic()` ensures a single database transaction for ExtractedData and initial note creation
2. If note creation fails, the entire operation will rollback (ExtractedData not created)
3. The response should include the note in the `notes` array (this already happens automatically since ExtractedDataSerializer includes the `notes` field)

### Response Body

The response should include the newly created note in the `notes` array:

```json
{
  "id": 999,
  "spec_section_number": "01 1000",
  "spec_section_name": "General Requirements",
  "extraction_type": "custom_highlights",
  "item_type": "custom_77",
  "requirement_text": "All materials shall be tested...",
  "pdf_locations": [...],
  "notes": [
    {
      "id": 1,
      "text": "This requirement applies to phase 2 only",
      "created_by_id": 123,
      "created_by_name": "John Doe",
      "created_at": "2025-01-15T10:30:00Z",
      "updated_at": "2025-01-15T10:30:00Z"
    }
  ],
  // ... other fields
}
```

**If no note was provided:**
```json
{
  "id": 999,
  "notes": [],
  // ... other fields
}
```

## Error Handling

### Validation Errors

If `note_text` is provided but fails validation (e.g., empty after trimming):

**Status Code:** `400 Bad Request`

**Response:**
```json
{
  "note_text": ["Text cannot be empty."]
}
```

### General Errors

Any errors during note creation should rollback the ExtractedData creation and return appropriate error response.

## Testing Requirements

### Test Cases to Add

1. **Create ExtractedData without note** (existing behavior)
   - `note_text` not provided → ExtractedData created, `notes` array is empty

2. **Create ExtractedData with valid note**
   - `note_text` provided with valid text → ExtractedData and ExtractionNote both created
   - Response includes note in `notes` array

3. **Create ExtractedData with empty note_text**
   - `note_text` is empty string or whitespace → ExtractedData created, no note created, `notes` array is empty

4. **Create ExtractedData with invalid note**
   - Verify validation errors are returned
   - Verify ExtractedData is NOT created (transaction rollback)

5. **Permission checks**
   - Only project members can create ExtractedData with notes
   - `created_by` is correctly set to the requesting user

### Test File Location

Add tests to existing test file or create new test class:
- `apps/deliverables/tests/test_extracted_data_viewset.py`

### Example Test

```python
def test_create_extracted_data_with_note(self):
    """Test creating ExtractedData with initial note"""
    url = reverse('extracted-data-list', kwargs={'project_pk': self.project.id})
    data = {
        'spec_section': self.section.id,
        'spec_section_number': '01 1000',
        'spec_section_name': 'General Requirements',
        'extraction_type': 'custom_highlights',
        'item_type': 'custom_77',
        'requirement_text': 'Test requirement',
        'pdf_locations': [{'page_no': 1, 'x': 100, 'y': 200, 'width': 300, 'height': 20}],
        'custom_item_type_id': self.custom_type.id,
        'note_text': 'Initial note text'
    }

    response = self.client.post(url, data, format='json')

    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    self.assertEqual(ExtractedData.objects.count(), 1)
    self.assertEqual(ExtractionNote.objects.count(), 1)

    # Verify note is included in response
    self.assertIn('notes', response.data)
    self.assertEqual(len(response.data['notes']), 1)
    self.assertEqual(response.data['notes'][0]['text'], 'Initial note text')
    self.assertEqual(response.data['notes'][0]['created_by_id'], self.user.id)
```

## Rationale

### Why This Approach?

1. **Atomic Operation:** User intent is to create "highlight with note" as a single action
2. **Better UX:** Single API call, faster response, no race conditions
3. **Simpler Error Handling:** Either both succeed or both fail (transaction rollback)
4. **Performance:** One round-trip instead of two
5. **Consistency:** Response format remains the same (notes always included in ExtractedData)

### Alternatives Considered

**Two-Request Approach:** Create ExtractedData first, then create note via `/notes/` endpoint
- **Rejected because:**
  - Two API calls = slower
  - Partial failure scenarios (highlight exists but note fails)
  - More complex frontend error handling
  - Not atomic (highlight exists briefly without note)

## Related Documentation

- [Extraction Notes Implementation Plan](../plans/extraction-notes-implementation.md)
- [Extraction Notes Frontend Design](../plans/extraction-notes-frontend-design.md)
- ExtractionNote Model: `apps/deliverables/models.py`
- ExtractionNote ViewSet: `apps/deliverables/views/extraction_note_views.py`
- ExtractionNote API Endpoints: Already implemented per extraction notes plan

## Questions?

For questions or clarifications about this API modification, please refer to the extraction notes implementation plan or consult the frontend design document.
