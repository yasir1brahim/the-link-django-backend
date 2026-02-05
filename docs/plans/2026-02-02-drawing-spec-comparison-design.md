# Drawing Spec Comparison Feature Design

## Overview

This feature enables comparison of drawing notes against project specifications to detect conflicts. When the `drawing_spec_comparison` feature flag is active, users can trigger a project-wide comparison that invokes an AWS Lambda function. The lambda analyzes notes against specs and posts results back to a webhook, where we store detected conflicts and skipped notes for retrieval via read endpoints.

## Prerequisites

This feature depends on the discipline classification feature (merged in PR #238 `note-discipline`), which adds:
- `DrawingNote.disciplines` - ArrayField of discipline values
- `DrawingNote.discipline_confidence` - confidence level
- `DrawingPage.sheet_discipline` - single discipline from sheet number prefix

Ensure the codebase is based on `develop` branch with these fields available.

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
│ 2. Resolve project_version      │
│ 3. Validate notes/specs exist   │
│ 4. Create SpecComparison        │
│    (status: PENDING)            │
│ 5. Generate event_id            │
│ 6. Gather DrawingNotes          │
│ 7. Gather SpecSections          │
│ 8. Upload payload to S3         │
│ 9. Invoke lambda                │
│10. Set status: PROCESSING       │
│    (or FAILED if invoke fails)  │
└─────────────────────────────────┘
        │
        ▼ (async)
┌─────────────────────────────────┐
│  Lambda processes comparison    │
│  Posts result to webhook        │
│  (only sends terminal status)   │
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│  POST /webhooks/spec-comparison/│
├─────────────────────────────────┤
│ 1. Validate payload via serial. │
│ 2. select_for_update comparison │
│ 4. Create webhook event (unique)│
│ 5. Update SpecComparison status │
│ 6. If SUCCESS/PARTIAL_SUCCESS:  │
│    Store conflicts & skipped    │
│ 7. Update summary counts        │
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│  GET /projects/{id}/            │
│  spec-conflicts/                │
├─────────────────────────────────┤
│ Returns conflicts from latest   │
│ successful comparison           │
│ (or by comparison_id if valid)  │
└─────────────────────────────────┘
```

## Data Models

All new models use integer primary keys (Django default) to match existing deliverables models. `BaseModel` provides `created_at` and `updated_at` timestamps.

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
| `id` | Integer | Primary key (Django default) |
| `project` | FK(Project) | Project being compared |
| `project_version` | FK(ProjectVersion) | Version being compared |
| `triggered_by` | FK(User, on_delete=SET_NULL, null=True) | User who initiated comparison |
| `status` | CharField | SpecComparisonStatus choices |
| `event_id` | CharField(max_length=64, unique=True) | Server-generated event ID for idempotency |
| `started_at` | DateTimeField | When processing began (nullable) |
| `completed_at` | DateTimeField | When processing finished - set for all terminal states including FAILED (nullable) |
| `notes_processed` | IntegerField(default=0) | Count of notes analyzed |
| `notes_skipped` | IntegerField(default=0) | Count of notes skipped |
| `spec_files_processed` | IntegerField(default=0) | Count of spec files (SpecSection PDFs) processed |
| `notes_with_mismatch` | IntegerField(default=0) | Notes where discipline differs from sheet |
| `error_message` | TextField | Error details on failure (nullable) |
| `payload_s3_key` | CharField(max_length=1024) | S3 key for uploaded payload (nullable) |
| `created_at` | DateTimeField | From BaseModel |
| `updated_at` | DateTimeField | From BaseModel |

**Indexes:**
- `(project, project_version, created_at)` - For finding comparisons by project
- `(project, status, completed_at)` - For finding latest successful comparison

### SpecComparisonWebhookEvent

Tracks webhook deliveries for idempotency (mirrors `DrawingExtractionWebhookEvent` pattern).

| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `comparison` | FK(SpecComparison, on_delete=CASCADE) | Parent comparison |
| `event_id` | CharField(max_length=64, unique=True) | Event ID from webhook payload |
| `new_status` | CharField(max_length=32) | Status reported by webhook |
| `created_at` | DateTimeField | From BaseModel |

**Note:** Full payload is NOT stored to avoid DB bloat. If debugging is needed, payloads can be retrieved from CloudWatch logs.

### SpecConflict

Stores each detected conflict with full fidelity for future UI highlighting.

| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `comparison` | FK(SpecComparison, on_delete=CASCADE) | Parent comparison run |
| `note` | FK(DrawingNote, on_delete=SET_NULL, null=True) | Link to source note |
| `note_id_from_lambda` | CharField(max_length=64) | Note ID as sent to/from lambda |
| `note_text` | TextField | The note text content |
| `spec_text` | TextField | Conflicting spec text |
| `spec_file_s3_key` | CharField(max_length=1024) | S3 key of spec PDF (without bucket prefix) |
| `spec_page_number` | IntegerField | 1-indexed page number |
| `spec_masterformat_number` | CharField(max_length=32) | MasterFormat number (e.g., "220500") |
| `confidence` | FloatField | Confidence score (0-1) |
| `reason` | TextField | Explanation of the conflict |
| `pdf_locations` | JSONField(default=list) | Array of bounding boxes for highlighting |
| `created_at` | DateTimeField | From BaseModel |

**Indexes:**
- `(comparison)` - For fetching all conflicts for a comparison

**Ordering:** `class Meta: ordering = ['id']` for deterministic pagination.

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
| `id` | Integer | Primary key |
| `comparison` | FK(SpecComparison, on_delete=CASCADE) | Parent comparison run |
| `note` | FK(DrawingNote, on_delete=SET_NULL, null=True) | Link to source note |
| `note_id_from_lambda` | CharField(max_length=64) | Note ID as sent to/from lambda |
| `disciplines` | JSONField(default=list) | Original disciplines array from note |
| `sheet_discipline` | CharField(max_length=32) | Sheet's discipline (nullable) |
| `reason` | CharField(max_length=32) | SkipReason choices |
| `detail` | TextField | Additional context (nullable) |
| `created_at` | DateTimeField | From BaseModel |

**Indexes:**
- `(comparison, reason)` - For filtering skipped notes by reason

**Ordering:** `class Meta: ordering = ['id']` for deterministic pagination.

## Terminology

To avoid confusion between data sources and processing units:

| Term | Meaning |
|------|---------|
| **SpecSection** | Django model representing a spec PDF file with its MasterFormat classification |
| **spec file** | The actual PDF file (stored in S3, referenced by `SpecSection.file_s3_key`) |
| **spec_files_processed** | Count of unique spec PDFs downloaded and analyzed by the lambda |
| **spec_file_s3_key** | S3 key (path) to the spec PDF, without `s3://bucket/` prefix |

## API Endpoints

### Trigger Endpoint

**`POST /api/deliverables/projects/{project_id}/trigger-spec-comparison/`**

Initiates a new spec comparison for the project.

**Authentication:** Required (IsAuthenticated + ProjectAccessPermissions)

**Feature Flag:** `drawing_spec_comparison` must be active

**Request Body:** (optional)
```json
{
    "project_version_id": 123  // Optional: defaults to latest active version
}
```

**Version Selection:**
- If `project_version_id` provided, use that version (validate it belongs to project)
- Otherwise, use the project's current active version (`project.current_version`)
- If `project.current_version` is None, return 400 with message "Project has no active version"

**Pre-validation:**
- Count notes and specs BEFORE creating comparison
- Return 400 if either count is zero

**Response (201 Created):**
```json
{
    "id": 123,
    "status": "PROCESSING",
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "created_at": "2026-02-02T10:30:00Z",
    "started_at": "2026-02-02T10:30:01Z",
    "triggered_by": {
        "id": 456,
        "display_name": "John Doe"
    }
}
```

**Error Responses:**
- `403 Forbidden` - Feature flag not active
- `400 Bad Request` - No notes or specs in project, invalid project_version_id, or project has no active version
- `404 Not Found` - Project not found

**Implementation Notes:**
- Validate notes/specs exist before creating comparison
- Generate `event_id` server-side (UUID) before invoking lambda
- After successful lambda invocation, set `status=PROCESSING` and `started_at=now()`
- If lambda invocation fails, set `status=FAILED`, `error_message`, and `completed_at=now()`

### Webhook Endpoint

**`POST /api/deliverables/webhooks/spec-comparison/`**

Receives comparison results from the lambda.

**Authentication:** AllowAny (lambda callback)

**Request Body:** (from lambda - only terminal statuses)
```json
{
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "comparison_id": 123,
    "status": "SUCCESS",
    "conflicts": [...],
    "skipped_notes": [...],
    "notes_processed": 150,
    "notes_skipped": 12,
    "spec_files_processed": 8,
    "notes_with_mismatch": 5,
    "error_message": null
}
```

**Note:** Lambda only sends terminal statuses (SUCCESS, PARTIAL_SUCCESS, FAILED). It does not send intermediate PROCESSING updates.

**Response:** `200 OK`

**Validation:**
- `event_id` is required and must be non-empty
- `status` must be a valid terminal `SpecComparisonStatus` value
- Payload validated via `SpecComparisonWebhookSerializer`
- `spec_source_file` in conflicts must be `s3://` URI format (validated)

**Idempotency (race-safe):**
- Use `select_for_update` on comparison within transaction
- Create `SpecComparisonWebhookEvent` with unique `event_id`
- If `IntegrityError` on event creation, return 200 OK (duplicate)
- This pattern matches `DrawingExtractionWebhookEvent`

**Data Storage:**
- Conflicts and skipped notes are ONLY stored for SUCCESS and PARTIAL_SUCCESS statuses
- FAILED status only updates comparison metadata and error_message (no partial data)

### Read Conflicts Endpoint

**`GET /api/deliverables/projects/{project_id}/spec-conflicts/`**

Returns conflicts from the latest **successful** comparison (SUCCESS or PARTIAL_SUCCESS). FAILED comparisons are excluded from "latest" selection.

**Authentication:** Required

**Query Parameters:**
- `comparison_id` (optional) - Filter to specific comparison (must belong to this project)
- `page`, `page_size` - Pagination

**Scoping:**
- If `comparison_id` provided, verify it belongs to `project_id` (return 404 if not)
- "Latest" means latest comparison with SUCCESS or PARTIAL_SUCCESS status, ordered by `completed_at` DESC

**Response (200 OK):**
```json
{
    "count": 42,
    "next": "...",
    "previous": null,
    "comparison": {
        "id": 123,
        "status": "SUCCESS",
        "completed_at": "2026-02-02T10:35:00Z"
    },
    "results": [
        {
            "id": 789,
            "note_id": 456,
            "note_text": "Provide shutoff valves at...",
            "spec_text": "Shutoff valves shall be...",
            "spec_file_s3_key": "projects/123/specs/plumbing.pdf",
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

**Note on `spec_file_url`:** This is computed in the serializer via `SerializerMethodField`, generating a presigned S3 URL with 1-hour TTL from `spec_file_s3_key`. It is NOT stored in the database. For large result sets, consider memoizing presigned URLs per `spec_file_s3_key` within the serializer context to avoid redundant S3 calls.

**Ordering:** Results are ordered by `id` for deterministic pagination.

### Read Skipped Notes Endpoint

**`GET /api/deliverables/projects/{project_id}/skipped-notes/`**

Returns skipped notes from the latest successful comparison.

**Authentication:** Required

**Query Parameters:**
- `comparison_id` (optional) - Filter to specific comparison (must belong to this project)
- `reason` (optional) - Filter by skip reason
- `page`, `page_size` - Pagination

**Response (200 OK):**
```json
{
    "count": 12,
    "results": [
        {
            "id": 101,
            "note_id": 456,
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
            "id": 123,
            "status": "SUCCESS",
            "event_id": "550e8400-e29b-41d4-a716-446655440000",
            "created_at": "2026-02-02T10:30:00Z",
            "started_at": "2026-02-02T10:30:01Z",
            "completed_at": "2026-02-02T10:35:00Z",
            "triggered_by": {"display_name": "John Doe"},
            "notes_processed": 150,
            "notes_skipped": 12,
            "spec_files_processed": 8,
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

### Handling Payload Size Limits

Lambda function URLs have a ~6MB payload limit. To avoid this:

1. Build the payload in memory
2. Upload to S3 as JSON
3. Pass S3 pointer to lambda

**Memory considerations:** For very large projects (10k+ notes), building the full payload in memory could be slow. Future optimization could stream notes to S3 in JSONL format or batch the comparison.

**Payload lifecycle:** Add an S3 lifecycle policy to delete payload files after 30 days to prevent accumulation. Alternatively, delete `payload_s3_key` after receiving a terminal webhook.

```python
import json
import uuid

def trigger_spec_comparison(project, project_version, user):
    # Pre-validate: count notes and specs
    notes_count = get_notes_queryset(project, project_version).count()
    specs_count = get_specs_queryset(project, project_version).count()

    if notes_count == 0:
        raise ValidationError("No drawing notes found for comparison")
    if specs_count == 0:
        raise ValidationError("No spec sections found for comparison")

    # Create comparison with server-generated event_id
    event_id = str(uuid.uuid4())
    comparison = SpecComparison.objects.create(
        project=project,
        project_version=project_version,
        triggered_by=user,
        status=SpecComparisonStatus.PENDING,
        event_id=event_id,
    )

    try:
        payload = build_comparison_payload(project, project_version, comparison.id, event_id)

        # Upload payload to S3
        payload_s3_key = f"spec-comparisons/{comparison.id}/payload.json"
        s3.put_object(
            Bucket=settings.S3_BUCKET,
            Key=payload_s3_key,
            Body=json.dumps(payload),
            ContentType='application/json',
        )
        comparison.payload_s3_key = payload_s3_key

        # Invoke lambda with S3 pointer
        lambda_payload = {
            "payload_s3_uri": f"s3://{settings.S3_BUCKET}/{payload_s3_key}",
            "callback_url": settings.BACKEND_SPEC_COMPARISON_CALLBACK_URL,
            "comparison_id": comparison.id,
            "event_id": event_id,
        }

        invoke_lambda(lambda_payload, settings.SPEC_COMPARISON_LAMBDA_FUNCTION_URL)

        # Update to PROCESSING on successful invocation
        comparison.status = SpecComparisonStatus.PROCESSING
        comparison.started_at = timezone.now()
        comparison.save()

    except Exception as e:
        comparison.status = SpecComparisonStatus.FAILED
        comparison.error_message = str(e)
        comparison.completed_at = timezone.now()  # Set completed_at for FAILED too
        comparison.save()
        raise

    return comparison
```

### Payload Building with Precise Selection

```python
def get_notes_queryset(project, project_version):
    """Get notes from the latest successful extraction per drawing file."""
    from django.db.models import Subquery, OuterRef

    # Subquery: latest successful extraction ID per drawing file
    latest_extraction_subquery = DrawingExtraction.objects.filter(
        drawing_file=OuterRef('section__page__extraction__drawing_file'),
        drawing_file__project=project,
        drawing_file__project_version=project_version,
        status=DrawingExtractionStatus.SUCCESS,
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
                "s3_key": spec.file_s3_key,  # Also include raw key for backend storage
                "masterformat_number": spec.masterformat_section.masterformat_number,
            }
            for spec in spec_sections
        ],
        "callback_url": settings.BACKEND_SPEC_COMPARISON_CALLBACK_URL,
    }

    return payload
```

## Webhook Handler Logic

### Webhook Payload Serializer

```python
class PdfLocationSerializer(serializers.Serializer):
    page_no = serializers.IntegerField()
    x = serializers.FloatField()
    y = serializers.FloatField()
    width = serializers.FloatField()
    height = serializers.FloatField()


class SpecConflictPayloadSerializer(serializers.Serializer):
    note_id = serializers.CharField()
    note_text = serializers.CharField()
    spec_text = serializers.CharField()
    spec_source_file = serializers.CharField()  # Must be s3://bucket/key format
    spec_page_number = serializers.IntegerField()
    spec_masterformat_number = serializers.CharField()
    confidence = serializers.FloatField()
    reason = serializers.CharField()
    pdf_locations = PdfLocationSerializer(many=True, required=False, default=list)

    def validate_spec_source_file(self, value):
        """Enforce s3://{bucket}/{key} URI format contract."""
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
        return value


class SkippedNotePayloadSerializer(serializers.Serializer):
    note_id = serializers.CharField()
    disciplines = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    sheet_discipline = serializers.CharField(required=False, allow_null=True)
    reason = serializers.ChoiceField(choices=SkipReason.choices)
    detail = serializers.CharField(required=False, allow_null=True)


class SpecComparisonWebhookSerializer(serializers.Serializer):
    event_id = serializers.CharField(required=True, allow_blank=False)
    comparison_id = serializers.IntegerField(required=True)
    status = serializers.ChoiceField(choices=[
        SpecComparisonStatus.SUCCESS,
        SpecComparisonStatus.PARTIAL_SUCCESS,
        SpecComparisonStatus.FAILED,
    ])  # Only terminal statuses allowed
    conflicts = SpecConflictPayloadSerializer(many=True, required=False, default=list)
    skipped_notes = SkippedNotePayloadSerializer(many=True, required=False, default=list)
    notes_processed = serializers.IntegerField(required=False, default=0)
    notes_skipped = serializers.IntegerField(required=False, default=0)
    spec_files_processed = serializers.IntegerField(required=False, default=0)
    notes_with_mismatch = serializers.IntegerField(required=False, default=0)
    error_message = serializers.CharField(required=False, allow_null=True)
```

### Webhook View

```python
from django.db import IntegrityError

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


@api_view(['POST'])
@permission_classes([AllowAny])
def spec_comparison_webhook(request):
    # Validate payload
    serializer = SpecComparisonWebhookSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": "Invalid payload", "details": serializer.errors}, status=400)

    data = serializer.validated_data
    event_id = data['event_id']
    comparison_id = data['comparison_id']
    new_status = data['status']

    with transaction.atomic():
        # Lock comparison row to prevent races
        try:
            comparison = SpecComparison.objects.select_for_update().get(id=comparison_id)
        except SpecComparison.DoesNotExist:
            return Response({"error": "Comparison not found"}, status=404)

        # Verify event_id matches
        if comparison.event_id != event_id:
            return Response({"error": "Event ID mismatch"}, status=400)

        # Create webhook event for idempotency (unique constraint on event_id)
        try:
            SpecComparisonWebhookEvent.objects.create(
                comparison=comparison,
                event_id=event_id,
                new_status=new_status,
            )
        except IntegrityError:
            # Duplicate event_id - already processed
            return Response({"status": "already_processed"}, status=200)

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
            return Response({"status": "processed"}, status=200)

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
            notes_by_id = {
                str(n.id): n
                for n in DrawingNote.objects.filter(id__in=valid_note_ids)
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

    return Response({"status": "processed"}, status=200)
```

## File Organization

| File | Changes |
|------|---------|
| `apps/deliverables/models.py` | Add `SpecComparisonStatus`, `SkipReason`, `SpecComparison`, `SpecComparisonWebhookEvent`, `SpecConflict`, `SkippedNote` with indexes |
| `apps/deliverables/serializers/spec_comparison_serializers.py` | New file with read serializers and webhook payload serializers |
| `apps/deliverables/views/spec_comparison_views.py` | New file with views |
| `apps/deliverables/urls.py` | Add routes for new endpoints |
| `apps/utils/feature_flags.py` | Add `is_drawing_spec_comparison_active()` |
| `the_link/settings.py` | Add feature flag name and lambda URL settings |
| `apps/deliverables/admin.py` | Register new models |
| `apps/deliverables/migrations/XXXX_add_spec_comparison_models.py` | New migration with indexes |

## Test Plan

### Unit Tests

**Models:**
- Test `SpecComparisonStatus` and `SkipReason` enum values
- Test model field defaults and constraints
- Test `on_delete=SET_NULL` behavior for note FKs

**Serializers:**
- Test `SpecComparisonWebhookSerializer` validation (required fields, terminal status only)
- Test nested `PdfLocationSerializer` validation
- Test `SkippedNotePayloadSerializer` with valid/invalid `SkipReason`
- Test `spec_source_file` validation rejects non-s3:// URIs
- Test `spec_source_file` validation rejects malformed URIs (`s3://bucket`, `s3://bucket/`, `s3:///key`)

**Utilities:**
- Test `parse_s3_uri_to_key` with various URI formats
- Test `safe_int` with valid/invalid inputs

### API Tests

**Trigger Endpoint:**
- Test successful trigger returns 201 with PROCESSING status
- Test 403 when feature flag inactive
- Test 400 when no notes exist
- Test 400 when no specs exist
- Test 404 for non-existent project
- Test optional `project_version_id` parameter
- Test 400 when `project.current_version` is None and no version_id provided
- Test lambda invocation failure sets FAILED status with completed_at

**Webhook Endpoint:**
- Test valid payload processing returns 200
- Test invalid payload returns 400
- Test invalid spec_source_file format (non-s3://) returns 400
- Test event_id mismatch returns 400
- Test comparison not found returns 404
- Test idempotency: duplicate event_id returns 200 without re-processing
- Test race condition: concurrent requests only process once (via select_for_update + unique constraint)
- Test SUCCESS status creates conflicts and skipped notes
- Test FAILED status does NOT create conflicts/skipped notes
- Test note FK linking works when note exists
- Test note FK is null when note ID not found
- Test non-integer note_id is handled gracefully (stored in note_id_from_lambda, FK is null)

**Read Endpoints:**
- Test authentication required
- Test pagination works correctly
- Test `comparison_id` filter validates project ownership
- Test "latest" selection uses most recent SUCCESS/PARTIAL_SUCCESS (excludes FAILED)
- Test empty results when no comparisons exist
- Test `spec_file_url` is a valid presigned URL
- Test `reason` filter on skipped notes endpoint
- Test pagination is stable/deterministic (ordered by id)

### Integration Tests

- Test full flow: trigger → lambda invocation → webhook → read results
- Test with realistic payload sizes (many notes/specs)

## Edge Cases

| Scenario | Handling |
|----------|----------|
| No notes in project | Return 400 with message "No drawing notes found for comparison" |
| No specs in project | Return 400 with message "No spec sections found for comparison" |
| Comparison already in progress | Allow parallel runs; user can manage via comparison list |
| Lambda invocation fails | Set status to FAILED with error_message and completed_at |
| Lambda timeout | Comparison stays PROCESSING; consider adding stale check later |
| Duplicate webhook delivery | Return 200 OK via unique event_id constraint (race-safe) |
| Concurrent webhook deliveries | select_for_update + IntegrityError handling prevents double-processing |
| event_id missing in webhook | Return 400 Bad Request (serializer validation) |
| comparison_id not found | Return 404 |
| event_id mismatch | Return 400 Bad Request |
| Note ID not found | Store conflict/skipped note with null FK, keep note_id_from_lambda |
| Note ID not an integer | Safely skip FK linking, store note_id_from_lambda |
| Invalid spec_source_file format | Return 400 Bad Request (must be s3:// URI) |
| comparison_id doesn't belong to project | Return 404 on read endpoints |
| No successful comparisons | Return empty results with null comparison metadata |
| Only FAILED comparisons exist | "Latest" returns empty (FAILED excluded) |
| FAILED webhook status | Update metadata only, no conflicts/skipped notes stored |
| project.current_version is None | Return 400 with message "Project has no active version" |
| Malformed spec_source_file (s3://bucket only) | Return 400 Bad Request (serializer validation) |

## Future Considerations

- **Highlighting UI:** pdf_locations stored for future spec PDF highlighting
- **Comparison history:** Model supports multiple runs; UI can show history when needed
- **Partial re-runs:** Could add ability to re-compare specific notes or disciplines
- **Notifications:** Could notify user when comparison completes
- **Stale comparison cleanup:** Background job to mark old PROCESSING comparisons as FAILED
- **Payload streaming:** For very large projects, stream notes to S3 in JSONL format
- **Payload cleanup:** Delete payload_s3_key after terminal webhook or add S3 lifecycle policy (30 days)

---

**Design reviewed through iterative external AI review process. Key design decisions:**
- Made event_id server-generated and required; validates match on webhook
- Added idempotency via SpecComparisonWebhookEvent table + select_for_update (race-safe)
- Added status transitions: PENDING → PROCESSING on invoke, FAILED on invoke error
- Added S3 payload upload to handle large payloads (>6MB limit)
- Refined extraction query to select latest successful extraction per drawing file
- Added webhook payload validation via serializer
- Enforced project scoping on read endpoints; defined "latest" as latest successful
- Added database indexes on comparison, conflict, and skipped note tables
- Set FK on_delete=SET_NULL for note references
- Documented spec_file_url as computed presigned URL (not stored)
- Added explicit model ordering for deterministic pagination
- FAILED status only updates metadata; conflicts/skipped notes NOT stored for failed runs
- Strengthened spec_source_file validation to require full s3://bucket/key format
- Added 400 handling when project.current_version is None
