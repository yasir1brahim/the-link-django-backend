# QA Planner Implementation Tasks

## Task 0: Database Migration for QA Planner Fields ✅
**Priority**: CRITICAL - Must be done first
**Status**: COMPLETED

### Changes Required
1. Add `qa_options_selected` JSON field
2. Add `completion_status` JSON field  
3. Update model with new fields

### Files to Modify
- `apps/deliverables/models.py`
- New migration file

---

## Task 1: Backend QA Planner Generation ✅
**Dependencies**: Task 0
**Status**: COMPLETED

### Changes Required
- Add `qa_planner` case to `generate_ai_log` method
- Create `generate_qa_planner_log` method
- Handle multiple lambda invocations

### Files to Modify
- `apps/deliverables/views/specgpt_views.py`

---

## Task 2: Webhook Handler Updates ✅
**Dependencies**: Task 1
**Status**: COMPLETED

### Changes Required
- Handle partial results from multiple lambdas
- Implement result merging logic
- Add completion detection

### Files to Modify
- `apps/deliverables/views/specgpt_views.py`

---

## Task 3: Lambda Payload Generator ✅
**Dependencies**: Task 1
**Status**: COMPLETED

### Changes Required
- Map QA options to prompt templates
- Generate unique tracking identifiers
- Create standardized payloads

### Files to Modify
- `apps/deliverables/views/specgpt_views.py`

---

## Task 4: PromptLayer Templates 👤
**Assigned to**: User (Manual)
**Status**: Pending user action

### QA Prompts Needed
- qa_inspections_prompt
- qa_mock_ups_prompt
- qa_pre_installation_meetings_prompt  
- qa_warranties_prompt
- qa_certificates_prompt
- qa_reports_prompt

---

## Task 5: Frontend API Utils ✅
**Dependencies**: Task 1, 2
**Status**: COMPLETED

### Changes Required
- Add `generateQAPlannerLog` function
- Update log type handling

### Files to Modify
- `the-link-web-app/src/components/SpecGpt/utils/apiUtils.js`

---

## Task 6: Frontend Chat Component ✅
**Dependencies**: Task 5
**Status**: COMPLETED

### Changes Required
- Replace placeholder QA planner logic
- Handle sortable data table display
- Group by item_type

### Files to Modify
- `the-link-web-app/src/components/SpecGpt/components/Chat/index.js`

---

## Task 8: Lambda Handler Updates ✅
**Dependencies**: Task 4
**Status**: COMPLETED

### Changes Required
- Add QAPlannerRow model
- Handle QA-specific processing
- Include item_type in responses

### Files to Modify
- `LogManager/glue_jobs/generate_ai_log/lambda/generate_ai_log.py`

---

## Task 9: Testing 🧪
**Dependencies**: All implementation tasks
**Status**: Pending

### Test Types Needed
- Unit tests for QA planner generation
- Integration tests for webhook handling
- End-to-end tests

---

## Task 10: Admin Interface 🔄
**Dependencies**: Task 0, 1
**Status**: Pending

### Changes Required
- Display QA planner logs appropriately
- Show selected options and completion status

### Files to Modify
- `apps/deliverables/admin.py`

---

## Legend
- ⏳ In Progress
- 🔄 Ready to implement  
- 👤 User action required
- 🧪 Testing phase
- ✅ Complete
- ❌ Blocked
