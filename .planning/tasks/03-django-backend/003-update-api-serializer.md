# Task: Update API Serializer

## Task Title
Update AiGeneratedLogSerializer to include log_data field

## Parent Feature
Django Backend - API Integration

## Complexity
Medium

## Estimated Time
3 hours

## Dependencies
- 01-backend-foundation/002-update-aigeneratedlog-model.md

## Description
Update the `AiGeneratedLogSerializer` to include the new `log_data` field and handle feature flag logic to return appropriate data format based on flag status.

## Implementation Details

### Files to Modify
- `the_link_django/apps/deliverables/serializers/specgpt.py` - Update AiGeneratedLogSerializer

### Code Patterns to Follow
- Follow existing serializer field patterns
- Use feature flag utility function for conditional logic
- Maintain existing API contract
- Add proper field validation and documentation

### Implementation Steps
1. Import the feature flag utility function:
   ```python
   from apps.utils.feature_flags import is_inspection_log_use_data_tables_feature_flag_active
   ```
2. Add `log_data` field to serializer:
   ```python
   log_data = serializers.JSONField(required=False, allow_null=True)
   ```
3. Add method to determine data format based on feature flag:
   ```python
   def get_data_format(self, obj):
       """Return appropriate data format based on feature flag status."""
       request = self.context.get('request')
       if not request:
           return 'markdown'  # Default to markdown if no request context
       
       use_data_tables = is_inspection_log_use_data_tables_feature_flag_active(
           request.user, request.team
       )
       
       if use_data_tables and obj.log_data:
           return 'structured'
       else:
           return 'markdown'
   ```
4. Update serializer to conditionally include fields based on format
5. Add proper field validation and error handling

### Serializer Field Configuration
- **log_data**: JSONField, optional, nullable
- **data_format**: Computed field indicating which format to use
- **Conditional Fields**: Include appropriate fields based on format

### API Response Structure
```json
{
  "id": 123,
  "project": 1,
  "project_version": 1,
  "log_type": "inspection_log",
  "log_status": "SUCCESS",
  "log_table": "...",  // Always included for backward compatibility
  "log_data": {...},   // Included when feature flag active and data available
  "data_format": "structured",  // "structured" or "markdown"
  "created_at": "2024-01-01T00:00:00Z",
  "project_name": "Test Project",
  "project_version_number": "1.0"
}
```

## Acceptance Criteria
- [ ] `log_data` field added to serializer
- [ ] Feature flag logic integrated for data format determination
- [ ] API returns appropriate data format based on flag status
- [ ] Backward compatibility maintained for existing API consumers
- [ ] Proper field validation and error handling
- [ ] `data_format` field indicates which format is being used
- [ ] No breaking changes to existing API contract
- [ ] Serializer handles both structured and markdown data correctly

## Testing Approach
- [ ] Test serializer with feature flag active and structured data
- [ ] Test serializer with feature flag active but no structured data
- [ ] Test serializer with feature flag inactive (existing behavior)
- [ ] Test field validation for log_data
- [ ] Test data_format field computation
- [ ] Test backward compatibility with existing API consumers
- [ ] Test error handling for invalid data
- [ ] Run existing serializer tests to ensure no regressions

## Quick Status
This task maintains operational Quick by:
- Following existing serializer patterns and field definitions
- Maintaining backward compatibility with existing API contract
- Adding optional fields that don't break existing functionality
- Providing clear indication of data format being used
- No changes to existing field behavior
