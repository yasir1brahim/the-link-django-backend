# Architecture Decisions: Inspection Log Data Tables Feature

## Decision 1: Data Storage Strategy

### Context
We need to store inspection log and owner deliverables log data in a structured format when the feature flag is active, while maintaining backward compatibility with the existing markdown table format.

### Options Considered

1. **Replace existing `log_table` field**: Convert the existing TextField to JSONField
2. **Add new `log_data` field**: Keep existing field and add new JSONField for structured data
3. **Use separate model**: Create new model for structured log data

### Chosen Solution
**Add new `log_data` JSONField to existing `AiGeneratedLog` model**

### Rationale
- **Backward Compatibility**: Existing `log_table` field remains unchanged, ensuring no breaking changes
- **Fallback Strategy**: When flag is active but structured data isn't available, system falls back to markdown table
- **Dual Storage**: Structured data stored in `log_data`, markdown table stored in `log_table` for fallback
- **Minimal Migration Risk**: No need to migrate existing data or update existing code paths
- **Simple Implementation**: Single model change with clear separation of concerns
- **Follows Existing Patterns**: Consistent with how other features handle multiple data formats

## Decision 2: Feature Flag Integration Strategy

### Context
The feature flag needs to be checked at multiple layers: Django backend, React frontend, and AWS Lambda function.

### Options Considered

1. **Backend-only flag checking**: Check flag in Django and pass result to Lambda
2. **Frontend-only flag checking**: Check flag in React and conditionally call different APIs
3. **Multi-layer flag checking**: Check flag at each layer independently

### Chosen Solution
**Backend-driven flag checking with flag parameter passing**

### Rationale
- **Single Source of Truth**: Django backend is the authoritative source for feature flags
- **Consistent Behavior**: All components use the same flag status
- **Simplified Frontend**: React components don't need to manage flag state
- **Lambda Integration**: Lambda receives flag status as parameter, enabling conditional processing

## Decision 3: Sorting Implementation Strategy

### Context
When the feature flag is active, users need to be able to sort data by different columns.

### Options Considered

1. **Frontend-only sorting**: Sort data in React after fetching from API
2. **Backend-only sorting**: Sort data in Django before returning to frontend

### Chosen Solution
**Backend sorting**

### Rationale
- **Performance**: Backend sorting is more efficient for large datasets
- **Consistency**: All clients get the same sorted data
- **Scalability**: Can handle large datasets without frontend performance issues
- **Testability**: Backend logic is more testable than frontend sorting logic
- **Simplicity**: Keeps frontend simple and focused on presentation
- **Follows Existing Patterns**: Consistent with how combinedLogs.jsx handles sorting

## Decision 4: Table Component Architecture

### Context
We need to create a sortable table component for displaying structured log data when the feature flag is active.

### Options Considered

1. **Create new component from scratch**: Build entirely new sortable table component
2. **Extend combinedLogs.jsx**: Modify existing component to handle both formats
3. **Extract reusable component**: Create base sortable table component and extend it

### Chosen Solution
**Extract reusable sortable table component from combinedLogs.jsx**

### Rationale
- **Code Reuse**: Leverages existing, tested sorting and table logic
- **Consistency**: Maintains same look and feel as existing tables
- **Maintainability**: Single source of truth for table functionality
- **Testing**: Can reuse existing test patterns and coverage
- **Standards Compliance**: Follows existing code patterns and architecture
