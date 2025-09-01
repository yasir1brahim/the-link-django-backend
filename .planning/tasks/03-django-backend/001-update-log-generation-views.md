# Task: Update Log Generation Views

## Task Title
Pass feature flag to Lambda function in Django views

## Parent Feature
Django Backend - View Integration

## Complexity
Medium

## Estimated Time
4 hours

## Dependencies
- 01-backend-foundation/003-add-feature-flag-utility.md
- 02-lambda-updates/001-update-lambda-parameters.md

## Description
Modify Django views to check the feature flag status and pass the `use_data_tables` parameter to the Lambda function when generating inspection logs and owner deliverables logs.

## Implementation Details

### Files to Modify
- `the_link_django/apps/deliverables/views/specgpt_views.py` - Update log generation methods

### Code Patterns to Follow
- Use the new feature flag utility function
- Follow existing Lambda invocation patterns
- Maintain existing error handling
- Add proper logging for feature flag status

### Implementation Steps
1. Import the new feature flag utility function:
   ```python
   from apps.utils.feature_flags import is_inspection_log_use_data_tables_feature_flag_active
   ```
2. Update the `generate_general_log` method to check feature flag and pass parameter:
   ```python
   # Check feature flag status
   use_data_tables = is_inspection_log_use_data_tables_feature_flag_active(request.user, request.team)
   
   # Add to Lambda payload
   lambda_payload = {
       'project_id': project_id,
       'project_version_id': project_version_id,
       'log_type': promptlayer_template_name,
       'use_data_tables': use_data_tables,
       # ... existing parameters
   }
   ```
3. Update both `generate_inspection_log` and `generate_owner_deliverables_log` methods
4. Add logging to track feature flag usage
5. Ensure proper error handling for feature flag checks

### Feature Flag Integration
- **Check Location**: Before Lambda invocation
- **Parameter Name**: `use_data_tables`
- **Default Behavior**: `False` when flag is inactive
- **Logging**: Track when feature flag is active/inactive

### Lambda Payload Update
The Lambda function call should include the new parameter:
```python
requests.post(
    settings.GENERATE_LOG_LAMBDA_FUNCTION_URL,
    json={
        'project_id': project_id,
        'project_version_id': project_version_id,
        'log_type': promptlayer_template_name,
        'use_data_tables': use_data_tables,  # New parameter
        'bucket': s3_bucket,
        'spec_sections': spec_sections,
        'callback_url': settings.BACKEND_AI_LOG_CALLBACK_URL,
        'ai_generated_log_id': str(processing_log.id) if processing_log else None,
        # ... other existing parameters
    }
)
```

## Acceptance Criteria
- [ ] Feature flag utility function imported and used
- [ ] `use_data_tables` parameter passed to Lambda function
- [ ] Both inspection log and owner deliverables log generation updated
- [ ] Feature flag status properly checked before Lambda invocation
- [ ] No breaking changes to existing functionality
- [ ] Proper error handling for feature flag checks
- [ ] Logging added for feature flag usage
- [ ] Lambda payload includes new parameter

## Testing Approach
- [ ] Test with feature flag active for inspection logs
- [ ] Test with feature flag active for owner deliverables logs
- [ ] Test with feature flag inactive (existing behavior)
- [ ] Test feature flag utility function integration
- [ ] Verify Lambda payload includes correct parameter
- [ ] Test error handling for feature flag utility
- [ ] Test logging of feature flag status
- [ ] Run existing view tests to ensure no regressions

## Quick Status
This task maintains operational Quick by:
- Following existing view patterns and error handling
- Adding optional parameter that doesn't break existing functionality
- Maintaining backward compatibility when flag is inactive
- Proper logging for debugging and monitoring
- No changes to existing API contracts
