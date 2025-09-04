# Product Requirements Document: Inspection Log Data Tables Feature

## Overview

Add a new feature flag "inspection_log_use_data_tables" that enables structured data storage and display for inspection logs and owner deliverables logs. When active, the system will store log data as structured JSON objects instead of markdown tables, enabling sortable column display similar to the existing combinedLogs.jsx component.

## Problem Statement

Currently, inspection logs and owner deliverables logs are stored as markdown table strings in the `log_table` field of the `AiGeneratedLog` model. This approach limits the ability to:
- Sort data by different columns
- Filter data efficiently
- Provide interactive table experiences
- Maintain data structure integrity

## Goals

- Enable structured data storage for inspection logs and owner deliverables logs
- Provide sortable column functionality similar to existing project logs
- Maintain backward compatibility with existing markdown table format
- Improve user experience with interactive data tables

## Success Metrics

- Feature flag can be toggled without breaking existing functionality
- Data is properly stored as structured JSON when flag is active
- Frontend displays sortable tables when flag is active
- Existing markdown table functionality continues to work when flag is inactive

## Requirements

### Core Functional Requirements

1. **Feature Flag Implementation**
   - Add new feature flag "inspection_log_use_data_tables"
   - Integrate flag checking in Django backend and React frontend
   - Pass flag status to AWS Lambda function

2. **Backend Data Storage**
   - Add new JSON field `log_data` to `AiGeneratedLog` model
   - Store structured data objects when flag is active
   - Maintain existing `log_table` field for backward compatibility

3. **AWS Lambda Integration**
   - Update Lambda function to accept feature flag parameter
   - Return structured data objects instead of markdown when flag is active
   - Maintain existing markdown table generation when flag is inactive

4. **API Endpoint Updates**
   - Update API to return structured data when flag is active
   - Support sorting parameters for all columns
   - Maintain existing API contract for backward compatibility

5. **Frontend Implementation**
   - Create new sortable table component based on combinedLogs.jsx
   - Integrate feature flag checking in React components
   - Display structured data tables when flag is active

### Constraints

- Must maintain backward compatibility with existing markdown table format, if the flag is on and structured data isn't available, fall back to the markdown table string
- Must not break existing functionality when feature flag is inactive
- Must follow existing code patterns and architecture

### Dependencies

- Existing feature flag system
- AWS Step Functions and Lambda infrastructure
- Django REST framework
- React frontend components

## User Experience

### User Flow

1. User navigates to inspection log or owner deliverables log
2. System checks feature flag status
3. If flag is active:
   - Display sortable data table with column headers
   - Allow clicking column headers to sort data
   - Show data in structured format
4. If flag is inactive:
   - Display existing markdown table format
   - Maintain current user experience

### UI Considerations

- Table should match existing design patterns from combinedLogs.jsx
- Column headers should be clickable for sorting
- Sort indicators should be visible
- Responsive design for different screen sizes

## Technical Approach

### Architecture Overview

1. **Feature Flag Layer**: Check flag status in Django and React
2. **Data Processing Layer**: Lambda function generates structured data or markdown
3. **Storage Layer**: Store data in appropriate format based on flag
4. **API Layer**: Return data in correct format with sorting support
5. **Presentation Layer**: Display appropriate UI based on flag status

### Component Changes Needed

- `AiGeneratedLog` model: Add `log_data` JSON field
- Django views: Add feature flag checking and sorting logic
- Lambda function: Add flag parameter and structured data generation
- React components: Add feature flag integration and new table component
- API endpoints: Add sorting parameters and structured data response

## Acceptance Criteria

1. Feature flag "inspection_log_use_data_tables" can be created and toggled
2. When flag is inactive, existing functionality works unchanged
3. When flag is active:
   - Lambda function receives flag parameter
   - Lambda posts back data in structured json format rather than Markdown
   - Structured data is stored in `log_data` field
   - Strucutred data is converted to a Markdown table and stored in the existing log field, so we can fall back to it if the flag is turned off. Note: code exists to do this already, it can be found in convert_to_markdown_table in the_link_django/apps/deliverables/utils.py
   - API returns structured data with sorting support
   - Frontend displays sortable table
4. All existing tests pass
5. New tests cover feature flag functionality

## Open Questions

1. **AWS Step Function Updates**: What specific changes are needed in the Step Function definition to pass the feature flag parameter?
 - Don't worry about this part, I'll handle it manually. It will be a simple change though, just returning data before the step function converts it to markdown
2. **Data Migration**: Should existing markdown table data be migrated to structured format when flag is enabled?
 - No, see above, we'll just fall back to the markdown table version in this case. This should be rare
3. **Performance**: What is the expected performance impact of storing structured data vs markdown?
 - This doesn't really matter right now
4. **Column Definitions**: What are the exact column definitions for inspection logs and owner deliverables logs?
 - The shape can be found in the following classes:
 ```

class InspectionLogRow(BaseModel):
    spec_section_number: str = Field(alias="Spec Section #", description="The section this item was found in")
    spec_section_name: str = Field(alias="Spec Section Name", description="The name of the section")
    inspection_type_and_requirements: str = Field(alias="Inspection Type And Requirements", description="The type and requirements of the inspection")
    inspection_frequency: str = Field(alias="Inspection Frequency", description="The frequency of the inspection")
    responsible_party: str = Field(alias="Responsible Party", description="The responsible party for the inspection")

class InspectionLog(BaseModel):
    results: List['InspectionLogRow'] = Field(description="List of inspection log rows")

class OwnerDeliverablesRow(BaseModel):
    spec_section_number: str = Field(alias="Spec Section #", description="The section this item was found in")
    spec_section_name: str = Field(alias="Spec Section Name", description="The name of the section")
    deliverable_type: str = Field(alias="Deliverable Type", description="The type of deliverable")
    when_due: str = Field(alias="When Due", description="The date the deliverable is due")
    responsible_party: str = Field(alias="Responsible Party", description="The responsible party for the deliverable")
    exact_requirement_text: str = Field(alias="Exact Requirement Text", description="The exact requirement text")

class OwnerDeliverablesLog(BaseModel):
    results: List['OwnerDeliverablesRow'] = Field(description="List of owner deliverables rows")
```
5. **Sorting Logic**: Should sorting be done on the backend or frontend for optimal performance?
 - Probably the backend for consistency with existing code and to keep the frontend simple. THe backend is more testable at the moment so I'd rather have logic live there
