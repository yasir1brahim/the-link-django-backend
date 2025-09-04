# Task: Update Lambda Data Generation Logic

## Task Title
Modify Lambda to return structured data when flag is active

## Parent Feature
Lambda Updates - Data Generation

## Complexity
High

## Estimated Time
6 hours

## Dependencies
- 02-lambda-updates/001-update-lambda-parameters.md

## Description
Update the Lambda function to conditionally return structured JSON data instead of markdown when the `use_data_tables` flag is active. The function should maintain existing markdown generation when the flag is inactive.

## Implementation Details

### Files to Modify
- `LogManager/glue_jobs/generate_ai_log/lambda/generate_ai_log.py` - Update data generation logic

### Code Patterns to Follow
- Use existing `convert_to_markdown_table` function for fallback
- Follow existing data structure patterns for inspection logs and owner deliverables
- Maintain existing error handling and logging
- Use existing Pydantic models for data validation

### Implementation Steps
1. Update the `generate_ai_log_from_spec_section` function to accept `use_data_tables` parameter
2. Modify the function to return structured data when flag is active:
   ```python
   if use_data_tables:
       # Return structured data based on log_type
       if log_type == "inspection_log":
           return InspectionLog(results=chunk_results).model_dump()
       elif log_type == "owner_deliverables":
           return OwnerDeliverablesLog(results=chunk_results).model_dump()
   else:
       # Return markdown table (existing behavior)
       return convert_to_markdown_table(chunk_results, log_row_model)
   ```
3. Update the `lambda_handler` to pass the parameter to the generation function
4. Update the result dictionary to include both structured data and markdown
5. Ensure proper error handling for both data formats

### Data Format Changes
- **When flag active**: Return structured JSON matching Pydantic models
- **When flag inactive**: Return markdown table string (existing behavior)
- **Fallback**: Always generate markdown for backward compatibility

### Result Structure
```json
{
  "s3_key": "...",
  "structured_data": {...},  // When use_data_tables is true
  "markdown_table": "...",   // Always included for fallback
  "use_data_tables": true
}
```

## Acceptance Criteria
- [ ] Lambda returns structured data when `use_data_tables: true`
- [ ] Lambda returns markdown when `use_data_tables: false`
- [ ] Both inspection logs and owner deliverables logs work correctly
- [ ] Structured data matches Pydantic model schemas
- [ ] Markdown fallback is always generated
- [ ] No breaking changes to existing functionality
- [ ] Error handling works for both data formats
- [ ] Result includes both data formats for flexibility

## Testing Approach
- [ ] Test with `use_data_tables: true` for inspection logs
- [ ] Test with `use_data_tables: true` for owner deliverables logs
- [ ] Test with `use_data_tables: false` (existing behavior)
- [ ] Test without parameter (backward compatibility)
- [ ] Verify structured data matches expected schema
- [ ] Verify markdown table is properly formatted
- [ ] Test error scenarios for both formats
- [ ] Test with sample data from both log types

## Quick Status
This task maintains operational Quick by:
- Maintaining existing markdown generation as fallback
- Using established Pydantic models for data validation
- Following existing error handling patterns
- Providing both data formats for maximum compatibility
- No changes to existing API contracts
