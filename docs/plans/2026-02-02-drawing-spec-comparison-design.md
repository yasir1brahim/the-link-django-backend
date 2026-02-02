# Drawing Spec Comparison Feature Design

## Overview

This feature enables comparison of drawing notes against project specifications to detect conflicts. When the `drawing_spec_comparison` feature flag is active, users can trigger a project-wide comparison that invokes an AWS Lambda function. The lambda analyzes notes against specs and posts results back to a webhook, where we store detected conflicts and skipped notes for retrieval via read endpoints.

## Data Flow

```
User triggers comparison
        │
        ▼
┌─────────────────────────────────┐
│  POST /projects/{id}/           │
│  trigger-spec-comparison/       │
├─────────────────────────────────┤
│ 1. Check feature flag           │
│ 2. Create SpecComparison        │
│    (status: PENDING)            │
│ 3. Gather DrawingNotes          │
│ 4. Gather SpecSections          │
│ 5. Build payload, invoke lambda │
└─────────────────────────────────┘
        │
        ▼ (async)
┌─────────────────────────────────┐
│  Lambda processes comparison    │
│  Posts result to webhook        │
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│  POST /webhooks/spec-comparison/│
├─────────────────────────────────┤
│ 1. Idempotency check (event_id) │
│ 2. Update SpecComparison status │
│ 3. Store SpecConflict records   │
│ 4. Store SkippedNote records    │
│ 5. Update summary counts        │
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│  GET /projects/{id}/            │
│  spec-conflicts/                │
├─────────────────────────────────┤
│ Returns conflicts from latest   │
│ comparison (or by comparison_id)│
└─────────────────────────────────┘
```

## Data Models

### SpecComparisonStatus (Enum)

```python
class SpecComparisonStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    SUCCESS = "SUCCESS", "Success"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS", "Partial Success"
    FAILED = "FAILED", "Failed"
```

### SkipReason (Enum)

```python
class SkipReason(models.TextChoices):
    UNKNOWN_DISCIPLINE = "unknown_discipline", "Unknown Discipline"
    SKIP_BY_POLICY = "skip_by_policy", "Skip by Policy"
    NO_MATCHING_SPECS = "no_matching_specs", "No Matching Specs"
    MALFORMED_DISCIPLINE = "malformed_discipline", "Malformed Discipline"
```

### SpecComparison

Tracks each comparison run (similar to `DrawingExtraction`).

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key (from BaseModel) |
| `project` | FK(Project) | Project being compared |
| `project_version` | FK(ProjectVersion) | Version being compared |
| `triggered_by` | FK(User) | User who initiated comparison |
| `status` | CharField | SpecComparisonStatus choices |
| `started_at` | DateTimeField | When processing began (nullable) |
| `completed_at` | DateTimeField | When processing finished (nullable) |
| `notes_processed` | IntegerField | Count of notes analyzed |
| `notes_skipped` | IntegerField | Count of notes skipped |
| `specs_processed` | IntegerField | Count of spec files processed |
| `notes_with_mismatch` | IntegerField | Notes where discipline differs from sheet |
| `error_message` | TextField | Error details on failure (nullable) |
| `event_id` | CharField | Webhook event ID for idempotency (unique, nullable) |
| `created_at` | DateTimeField | From BaseModel |
| `updated_at` | DateTimeField | From BaseModel |

### SpecConflict

Stores each detected conflict with full fidelity for future UI highlighting.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `comparison` | FK(SpecComparison) | Parent comparison run |
| `note` | FK(DrawingNote) | Link to source note (nullable) |
| `note_id_from_lambda` | CharField | Note ID as sent to/from lambda |
| `note_text` | TextField | The note text content |
| `spec_text` | TextField | Conflicting spec text |
| `spec_source_file` | CharField | S3 URI of spec PDF |
| `spec_page_number` | IntegerField | 1-indexed page number |
| `spec_masterformat_number` | CharField | MasterFormat number (e.g., "220500") |
| `confidence` | FloatField | Confidence score (0-1) |
| `reason` | TextField | Explanation of the conflict |
| `pdf_locations` | JSONField | Array of bounding boxes for highlighting |
| `created_at` | DateTimeField | From BaseModel |

**pdf_locations schema:**
```json
[
    {
        "page_no": 1,
        "x": 72.0,
        "y": 144.5,
        "width": 200.0,
        "height": 12.0
    }
]
```

### SkippedNote

Stores why notes were not analyzed.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `comparison` | FK(SpecComparison) | Parent comparison run |
| `note` | FK(DrawingNote) | Link to source note (nullable) |
| `note_id_from_lambda` | CharField | Note ID as sent to/from lambda |
| `disciplines` | JSONField | Original disciplines array from note |
| `sheet_discipline` | CharField | Sheet's discipline (nullable) |
| `reason` | CharField | SkipReason choices |
| `detail` | TextField | Additional context (nullable) |
| `created_at` | DateTimeField | From BaseModel |

## API Endpoints

### Trigger Endpoint

**`POST /api/deliverables/projects/{project_id}/trigger-spec-comparison/`**

Initiates a new spec comparison for the project.

**Authentication:** Required (IsAuthenticated + ProjectAccessPermissions)

**Feature Flag:** `drawing_spec_comparison` must be active

**Request Body:** None required (project-wide automatic)

**Response (201 Created):**
```json
{
    "id": "uuid",
    "status": "PENDING",
    "created_at": "2026-02-02T10:30:00Z",
    "triggered_by": {
        "id": "uuid",
        "display_name": "John Doe"
    }
}
```

**Error Responses:**
- `403 Forbidden` - Feature flag not active
- `400 Bad Request` - No notes or specs in project
- `404 Not Found` - Project not found

### Webhook Endpoint

**`POST /api/deliverables/webhooks/spec-comparison/`**

Receives comparison results from the lambda.

**Authentication:** AllowAny (lambda callback)

**Request Body:** (from lambda)
```json
{
    "event_id": "unique-event-id",
    "comparison_id": "uuid",
    "status": "SUCCESS",
    "conflicts": [...],
    "skipped_notes": [...],
    "notes_processed": 150,
    "notes_skipped": 12,
    "specs_processed": 8,
    "notes_with_mismatch": 5,
    "error_message": null
}
```

**Response:** `200 OK`

**Idempotency:** Duplicate `event_id` values are ignored (return 200 OK).

### Read Conflicts Endpoint

**`GET /api/deliverables/projects/{project_id}/spec-conflicts/`**

Returns conflicts from the latest comparison (or filtered by comparison_id).

**Authentication:** Required

**Query Parameters:**
- `comparison_id` (optional) - Filter to specific comparison
- `page`, `page_size` - Pagination

**Response (200 OK):**
```json
{
    "count": 42,
    "next": "...",
    "previous": null,
    "comparison": {
        "id": "uuid",
        "status": "SUCCESS",
        "completed_at": "2026-02-02T10:35:00Z"
    },
    "results": [
        {
            "id": "uuid",
            "note_id": "uuid",
            "note_text": "Provide shutoff valves at...",
            "spec_text": "Shutoff valves shall be...",
            "spec_source_file": "s3://bucket/specs/plumbing.pdf",
            "spec_file_url": "https://presigned-url...",
            "spec_page_number": 15,
            "spec_masterformat_number": "220500",
            "confidence": 0.85,
            "reason": "Note specifies ball valves but spec requires gate valves",
            "pdf_locations": [
                {"page_no": 15, "x": 72.0, "y": 144.5, "width": 200.0, "height": 12.0}
            ]
        }
    ]
}
```

### Read Skipped Notes Endpoint

**`GET /api/deliverables/projects/{project_id}/skipped-notes/`**

Returns skipped notes from the latest comparison.

**Authentication:** Required

**Query Parameters:**
- `comparison_id` (optional) - Filter to specific comparison
- `reason` (optional) - Filter by skip reason
- `page`, `page_size` - Pagination

**Response (200 OK):**
```json
{
    "count": 12,
    "results": [
        {
            "id": "uuid",
            "note_id": "uuid",
            "disciplines": ["plumbing"],
            "sheet_discipline": "mechanical",
            "reason": "no_matching_specs",
            "detail": "Division 22 has no specs uploaded"
        }
    ]
}
```

### List Comparisons Endpoint

**`GET /api/deliverables/projects/{project_id}/spec-comparisons/`**

Lists comparison runs for history/debugging.

**Authentication:** Required

**Response (200 OK):**
```json
{
    "count": 5,
    "results": [
        {
            "id": "uuid",
            "status": "SUCCESS",
            "created_at": "2026-02-02T10:30:00Z",
            "completed_at": "2026-02-02T10:35:00Z",
            "triggered_by": {"display_name": "John Doe"},
            "notes_processed": 150,
            "notes_skipped": 12,
            "specs_processed": 8,
            "conflict_count": 42
        }
    ]
}
```

## Feature Flag & Settings

### Feature Flag

- **Name:** `drawing_spec_comparison`
- **Setting:** `DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME = "drawing_spec_comparison"`
- **Helper function:**
  ```python
  def is_drawing_spec_comparison_active(user, team, project=None):
      return (
          settings.DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or
          settings.DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME in get_active_flags_for_team(team) or
          (project and settings.DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME in get_active_flags_for_project(project))
      )
  ```

### Settings

```python
# settings.py

DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME = "drawing_spec_comparison"

SPEC_COMPARISON_LAMBDA_FUNCTION_URL = env(
    "SPEC_COMPARISON_LAMBDA_FUNCTION_URL",
    default="https://lambda-url.amazonaws.com/spec-comparison"
)

BACKEND_SPEC_COMPARISON_CALLBACK_URL = BACKEND_BASE_URL + "/api/deliverables/webhooks/spec-comparison/"
```

## Lambda Payload Construction

When triggering a comparison, build the payload as follows:

```python
def build_comparison_payload(project, project_version, comparison_id):
    # Gather all notes from latest successful extractions
    drawing_notes = DrawingNote.objects.filter(
        section__page__extraction__drawing_file__project=project,
        section__page__extraction__drawing_file__project_version=project_version,
        section__page__extraction__status=DrawingExtractionStatus.SUCCESS,
    ).select_related(
        'section__page'
    )

    # Gather all spec sections
    spec_sections = SpecSection.objects.filter(
        document__project=project,
        document__project_version=project_version,
        file_s3_key__isnull=False,
    ).select_related('masterformat_section')

    payload = {
        "notes": [
            {
                "id": str(note.id),
                "text": note.text,
                "disciplines": note.disciplines,
                "sheet_discipline": note.section.page.sheet_discipline,
                "sheet_number": note.section.page.sheet_number,
                "sheet_title": note.section.page.sheet_title,
            }
            for note in drawing_notes
        ],
        "spec_files": [
            {
                "s3_uri": f"s3://{settings.S3_BUCKET}/{spec.file_s3_key}",
                "masterformat_number": spec.masterformat_section.masterformat_number,
            }
            for spec in spec_sections
        ],
        "callback_url": f"{settings.BACKEND_SPEC_COMPARISON_CALLBACK_URL}?comparison_id={comparison_id}",
    }

    return payload
```

## Webhook Handler Logic

```python
@api_view(['POST'])
@permission_classes([AllowAny])
@transaction.atomic
def spec_comparison_webhook(request):
    payload = request.data
    event_id = payload.get('event_id')
    comparison_id = request.query_params.get('comparison_id') or payload.get('comparison_id')

    # Idempotency check
    if SpecComparison.objects.filter(event_id=event_id).exists():
        return Response({"status": "already_processed"}, status=200)

    # Fetch comparison
    try:
        comparison = SpecComparison.objects.get(id=comparison_id)
    except SpecComparison.DoesNotExist:
        return Response({"error": "Comparison not found"}, status=404)

    # Update status
    new_status = payload.get('status')
    comparison.status = new_status
    comparison.event_id = event_id
    comparison.notes_processed = payload.get('notes_processed', 0)
    comparison.notes_skipped = payload.get('notes_skipped', 0)
    comparison.specs_processed = payload.get('specs_processed', 0)
    comparison.notes_with_mismatch = payload.get('notes_with_mismatch', 0)

    if new_status in [SpecComparisonStatus.SUCCESS, SpecComparisonStatus.PARTIAL_SUCCESS, SpecComparisonStatus.FAILED]:
        comparison.completed_at = timezone.now()

    if new_status == SpecComparisonStatus.FAILED:
        comparison.error_message = payload.get('error_message')

    comparison.save()

    # Build note ID lookup for FK linking
    note_ids = [c['note_id'] for c in payload.get('conflicts', [])]
    note_ids += [s['note_id'] for s in payload.get('skipped_notes', [])]
    notes_by_id = {
        str(n.id): n
        for n in DrawingNote.objects.filter(id__in=note_ids)
    }

    # Create conflicts
    conflicts_to_create = [
        SpecConflict(
            comparison=comparison,
            note=notes_by_id.get(c['note_id']),
            note_id_from_lambda=c['note_id'],
            note_text=c['note_text'],
            spec_text=c['spec_text'],
            spec_source_file=c['spec_source_file'],
            spec_page_number=c['spec_page_number'],
            spec_masterformat_number=c['spec_masterformat_number'],
            confidence=c['confidence'],
            reason=c['reason'],
            pdf_locations=c.get('pdf_locations', []),
        )
        for c in payload.get('conflicts', [])
    ]
    SpecConflict.objects.bulk_create(conflicts_to_create)

    # Create skipped notes
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
        for s in payload.get('skipped_notes', [])
    ]
    SkippedNote.objects.bulk_create(skipped_to_create)

    return Response({"status": "processed"}, status=200)
```

## File Organization

| File | Changes |
|------|---------|
| `apps/deliverables/models.py` | Add `SpecComparisonStatus`, `SkipReason`, `SpecComparison`, `SpecConflict`, `SkippedNote` |
| `apps/deliverables/serializers/spec_comparison_serializers.py` | New file with serializers |
| `apps/deliverables/views/spec_comparison_views.py` | New file with views |
| `apps/deliverables/urls.py` | Add routes for new endpoints |
| `apps/utils/feature_flags.py` | Add `is_drawing_spec_comparison_active()` |
| `the_link/settings.py` | Add feature flag name and lambda URL settings |
| `apps/deliverables/admin.py` | Register new models |
| `apps/deliverables/migrations/XXXX_add_spec_comparison_models.py` | New migration |

## Edge Cases

| Scenario | Handling |
|----------|----------|
| No notes in project | Return 400 with message "No drawing notes found for comparison" |
| No specs in project | Return 400 with message "No spec sections found for comparison" |
| Comparison already in progress | Allow parallel runs; user can manage via comparison list |
| Lambda timeout | Comparison stays PROCESSING; consider adding stale check later |
| Duplicate webhook delivery | Idempotency via event_id; return 200 OK |
| Note ID not found | Store conflict/skipped note with null FK, keep note_id_from_lambda |

## Future Considerations

- **Highlighting UI:** pdf_locations stored for future spec PDF highlighting
- **Comparison history:** Model supports multiple runs; UI can show history when needed
- **Partial re-runs:** Could add ability to re-compare specific notes or disciplines
- **Notifications:** Could notify user when comparison completes
