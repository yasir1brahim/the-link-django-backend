# Drawing Parser Webhook Design

## Overview

This document describes the design for a webhook system to receive parsed drawing data from an AWS extraction service. The system will store extracted notes from construction drawings (mechanical, electrical, etc.) and make them available via API.

## Background

An AWS Lambda process extracts notes and text from construction drawing PDFs. This webhook receives the extraction results and stores them in our database for display in a table UI similar to the submittal items table.

---

## Data Structure from AWS

The extraction service returns JSON with this structure:

```json
{
  "file_name": "Mechanical IFC Set.pdf",
  "total_pages": 23,
  "pages": [
    {
      "page_number": 1,
      "extraction_status": "success",
      "page_type": "drawing",
      "note_sections": [
        {
          "header": "GENERAL NOTES:",
          "header_bbox": [x1, y1, x2, y2],
          "notes": [
            {
              "note_number": 1,
              "category": "GENERAL NOTES",
              "text": "Full note text...",
              "drawing_references": [
                {
                  "reference_text": "DETAIL 04/M702",
                  "drawing_id": "M702",
                  "detail_number": "04"
                }
              ],
              "bounding_box": [x1, y1, x2, y2],
              "source_blocks": [[x1, y1, x2, y2], ...]
            }
          ]
        }
      ],
      "spec_content": null
    },
    {
      "page_number": 13,
      "extraction_status": "success",
      "page_type": "spec",
      "note_sections": [],
      "spec_content": "Long text content for specification pages..."
    }
  ]
}
```

### Key Data Points

- **page_type**: Either `"drawing"` (has notes) or `"spec"` (has spec_content text)
- **extraction_status**: `"success"` or `"no_notes_found"`
- **drawing_references**: Cross-references to other drawings (stored as JSON, not linked as FKs in v1)
- **bounding_box / source_blocks**: Coordinates for highlighting in PDF viewer

---

## Models

### Enums

```python
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
```

### DrawingFile

The uploaded drawing document (e.g., mechanical drawings PDF).

```python
class DrawingFile(BaseModel):
    project = models.ForeignKey("Project", on_delete=models.CASCADE)
    project_version = models.ForeignKey("ProjectVersion", on_delete=models.CASCADE)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    file_name = models.CharField(max_length=512)
    file_s3_key = models.CharField(max_length=1024)
    md5 = models.CharField(max_length=64)
    total_pages = models.IntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['project', 'project_version']),
        ]

    @property
    def latest_extraction(self):
        return self.extractions.order_by('-created_at').first()

    @property
    def extraction_status(self):
        extraction = self.latest_extraction
        return extraction.status if extraction else None
```

**Design Decision**: No `processing_status` field on this model. Status is derived from the latest `DrawingExtraction` record to avoid data duplication and sync issues.

### DrawingExtraction

Tracks each extraction attempt for a drawing file.

```python
class DrawingExtraction(BaseModel):
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
    # e.g., "3 of 23 pages failed to extract"

    class Meta:
        indexes = [
            models.Index(fields=['drawing_file', 'status']),
        ]
```

### DrawingPage

Individual page from a drawing file.

```python
class DrawingPage(BaseModel):
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
        unique_together = [['extraction', 'page_number']]
```

### DrawingNoteSection

A section header containing notes on a drawing page (e.g., "GENERAL NOTES:").

```python
class DrawingNoteSection(BaseModel):
    page = models.ForeignKey(
        "DrawingPage",
        on_delete=models.CASCADE,
        related_name="note_sections"
    )

    header = models.CharField(max_length=512)
    header_bbox = models.JSONField(null=True, blank=True)  # [x1, y1, x2, y2]

    class Meta:
        ordering = ['id']
```

### DrawingNote

Individual note extracted from a drawing.

```python
class DrawingNote(BaseModel):
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
```

---

## API Endpoints

### 1. Upload Endpoint (Modified)

**Endpoint**: `POST /upload-file/`

**Changes**: Add `file_type` parameter to existing `FileUploadSerializer`.

```python
# In FileUploadSerializer
file_type = serializers.ChoiceField(
    choices=['spec', 'drawing'],
    default='spec',
    required=False
)
```

**Flow for `file_type='drawing'`**:

1. Validate file and check for duplicates (same as specs)
2. Upload to S3 at path: `drawings/project_{id}__version_{id}__{timestamp}_{filename}`
3. Create `DrawingFile` record
4. Create `DrawingExtraction` record with `status=PENDING`
5. Trigger AWS extraction Lambda with `extraction_id`

**Response**: Same structure as current upload endpoint, with drawing file IDs included.

### 2. Webhook Endpoint

**Endpoint**: `POST /webhooks/drawing-extraction/`

**Authentication**: `AllowAny` (external service callback)

**Request Schema**:

```python
class DrawingExtractionWebhookRequest(TypedDict):
    extraction_id: int                      # Maps to DrawingExtraction.id
    new_status: str                         # PROCESSING, SUCCESS, PARTIAL_SUCCESS, FAILED

    # S3 paths
    source_s3_key: NotRequired[str]
    output_s3_key: NotRequired[str]

    # Processing metadata
    model_version: NotRequired[str]
    processing_time_ms: NotRequired[int]
    error_message: NotRequired[str]

    # Parsed data (on SUCCESS/PARTIAL_SUCCESS)
    data: NotRequired[DrawingExtractionData]


class DrawingExtractionData(TypedDict):
    file_name: str
    total_pages: int
    pages: List[PageData]


class PageData(TypedDict):
    page_number: int
    extraction_status: str
    page_type: str
    note_sections: List[NoteSectionData]
    spec_content: Optional[str]


class NoteSectionData(TypedDict):
    header: str
    header_bbox: Optional[List[float]]
    notes: List[NoteData]


class NoteData(TypedDict):
    note_number: int
    category: str
    text: str
    drawing_references: List[dict]
    bounding_box: Optional[List[float]]
    source_blocks: Optional[List[List[float]]]
```

**Processing Flow**:

```python
@api_view(['POST'])
@permission_classes([AllowAny])
def drawing_extraction_webhook(request):
    payload = request.data
    extraction_id = payload['extraction_id']
    new_status = payload['new_status']

    extraction = DrawingExtraction.objects.get(id=extraction_id)

    if new_status == 'PROCESSING':
        extraction.status = DrawingExtractionStatus.PROCESSING
        extraction.started_at = timezone.now()
        extraction.save()

    elif new_status in ['SUCCESS', 'PARTIAL_SUCCESS']:
        extraction.status = new_status
        extraction.completed_at = timezone.now()
        extraction.model_version = payload.get('model_version')
        extraction.processing_time_ms = payload.get('processing_time_ms')
        extraction.output_s3_key = payload.get('output_s3_key')
        extraction.save()

        # Update drawing file total_pages
        data = payload['data']
        extraction.drawing_file.total_pages = data['total_pages']
        extraction.drawing_file.save()

        # Create page, section, and note records
        _create_drawing_records(extraction, data)

    elif new_status == 'FAILED':
        extraction.status = DrawingExtractionStatus.FAILED
        extraction.completed_at = timezone.now()
        extraction.error_message = payload.get('error_message')
        extraction.save()

    return Response(status=status.HTTP_200_OK)
```

### 3. Drawing Notes List Endpoint

**Endpoint**: `GET /projects/<project_id>/drawing-notes/`

**Pattern**: Mirror `SubmittalItemViewSet`

```python
class DrawingNoteViewSet(viewsets.ReadOnlyModelViewSet):
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

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Get filter values for UI dropdowns
        all_filter_vals = {
            'category': list(queryset.values_list('category', flat=True).distinct()),
            'drawing_file': list(queryset.values_list(
                'section__page__drawing_file__file_name', flat=True
            ).distinct()),
        }

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)

        return self.get_paginated_response({
            'results': serializer.data,
            'all_filter_vals': all_filter_vals,
            'total_count': queryset.count(),
        })
```

**Serializer**:

```python
class DrawingNoteReadSerializer(serializers.ModelSerializer):
    # Flattened fields for table display
    drawing_file_id = serializers.IntegerField(source='section.page.drawing_file.id')
    drawing_file_name = serializers.CharField(source='section.page.drawing_file.file_name')
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

    def get_page_extraction_failed(self, obj):
        return obj.section.page.extraction_status == DrawingPageExtractionStatus.FAILED
```

**Query Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_version_id` | int | Filter by project version |
| `category` | string | Filter by note category |
| `drawing_file_id` | int | Filter by specific drawing file |
| `search` | string | Full-text search in note text |
| `page_number` | int | Page number for pagination |
| `limit` | int | Items per page (max 100) |

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `apps/deliverables/models.py` | Modify | Add 3 enums + 5 models |
| `apps/deliverables/views/main_views.py` | Modify | Update `upload_file` for `file_type` param |
| `apps/deliverables/views/drawing_views.py` | Create | Webhook view + ViewSet |
| `apps/deliverables/serializers.py` | Modify | Add `DrawingNoteReadSerializer` |
| `apps/deliverables/urls.py` | Modify | Add webhook URL + ViewSet router |
| `apps/deliverables/permissions.py` | Modify | Add `DrawingNoteAccessPermissions` |
| `apps/deliverables/admin.py` | Modify | Add model admins for debugging |

---

## Workflow

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. UPLOAD                                                                │
│    User uploads drawing PDF → DrawingFile created → DrawingExtraction   │
│    created (PENDING) → S3 upload → Trigger AWS Lambda                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. PROCESSING                                                            │
│    AWS Lambda sends webhook: new_status=PROCESSING                       │
│    → DrawingExtraction.status = PROCESSING                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. COMPLETION                                                            │
│    AWS Lambda sends webhook: new_status=SUCCESS + data                   │
│    → DrawingExtraction.status = SUCCESS                                 │
│    → Create DrawingPage records                                         │
│    → Create DrawingNoteSection records                                  │
│    → Create DrawingNote records                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. DISPLAY                                                               │
│    Frontend calls GET /projects/{id}/drawing-notes/                      │
│    → Returns paginated notes with filter options                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Design Decisions

### S3 Path Convention

Drawings use a **separate prefix** from specs:
- **Drawings**: `drawings/project_{id}__version_{id}__{timestamp}_{filename}`
- **Specs**: `original/project_{id}__version_{id}__{timestamp}_{filename}`

This provides clearer separation and easier management of permissions/lifecycle policies.

### Duplicate Detection

Duplicates are checked **within the same project version only**. This allows users to re-upload the same drawing in a new project version (e.g., updated revisions).

### Error Communication for PARTIAL_SUCCESS

Use **both** page-level status and a summary message:

1. **Page-level**: Each `DrawingPage` has `extraction_status` field showing success/failure
2. **Summary**: `DrawingExtraction` includes a `failure_summary` field (e.g., "3 of 23 pages failed")
3. **API Response**: The drawing notes list endpoint includes extraction status info

Add to `DrawingExtraction` model:
```python
failure_summary = models.CharField(max_length=256, null=True, blank=True)
# e.g., "3 of 23 pages failed to extract"
```

Update API response to include:
```python
class DrawingNoteReadSerializer:
    # ... existing fields ...
    extraction_status = serializers.CharField(source='section.page.extraction_status')
    page_extraction_failed = serializers.SerializerMethodField()

    def get_page_extraction_failed(self, obj):
        return obj.section.page.extraction_status == 'failed'
```

---

## Future Enhancements (v2)

1. **SpecSection Integration**: Create SpecSection records for `page_type=spec` pages to enable cross-referencing with submittal extraction system.

2. **Drawing Reference Linking**: Parse `drawing_references` and create FK relationships to other DrawingPage records when the referenced drawing exists.

3. **Re-extraction**: Allow users to trigger re-extraction for a DrawingFile (creates new DrawingExtraction, keeps old data until new one succeeds).

4. **Batch Operations**: Support bulk actions on drawing notes (export, categorize, etc.).
