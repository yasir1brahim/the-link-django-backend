# AI Generated Log Export Error Fix

## Problem

The export endpoint for AI generated logs was failing with an internal server error when trying to export owner deliverables data. The error was:

```
ValueError: Cannot convert [{'x': 180.0019073486328, 'y': 234.852783203125, ...}] to Excel
```

### Root Cause

The `pdf_locations` field in the log data contained a list of dictionaries (JSON data representing PDF coordinates for highlighting). The `openpyxl` library cannot directly write complex Python data structures (lists, dicts) to Excel cells.

## Solution

### 1. Added Comprehensive Logging
- Added `[AI_LOG_EXPORT][log_id={pk}]` tag to all log messages for easy filtering
- Added detailed logging at every step of the export process
- Added full traceback logging for errors

### 2. Fixed Complex Data Type Handling
- Added automatic conversion of lists and dicts to JSON strings before writing to Excel
- Added error handling for serialization failures with fallback to `str()`

### 3. Filtered Out Metadata Fields
- Excluded internal/metadata fields (`pdf_locations`, `metadata`, `internal_id`, `source_data`) from Excel exports
- These fields are not useful in exported spreadsheets and can cause issues

### 4. Fixed Log Type Matching
- Updated log type matching to handle both variants: `owner_deliverables_log` and `owner_deliverables`
- Some logs in the system don't have the `_log` suffix

### 5. Added Comprehensive Tests
- Added `test_export_handles_complex_data_types_in_fields()` - tests export with `pdf_locations` field
- Added `test_export_handles_nested_dicts_in_fields()` - tests export with nested dictionary data
- Total of 11 test cases for the export endpoint

## Code Changes

### Modified Files

1. **`apps/deliverables/views/specgpt_views.py`**
   - Added logging and traceback imports
   - Added `log_prefix` variable with `[AI_LOG_EXPORT]` tag
   - Added comprehensive logging throughout export method
   - Added complex data type serialization (lines 797-803)
   - Added metadata field exclusion (lines 778-781)
   - Fixed log type matching to handle variants (lines 760, 765)

2. **`apps/deliverables/tests/test_ai_generated_log_views.py`**
   - Added `test_export_handles_complex_data_types_in_fields()` test
   - Added `test_export_handles_nested_dicts_in_fields()` test

## How to Filter Logs in QA

Now you can easily filter export-related logs:

```bash
# All export logs
grep "AI_LOG_EXPORT"

# Specific log ID
grep "AI_LOG_EXPORT.*log_id=149"

# Only errors
grep "AI_LOG_EXPORT.*ERROR"
```

## Expected Behavior After Fix

1. ✅ Exports with `pdf_locations` field will succeed
2. ✅ Complex data types (lists, dicts) are converted to JSON strings
3. ✅ Metadata fields are excluded from exports
4. ✅ Both `owner_deliverables_log` and `owner_deliverables` log types work correctly
5. ✅ Detailed logs show exactly where issues occur if any problems arise

## Testing

Run the export tests:

```bash
docker-compose exec web python manage.py test apps.deliverables.tests.test_ai_generated_log_views.AiGeneratedLogExportTests
```

All tests should pass, including the new tests for complex data types.

## Deployment Notes

After deploying to QA:
1. Try exporting log ID 149 again
2. It should now succeed
3. The `pdf_locations` field will be excluded from the export (or converted to JSON string if dynamic headers are used)
4. Check logs with `grep "AI_LOG_EXPORT.*log_id=149"` to see detailed execution flow

