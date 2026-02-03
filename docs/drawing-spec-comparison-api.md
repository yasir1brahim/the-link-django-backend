# Drawing Spec Comparison API

This document describes the API endpoints for the drawing spec comparison feature, which compares drawing notes against project specifications to detect conflicts.

## Overview

The comparison workflow is:
1. **Trigger** a comparison for a project version
2. **Poll** the comparison status until it completes
3. **Fetch** conflicts and skipped notes to display in the UI

## Authentication

All endpoints require authentication. Include the JWT token in the `Authorization` header:
```
Authorization: Bearer <token>
```

## Feature Flag

This feature is gated behind the `drawing_spec_comparison` feature flag. The API will return `403 Forbidden` if the flag is not enabled for the user/team/project.

---

## Endpoints

### 1. Trigger a Comparison

Start a new spec comparison for a project version.

```
POST /api/deliverables/projects/{project_id}/trigger-spec-comparison/
```

**Request Body:**
```json
{
  "project_version_id": 123
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "status": "PROCESSING",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2026-02-03T10:00:00Z",
  "started_at": "2026-02-03T10:00:00Z",
  "triggered_by": {
    "id": 42,
    "display_name": "John Doe"
  }
}
```

**Status Values:**
- `PROCESSING` - Comparison is running (normal response)
- `FAILED` - Comparison failed immediately (check `error_message` on the comparison)

**Error Responses:**
| Status | Reason |
|--------|--------|
| 400 | Missing `project_version_id`, invalid version, no drawing notes, or no spec sections |
| 403 | Not authenticated, not a project member, or feature flag disabled |
| 404 | Project not found |

---

### 2. List Comparisons (Poll for Status)

Get all comparisons for a project to check status and find the latest completed comparison.

```
GET /api/deliverables/projects/{project_id}/spec-comparisons/
```

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `page` | int | Page number (default: 1) |
| `limit` | int | Results per page (default: 50, max: 100) |

**Response (200 OK):**
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 2,
      "status": "PROCESSING",
      "event_id": "550e8400-e29b-41d4-a716-446655440001",
      "created_at": "2026-02-03T11:00:00Z",
      "started_at": "2026-02-03T11:00:00Z",
      "completed_at": null,
      "triggered_by": {
        "display_name": "John Doe"
      },
      "notes_processed": 0,
      "notes_skipped": 0,
      "spec_files_processed": 0,
      "conflict_count": 0
    },
    {
      "id": 1,
      "status": "SUCCESS",
      "event_id": "550e8400-e29b-41d4-a716-446655440000",
      "created_at": "2026-02-03T10:00:00Z",
      "started_at": "2026-02-03T10:00:00Z",
      "completed_at": "2026-02-03T10:05:00Z",
      "triggered_by": {
        "display_name": "John Doe"
      },
      "notes_processed": 150,
      "notes_skipped": 12,
      "spec_files_processed": 25,
      "conflict_count": 8
    }
  ]
}
```

**Status Values:**
| Status | Description |
|--------|-------------|
| `PENDING` | Queued but not started |
| `PROCESSING` | Currently running |
| `SUCCESS` | Completed successfully |
| `PARTIAL_SUCCESS` | Completed with some errors |
| `FAILED` | Failed completely |

**Polling Strategy:**
```javascript
// Poll every 5 seconds while status is PROCESSING
const pollComparison = async (projectId, comparisonId) => {
  const response = await fetch(`/api/deliverables/projects/${projectId}/spec-comparisons/`);
  const data = await response.json();
  const comparison = data.results.find(c => c.id === comparisonId);

  if (comparison.status === 'PROCESSING') {
    setTimeout(() => pollComparison(projectId, comparisonId), 5000);
  } else {
    // Comparison complete - fetch results
    fetchConflicts(projectId, comparison.project_version_id);
  }
};
```

---

### 3. Get Spec Conflicts

Get conflicts from a comparison. By default, returns conflicts from the latest successful comparison.

```
GET /api/deliverables/projects/{project_id}/spec-conflicts/
```

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `project_version_id` | int | **Yes** | The project version to query |
| `comparison_id` | int | No | Specific comparison ID (defaults to latest successful) |
| `page` | int | No | Page number (default: 1) |
| `limit` | int | No | Results per page (default: 50, max: 100) |
| `sort_column` | string | No | Column to sort by (see Sorting below) |
| `sort_direction` | string | No | `asc` (default) or `desc` |
| `search` | string | No | Search across note_text, spec_text, and reason (case-insensitive) |
| `sheet_number` | string | No | Filter by exact sheet number |
| `spec_masterformat_number` | string | No | Filter by exact MasterFormat number |
| `reason` | string | No | Filter by exact reason |

**Sorting:**
Supported `sort_column` values:
- `sheet_number` - Sort by drawing sheet number
- `note_text` - Sort by note text
- `spec_text` - Sort by spec text
- `spec_masterformat_number` - Sort by MasterFormat section number
- `reason` - Sort by conflict reason

**Response (200 OK):**
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
  "filter_options": {
    "sheet_numbers": ["M-101", "P-201", "P-202"],
    "spec_masterformat_numbers": ["220500", "230500", "260500"],
    "reasons": ["Dimension mismatch", "Material conflict", "Valve type mismatch"]
  },
  "results": [
    {
      "id": 101,
      "note_id": 5432,
      "note_id_from_lambda": "5432",
      "note_text": "Provide ball valves at all fixture connections",
      "sheet_number": "P-201",
      "sheet_title": "Plumbing First Floor Plan",
      "drawing_file_url": "https://s3.amazonaws.com/bucket/drawings/P-201.pdf?signature=...",
      "drawing_page_number": 3,
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

**Response when no comparisons exist:**
```json
{
  "count": 0,
  "next": null,
  "previous": null,
  "comparison": null,
  "filter_options": {
    "sheet_numbers": [],
    "spec_masterformat_numbers": [],
    "reasons": []
  },
  "results": []
}
```

**Field Descriptions:**
| Field | Description |
|-------|-------------|
| `note_id` | FK to DrawingNote (may be null if note was deleted) |
| `note_id_from_lambda` | Original note ID from lambda (always present) |
| `note_text` | The text of the drawing note |
| `sheet_number` | Drawing sheet number (e.g., "P-201") |
| `sheet_title` | Drawing sheet title (e.g., "Plumbing First Floor Plan") |
| `drawing_file_url` | Pre-signed S3 URL to view the drawing PDF (valid for 1 hour) |
| `drawing_page_number` | Page number in the drawing PDF |
| `drawing_bounding_box` | Bounding box [x1, y1, x2, y2] for highlighting the note |
| `spec_text` | The conflicting text from the spec |
| `spec_file_url` | Pre-signed S3 URL to view the spec PDF (valid for 1 hour) |
| `spec_page_number` | Page number in the spec PDF |
| `spec_masterformat_number` | MasterFormat section number (e.g., "220500") |
| `confidence` | Confidence score from 0.0 to 1.0 |
| `reason` | Human-readable explanation of the conflict |
| `pdf_locations` | Bounding boxes for highlighting in spec PDF viewer |

**filter_options:**
The `filter_options` object contains all unique values from the unfiltered dataset, useful for populating dropdown filters in the UI:
- `sheet_numbers` - All unique sheet numbers (sorted)
- `spec_masterformat_numbers` - All unique MasterFormat numbers (sorted)
- `reasons` - All unique conflict reasons (sorted)

---

### 4. Get Skipped Notes

Get notes that were skipped during comparison (e.g., no matching specs found).

```
GET /api/deliverables/projects/{project_id}/skipped-notes/
```

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `project_version_id` | int | **Yes** | The project version to query |
| `comparison_id` | int | No | Specific comparison ID (defaults to latest successful) |
| `reason` | string | No | Filter by skip reason |
| `page` | int | No | Page number (default: 1) |
| `limit` | int | No | Results per page (default: 50, max: 100) |

**Response (200 OK):**
```json
{
  "count": 12,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 201,
      "note_id": 5433,
      "note_id_from_lambda": "5433",
      "disciplines": ["plumbing", "mechanical"],
      "sheet_discipline": "mechanical",
      "reason": "no_matching_specs",
      "detail": "Division 22 has no specs uploaded for this project"
    }
  ]
}
```

**Skip Reasons:**
| Reason | Description |
|--------|-------------|
| `unknown_discipline` | Could not determine the discipline for the note |
| `skip_by_policy` | Skipped due to a policy rule |
| `no_matching_specs` | No spec files found for the note's discipline |
| `malformed_discipline` | Discipline data was malformed |

---

### 5. Export Spec Conflicts to Excel

Export conflicts to an Excel (.xlsx) file. Supports all the same filters as the conflicts list endpoint.

```
GET /api/deliverables/projects/{project_id}/spec-conflicts/export/
```

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `project_version_id` | int | **Yes** | The project version to query |
| `comparison_id` | int | No | Specific comparison ID (defaults to latest successful) |
| `search` | string | No | Search across note_text, spec_text, and reason |
| `sheet_number` | string | No | Filter by exact sheet number |
| `spec_masterformat_number` | string | No | Filter by exact MasterFormat number |
| `reason` | string | No | Filter by exact reason |

**Response (200 OK):**
- Content-Type: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- Content-Disposition: `attachment; filename=spec_conflicts.xlsx`

The Excel file contains the following columns:
| Column | Description |
|--------|-------------|
| Drawing # | Sheet number from the drawing |
| Sheet Title | Title of the drawing sheet |
| Drawing Content | The note text from the drawing |
| Related Spec Content | The conflicting text from the spec |
| Spec Section | MasterFormat section number |
| Spec Page | Page number in the spec PDF |
| Reason | Human-readable explanation of the conflict |
| Confidence | Confidence percentage (e.g., "85%") |

**Error Responses:**
| Status | Reason |
|--------|--------|
| 400 | Missing `project_version_id` or invalid version |
| 403 | Not authenticated or not a project member |
| 404 | Project not found |

---

## UI Integration Example

### Triggering and Displaying Results

```tsx
// React example
const SpecComparisonPanel = ({ projectId, projectVersionId }) => {
  const [comparison, setComparison] = useState(null);
  const [conflicts, setConflicts] = useState([]);
  const [loading, setLoading] = useState(false);

  const triggerComparison = async () => {
    setLoading(true);
    const response = await api.post(
      `/projects/${projectId}/trigger-spec-comparison/`,
      { project_version_id: projectVersionId }
    );
    pollForCompletion(response.data.id);
  };

  const pollForCompletion = async (comparisonId) => {
    const response = await api.get(`/projects/${projectId}/spec-comparisons/`);
    const comp = response.data.results.find(c => c.id === comparisonId);

    if (comp.status === 'PROCESSING') {
      setTimeout(() => pollForCompletion(comparisonId), 5000);
    } else {
      setComparison(comp);
      setLoading(false);
      if (comp.status === 'SUCCESS' || comp.status === 'PARTIAL_SUCCESS') {
        fetchConflicts();
      }
    }
  };

  const fetchConflicts = async () => {
    const response = await api.get(
      `/projects/${projectId}/spec-conflicts/`,
      { params: { project_version_id: projectVersionId } }
    );
    setConflicts(response.data.results);
  };

  return (
    <div>
      <button onClick={triggerComparison} disabled={loading}>
        {loading ? 'Comparing...' : 'Run Comparison'}
      </button>

      {comparison && (
        <div>
          <p>Status: {comparison.status}</p>
          <p>Notes processed: {comparison.notes_processed}</p>
          <p>Conflicts found: {comparison.conflict_count}</p>
        </div>
      )}

      <table>
        <thead>
          <tr>
            <th>Drawing Note</th>
            <th>Spec Text</th>
            <th>Spec Section</th>
            <th>Confidence</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {conflicts.map(conflict => (
            <tr key={conflict.id}>
              <td>{conflict.note_text}</td>
              <td>{conflict.spec_text}</td>
              <td>
                <a href={conflict.spec_file_url} target="_blank">
                  {conflict.spec_masterformat_number} (p. {conflict.spec_page_number})
                </a>
              </td>
              <td>{Math.round(conflict.confidence * 100)}%</td>
              <td>{conflict.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
```

### Displaying Skipped Notes

```tsx
const SkippedNotesPanel = ({ projectId, projectVersionId }) => {
  const [skippedNotes, setSkippedNotes] = useState([]);

  useEffect(() => {
    const fetchSkipped = async () => {
      const response = await api.get(
        `/projects/${projectId}/skipped-notes/`,
        { params: { project_version_id: projectVersionId } }
      );
      setSkippedNotes(response.data.results);
    };
    fetchSkipped();
  }, [projectId, projectVersionId]);

  const reasonLabels = {
    'unknown_discipline': 'Unknown Discipline',
    'skip_by_policy': 'Skipped by Policy',
    'no_matching_specs': 'No Matching Specs',
    'malformed_discipline': 'Malformed Discipline',
  };

  return (
    <table>
      <thead>
        <tr>
          <th>Note ID</th>
          <th>Reason</th>
          <th>Detail</th>
        </tr>
      </thead>
      <tbody>
        {skippedNotes.map(note => (
          <tr key={note.id}>
            <td>{note.note_id || note.note_id_from_lambda}</td>
            <td>{reasonLabels[note.reason]}</td>
            <td>{note.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};
```

---

## Error Handling

All endpoints return errors in this format:

```json
{
  "error": "Human-readable error message",
  "details": { /* optional validation details */ }
}
```

Common HTTP status codes:
- `400` - Bad request (missing/invalid parameters)
- `403` - Forbidden (not authenticated, not a member, or feature disabled)
- `404` - Not found (project or comparison doesn't exist)

---

## Questions?

Contact the backend team if you have questions about these endpoints.
