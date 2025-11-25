## Architecture (Updated)

### System Architecture

**Component Integration:**
- Leverage Apryse's native sticky note annotations and reply system
- Extend existing `projectLogsReader.js` to manage note annotations alongside highlight rectangles
- Maintain a normalized cache of full `ExtractedData` records inside `DocumentHighlighter` so rectangle and sticky annotations share one source of truth
- Sync note state bidirectionally between backend API and Apryse annotations
- Use CustomData to track ExtractedData ID and note IDs on annotations

**Data Flow:**
```
Backend (Django)
    ↓ (GET ExtractedData with notes)
    ↓
React State (DocumentHighlighter ExtractedData cache)
    ↓ (Pass derived annotation props to projectLogsReader)
    ↓
Apryse Annotations
    - RectangleAnnotation (highlights - existing)
    - StickyAnnotation (note parent - NEW)
    - StickyAnnotation replies (individual notes - NEW)
    ↑ (annotationChanged events)
    ↑
Event Handlers (NEW)
    ↑ (POST/PATCH/DELETE to backend)
    ↑
Backend API
```
