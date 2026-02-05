# Spec Conflicts API - Required Changes

This document outlines the API changes required to support the Spec Conflicts UI feature.

---

## Summary

The frontend needs additional fields in the spec conflicts response to display drawing PDFs alongside spec PDFs, plus server-side sorting and filtering support.

---

## 1. Additional Fields on Conflict Response

**Endpoint:** `GET /api/deliverables/projects/{project_id}/spec-conflicts/`

The current response includes spec PDF information but is missing the corresponding drawing note PDF information. Please add the following fields to each conflict object:

### Required New Fields

| Field | Type | Description |
|-------|------|-------------|
| `sheet_number` | string \| null | The drawing sheet number (e.g., "M-101") |
| `sheet_title` | string \| null | The drawing sheet title (e.g., "Mechanical Floor Plan") |
| `drawing_file_url` | string | Pre-signed S3 URL to the drawing PDF (same format as `spec_file_url`) |
| `drawing_page_number` | int | Page number in the drawing PDF where the note appears |
| `drawing_bounding_box` | array | Coordinates `[x1, y1, x2, y2]` for highlighting the note in the drawing PDF |

### Updated Response Example

```json
{
  "count": 8,
  "next": null,
  "previous": null,
  "comparison": {
    "id": 1,
    "status": "SUCCESS",
    "completed_at": "2026-02-03T10:05:00Z"
  },
  "results": [
    {
      "id": 101,
      "note_id": 5432,
      "note_id_from_lambda": "5432",
      "note_text": "Provide ball valves at all fixture connections",

      "sheet_number": "P-201",
      "sheet_title": "Plumbing Riser Diagram",
      "drawing_file_url": "https://s3.amazonaws.com/bucket/projects/123/drawings/P-201.pdf?signature=...",
      "drawing_page_number": 1,
      "drawing_bounding_box": [120.5, 340.2, 280.0, 360.8],

      "spec_text": "Shutoff valves shall be gate type with bronze body",
      "spec_file_s3_key": "projects/123/specs/22-0500-plumbing.pdf",
      "spec_file_url": "https://s3.amazonaws.com/bucket/projects/123/specs/22-0500-plumbing.pdf?signature=...",
      "spec_page_number": 15,
      "spec_masterformat_number": "220500",
      "confidence": 0.85,
      "reason": "Drawing specifies ball valves but spec requires gate valves",
      "pdf_locations": [
        {
          "page_no": 15,
          "x": 72.0,
          "y": 144.5,
          "width": 200.0,
          "height": 12.0
        }
      ]
    }
  ]
}
```

---

## 2. Server-Side Sorting

**Endpoint:** `GET /api/deliverables/projects/{project_id}/spec-conflicts/`

Please add support for server-side sorting via query parameters:

### New Query Parameters

| Param | Type | Description |
|-------|------|-------------|
| `sort_column` | string | Column to sort by (see values below) |
| `sort_direction` | string | `asc` or `desc` (default: `asc`) |

### Sortable Columns

| `sort_column` value | Sorts by |
|---------------------|----------|
| `sheet_number` | Drawing sheet number |
| `note_text` | Drawing note text content |
| `spec_text` | Related spec text content |
| `spec_masterformat_number` | Spec section number |
| `reason` | Conflict reason |

### Example Request

```
GET /api/deliverables/projects/123/spec-conflicts/?project_version_id=456&sort_column=sheet_number&sort_direction=asc
```

---

## 3. Server-Side Filtering

**Endpoint:** `GET /api/deliverables/projects/{project_id}/spec-conflicts/`

Please add support for server-side filtering via query parameters:

### New Query Parameters

| Param | Type | Description |
|-------|------|-------------|
| `search` | string | Text search across `note_text`, `spec_text`, and `reason` |
| `sheet_number` | string | Filter by exact sheet number |
| `spec_masterformat_number` | string | Filter by exact spec section |
| `reason` | string | Filter by exact reason value |

### Example Request

```
GET /api/deliverables/projects/123/spec-conflicts/?project_version_id=456&sheet_number=P-201&search=valve
```

---

## 4. Filter Options in Response

To populate filter dropdowns in the UI, please include available filter values in the response (similar to how drawing notes API returns `all_filter_vals`):

### New Response Field

```json
{
  "count": 8,
  "next": null,
  "previous": null,
  "comparison": { ... },
  "results": [ ... ],
  "filter_options": {
    "sheet_numbers": ["P-201", "P-202", "M-101", "M-102"],
    "spec_masterformat_numbers": ["220500", "230500", "260100"],
    "reasons": [
      "Drawing specifies ball valves but spec requires gate valves",
      "Material mismatch between drawing and spec",
      "Dimension conflict"
    ]
  }
}
```

**Note:** `filter_options` should return all unique values across the full dataset (not just the current page), but only when no filters are applied. When filters are active, this field can be omitted or return the unfiltered values.

---

## 5. Excel Export Endpoint

**New Endpoint:** `GET /api/deliverables/projects/{project_id}/spec-conflicts/export/`

Please add an export endpoint that returns an Excel file with all conflicts (respecting current filters).

### Query Parameters

Same filtering parameters as the main endpoint:
- `project_version_id` (required)
- `comparison_id` (optional)
- `search` (optional)
- `sheet_number` (optional)
- `spec_masterformat_number` (optional)
- `reason` (optional)

### Response

- Content-Type: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- Content-Disposition: `attachment; filename="spec_conflicts.xlsx"`

### Excel Columns

| Column Header | Source Field |
|---------------|--------------|
| Drawing # | `sheet_number` |
| Sheet Title | `sheet_title` |
| Drawing Content | `note_text` |
| Related Spec Content | `spec_text` |
| Spec Section | `spec_masterformat_number` |
| Spec Page | `spec_page_number` |
| Reason | `reason` |
| Confidence | `confidence` (formatted as percentage) |

---

## Questions?

Contact the frontend team if you have questions about these requirements.
