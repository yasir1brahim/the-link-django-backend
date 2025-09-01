# Task: Update Webhook Handler

## Task Title
Handle structured data in webhook callback

## Parent Feature
Django Backend - Webhook Integration

## Complexity
Medium

## Estimated Time
4 hours

## Dependencies
- 01-backend-foundation/002-update-aigeneratedlog-model.md
- 02-lambda-updates/002-update-lambda-data-generation.md

## Description
Update the webhook handler to store structured data in the `log_data` field when the feature flag is active, and convert structured data to markdown for fallback storage in the existing `log_table` field.

## Implementation Details

### Files to Modify
- `the_link_django/apps/deliverables/views/specgpt_views.py` - Update `ai_log_generation_webhook` function

### Code Patterns to Follow
- Use existing `convert_to_markdown_table` utility function
- Follow existing webhook handling patterns
- Maintain existing error handling and logging
- Use existing Pydantic models for data validation

### Implementation Steps
1. Import the `convert_to_markdown_table` utility function:
   ```python
   from apps.deliverables.utils import convert_to_markdown_table
   ```
2. Update the webhook handler to process structured data:
   ```python
   # Check if structured data is available
   if request_data.get('structured_data'):
       # Store structured data in log_data field
       log_obj.log_data = request_data['structured_data']
       
       # Convert to markdown for fallback
       if request_data['log_type'] == 'inspection_log':
           markdown_table = convert_to_markdown_table(
               request_data['structured_data']['results'], 
               InspectionLogRow
           )
       elif request_data['log_type'] == 'owner_deliverables':
           markdown_table = convert_to_markdown_table(
               request_data['structured_data']['results'], 
               OwnerDeliverablesRow
           )
       
       # Store markdown in log_table for fallback
       log_obj.log_table = markdown_table
   else:
       # Fallback to existing markdown table
       log_obj.log_table = request_data.get('table', '')
   ```
3. Update the `AiLogGenerationRequest` TypedDict to include structured data
4. Add proper error handling for structured data processing
5. Add logging for structured data handling

### Webhook Payload Update
The webhook should handle both data formats:
```json
{
  "new_status": "SUCCESS",
  "ai_generated_log_id": "...",
  "project_id": "...",
  "project_version_id": "...",
  "log_type": "inspection_log",
  "structured_data": {
    "results": [...]
  },
  "table": "...",  // Markdown fallback
  "use_data_tables": true
}
```

### Data Storage Strategy
- **log_data field**: Store structured JSON data when available
- **log_table field**: Store markdown table (either from Lambda or converted from structured data)
- **Fallback**: Always ensure log_table has markdown for backward compatibility

## Acceptance Criteria
- [ ] Webhook handler processes structured data when available
- [ ] Structured data stored in `log_data` field
- [ ] Markdown table stored in `log_table` field for fallback
- [ ] `convert_to_markdown_table` utility used for conversion
- [ ] Both inspection logs and owner deliverables logs handled correctly
- [ ] No breaking changes to existing functionality
- [ ] Proper error handling for structured data processing
- [ ] Logging added for structured data handling
- [ ] Backward compatibility maintained when structured data not available

## Testing Approach
- [ ] Test webhook with structured data for inspection logs
- [ ] Test webhook with structured data for owner deliverables logs
- [ ] Test webhook with markdown table only (existing behavior)
- [ ] Test conversion from structured data to markdown
- [ ] Verify both fields are populated correctly
- [ ] Test error handling for invalid structured data
- [ ] Test fallback behavior when structured data missing
- [ ] Run existing webhook tests to ensure no regressions

## Quick Status
This task maintains operational Quick by:
- Using existing utility function for markdown conversion
- Maintaining backward compatibility with existing log_table field
- Following established webhook handling patterns
- Providing fallback to markdown for all scenarios
- No changes to existing API contracts
