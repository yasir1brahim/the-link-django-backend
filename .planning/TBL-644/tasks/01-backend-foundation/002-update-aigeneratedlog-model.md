# Task: Update AiGeneratedLog Model with log_data Field

## Task Title
Add log_data JSONField to AiGeneratedLog model

## Parent Feature
Backend Foundation - Data Storage

## Complexity
Medium

## Estimated Time
3 hours

## Dependencies
- 001-add-feature-flag-constant.md

## Description
Add a new `log_data` JSONField to the existing `AiGeneratedLog` model to store structured data alongside the existing `log_table` field. This field will store the structured JSON data when the feature flag is active, while maintaining backward compatibility with the existing markdown table format.

## Implementation Details

### Files to Modify
- `the_link_django/apps/deliverables/models.py` - Add log_data field to AiGeneratedLog model
- `the_link_django/apps/deliverables/migrations/` - Create new migration file

### Code Patterns to Follow
- Follow existing model field patterns
- Use Django's JSONField for structured data storage
- Add appropriate field options (null=True, blank=True for optional field)
- Include field in model's `__str__` method if appropriate

### Implementation Steps
1. Add `log_data` JSONField to AiGeneratedLog model:
   ```python
   log_data = models.JSONField(blank=True, null=True, help_text="Structured data for inspection logs and owner deliverables logs")
   ```
2. Generate migration: `docker-compose exec web python manage.py makemigrations deliverables`
3. Review generated migration file
4. Update model's `__str__` method if needed
5. Add field to model's Meta class if needed

### Field Configuration
- **Field Type**: JSONField
- **Null**: True (allows empty values)
- **Blank**: True (allows empty in forms)
- **Default**: None
- **Help Text**: Descriptive text for admin interface

## Acceptance Criteria
- [ ] log_data JSONField added to AiGeneratedLog model
- [ ] Migration file created and reviewed
- [ ] Field accepts JSON data without errors
- [ ] Existing log_table field unchanged
- [ ] Model can be saved with both fields populated
- [ ] No breaking changes to existing functionality
- [ ] Migration can be applied and rolled back safely

## Testing Approach
- [ ] Create test instance with log_data field
- [ ] Verify JSON data can be stored and retrieved
- [ ] Test migration forward and backward
- [ ] Run existing model tests to ensure no regressions
- [ ] Test with sample structured data (inspection log and owner deliverables format)
- [ ] Verify admin interface works with new field

## Quick Status
This task maintains operational Quick by:
- Adding optional field that doesn't break existing functionality
- Maintaining backward compatibility with existing log_table field
- Following Django best practices for model changes
- Migration can be rolled back if issues arise
- Existing data remains unaffected
