# QA Planner Backend Development Plan

## Overview

The QA Planner feature will allow users to select multiple QA options (Inspections, Mock-ups/Sample Construction, Pre-installation meetings, Warranties, Certificates, Closeout submittals, Test Reports, Commissioning, Delegated Design) and generate AI logs for each selected option. This builds on the existing AiGeneratedLog system but requires processing multiple lambda invocations and merging the results.

## Current System Analysis

### Existing Components
- **AiGeneratedLog Model**: Stores AI-generated log data with `log_type`, `log_status`, `log_data` (JSON), and `log_table` (markdown)
- **AI Log Generation Flow**: Creates log → invokes lambda → receives webhook → updates log
- **QA Options**: Update frontend options to: Inspections, Mock-ups/Sample Construction, Pre-installation meetings, Warranties, Certificates, Closeout submittals, Test Reports, Commissioning, Delegated Design
- **Lambda Processing**: Existing `generate_ai_log` lambda processes individual log types

### Key Patterns to Follow
1. **Log Types**: Current system supports `inspection_log` and `owner_deliverables_log`
2. **Processing Flow**: Backend creates log with "PROCESSING" status → Lambda processes → Webhook updates to "SUCCESS"/"FAILURE"
3. **Data Structure**: Supports both markdown (`log_table`) and structured JSON (`log_data`)
4. **Feature Flags**: Uses feature flags to determine data format preference

## Implementation Plan

### Phase 1: Database & Model Updates
- Add new fields to AiGeneratedLog for QA planner tracking
- Create database migration for new fields
- Add new log_type and status values

### Phase 2: Backend Foundation  
- Add new `qa_planner` log type to the system
- Create new API endpoint for QA Planner generation
- Extend webhook handler to support merged results and partial failures

### Phase 3: Lambda Integration
- Update existing lambda to handle QA-specific processing
- Create QA-specific prompt templates in PromptLayer (done manually)
- Implement multiple lambda invocation logic
- Handle result merging and item_type tagging (this should be done in backend code)

### Phase 4: Frontend Integration
- Update frontend to call new QA Planner endpoint
- Handle QA Planner log display in sortable data table grouped by item_type
- Display partial failure status to users

### Phase 5: Testing & Refinement
- Comprehensive testing of multi-lambda processing
- Error handling and edge cases
- Performance optimization

## Detailed Task Breakdown

### Task 1: Extend AiGeneratedLog System for QA Planner
**File**: `apps/deliverables/views/specgpt_views.py`
**Complexity**: Medium

**Changes Needed**:
1. Add `qa_planner` case to `generate_ai_log` method
2. Create `generate_qa_planner_log` method
3. Handle multiple lambda invocations for selected options
4. Create initial log with combined metadata

**Implementation Details**:
- New method `generate_qa_planner_log(project_id, project_version_id, selected_options, request)`
- Logic to create single AiGeneratedLog with `log_type='qa_planner'`
- Track selected options in log metadata or separate field
- Invoke lambda for each selected option with unique identifiers

### Task 2: Update Webhook Handler for Merged Results
**File**: `apps/deliverables/views/specgpt_views.py`
**Complexity**: High

**Changes Needed**:
1. Modify `ai_log_generation_webhook` to handle partial results
2. Implement result merging logic
3. Add `item_type` tagging to each JSON object
4. Handle completion detection (all lambdas finished)

**Implementation Details**:
- Track completion status for multi-part QA logs
- Merge `log_data` arrays from multiple lambda responses
- Add `item_type` field to each result object based on source lambda
- Update log status only when all parts complete
- Handle partial failures gracefully

### Task 3: Create QA-Specific Lambda Payload Generator
**File**: `apps/deliverables/views/specgpt_views.py`
**Complexity**: Medium

**Changes Needed**:
1. Create method to generate lambda payloads for each QA option
2. Map QA options to appropriate prompts
3. Generate unique tracking identifiers for each invocation

**Implementation Details**:
- Method `generate_qa_lambda_payload(qa_option, project_data, log_id)`
- Mapping dictionary for QA options to prompt templates
- Unique sub-task identifiers for tracking partial results
- Standardized prompt structure for different QA types

### Task 4: Add QA Option Prompt Templates (MANUAL TASK)
**File**: PromptLayer (done manually by user)
**Complexity**: Medium
**Status**: User will handle this manually

**QA Option Prompts Needed**:
- `qa_inspections_prompt`: Focus on inspection requirements
- `qa_mock_ups_prompt`: Focus on mock-up requirements  
- `qa_pre_installation_meetings_prompt`: Focus on meeting requirements
- `qa_warranties_prompt`: Focus on warranty requirements
- `qa_certificates_prompt`: Focus on certification requirements
- `qa_reports_prompt`: Focus on reporting requirements

**Output Schema** (for all QA types):
```python
class QAPlannerRow(BaseModel):
    spec_section_number: str = Field(alias="Spec Section #", description="The section this item was found in")
    spec_section_name: str = Field(alias="Spec Section Name", description="The name of the section")
    item_type: str = Field(alias="Item Type", description="Type of the item, maps to the option chosen in the QA planner modal")
    item_text: str = Field(alias="Item Text", description="Text of the QA item, as extracted from the spec document")
    responsible_party: str = Field(alias="Responsible Party", description="The responsible party for the QA item")
```

### Task 5: Extend Frontend API Utils
**File**: `the-link-web-app/src/components/SpecGpt/utils/apiUtils.js`
**Complexity**: Low

**Changes Needed**:
1. Add `generateQAPlannerLog` function
2. Update log type handling for QA planner logs

**Implementation Details**:
```javascript
const generateQAPlannerLog = async (projectId, projectVersionId, selectedOptions) => {
    // Call new QA planner endpoint with selected options
}
```

### Task 6: Update Frontend Chat Component
**File**: `the-link-web-app/src/components/SpecGpt/components/Chat/index.js`
**Complexity**: Low

**Changes Needed**:
1. Replace placeholder logic in `onQAPlannerSubmit`
2. Call new QA planner API function
3. Handle QA planner log display in sortable data table
4. Display partial failure status to users
5. Group results by item_type in the UI

**Display Requirements**:
- Use existing sortable data table component
- Group by item_type (inspections, warranties, etc.)
- Show partial failure status prominently
- Allow sorting within each group

### Task 0: Add Database Migration for QA Planner Fields
**File**: New migration file
**Complexity**: Low
**Priority**: HIGH - Must be done first

**Changes Needed**:
1. Add `qa_options_selected` JSON field to track selected options
2. Add `completion_status` JSON field for tracking partial completion
3. Add new log_status values: 'PARTIAL_SUCCESS', 'PARTIAL_FAILURE'
4. Update model constraints and validation

**New Fields**:
```python
qa_options_selected = models.JSONField(blank=True, null=True, help_text="Selected QA options for qa_planner log type")
completion_status = models.JSONField(blank=True, null=True, help_text="Status of each QA option processing")
```

### Task 8: Update Lambda Handler for QA Processing
**File**: `LogManager/glue_jobs/generate_ai_log/lambda/generate_ai_log.py`
**Complexity**: Medium

**Changes Needed**:
1. Add QA-specific log models
2. Handle QA option-specific processing
3. Include sub-task metadata in responses

### Task 9: Add Comprehensive Tests
**Files**: Test files
**Complexity**: Medium

**Changes Needed**:
1. Unit tests for QA planner log generation
2. Integration tests for webhook handling
3. End-to-end tests for complete flow
4. Edge case testing (partial failures, timeouts)

### Task 10: Update Admin Interface
**File**: `apps/deliverables/admin.py`
**Complexity**: Low

**Changes Needed**:
1. Update admin display for QA planner logs
2. Add filters for QA log types
3. Display selected options in admin view

## API Specification

### New Endpoint: Generate QA Planner Log
```
POST /api/deliverables/{project_id}/specgpt-chats/generate-qa-planner-log/

Request Body:
{
    "project_id": "string",
    "project_version_id": "string", 
    "selected_options": ["inspections", "warranties", "certificates"]
}

Response:
{
    "id": "log_id",
    "project": "project_id",
    "project_version": "project_version_id",
    "log_type": "qa_planner",
    "log_status": "PROCESSING",
    "selected_options": ["inspections", "warranties", "certificates"],
    "created_at": "timestamp"
}
```

### Enhanced Webhook Payload
```json
{
    "project_id": "string",
    "project_version_id": "string", 
    "ai_generated_log_id": "string",
    "log_type": "qa_planner__inspections",
    "new_status": "SUCCESS",
    "table": [
        {
            "item_type": "inspections",
            "spec_section_number": "03 30 00",
            "requirements": "...",
            // ... other fields
        }
    ]
}
```

## Data Structure

### Enhanced AiGeneratedLog Structure
```json
{
    "log_data": [
        {
            "item_type": "inspections",
            "spec_section_number": "03 30 00",
            "spec_section_name": "Cast-in-Place Concrete",
            "inspection_type_and_requirements": "Concrete strength testing",
            "inspection_frequency": "Every pour",
            "responsible_party": "Testing laboratory"
        },
        {
            "item_type": "warranties", 
            "spec_section_number": "07 21 00",
            "spec_section_name": "Thermal Insulation",
            "warranty_type": "Material warranty",
            "warranty_duration": "10 years",
            "responsible_party": "Manufacturer"
        }
    ],
    "metadata": {
        "selected_options": ["inspections", "warranties"],
        "completion_status": {
            "inspections": "SUCCESS",
            "warranties": "SUCCESS"
        }
    }
}
```

## Error Handling Strategy

1. **Partial Failures**: Continue processing other options if one fails
2. **Timeout Handling**: Set reasonable timeouts for lambda processing
3. **Retry Logic**: Implement retry for transient failures
4. **User Feedback**: Provide clear status updates for each option
5. **Graceful Degradation**: Show partial results if some options fail

## Testing Strategy

1. **Unit Tests**: Test individual components (log generation, webhook handling, merging)
2. **Integration Tests**: Test complete flow with mock lambda responses
3. **Load Tests**: Test multiple concurrent QA planner requests
4. **User Acceptance Tests**: Test with real prompts and data

## Deployment Considerations

1. **Feature Flags**: Use feature flags to control QA planner availability
2. **Gradual Rollout**: Enable for specific teams/projects first
3. **Monitoring**: Add comprehensive logging and metrics
4. **Rollback Plan**: Ability to disable QA planner if issues arise

## Success Metrics

1. **Functionality**: Successfully processes multiple QA options and merges results
2. **Performance**: Completes processing within acceptable time limits
3. **Reliability**: Handles failures gracefully without data loss
4. **User Experience**: Provides clear feedback throughout the process

## Implementation Order

1. **Task 0**: Database Migration (PRIORITY)
2. **Task 1**: Backend QA Planner Generation
3. **Task 2**: Webhook Handler Updates
4. **Task 3**: Lambda Payload Generator
5. **Task 4**: PromptLayer Templates (MANUAL)
6. **Task 5**: Frontend API Utils
7. **Task 6**: Frontend Chat Component
8. **Task 8**: Lambda Handler Updates
9. **Task 9**: Testing
10. **Task 10**: Admin Interface

## Next Steps

1. ✅ Requirements clarified and development plan updated
2. Begin implementation with Task 0 (Database Migration)
3. Implement tasks sequentially with testing at each step
4. User creates PromptLayer templates in parallel
5. Conduct thorough testing before deployment
6. Deploy with feature flags for controlled rollout
