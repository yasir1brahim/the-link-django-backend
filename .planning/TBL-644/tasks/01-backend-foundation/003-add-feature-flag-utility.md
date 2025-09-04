# Task: Add Feature Flag Utility Function

## Task Title
Add inspection log feature flag utility function

## Parent Feature
Backend Foundation - Feature Flag Implementation

## Complexity
Low

## Estimated Time
2 hours

## Dependencies
- 001-add-feature-flag-constant.md

## Description
Add a new utility function to check the "inspection_log_use_data_tables" feature flag status, following the existing pattern used by other feature flag utility functions in the system.

## Implementation Details

### Files to Modify
- `the_link_django/apps/utils/feature_flags.py` - Add new utility function

### Code Patterns to Follow
- Follow existing utility function patterns (e.g., `is_notices_feature_flag_active`, `is_versioning_feature_flag_active`)
- Use the same function signature and return type as existing functions
- Include proper docstring and type hints
- Follow existing naming convention

### Implementation Steps
1. Add new utility function to feature_flags.py:
   ```python
   def is_inspection_log_use_data_tables_feature_flag_active(user, team, project=None):
       """
       Check if the inspection_log_use_data_tables feature flag is active for the given user/team.
       
       Args:
           user: User object
           team: Team object
           project: Optional Project object
           
       Returns:
           bool: True if flag is active, False otherwise
       """
       return (settings.INSPECTION_LOG_USE_DATA_TABLES_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or 
               settings.INSPECTION_LOG_USE_DATA_TABLES_FEATURE_FLAG_NAME in get_active_flags_for_team(team))
   ```
2. Add import for the new constant if needed
3. Follow existing function placement and formatting

### Function Signature
- **Name**: `is_inspection_log_use_data_tables_feature_flag_active`
- **Parameters**: `user`, `team`, `project=None`
- **Return Type**: `bool`
- **Behavior**: Check user flags first, then team flags

## Acceptance Criteria
- [ ] New utility function added to feature_flags.py
- [ ] Function follows existing naming and signature patterns
- [ ] Function returns correct boolean value based on flag status
- [ ] Function handles edge cases (None values, missing flags)
- [ ] Proper docstring and type hints included
- [ ] No breaking changes to existing functionality
- [ ] Function can be imported and used throughout the application

## Testing Approach
- [ ] Test function with user who has flag enabled
- [ ] Test function with team that has flag enabled
- [ ] Test function with neither user nor team having flag
- [ ] Test function with None values for parameters
- [ ] Test function import and usage in other modules
- [ ] Run existing feature flag tests to ensure no regressions
- [ ] Test integration with existing flag checking logic

## Quick Status
This task maintains operational Quick by:
- Following established patterns to minimize risk
- Adding function that doesn't affect existing functionality
- Proper error handling and edge case management
- Immediate rollback possible by removing the function
- No changes to existing code paths
