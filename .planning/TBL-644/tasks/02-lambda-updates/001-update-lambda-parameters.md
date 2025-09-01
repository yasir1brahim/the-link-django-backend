# Task: Update Lambda Function Parameters

## Task Title
Add feature flag parameter to Lambda function

## Parent Feature
Lambda Updates - Parameter Integration

## Complexity
Medium

## Estimated Time
4 hours

## Dependencies
- 01-backend-foundation/001-add-feature-flag-constant.md

## Description
Modify the Lambda function to accept and process the `use_data_tables` feature flag parameter. This will enable the Lambda function to conditionally generate structured data or markdown based on the flag status.

## Implementation Details

### Files to Modify
- `LogManager/glue_jobs/generate_ai_log/lambda/generate_ai_log.py` - Update lambda_handler function

### Code Patterns to Follow
- Follow existing parameter handling patterns in the Lambda function
- Add parameter to the event parsing section
- Include parameter in function documentation
- Maintain backward compatibility for existing calls

### Implementation Steps
1. Update the `lambda_handler` function to accept `use_data_tables` parameter:
   ```python
   # Add to parsed_event extraction section
   use_data_tables = parsed_event.get('use_data_tables', False)
   ```
2. Add parameter to the function documentation
3. Update the result dictionary to include the parameter
4. Ensure parameter is properly passed through the function
5. Add parameter validation if needed

### Parameter Configuration
- **Parameter Name**: `use_data_tables`
- **Type**: `bool`
- **Default**: `False` (maintains backward compatibility)
- **Required**: No (optional parameter)
- **Description**: Controls whether to return structured data or markdown

### Event Structure Update
The Lambda function should accept events with the new parameter:
```json
{
  "project_id": "...",
  "project_version_id": "...",
  "log_type": "...",
  "use_data_tables": true,
  // ... other existing parameters
}
```

## Acceptance Criteria
- [ ] Lambda function accepts `use_data_tables` parameter
- [ ] Parameter defaults to `False` for backward compatibility
- [ ] Parameter is properly extracted from event
- [ ] Parameter is included in result dictionary
- [ ] No breaking changes to existing functionality
- [ ] Function handles missing parameter gracefully
- [ ] Parameter is documented in function comments

## Testing Approach
- [ ] Test Lambda function with `use_data_tables: true`
- [ ] Test Lambda function with `use_data_tables: false`
- [ ] Test Lambda function without the parameter (backward compatibility)
- [ ] Test parameter extraction and validation
- [ ] Verify parameter is included in result
- [ ] Test with existing event structure
- [ ] Test error handling for invalid parameter values

## Quick Status
This task maintains operational Quick by:
- Adding optional parameter that doesn't break existing functionality
- Maintaining backward compatibility with existing calls
- Following established Lambda function patterns
- Parameter defaults to safe value (False)
- No changes to core processing logic yet
