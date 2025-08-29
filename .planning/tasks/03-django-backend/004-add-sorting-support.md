# Task: Add Backend Sorting Support

## Task Title
Implement backend sorting for structured data

## Parent Feature
Django Backend - API Enhancement

## Complexity
High

## Estimated Time
6 hours

## Dependencies
- 03-django-backend/003-update-api-serializer.md

## Description
Add sorting parameters and logic to API endpoints to support sorting structured data by all relevant columns for both inspection logs and owner deliverables logs.

## Implementation Details

### Files to Modify
- `the_link_django/apps/deliverables/views/specgpt_views.py` - Update AiGeneratedLogViewSet

### Code Patterns to Follow
- Follow existing sorting patterns from other ViewSets
- Use Django ORM ordering for efficient database queries
- Add proper parameter validation
- Maintain existing API contract

### Implementation Steps
1. Add sorting parameters to ViewSet:
   ```python
   def get_queryset(self):
       queryset = super().get_queryset()
       
       # Get sorting parameters
       order_by = self.request.query_params.get('order_by', 'created_at')
       order_direction = self.request.query_params.get('order', 'desc')
       
       # Validate sorting parameters
       valid_sort_fields = self.get_valid_sort_fields()
       if order_by not in valid_sort_fields:
           order_by = 'created_at'  # Default
       
       # Apply sorting
       if order_direction == 'desc':
           order_by = f'-{order_by}'
       
       return queryset.order_by(order_by)
   ```
2. Add method to get valid sort fields based on log type:
   ```python
   def get_valid_sort_fields(self):
       log_type = self.request.query_params.get('log_type')
       
       if log_type == 'inspection_log':
           return [
               'created_at', 'spec_section_number', 'spec_section_name',
               'inspection_type_and_requirements', 'inspection_frequency', 'responsible_party'
           ]
       elif log_type == 'owner_deliverables_log':
           return [
               'created_at', 'spec_section_number', 'spec_section_name',
               'deliverable_type', 'when_due', 'responsible_party', 'exact_requirement_text'
           ]
       else:
           return ['created_at']  # Default
   ```
3. Add custom serializer method for structured data sorting
4. Add proper error handling for invalid sort parameters
5. Add documentation for sorting parameters

### Sorting Parameters
- **order_by**: Field to sort by (e.g., 'spec_section_number', 'responsible_party')
- **order**: Sort direction ('asc' or 'desc')
- **Default**: Sort by 'created_at' in 'desc' order

### Valid Sort Fields
**Inspection Logs:**
- spec_section_number
- spec_section_name
- inspection_type_and_requirements
- inspection_frequency
- responsible_party

**Owner Deliverables Logs:**
- spec_section_number
- spec_section_name
- deliverable_type
- when_due
- responsible_party
- exact_requirement_text

### API Query Parameters
```
GET /api/projects/{project_id}/ai-generated-logs/?project_version_id=1&log_type=inspection_log&order_by=spec_section_number&order=asc
```

## Acceptance Criteria
- [ ] API accepts sorting parameters (order_by, order)
- [ ] Sorting works for all valid fields for both log types
- [ ] Invalid sort parameters are handled gracefully
- [ ] Default sorting behavior maintained when no parameters provided
- [ ] Sorting is efficient using database queries
- [ ] API documentation updated with sorting parameters
- [ ] No breaking changes to existing API contract
- [ ] Proper error handling for invalid parameters
- [ ] Sorting works with both structured and markdown data

## Testing Approach
- [ ] Test sorting by each valid field for inspection logs
- [ ] Test sorting by each valid field for owner deliverables logs
- [ ] Test ascending and descending sort orders
- [ ] Test invalid sort parameters (graceful fallback)
- [ ] Test default sorting behavior
- [ ] Test sorting with feature flag active and inactive
- [ ] Test performance with large datasets
- [ ] Test error handling for invalid parameters
- [ ] Run existing API tests to ensure no regressions

## Quick Status
This task maintains operational Quick by:
- Following existing ViewSet patterns and sorting implementations
- Maintaining backward compatibility with existing API contract
- Adding optional parameters that don't break existing functionality
- Using efficient database queries for sorting
- Providing graceful fallback for invalid parameters
