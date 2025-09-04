# Testing Strategy: Inspection Log Data Tables Feature

## Testing Overview

This document outlines the comprehensive testing strategy for the inspection log data tables feature, covering unit tests, integration tests, and end-to-end testing approaches.

## Core Test Categories

### 1. Unit Tests

#### Backend Unit Tests

**Feature Flag Utility Tests**
- Test new `is_inspection_log_use_data_tables_flag_active` function
- Test flag checking with different user/team combinations
- Test flag behavior when user/team not found
- **Automation**: Full automation with pytest

**Model Tests**
- Test `AiGeneratedLog` model with new `log_data` field
- Test field validation and constraints
- Test model serialization/deserialization
- **Automation**: Full automation with Django test framework

**Serializer Tests**
- Test `AiGeneratedLogSerializer` with both flag states
- Test serialization of structured data vs markdown
- Test sorting parameter handling
- **Automation**: Full automation with Django REST framework tests

**View Tests**
- Test log generation views with feature flag
- Test webhook handler with structured data
- Test API endpoints with sorting parameters
- **Automation**: Full automation with Django test framework

#### Frontend Unit Tests

**Feature Flag Context Tests**
- Test new flag check function in React context
- Test flag state management
- Test flag loading behavior
- **Automation**: Full automation with Jest

**Sortable Table Component Tests**
- Test component rendering with different data formats
- Test sorting functionality for all columns
- Test component props and state management
- **Automation**: Full automation with Jest and React Testing Library

**LogViewer Component Tests**
- Test component behavior with feature flag active/inactive
- Test switching between table and markdown display
- Test API integration and error handling
- **Automation**: Full automation with Jest and React Testing Library

### 2. Integration Tests

#### Backend Integration Tests

**API Integration Tests**
- Test complete API flow from request to response
- Test feature flag integration across all endpoints
- Test sorting functionality with real data
- **Automation**: Full automation with Django test framework

**Lambda Integration Tests**
- Test Lambda function with feature flag parameter
- Test structured data generation vs markdown generation
- Test error handling and edge cases
- Test fallback to markdown table when structured data unavailable
- **Automation**: Full automation with AWS testing tools

**Database Integration Tests**
- Test data storage and retrieval with new fields
- Test migration scripts
- Test performance with realistic data volumes
- **Automation**: Full automation with Django test framework

#### Frontend Integration Tests

**Component Integration Tests**
- Test LogViewer integration with sortable table
- Test API utility integration with sorting parameters
- Test feature flag integration across components
- **Automation**: Full automation with Jest and React Testing Library

**API Integration Tests**
- Test frontend API calls with backend responses
- Test error handling and loading states
- Test data transformation between frontend and backend
- **Automation**: Full automation with Jest and MSW (Mock Service Worker)

### 3. End-to-End Tests

**Complete User Flow Tests**
- Test inspection log generation with flag active
- Test inspection log generation with flag inactive
- Test owner deliverables log generation with both flag states
- Test sorting functionality in browser
- **Automation**: Partial automation with Cypress or Playwright

**Cross-Browser Tests**
- Test functionality in Chrome, Firefox, Safari, Edge
- Test responsive design on different screen sizes
- Test accessibility compliance
- **Automation**: Partial automation with browser testing tools

## Critical Test Scenarios

### Scenario 1: Feature Flag Active - Inspection Log
1. User enables feature flag for team
2. User generates inspection log
3. Lambda receives flag parameter and generates structured data
4. Backend stores data in `log_data` field
5. Backend converts structured data to markdown and stores in `log_table` for fallback
6. Frontend displays sortable table
7. User can sort by all columns (spec_section_number, spec_section_name, inspection_type_and_requirements, inspection_frequency, responsible_party)

**Test Coverage**: Unit, Integration, E2E

### Scenario 2: Feature Flag Inactive - Inspection Log
1. User does not have feature flag enabled
2. User generates inspection log
3. Lambda generates markdown table
4. Backend stores data in `log_table` field
5. Frontend displays markdown table
6. Existing functionality preserved

**Test Coverage**: Unit, Integration, E2E

### Scenario 3: Feature Flag Active - Owner Deliverables Log
1. User enables feature flag for team
2. User generates owner deliverables log
3. Lambda receives flag parameter and generates structured data
4. Backend stores data in `log_data` field
5. Backend converts structured data to markdown and stores in `log_table` for fallback
6. Frontend displays sortable table
7. User can sort by all columns (spec_section_number, spec_section_name, deliverable_type, when_due, responsible_party, exact_requirement_text)

**Test Coverage**: Unit, Integration, E2E

### Scenario 4: Sorting Functionality
1. User has feature flag active
2. User generates log with structured data
3. User clicks column header to sort
4. Backend receives sorting parameters
5. Backend sorts data and returns sorted results
6. Frontend displays sorted table

**Test Coverage**: Unit, Integration, E2E

### Scenario 5: Fallback to Markdown
1. Feature flag is active but structured data is not available
2. System falls back to markdown table display
3. User sees markdown table instead of sortable table
4. Existing functionality is preserved

**Test Coverage**: Unit, Integration, E2E

### Scenario 6: Error Handling
1. Lambda function fails during processing
2. Backend handles error gracefully
3. Frontend displays appropriate error message
4. User can retry operation

**Test Coverage**: Unit, Integration, E2E

## Automation vs Manual Testing

### Automated Testing (80%)

**Unit Tests**: 100% automation
- All backend utility functions
- All model and serializer logic
- All React component logic
- All API endpoint logic

**Integration Tests**: 100% automation
- Backend API integration
- Frontend component integration
- Database integration
- Lambda function integration

**End-to-End Tests**: 60% automation
- Basic user flows
- Feature flag scenarios
- Sorting functionality
- Error handling

### Manual Testing (20%)

**User Experience Testing**
- Visual design consistency
- Responsive design on various devices
- Accessibility compliance
- Performance with large datasets

**Exploratory Testing**
- Edge cases not covered by automated tests
- Cross-browser compatibility
- Real-world usage scenarios
- Integration with other features

## Test Data Requirements

### Backend Test Data
- Sample inspection log data (structured and markdown formats)
- Sample owner deliverables log data (structured and markdown formats)
- User and team data with various feature flag combinations
- Large datasets for performance testing

### Frontend Test Data
- Mock API responses for both flag states
- Sample table data for sorting tests
- Error response scenarios
- Loading state data

## Performance Testing

### Backend Performance Tests
- Database query performance with new JSON fields
- API response times with sorting
- Lambda function execution times
- Memory usage with large datasets

### Frontend Performance Tests
- Component rendering times
- Table sorting performance
- Memory usage with large datasets
- Page load times

## Security Testing

### Backend Security Tests
- Feature flag access control
- API endpoint authorization
- Data validation and sanitization
- SQL injection prevention

### Frontend Security Tests
- XSS prevention
- CSRF protection
- Input validation
- Secure API communication

## Test Environment Requirements

### Backend Test Environment
- Django test database
- Mock AWS services (Lambda, S3)
- Feature flag test configuration
- Performance testing tools

### Frontend Test Environment
- React development server
- Mock API server
- Browser testing tools
- Performance monitoring tools

## Test Execution Strategy

### Pre-commit Testing
- Unit tests for changed code
- Basic integration tests
- Code quality checks

### Continuous Integration
- Full unit test suite
- Integration tests
- Basic E2E tests
- Performance regression tests

### Pre-deployment Testing
- Full test suite execution
- Manual testing of critical scenarios
- Performance testing
- Security testing

### Post-deployment Testing
- Smoke tests in production
- Performance monitoring
- Error rate monitoring
- User feedback collection

## Test Maintenance

### Regular Maintenance
- Update test data as needed
- Refactor tests when code changes
- Monitor test execution times
- Review test coverage metrics

### Test Documentation
- Document test scenarios and expected results
- Maintain test data documentation
- Update test environment setup guides
- Document troubleshooting procedures
