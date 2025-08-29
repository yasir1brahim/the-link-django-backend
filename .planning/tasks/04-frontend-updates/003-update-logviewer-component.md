# Task: Update LogViewer Component

## Task Title
Integrate feature flag and sortable table in LogViewer

## Parent Feature
Frontend Updates - Component Integration

## Complexity
Medium

## Estimated Time
5 hours

## Dependencies
- 04-frontend-updates/001-add-react-feature-flag.md
- 04-frontend-updates/002-create-sortable-table-component.md
- 03-django-backend/004-add-sorting-support.md

## Description
Modify the LogViewer component to check the feature flag status and display either a sortable table (when flag is active and structured data is available) or the existing markdown display (when flag is inactive or structured data is not available).

## Implementation Details

### Files to Modify
- `the-link-web-app/src/components/SpecGpt/components/Chat/LogViewer/index.js` - Update LogViewer component

### Code Patterns to Follow
- Use the new feature flag utility function
- Integrate the new SortableTable component
- Maintain existing markdown display functionality
- Follow existing component patterns and error handling

### Implementation Steps
1. Import the feature flag utility and SortableTable component:
   ```javascript
   import { useFeatureFlags } from '../../../../../contexts/FeatureFlagsContext';
   import SortableTable from '../../../../shared/SortableTable';
   ```
2. Add feature flag checking logic:
   ```javascript
   const { isInspectionLogUseDataTablesFlagActive } = useFeatureFlags();
   const shouldUseDataTables = isInspectionLogUseDataTablesFlagActive(teamId);
   ```
3. Add state for sorting and filtering:
   ```javascript
   const [sorting, setSorting] = useState({ column: '', order: 'desc' });
   const [filterValues, setFilterValues] = useState({});
   ```
4. Add function to handle sorting:
   ```javascript
   const handleSort = async (columnName) => {
       // Call API with sorting parameters
       const sortedData = await fetchSortedLogData(projectId, logId, columnName, sorting.order);
       setLogMessage(prev => ({ ...prev, data: sortedData }));
   };
   ```
5. Add conditional rendering logic:
   ```javascript
   const renderContent = () => {
       if (shouldUseDataTables && logMessage?.data?.results) {
           return (
               <SortableTable
                   data={logMessage.data.results}
                   columns={getColumnsForLogType(logType)}
                   onSort={handleSort}
                   sorting={sorting}
                   onFilter={handleFilter}
                   filterValues={filterValues}
               />
           );
       } else {
           return (
               <div className="markdown-content">
                   {logMessage?.message}
               </div>
           );
       }
   };
   ```

### Column Definitions
Create column definitions for both log types:
```javascript
const getColumnsForLogType = (logType) => {
    if (logType === 'inspection_log') {
        return [
            { key: 'spec_section_number', label: 'Spec Section #', sortable: true },
            { key: 'spec_section_name', label: 'Spec Section Name', sortable: true },
            { key: 'inspection_type_and_requirements', label: 'Inspection Type & Requirements', sortable: true },
            { key: 'inspection_frequency', label: 'Inspection Frequency', sortable: true },
            { key: 'responsible_party', label: 'Responsible Party', sortable: true }
        ];
    } else if (logType === 'owner_deliverables_log') {
        return [
            { key: 'spec_section_number', label: 'Spec Section #', sortable: true },
            { key: 'spec_section_name', label: 'Spec Section Name', sortable: true },
            { key: 'deliverable_type', label: 'Deliverable Type', sortable: true },
            { key: 'when_due', label: 'When Due', sortable: true },
            { key: 'responsible_party', label: 'Responsible Party', sortable: true },
            { key: 'exact_requirement_text', label: 'Exact Requirement Text', sortable: true }
        ];
    }
    return [];
};
```

### API Integration
Update API calls to include sorting parameters when needed:
```javascript
const fetchSortedLogData = async (projectId, logId, orderBy, order) => {
    const response = await fetch(`/api/projects/${projectId}/ai-generated-logs/${logId}/?order_by=${orderBy}&order=${order}`);
    return response.json();
};
```

## Acceptance Criteria
- [ ] Feature flag checking integrated into LogViewer
- [ ] SortableTable component integrated when flag is active
- [ ] Existing markdown display maintained when flag is inactive
- [ ] Sorting functionality works for all columns
- [ ] API calls include sorting parameters when needed
- [ ] Component handles both log types correctly
- [ ] No breaking changes to existing functionality
- [ ] Proper error handling for both display modes
- [ ] Responsive design maintained

## Testing Approach
- [ ] Test with feature flag active and structured data available
- [ ] Test with feature flag active but no structured data (fallback to markdown)
- [ ] Test with feature flag inactive (existing markdown display)
- [ ] Test sorting functionality for all columns
- [ ] Test API integration with sorting parameters
- [ ] Test error handling for both display modes
- [ ] Test responsive design on different screen sizes
- [ ] Test with both inspection logs and owner deliverables logs
- [ ] Run existing LogViewer tests to ensure no regressions

## Quick Status
This task maintains operational Quick by:
- Following existing component patterns and error handling
- Maintaining backward compatibility with existing markdown display
- Adding optional functionality that doesn't break existing features
- Providing fallback to existing display when needed
- No changes to existing API contracts
