# Discipline Classification Integration Guide

This document describes the new discipline classification fields added to the drawing notes extraction Lambda response.

## Overview

The extraction Lambda now classifies both sheets and individual notes by their construction discipline (e.g., mechanical, plumbing, electrical). This enables downstream filtering and routing of notes to relevant spec sections.

Classification uses the **NCS (US National CAD Standard) discipline designators**:

| Prefix | Discipline | Description |
|--------|------------|-------------|
| G | general | General project information |
| H | hazardous_materials | Hazmat remediation, abatement |
| V | survey_mapping | Site surveys, topographic maps |
| B | geotechnical | Soil reports, boring logs |
| C | civil | Site grading, utilities, roads |
| L | landscape | Planting, irrigation, hardscape |
| S | structural | Foundations, framing, steel |
| A | architectural | Floor plans, elevations, finishes |
| I | interiors | Interior design, furniture layouts |
| Q | equipment | Specialty equipment |
| F | fire_protection | Sprinklers, fire suppression |
| P | plumbing | Piping, fixtures, drainage |
| D | process | Industrial process systems |
| M | mechanical | HVAC, ductwork, ventilation |
| E | electrical | Power, lighting, panels |
| W | distributed_energy | Solar, wind, generators |
| T | telecommunications | Data, voice, security, AV |
| R | resource | Resource management |
| X | other | Does not fit other categories |
| Z | contractor_shop | Shop drawings, submittals |
| O | operations | Facility operations |

## New Fields

### Page-Level Fields

Each page in `pages[]` now includes:

| Field | Type | Description |
|-------|------|-------------|
| `sheet_discipline` | `string \| null` | The primary discipline of the sheet (e.g., `"mechanical"`, `"plumbing"`) |
| `sheet_discipline_confidence` | `"high" \| "medium" \| "low" \| null` | Confidence level of the classification |

**Sheet classification is based on the sheet number prefix** (e.g., `M-101` → `"mechanical"`, `P-201` → `"plumbing"`). Prefix-based classification always has `"high"` confidence.

### Note-Level Fields

Each note in `note_sections[].notes[]` now includes:

| Field | Type | Description |
|-------|------|-------------|
| `disciplines` | `string[]` | List of disciplines this note relates to (can be multiple) |
| `discipline_confidence` | `"high" \| "medium" \| "low" \| null` | Confidence level of the classification |

**Note classification is done per-note using an LLM**, which can identify:
- Notes that match the sheet discipline (most common)
- Notes that reference other disciplines (e.g., electrical note on a mechanical sheet)
- Coordination notes that span multiple disciplines

## Request Parameters

Two new optional parameters control discipline classification:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `classify_disciplines` | `boolean` | `true` | Enable/disable discipline classification |
| `classify_disciplines_with_llm` | `boolean` | `false` | Enable LLM-based per-note classification |

**Default behavior** (`classify_disciplines=true`, `classify_disciplines_with_llm=false`):
- Sheet discipline is classified by prefix (fast, no API cost)
- Notes inherit the sheet's discipline with `"low"` confidence

**With LLM enabled** (`classify_disciplines_with_llm=true`):
- Sheet discipline still uses prefix (with LLM fallback if prefix unknown)
- Each note is classified individually by the LLM
- Notes can have multiple disciplines and higher confidence

## Response Shape

### Full Response Structure

```json
{
  "file_name": "Mechanical IFC Set.pdf",
  "total_pages": 23,
  "pages": [
    {
      "page_number": 1,
      "rotation": 270,
      "rotated_page_width": 2592.0,
      "rotated_page_height": 1728.0,
      "unrotated_page_width": 1728.0,
      "unrotated_page_height": 2592.0,
      "extraction_status": "success",
      "note_sections": [...],
      "page_type": "drawing",
      "spec_content": null,
      "sheet_s3_uri": "s3://bucket/sheets/sheet_001.pdf",
      "sheet_title": "MECHANICAL FLOOR PLAN",
      "sheet_number": "M101",
      "sheet_upload_error": null,
      "sheet_discipline": "mechanical",           // NEW
      "sheet_discipline_confidence": "high"       // NEW
    }
  ],
  "extraction_metadata": {...}
}
```

### Note Object Structure

```json
{
  "note_number": 1,
  "category": "GENERAL NOTES",
  "text": "BIDDING CONTRACTORS ARE TO REVIEW ALL ARCHITECTURAL, MECHANICAL, ELECTRICAL, CIVIL AND STRUCTURAL DRAWINGS PRIOR TO SUBMITTING TENDER PRICE.",
  "drawing_references": [],
  "rotated_bounding_box": [1750.74, 208.11, 2071.55, 235.23],
  "unrotated_bounding_box": [1492.77, 1750.74, 1519.89, 2071.55],
  "source_blocks": [...],
  "disciplines": ["general", "mechanical", "electrical", "civil", "structural"],  // NEW
  "discipline_confidence": "high"                                                  // NEW
}
```

## Examples

### Example 1: Single-Discipline Note

A note about sanitary lines on a mechanical sheet:

```json
{
  "note_number": 5,
  "text": "WHERE NOT SHOWN, SANITARY LINES TO BE 100mmØ @ 1.0% OR SIZE OF FIXTURE.",
  "disciplines": ["plumbing"],
  "discipline_confidence": "high"
}
```

### Example 2: Cross-Discipline Note

A note mentioning plumbing on a mechanical sheet:

```json
{
  "note_number": 4,
  "text": "PLUMBING LINES ETC. ARE SHOWN DIAGRAMMATICALLY, FINAL LOCATIONS, ROUTING ETC. TO BE CO-ORDINATE ON SITE.",
  "disciplines": ["plumbing", "mechanical"],
  "discipline_confidence": "high"
}
```

### Example 3: Multi-Discipline Coordination Note

A general note that references multiple trades:

```json
{
  "note_number": 1,
  "text": "BIDDING CONTRACTORS ARE TO REVIEW ALL ARCHITECTURAL, MECHANICAL, ELECTRICAL, CIVIL AND STRUCTURAL DRAWINGS PRIOR TO SUBMITTING TENDER PRICE.",
  "disciplines": ["general", "mechanical", "electrical", "civil", "structural"],
  "discipline_confidence": "high"
}
```

### Example 4: Fallback to Sheet Discipline

When `classify_disciplines_with_llm=false` (default), notes inherit the sheet discipline:

```json
{
  "note_number": 2,
  "text": "LOCATIONS OF SERVICES ARE APPROXIMATE, VERIFY ON SITE.",
  "disciplines": ["mechanical"],
  "discipline_confidence": "low"
}
```

Note the `"low"` confidence indicates this was a fallback, not an LLM classification.

## Integration Notes

1. **Filtering by discipline**: Use `disciplines` array to filter notes for specific trades. Remember a note can belong to multiple disciplines.

2. **Confidence thresholds**: Consider using `discipline_confidence` to weight or filter results:
   - `"high"`: Strong match from LLM or prefix
   - `"medium"`: Reasonable inference
   - `"low"`: Fallback to sheet discipline (no LLM verification)

3. **Null handling**: Both `sheet_discipline` and `disciplines` can be empty/null if classification fails or is disabled.

4. **Cost considerations**: `classify_disciplines_with_llm=true` makes an additional LLM call per page with notes. Keep this disabled for bulk processing unless per-note classification is needed.

## TypeScript Types

```typescript
type Discipline =
  | "general" | "hazardous_materials" | "survey_mapping" | "geotechnical"
  | "civil" | "landscape" | "structural" | "architectural" | "interiors"
  | "equipment" | "fire_protection" | "plumbing" | "process" | "mechanical"
  | "electrical" | "distributed_energy" | "telecommunications" | "resource"
  | "other" | "contractor_shop" | "operations";

type Confidence = "high" | "medium" | "low";

interface ExtractedNote {
  note_number: number;
  category: string;
  text: string;
  drawing_references: DrawingReference[];
  rotated_bounding_box: [number, number, number, number];
  unrotated_bounding_box: [number, number, number, number];
  source_blocks: [number, number, number, number][];
  disciplines: Discipline[];           // NEW
  discipline_confidence: Confidence | null;  // NEW
}

interface PageResult {
  page_number: number;
  extraction_status: "success" | "no_notes_found" | "error" | "partial";
  note_sections: NoteSection[];
  sheet_title: string | null;
  sheet_number: string | null;
  sheet_discipline: Discipline | null;           // NEW
  sheet_discipline_confidence: Confidence | null; // NEW
  // ... other fields
}
```
