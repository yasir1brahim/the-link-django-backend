# Task: Add Feature Flag to React Context

## Task Title
Add inspection log feature flag to React feature flags context

## Parent Feature
Frontend Updates - Feature Flag Integration

## Complexity
Low

## Estimated Time
2 hours

## Dependencies
- None

## Description
Add a new flag check function to the React FeatureFlagsContext to support checking the "inspection_log_use_data_tables" feature flag status.

## Implementation Details

### Files to Modify
- `the-link-web-app/src/contexts/FeatureFlagsContext.js` - Add new flag check function

### Code Patterns to Follow
- Follow existing flag check function patterns
- Use consistent naming convention
- Add proper JSDoc documentation
- Include in convenience methods section

### Implementation Steps
1. Add new flag check function to FeatureFlagsContext:
   ```javascript
   const isInspectionLogUseDataTablesFlagActive = (teamId) => isFlagActive(INSPECTION_LOG_USE_DATA_TABLES_FEATURE_FLAG_NAME, teamId);
   ```
2. Add constant for feature flag name:
   ```javascript
   const INSPECTION_LOG_USE_DATA_TABLES_FEATURE_FLAG_NAME = 'inspection_log_use_data_tables';
   ```
3. Add to convenience methods section
4. Add proper JSDoc documentation
5. Export the new function

### Function Signature
- **Name**: `isInspectionLogUseDataTablesFlagActive`
- **Parameters**: `teamId` (optional)
- **Return Type**: `boolean`
- **Behavior**: Check if feature flag is active for user or team

### Usage Example
```javascript
import { useFeatureFlags } from '../contexts/FeatureFlagsContext';

const MyComponent = ({ teamId }) => {
    const { isInspectionLogUseDataTablesFlagActive } = useFeatureFlags();
    
    const shouldUseDataTables = isInspectionLogUseDataTablesFlagActive(teamId);
    
    return (
        <div>
            {shouldUseDataTables ? (
                <SortableTable data={structuredData} />
            ) : (
                <MarkdownTable data={markdownData} />
            )}
        </div>
    );
};
```

## Acceptance Criteria
- [ ] New flag check function added to FeatureFlagsContext
- [ ] Function follows existing naming and signature patterns
- [ ] Function returns correct boolean value based on flag status
- [ ] Function handles edge cases (missing teamId, etc.)
- [ ] Proper JSDoc documentation included
- [ ] Function is exported and can be imported
- [ ] No breaking changes to existing functionality
- [ ] Function can be used throughout the application

## Testing Approach
- [ ] Test function with user who has flag enabled
- [ ] Test function with team that has flag enabled
- [ ] Test function with neither user nor team having flag
- [ ] Test function with missing teamId parameter
- [ ] Test function import and usage in components
- [ ] Run existing feature flag tests to ensure no regressions
- [ ] Test integration with existing flag checking logic

## Quick Status
This task maintains operational Quick by:
- Following established patterns to minimize risk
- Adding function that doesn't affect existing functionality
- Proper error handling and edge case management
- Immediate rollback possible by removing the function
- No changes to existing code paths
