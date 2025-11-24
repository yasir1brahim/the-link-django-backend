# Custom Item Types API

## Overview
Custom Item Types let project teams create color-coded categories for `ExtractedData` records. Each custom type belongs to a single project, can be softly deactivated, and automatically forces associated extractions into the `custom_highlights` extraction type.

## Authentication
All endpoints require a valid JWT bearer token.

```
Authorization: Bearer <token>
```

## Base URL

```
/api/deliverables/projects/{project_id}/custom-item-types/
```

## Endpoints

### List Custom Item Types
**GET** `/api/deliverables/projects/{project_id}/custom-item-types/`

Returns paginated active custom types for the project.

Response body (truncated example):
```json
{
  "count": 2,
  "results": [
    {
      "id": 12,
      "name": "Safety Requirements",
      "color": "#FF5733",
      "description": "Items flagged during safety inspections",
      "extracted_data_count": 15,
      "created_by_name": "Alex Builder",
      "is_active": true,
      "created_at": "2025-01-05T15:42:00Z"
    }
  ]
}
```

### Create Custom Item Type
**POST** `/api/deliverables/projects/{project_id}/custom-item-types/`

Request body:
```json
{
  "name": "Quality Control",
  "color": "#3B82F6",
  "description": "Observations from QC walks"
}
```

Validation highlights:
- `name` – required, max 100 chars, unique per project (case-insensitive)
- `color` – required HEX string `#RRGGBB`
- `description` – optional text

### Retrieve Custom Item Type
**GET** `/api/deliverables/projects/{project_id}/custom-item-types/{id}/`

Returns detail including project metadata, creator, usage counts, and the five most recent extractions linked to the type.

### Update Custom Item Type
**PATCH** `/api/deliverables/projects/{project_id}/custom-item-types/{id}/`

Request body (example):
```json
{
  "name": "Critical Safety",
  "color": "#EF4444"
}
```

### Soft Delete Custom Item Type
**DELETE** `/api/deliverables/projects/{project_id}/custom-item-types/{id}/`

Marks the type inactive (`is_active=false`). Historical associations remain intact for auditing; inactive types are excluded from list responses.

### Assign Custom Type to Extracted Data
**POST** `/api/deliverables/projects/{project_id}/custom-item-types/{id}/assign-to-extracted-data/`

Bulk attaches a custom type to multiple `ExtractedData` records within the same project.

Request body:
```json
{
  "extracted_data_ids": [101, 102, 103]
}
```

Result:
```json
{
  "message": "Assigned custom type to 3 items.",
  "updated_count": 3
}
```

Side effects:
- `custom_item_type` foreign key is set
- `extraction_type` is forced to `custom_highlights`

### List Associated Extracted Data
**GET** `/api/deliverables/projects/{project_id}/custom-item-types/{id}/extracted-data/`

Supports pagination (`page`, `page_size`) and simple full-text search over `requirement_text` with the `search` query parameter. Response items include section metadata, requirement text snippet, creator name, and timestamps.

### Suggested Color Palette
**GET** `/api/deliverables/projects/{project_id}/custom-item-types/color-palette/`

Returns available HEX colors from a predefined palette along with colors already used in the project.

Example response:
```json
{
  "available_colors": ["#84CC16", "#22C55E", "#10B981"],
  "used_colors": ["#EF4444", "#3B82F6"]
}
```

## ExtractedData Integration Notes
- Any extraction saved with a `custom_item_type` automatically persists as `custom_highlights`.
- Attempting to set `extraction_type = "custom_highlights"` without a custom type raises a validation error.
- Cross-project assignments are blocked: the custom type’s project must match the extraction’s project.

## Error Examples

**400 Bad Request** (missing IDs during assignment):
```json
{
  "detail": "extracted_data_ids is required."
}
```

**400 Bad Request** (invalid color hex):
```json
{
  "color": ["Color must be in HEX format (#RRGGBB)."]
}
```

**400 Bad Request** (cross-project assignment):
```json
{
  "detail": "One or more ExtractedData ids are invalid for this project."
}
```

## Verification Checklist
1. Run migrations: `docker-compose exec -T web python manage.py migrate`
2. Execute automated tests: `docker-compose exec -T web python manage.py test apps.deliverables.tests.test_custom_item_types -v 2`
3. Smoke-test API routes with an authenticated client (e.g., `curl` or Postman).
4. Confirm custom types appear and can be edited via the Django admin (`CustomItemType` list).




