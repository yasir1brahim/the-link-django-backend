# Drawing Notes API - Discipline Classification Changes

This document describes the API changes to support discipline classification in the Drawing Notes endpoint.

## Endpoint

```
GET /api/deliverables/projects/{project_id}/drawing-notes/
```

---

## New Response Fields

Each drawing note in the response now includes these new fields:

| Field | Type | Description |
|-------|------|-------------|
| `disciplines` | `string[]` | Array of discipline codes assigned to the note (from AI classification) |
| `sheet_discipline` | `string \| null` | The discipline code for the entire sheet/page (from title block analysis) |

### Example Note Object

```json
{
  "id": 123,
  "drawing_file_id": 45,
  "drawing_file_name": "M-101 Mechanical Floor Plan.pdf",
  "drawing_file_url": "https://s3.amazonaws.com/...",
  "page_number": 1,
  "sheet_number": "M-101",
  "sheet_title": "MECHANICAL FLOOR PLAN - LEVEL 1",
  "section_header": "GENERAL NOTES",
  "note_number": "1",
  "category": "general",
  "text": "All mechanical equipment shall be installed per manufacturer specifications.",
  "disciplines": ["mechanical", "general"],
  "sheet_discipline": "mechanical",
  "page_extraction_status": "success",
  "page_extraction_failed": false,
  "bounding_box": {...},
  ...
}
```

---

## Available Discipline Values

The following NCS (US National CAD Standard) discipline codes are used:

| Code | Display Name |
|------|--------------|
| `general` | General |
| `hazardous_materials` | Hazardous Materials |
| `survey_mapping` | Survey/Mapping |
| `geotechnical` | Geotechnical |
| `civil` | Civil |
| `landscape` | Landscape |
| `structural` | Structural |
| `architectural` | Architectural |
| `interiors` | Interiors |
| `equipment` | Equipment |
| `fire_protection` | Fire Protection |
| `plumbing` | Plumbing |
| `process` | Process |
| `mechanical` | Mechanical |
| `electrical` | Electrical |
| `distributed_energy` | Distributed Energy |
| `telecommunications` | Telecommunications |
| `resource` | Resource |
| `other` | Other |
| `contractor_shop` | Contractor/Shop |
| `operations` | Operations |

---

## New Filter Parameters

### Filter by Sheet Discipline

Filter notes by the sheet-level discipline (exact match):

```
GET /api/deliverables/projects/{project_id}/drawing-notes/?sheet_discipline=mechanical
```

### Filter by Note Disciplines

Filter notes that contain a specific discipline (array contains):

```
GET /api/deliverables/projects/{project_id}/drawing-notes/?disciplines=electrical
```

This will return all notes where the `disciplines` array contains `"electrical"`, including cross-discipline notes like `["electrical", "mechanical"]`.

---

## New Filter Options in `all_filter_vals`

The `all_filter_vals` object now includes discipline options for populating filter dropdowns:

| Field | Type | Description |
|-------|------|-------------|
| `disciplines` | `string[]` | Sorted, deduplicated list of all discipline codes found in notes |
| `sheet_disciplines` | `string[]` | Sorted, deduplicated list of all sheet disciplines found in pages |
| `has_null_sheet_discipline` | `boolean` | True if any page has `sheet_discipline: null` |

Use these to populate discipline filter dropdowns in the UI.

---

## Sample Requests & Responses

### Request: List All Notes

```http
GET /api/deliverables/projects/123/drawing-notes/?project_version_id=456
Authorization: Bearer <token>
```

### Response

```json
{
  "count": 150,
  "next": "/api/deliverables/projects/123/drawing-notes/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1001,
      "drawing_file_id": 45,
      "drawing_file_name": "M-101 Mechanical Floor Plan.pdf",
      "drawing_file_url": "https://linkdocs.s3.amazonaws.com/...",
      "page_number": 1,
      "page_rotation": 0,
      "page_rotated_width": 792.0,
      "page_rotated_height": 612.0,
      "page_unrotated_width": 792.0,
      "page_unrotated_height": 612.0,
      "sheet_number": "M-101",
      "sheet_title": "MECHANICAL FLOOR PLAN - LEVEL 1",
      "section_header": "GENERAL NOTES",
      "section_rotated_header_bbox": [50, 100, 200, 120],
      "section_unrotated_header_bbox": [50, 100, 200, 120],
      "note_number": "1",
      "category": "general",
      "text": "All mechanical equipment shall be installed per manufacturer specifications.",
      "drawing_references": ["Detail A/M-201"],
      "bounding_box": [50, 130, 400, 160],
      "raw_bounding_box": [50, 130, 400, 160],
      "rotated_bounding_box": [50, 130, 400, 160],
      "unrotated_bounding_box": [50, 130, 400, 160],
      "page_extraction_status": "success",
      "page_extraction_failed": false,
      "sheet_discipline": "mechanical",
      "disciplines": ["mechanical", "general"]
    },
    {
      "id": 1002,
      "drawing_file_id": 46,
      "drawing_file_name": "E-101 Electrical Plan.pdf",
      "page_number": 1,
      "sheet_number": "E-101",
      "sheet_title": "ELECTRICAL PLAN - LEVEL 1",
      "section_header": "ELECTRICAL NOTES",
      "note_number": "1",
      "category": "electrical",
      "text": "Provide conduit sleeves at all fire-rated wall penetrations.",
      "sheet_discipline": "electrical",
      "disciplines": ["electrical", "fire_protection"],
      ...
    }
  ],
  "all_filter_vals": {
    "category": ["general", "electrical", "mechanical", "plumbing"],
    "drawing_files": [
      {"id": 45, "name": "M-101 Mechanical Floor Plan.pdf"},
      {"id": 46, "name": "E-101 Electrical Plan.pdf"}
    ],
    "sheet_numbers": ["E-101", "M-101", "M-102"],
    "sheet_titles": ["ELECTRICAL PLAN - LEVEL 1", "MECHANICAL FLOOR PLAN - LEVEL 1"],
    "has_null_sheet_number": false,
    "has_null_sheet_title": false,
    "disciplines": ["electrical", "fire_protection", "general", "mechanical"],
    "sheet_disciplines": ["electrical", "mechanical"],
    "has_null_sheet_discipline": false
  },
  "total_count": 150,
  "processing_status": {
    "is_processing": false,
    "files_processing": 0,
    "files_completed": 2,
    "files_failed": 0,
    "files": []
  }
}
```

### Request: Filter by Mechanical Discipline

```http
GET /api/deliverables/projects/123/drawing-notes/?disciplines=mechanical
Authorization: Bearer <token>
```

Returns only notes where `disciplines` array contains `"mechanical"`.

### Request: Filter by Sheet Discipline

```http
GET /api/deliverables/projects/123/drawing-notes/?sheet_discipline=electrical
Authorization: Bearer <token>
```

Returns only notes from sheets classified as electrical drawings.

### Request: Combined Filters

```http
GET /api/deliverables/projects/123/drawing-notes/?sheet_discipline=mechanical&category=general&search=equipment
Authorization: Bearer <token>
```

Returns notes from mechanical sheets, with category "general", containing "equipment" in the text.

---

## Notes on Implementation

### Empty/Null Values

- `disciplines` will be an empty array `[]` if no disciplines were assigned
- `sheet_discipline` will be `null` if the sheet discipline could not be determined

### Cross-Discipline Notes

A single note can belong to multiple disciplines. For example, a note about electrical conduit penetrations through fire-rated walls might have:

```json
{
  "disciplines": ["electrical", "fire_protection"],
  "sheet_discipline": "electrical"
}
```

When filtering by `disciplines=fire_protection`, this note would be included in results even though `sheet_discipline` is `"electrical"`.

### Backward Compatibility

- These are additive changes - no existing fields were modified or removed
- Existing filter parameters continue to work unchanged
- The export endpoint (`/export/`) supports the same filters
