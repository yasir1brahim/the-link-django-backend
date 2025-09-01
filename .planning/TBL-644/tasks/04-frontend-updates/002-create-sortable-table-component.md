# Task: Create Sortable Table Component

## Task Title
Extract reusable sortable table component from combinedLogs.jsx

## Parent Feature
Frontend Updates - Component Architecture

## Complexity
High

## Estimated Time
8 hours

## Dependencies
- None

## Description
Extract a reusable sortable table component from the existing combinedLogs.jsx component that can be used for displaying structured log data with sorting functionality. DO NOT CHANGE THE combinedLogs.jsx COMPONENT WHEN COMPLETING THIS TASK, only use it as a reference to copy code from.

## Implementation Details

### Files to Create/Modify
- `the-link-web-app/src/components/shared/SortableTable/index.jsx` - New reusable component
- `the-link-web-app/src/components/shared/SortableTable/SortableTable.scss` - Component styles
- `the-link-web-app/src/components/shared/SortableTable/__tests__/SortableTable.test.jsx` - Component tests

### Code Patterns to Follow
- Extract sorting logic from combinedLogs.jsx
- Follow existing component patterns and styling
- Use existing SortIcon and FilterIcon components
- Maintain responsive design and accessibility

### Implementation Steps
1. Create new SortableTable component:
   ```javascript
   const SortableTable = ({
       data,
       columns,
       onSort,
       sorting,
       onFilter,
       filterValues,
       className,
       ...props
   }) => {
       // Component implementation
   };
   ```
2. Extract sorting logic from combinedLogs.jsx
3. Extract table header rendering logic
4. Extract table row rendering logic
5. Extract sorting and filtering functionality
6. Add proper PropTypes and documentation
7. Create comprehensive test suite

### Component Props
- **data**: Array of data objects to display
- **columns**: Array of column definitions with sorting/filtering config
- **onSort**: Callback function for sorting
- **sorting**: Current sorting state
- **onFilter**: Callback function for filtering
- **filterValues**: Current filter values
- **className**: Additional CSS classes

### Column Definition Structure
```javascript
const columns = [
    {
        key: 'spec_section_number',
        label: 'Spec Section #',
        sortable: true,
        filterable: true,
        width: '10%'
    },
    {
        key: 'spec_section_name',
        label: 'Spec Section Name',
        sortable: true,
        filterable: true,
        width: '15%'
    },
    // ... more columns
];
```

### Styling and Design
- Maintain existing table styling from combinedLogs.jsx
- Support responsive design
- Include sort indicators and filter icons
- Support custom column widths
- Maintain accessibility features

## Acceptance Criteria
- [ ] Reusable SortableTable component created
- [ ] Component supports sorting by all columns
- [ ] Component supports filtering functionality
- [ ] Component maintains existing styling and design
- [ ] Component is responsive and accessible
- [ ] Component has comprehensive test coverage
- [ ] Component follows existing patterns and conventions
- [ ] Component can be easily integrated into other components
- [ ] combinedLogs.jsx REMAINS UNCHANGED. This contains complex logic and we don't want to change this file at all.
- [ ] No breaking changes to existing combinedLogs.jsx functionality

## Testing Approach
- [ ] Test component rendering with different data sets
- [ ] Test sorting functionality for all columns
- [ ] Test filtering functionality
- [ ] Test responsive design on different screen sizes
- [ ] Test accessibility features
- [ ] Test component integration with existing components
- [ ] Test error handling and edge cases
- [ ] Test performance with large datasets
- [ ] Test component props and callbacks

## Quick Status
This task maintains operational Quick by:
- Extracting existing functionality without breaking it
- Following established component patterns and conventions
- Maintaining existing styling and design
- Creating reusable component for future use
- No changes to existing combinedLogs.jsx functionality
