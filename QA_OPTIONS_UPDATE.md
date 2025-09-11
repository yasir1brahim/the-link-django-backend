# QA Planner Options Update

## ✅ Updated QA Options List

The QA Planner now supports the following 9 QA options:

### **New QA Options (Code Name → Display Name)**

1. `inspections` → **Inspections**
2. `mock_ups_sample_construction` → **Mock-ups/Sample Construction**
3. `pre_installation_meetings` → **Pre-installation meetings**
4. `warranties` → **Warranties**
5. `certificates` → **Certificates**
6. `closeout_submittals` → **Closeout submittals**
7. `test_reports` → **Test Reports**
8. `commissioning` → **Commissioning**
9. `delegated_design` → **Delegated Design**

### **Changes Made**

#### Backend Updates
**File**: `apps/deliverables/views/specgpt_views.py`
- Updated `QA_OPTION_PROMPTS` mapping to include all 9 new options
- Each option maps to its corresponding PromptLayer template

#### Frontend Updates
**File**: `src/components/SpecGpt/utils/qaUtils.js`
- Updated `QA_OPTION_LABELS` mapping with new options and display names
- Maintains pretty printing functionality for all new options

#### Lambda Updates
**File**: `LogManager/glue_jobs/generate_ai_log/lambda/generate_ai_log.py`
- No changes needed - existing logic handles any `qa_planner__*` log types automatically

### **PromptLayer Templates Needed**

You'll need to manually create these PromptLayer templates:

1. `qa_planner__inspections`
2. `qa_planner__mock_ups_sample_construction`
3. `qa_planner__pre_installation_meetings`
4. `qa_planner__warranties`
5. `qa_planner__certificates`
6. `qa_planner__closeout_submittals`
7. `qa_planner__test_reports`
8. `qa_planner__commissioning`
9. `qa_planner__delegated_design`

Each template should use the `QAPlannerRow` output schema:
```python
class QAPlannerRow(BaseModel):
    spec_section_number: str = Field(alias="Spec Section #")
    spec_section_name: str = Field(alias="Spec Section Name")
    item_type: str = Field(alias="Item Type")
    item_text: str = Field(alias="Item Text")
    responsible_party: str = Field(alias="Responsible Party")
```

### **What This Enables**

- **More Comprehensive QA Coverage**: 9 different QA categories instead of 6
- **Construction-Specific Options**: Added construction-focused items like "Delegated Design" and "Commissioning"
- **Better Organization**: More specific categories like "Test Reports" vs generic "Reports"
- **Professional Terminology**: Uses industry-standard terms like "Closeout submittals"

### **Example Usage**

User can now select from these options in the QA Planner modal:
- ✅ Inspections
- ✅ Mock-ups/Sample Construction
- ✅ Pre-installation meetings
- ✅ Warranties
- ✅ Certificates
- ✅ Closeout submittals
- ✅ Test Reports
- ✅ Commissioning
- ✅ Delegated Design

All selected options will be processed and combined into a single unified table showing all QA requirements across the selected categories.

### **Status**
✅ **Backend Updated**: All code changes complete
✅ **Frontend Updated**: Pretty printing and labels updated
✅ **Django Check**: Passes without errors
🔄 **PromptLayer Templates**: Need to be created manually

The QA Planner is now ready with the expanded set of 9 comprehensive QA options!
