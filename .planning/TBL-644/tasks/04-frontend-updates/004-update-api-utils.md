# Task: Update API Utility Functions

## Task Title
Update API utility functions to handle sorting

## Parent Feature
Frontend Updates - API Integration

## Complexity
Low

## Estimated Time
2 hours

## Dependencies
- 03-django-backend/004-add-sorting-support.md

## Description
Update API utility functions to include sorting parameters when making requests to the backend API for log data.

## Implementation Details

### Files to Modify
- `the-link-web-app/src/components/SpecGpt/utils/apiUtils.js` - Update API utility functions

### Code Patterns to Follow
- Follow existing API utility function patterns
- Maintain existing function signatures for backward compatibility
- Add optional sorting parameters
- Use existing error handling patterns

### Implementation Steps
1. Update existing API utility functions to accept sorting parameters:
   ```javascript
   const fetchAiGeneratedLogDetail = async (projectId, logId, orderBy = null, order = 'desc') => {
       const params = new URLSearchParams();
       if (orderBy) {
           params.append('order_by', orderBy);
           params.append('order', order);
       }
       
       const response = await fetch(`/api/projects/${projectId}/ai-generated-logs/${logId}/?${params.toString()}`);
       return response.json();
   };
   ```
2. Add new utility function for sorted data:
   ```javascript
   const fetchSortedLogData = async (projectId, logId, orderBy, order = 'desc') => {
       const params = new URLSearchParams({
           order_by: orderBy,
           order: order
       });
       
       const response = await fetch(`/api/projects/${projectId}/ai-generated-logs/${logId}/?${params.toString()}`);
       return response.json();
   };
   ```
3. Update existing functions to maintain backward compatibility
4. Add proper error handling for sorting parameters
5. Add JSDoc documentation for new parameters

### Function Updates
- **fetchAiGeneratedLogDetail**: Add optional sorting parameters
- **fetchAiGeneratedLogs**: Add optional sorting parameters
- **fetchSortedLogData**: New function for sorted data requests

### Parameter Structure
- **orderBy**: Field to sort by (e.g., 'spec_section_number', 'responsible_party')
- **order**: Sort direction ('asc' or 'desc')
- **Default**: No sorting (existing behavior)

### API Call Examples
```javascript
// Existing behavior (no sorting)
const logData = await fetchAiGeneratedLogDetail(projectId, logId);

// With sorting
const sortedLogData = await fetchAiGeneratedLogDetail(projectId, logId, 'spec_section_number', 'asc');

// New function for sorted data
const sortedData = await fetchSortedLogData(projectId, logId, 'responsible_party', 'desc');
```

## Acceptance Criteria
- [ ] Existing API utility functions updated to accept sorting parameters
- [ ] New fetchSortedLogData function created
- [ ] Backward compatibility maintained for existing function calls
- [ ] Sorting parameters properly passed to backend API
- [ ] Proper error handling for sorting parameters
- [ ] JSDoc documentation added for new parameters
- [ ] No breaking changes to existing functionality
- [ ] Functions handle invalid sorting parameters gracefully

## Testing Approach
- [ ] Test existing functions without sorting parameters (backward compatibility)
- [ ] Test functions with sorting parameters
- [ ] Test with valid sorting field names
- [ ] Test with invalid sorting parameters (graceful fallback)
- [ ] Test error handling for API failures
- [ ] Test integration with LogViewer component
- [ ] Run existing API utility tests to ensure no regressions
- [ ] Test with both inspection logs and owner deliverables logs

## Quick Status
This task maintains operational Quick by:
- Following existing API utility patterns and error handling
- Maintaining backward compatibility with existing function calls
- Adding optional parameters that don't break existing functionality
- Providing graceful fallback for invalid parameters
- No changes to existing API contracts
