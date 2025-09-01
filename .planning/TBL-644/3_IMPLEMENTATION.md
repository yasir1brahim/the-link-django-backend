# Implementation Breakdown: Inspection Log Data Tables Feature

## Task Overview

This document breaks down the implementation into actionable tasks with complexity ratings, dependencies, and acceptance criteria.

## Task Breakdown

### Phase 1: Backend Foundation

#### Task 1.1: Add Feature Flag to Django Settings
- **ID**: T1.1
- **Title**: Add inspection_log_use_data_tables feature flag constant
- **Description**: Add the new feature flag constant to Django settings
- **Complexity**: Low
- **Dependencies**: None
- **Acceptance Criteria**: 
  - Feature flag constant added to settings
  - Follows existing naming convention
  - No breaking changes to existing code

#### Task 1.2: Update AiGeneratedLog Model
- **ID**: T1.2
- **Title**: Add log_data JSONField to AiGeneratedLog model
- **Description**: Add new JSONField to store structured data alongside existing log_table field
- **Complexity**: Medium
- **Dependencies**: T1.1
- **Acceptance Criteria**:
  - New log_data JSONField added to model
  - Migration file created
  - Existing log_table field unchanged
  - Model tests updated

#### Task 1.3: Update Feature Flag Utility Functions
- **ID**: T1.3
- **Title**: Add inspection log feature flag utility function
- **Description**: Add utility function to check inspection_log_use_data_tables flag
- **Complexity**: Low
- **Dependencies**: T1.1
- **Acceptance Criteria**:
  - New utility function added
  - Follows existing pattern
  - Tests written for new function

### Phase 2: Lambda Function Updates

#### Task 2.1: Update Lambda Function Parameters
- **ID**: T2.1
- **Title**: Add feature flag parameter to Lambda function
- **Description**: Modify Lambda function to accept and process feature flag parameter
- **Complexity**: Medium
- **Dependencies**: T1.1
- **Acceptance Criteria**:
  - Lambda accepts use_data_tables parameter
  - Parameter properly passed through function
  - No breaking changes to existing functionality
  - Note: AWS Step Function changes will be handled manually

#### Task 2.2: Update Lambda Data Generation Logic
- **ID**: T2.2
- **Title**: Modify Lambda to return structured data when flag is active
- **Description**: Update Lambda function to return JSON objects instead of markdown when flag is active
- **Complexity**: High
- **Dependencies**: T2.1
- **Acceptance Criteria**:
  - Returns structured data when flag is active
  - Returns markdown when flag is inactive
  - Maintains existing data structure for both formats
  - Tests updated for both scenarios
  - Uses existing convert_to_markdown_table utility for fallback

### Phase 3: Django Backend Updates

#### Task 3.1: Update Log Generation Views
- **ID**: T3.1
- **Title**: Pass feature flag to Lambda function
- **Description**: Modify Django views to check feature flag and pass to Lambda
- **Complexity**: Medium
- **Dependencies**: T1.3, T2.1
- **Acceptance Criteria**:
  - Feature flag checked before Lambda invocation
  - Flag status passed to Lambda
  - Existing functionality unchanged when flag inactive

#### Task 3.2: Update Webhook Handler
- **ID**: T3.2
- **Title**: Handle structured data in webhook callback
- **Description**: Update webhook handler to store structured data in log_data field
- **Complexity**: Medium
- **Dependencies**: T1.2, T2.2
- **Acceptance Criteria**:
  - Stores structured data in log_data when flag is active
  - Stores markdown in log_table when flag is inactive
  - Converts structured data to markdown and stores in log_table for fallback
  - Maintains backward compatibility
  - Uses existing convert_to_markdown_table utility

#### Task 3.3: Update API Serializer
- **ID**: T3.3
- **Title**: Update AiGeneratedLogSerializer to include log_data
- **Description**: Modify serializer to include log_data field and handle feature flag logic
- **Complexity**: Medium
- **Dependencies**: T1.2
- **Acceptance Criteria**:
  - Serializer includes log_data field
  - Returns appropriate data format based on flag
  - Maintains existing API contract

#### Task 3.4: Add Sorting Support to API
- **ID**: T3.4
- **Title**: Implement backend sorting for structured data
- **Description**: Add sorting parameters and logic to API endpoints
- **Complexity**: High
- **Dependencies**: T3.3
- **Acceptance Criteria**:
  - API accepts sorting parameters
  - Sorts data by all relevant columns (spec_section_number, spec_section_name, inspection_type_and_requirements, inspection_frequency, responsible_party for inspection logs; spec_section_number, spec_section_name, deliverable_type, when_due, responsible_party, exact_requirement_text for owner deliverables)
  - Returns sorted data efficiently
  - Tests cover sorting functionality

### Phase 4: Frontend Updates

#### Task 4.1: Add Feature Flag to React Context
- **ID**: T4.1
- **Title**: Add inspection log feature flag to React feature flags context
- **Description**: Add new flag check function to FeatureFlagsContext
- **Complexity**: Low
- **Dependencies**: None
- **Acceptance Criteria**:
  - New flag check function added
  - Follows existing pattern
  - Tests written for new function

#### Task 4.2: Create Sortable Table Component
- **ID**: T4.2
- **Title**: Extract reusable sortable table component from combinedLogs.jsx
- **Description**: Create base sortable table component that can be reused for log data
- **Complexity**: High
- **Dependencies**: None
- **Acceptance Criteria**:
  - Reusable component extracted
  - Supports sorting by all columns
  - Maintains existing styling and behavior
  - Tests written for new component

#### Task 4.3: Update LogViewer Component
- **ID**: T4.3
- **Title**: Integrate feature flag and sortable table in LogViewer
- **Description**: Modify LogViewer to use sortable table when flag is active
- **Complexity**: Medium
- **Dependencies**: T4.1, T4.2, T3.4
- **Acceptance Criteria**:
  - Checks feature flag status
  - Displays sortable table when flag is active
  - Displays markdown when flag is inactive
  - Maintains existing functionality

#### Task 4.4: Update API Utils
- **ID**: T4.4
- **Title**: Update API utility functions to handle sorting
- **Description**: Modify API calls to include sorting parameters when needed
- **Complexity**: Low
- **Dependencies**: T3.4
- **Acceptance Criteria**:
  - API calls include sorting parameters
  - Maintains existing API contract
  - Tests updated for new parameters

### Phase 5: Testing and Validation

#### Task 5.1: Backend Testing
- **ID**: T5.1
- **Title**: Comprehensive backend testing
- **Description**: Write tests for all backend changes including feature flag logic
- **Complexity**: Medium
- **Dependencies**: All backend tasks
- **Acceptance Criteria**:
  - All new functionality tested
  - Existing functionality still works
  - Feature flag logic thoroughly tested
  - API sorting functionality tested

#### Task 5.2: Frontend Testing
- **ID**: T5.2
- **Title**: Frontend component testing
- **Description**: Write tests for new React components and updated functionality
- **Complexity**: Medium
- **Dependencies**: All frontend tasks
- **Acceptance Criteria**:
  - New components tested
  - Feature flag integration tested
  - Sorting functionality tested
  - Existing functionality preserved

#### Task 5.3: Integration Testing
- **ID**: T5.3
- **Title**: End-to-end integration testing
- **Description**: Test complete flow from feature flag to sorted table display
- **Complexity**: High
- **Dependencies**: All tasks
- **Acceptance Criteria**:
  - Complete flow works with flag active
  - Complete flow works with flag inactive
  - No regressions in existing functionality
  - Performance acceptable

## Critical Path

The critical path for this implementation is:
1. T1.1 → T1.2 → T1.3 (Backend Foundation)
2. T2.1 → T2.2 (Lambda Updates)
3. T3.1 → T3.2 → T3.3 → T3.4 (Django Backend)
4. T4.1 → T4.2 → T4.3 → T4.4 (Frontend Updates)
5. T5.1 → T5.2 → T5.3 (Testing)

## Parallel Work Opportunities

- **Backend and Frontend**: Tasks 1.1-1.3 can be done in parallel with T4.1
- **Lambda Updates**: T2.1 and T2.2 can be done in parallel with backend Django tasks
- **Testing**: T5.1 and T5.2 can be done in parallel once their respective phases are complete

## Risk Mitigation

- **Backward Compatibility**: Each task includes acceptance criteria for maintaining existing functionality
- **Feature Flag Safety**: Feature flag is checked at multiple layers to ensure consistent behavior
- **Testing Strategy**: Comprehensive testing at each layer ensures quality and prevents regressions
- **Incremental Deployment**: Changes can be deployed incrementally with feature flag providing safety net
