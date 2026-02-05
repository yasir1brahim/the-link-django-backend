# Drawing Parser Frontend Implementation Guide

## Overview

The backend is implementing a new feature to extract and display notes from construction drawing PDFs (mechanical, electrical, etc.). An AWS Lambda service parses PDF drawings and extracts structured note data, which is stored in our database and exposed via a new API endpoint.

## Motivation

Construction drawings contain important notes organized by category (General Notes, Plumbing Notes, etc.). This feature automates the extraction of these notes so they can be:
- Displayed in a searchable, filterable table
- Cross-referenced with other project data
- Exported for documentation purposes

## Frontend Display

**UI Pattern**: Table view similar to the existing Submittal Items table

The notes should be displayed in a paginated table with:
- Column headers for key fields (Drawing File, Page, Category, Note #, Text)
- Filter dropdowns for category and drawing file
- Search functionality (text search in note content)
- Pagination controls

---

## API Endpoint

### List Drawing Notes

```
GET /projects/{project_id}/drawing-notes/
```

**Authentication**: Required (standard project access permissions)

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_version_id` | int | Filter by project version |
| `category` | string | Filter by note category (e.g., "GENERAL NOTES") |
| `drawing_file_id` | int | Filter by specific drawing file |
| `search` | string | Case-insensitive text search in note content |
| `page_number` | int | Page number for pagination |
| `limit` | int | Items per page (max 100) |

### Sample Response

```json
{
  "count": 156,
  "next": "/projects/42/drawing-notes/?page_number=2&limit=25",
  "previous": null,
  "results": {
    "results": [
      {
        "id": 1001,
        "drawing_file_id": 15,
        "drawing_file_name": "Mechanical IFC Set.pdf",
        "page_number": 1,
        "section_header": "GENERAL NOTES:",
        "note_number": 1,
        "category": "GENERAL NOTES",
        "text": "All mechanical equipment shall be installed in accordance with manufacturer's specifications and local codes. Contractor shall verify all dimensions and conditions in field prior to fabrication.",
        "drawing_references": [
          {
            "reference_text": "DETAIL 04/M702",
            "drawing_id": "M702",
            "detail_number": "04"
          }
        ],
        "bounding_box": [120.5, 340.2, 580.8, 395.1],
        "page_extraction_status": "success",
        "page_extraction_failed": false
      },
      {
        "id": 1002,
        "drawing_file_id": 15,
        "drawing_file_name": "Mechanical IFC Set.pdf",
        "page_number": 1,
        "section_header": "GENERAL NOTES:",
        "note_number": 2,
        "category": "GENERAL NOTES",
        "text": "Provide access panels for all concealed valves, dampers, and equipment requiring maintenance.",
        "drawing_references": [],
        "bounding_box": [120.5, 400.0, 580.8, 435.2],
        "page_extraction_status": "success",
        "page_extraction_failed": false
      },
      {
        "id": 1003,
        "drawing_file_id": 15,
        "drawing_file_name": "Mechanical IFC Set.pdf",
        "page_number": 3,
        "section_header": "PLUMBING NOTES:",
        "note_number": 1,
        "category": "PLUMBING NOTES",
        "text": "All domestic water piping shall be Type L copper with lead-free solder joints.",
        "drawing_references": [
          {
            "reference_text": "SEE DETAIL 02/P501",
            "drawing_id": "P501",
            "detail_number": "02"
          }
        ],
        "bounding_box": [115.0, 520.3, 590.2, 555.8],
        "page_extraction_status": "success",
        "page_extraction_failed": false
      }
    ],
    "all_filter_vals": {
      "category": [
        "GENERAL NOTES",
        "PLUMBING NOTES",
        "ELECTRICAL NOTES",
        "HVAC NOTES"
      ],
      "drawing_file": [
        "Mechanical IFC Set.pdf",
        "Electrical IFC Set.pdf",
        "Plumbing IFC Set.pdf"
      ]
    },
    "total_count": 156
  }
}
```

---

## Response Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Unique note identifier |
| `drawing_file_id` | int | ID of the source drawing file |
| `drawing_file_name` | string | Filename of the source PDF |
| `page_number` | int | Page number within the PDF |
| `section_header` | string | Header of the note section (e.g., "GENERAL NOTES:") |
| `note_number` | int | Note number within its section |
| `category` | string | Category classification |
| `text` | string | Full text content of the note |
| `drawing_references` | array | Cross-references to other drawings (for future linking) |
| `bounding_box` | array | `[x1, y1, x2, y2]` coordinates for PDF highlighting |
| `page_extraction_status` | string | `"success"`, `"no_notes_found"`, or `"failed"` |
| `page_extraction_failed` | boolean | True if extraction failed for this page |

### Filter Values Object

The `all_filter_vals` object returns distinct values for filter dropdowns:
- `category`: List of all unique note categories in the result set
- `drawing_file`: List of all unique drawing file names in the result set

---

## Extraction Status Handling

The extraction process can have partial failures. Frontend should handle:

| `page_extraction_status` | Display Behavior |
|--------------------------|------------------|
| `success` | Normal display |
| `no_notes_found` | N/A (no notes returned for these pages) |
| `failed` | Show warning indicator on affected notes |

When `page_extraction_failed: true`, consider showing an icon or badge to indicate the note came from a page with extraction issues.

---

## Upload Flow (For Reference)

When uploading drawing files, use the existing upload endpoint with an additional parameter:

```
POST /upload-file/
```

**New Parameter**:
```json
{
  "file_type": "drawing"  // Use "drawing" instead of default "spec"
}
```

The backend handles extraction automatically after upload. Notes become available via the GET endpoint once extraction completes.

---

## Future Considerations (v2)

- **PDF Viewer Integration**: The `bounding_box` coordinates can be used to highlight notes in a PDF viewer
- **Drawing Reference Links**: `drawing_references` will eventually link to actual drawing pages
- **Re-extraction**: Users may be able to trigger re-extraction for failed pages
