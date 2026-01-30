# Discipline Classification Backend Integration

## Overview

Integrate the new discipline classification fields from the drawing notes extraction Lambda into the Django backend. This enables filtering notes by construction trade (mechanical, plumbing, electrical, etc.).

## Changes

### 1. Model Changes

**File:** `apps/deliverables/models.py`

#### New Enums

```python
class Discipline(models.TextChoices):
    GENERAL = "general", "General"
    HAZARDOUS_MATERIALS = "hazardous_materials", "Hazardous Materials"
    SURVEY_MAPPING = "survey_mapping", "Survey/Mapping"
    GEOTECHNICAL = "geotechnical", "Geotechnical"
    CIVIL = "civil", "Civil"
    LANDSCAPE = "landscape", "Landscape"
    STRUCTURAL = "structural", "Structural"
    ARCHITECTURAL = "architectural", "Architectural"
    INTERIORS = "interiors", "Interiors"
    EQUIPMENT = "equipment", "Equipment"
    FIRE_PROTECTION = "fire_protection", "Fire Protection"
    PLUMBING = "plumbing", "Plumbing"
    PROCESS = "process", "Process"
    MECHANICAL = "mechanical", "Mechanical"
    ELECTRICAL = "electrical", "Electrical"
    DISTRIBUTED_ENERGY = "distributed_energy", "Distributed Energy"
    TELECOMMUNICATIONS = "telecommunications", "Telecommunications"
    RESOURCE = "resource", "Resource"
    OTHER = "other", "Other"
    CONTRACTOR_SHOP = "contractor_shop", "Contractor/Shop"
    OPERATIONS = "operations", "Operations"


class DisciplineConfidence(models.TextChoices):
    HIGH = "high", "High"
    MEDIUM = "medium", "Medium"
    LOW = "low", "Low"
```

#### DrawingPage - Add Fields

```python
sheet_discipline = models.CharField(
    max_length=32,
    choices=Discipline.choices,
    null=True,
    blank=True,
    help_text="Primary discipline of the sheet based on sheet number prefix (e.g., M-101 → mechanical)",
)
sheet_discipline_confidence = models.CharField(
    max_length=16,
    choices=DisciplineConfidence.choices,
    null=True,
    blank=True,
    help_text="Confidence level of the discipline classification",
)
```

#### DrawingNote - Add Fields

```python
from django.contrib.postgres.fields import ArrayField

disciplines = ArrayField(
    models.CharField(max_length=32, choices=Discipline.choices),
    default=list,
    blank=True,
    help_text="List of disciplines this note relates to (can be multiple)",
)
discipline_confidence = models.CharField(
    max_length=16,
    choices=DisciplineConfidence.choices,
    null=True,
    blank=True,
    help_text="Confidence level of the discipline classification",
)
```

### 2. Webhook Handler Changes

**File:** `apps/deliverables/views/drawing_views.py`

Update `_create_drawing_records()` to extract new fields from Lambda payload.

#### DrawingPage creation:

```python
DrawingPage(
    # ... existing fields ...
    sheet_discipline=page_data.get("sheet_discipline"),
    sheet_discipline_confidence=page_data.get("sheet_discipline_confidence"),
)
```

#### DrawingNote creation:

```python
DrawingNote(
    # ... existing fields ...
    disciplines=note_data.get("disciplines", []),
    discipline_confidence=note_data.get("discipline_confidence"),
)
```

### 3. Serializer Changes

**File:** `apps/deliverables/serializers/drawing_serializers.py`

Update `DrawingNoteReadSerializer`:

```python
class DrawingNoteReadSerializer(serializers.ModelSerializer):
    # ... existing fields ...
    sheet_discipline = serializers.SerializerMethodField()

    def get_sheet_discipline(self, obj):
        return obj.section.page.sheet_discipline

    class Meta:
        model = DrawingNote
        fields = [
            # ... existing fields ...
            "sheet_discipline",
            "disciplines",
        ]
```

### 4. API Filter Changes

**File:** `apps/deliverables/views/drawing_views.py`

Update `DrawingNoteViewSet` to support discipline filtering:

```python
# In get_queryset() or list():
sheet_discipline = request.query_params.get("sheet_discipline")
disciplines = request.query_params.get("disciplines")

if sheet_discipline:
    queryset = queryset.filter(section__page__sheet_discipline=sheet_discipline)

if disciplines:
    queryset = queryset.filter(disciplines__contains=[disciplines])
```

**Example API calls:**
- `GET /api/deliverables/projects/123/drawing-notes/?sheet_discipline=mechanical`
- `GET /api/deliverables/projects/123/drawing-notes/?disciplines=plumbing`

### 5. Migration

Create migration adding 4 fields:
- `DrawingPage.sheet_discipline`
- `DrawingPage.sheet_discipline_confidence`
- `DrawingNote.disciplines`
- `DrawingNote.discipline_confidence`

All fields are nullable/optional for backward compatibility.

## Files Changed

| File | Changes |
|------|---------|
| `apps/deliverables/models.py` | Add `Discipline` and `DisciplineConfidence` enums; add fields to `DrawingPage` and `DrawingNote` |
| `apps/deliverables/views/drawing_views.py` | Update `_create_drawing_records()` to extract new fields; add filters to `DrawingNoteViewSet` |
| `apps/deliverables/serializers/drawing_serializers.py` | Add `sheet_discipline` and `disciplines` to response |
| `apps/deliverables/migrations/00XX_*.py` | New migration for the 4 fields |

## Notes

- Confidence fields are stored in the database for debugging/analysis but not exposed in the API
- Invalid discipline values from Lambda will raise IntegrityError (intentional - we want to know about mismatches)
- The `disciplines` ArrayField uses PostgreSQL's `__contains` lookup for filtering
