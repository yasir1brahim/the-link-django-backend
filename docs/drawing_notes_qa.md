# Drawing Notes Extraction QA Plan

## Overview
This feature extracts text labeled as drawing notes from uploaded drawing PDFs and displays the results in the Drawings UI. The goal is to automatically parse note sections (e.g., "GENERAL NOTES", "DRAINAGE NOTES") and show the full note text with a synced PDF viewer so QA can validate that the correct notes were captured and positioned.

## Test Plan
### Core Flows
- [ ] Upload a single drawing PDF that contains clearly labeled note sections (e.g., GENERAL NOTES).
- [ ] Verify the drawing shows in the table with status transitions (PENDING -> PROCESSING -> SUCCESS or PARTIAL_SUCCESS).
- [ ] Confirm notes appear in the table and the full note text is visible (no truncation).
- [ ] Click a note row and confirm the PDF viewer jumps to the correct note annotation and it is visible in the viewport.
- [ ] Scroll the notes table and confirm the PDF viewer stays fixed.

### Content Accuracy
- [ ] Verify each note section header matches the drawing (e.g., "DRAINAGE NOTES").
- [ ] Validate the extracted note text matches the drawing text for all notes.
- [ ] Confirm drawing references (if present in text) appear in the note details.

### Batch and Versioning
- [ ] Upload multiple drawing files in a single request and confirm each gets its own extraction.
- [ ] Upload the same drawing again and confirm a new extraction is created without breaking the existing notes.
- [ ] Test with a project that has multiple versions and confirm notes are attached to the correct version.

### Edge Cases
- [ ] Upload a drawing with no notes and confirm status is SUCCESS or PARTIAL_SUCCESS with zero notes.
- [ ] Upload a multi-page drawing with both spec-like pages and drawing pages; confirm notes are extracted only where appropriate.
- [ ] Test a rotated drawing (90/180/270) and confirm bounding boxes align with the correct text.
- [ ] Test a large PDF (many pages) and confirm processing completes without UI lockups.
- [ ] Trigger a failure (bad file or revoke lambda access) and confirm status moves to FAILED and the UI shows no notes.

### Regression Checks
- [ ] Submittal log viewer still works as before (no regression).
