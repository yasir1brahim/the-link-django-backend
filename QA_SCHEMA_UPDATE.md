# QA Planner Schema Update

## ✅ Updated QAPlannerRow Schema

The QAPlannerRow schema has been enhanced with additional fields for better QA requirement tracking.

### **New Schema Structure**

```python
class QAPlannerRow(BaseModel):
    spec_section_number: str = Field(alias="Spec Section #", description="The section this item was found in")
    spec_section_name: str = Field(alias="Spec Section Name", description="The name of the section")
    paragraph_number: str = Field(alias="Paragraph Number", description="The paragraph number within the spec section")  # NEW
    item_type: str = Field(alias="Item Type", description="Type of the item, maps to the option chosen in the QA planner modal")
    requirement_text: str = Field(alias="Requirement Text", description="Text of the QA requirement, as extracted from the spec document")  # RENAMED
    responsible_party: str = Field(alias="Responsible Party", description="The responsible party for the QA item")
    date_due: str = Field(alias="Date Due", description="When the QA item is due or required")  # NEW
```

### **Changes Made**

#### **Added Fields:**
1. **`paragraph_number`** (alias: "Paragraph Number")
   - Captures the specific paragraph within the spec section
   - Helps pinpoint exact location of requirements
   - Displayed as "Para #" in the UI table

2. **`date_due`** (alias: "Date Due") 
   - Captures when the QA item is due or required
   - Important for scheduling and compliance tracking
   - Displayed as "Date Due" in the UI table

#### **Renamed Fields:**
1. **`item_text` → `requirement_text`** (alias: "Item Text" → "Requirement Text")
   - More accurate naming for QA requirements
   - Maintains the same data but with clearer semantics

### **Updated UI Table Structure**

The QA Planner table now displays 7 columns:

| Column | Width | Description |
|--------|-------|-------------|
| **Spec Section #** | 10% | Section number (e.g., "03 30 00") |
| **Spec Section Name** | 18% | Section name (expandable) |
| **Para #** | 8% | Paragraph number within section |
| **QA Type** | 12% | Type of QA item (pretty printed) |
| **Requirements** | 30% | Full requirement text (expandable) |
| **Responsible Party** | 12% | Who is responsible |
| **Date Due** | 10% | When item is due |

### **Benefits of Enhanced Schema**

1. **Better Traceability**: Paragraph numbers provide exact spec location
2. **Improved Scheduling**: Date due field enables timeline tracking
3. **Clearer Semantics**: "Requirement Text" is more descriptive than "Item Text"
4. **Enhanced Organization**: More detailed breakdown of QA requirements
5. **Compliance Tracking**: Due dates help ensure timely completion

### **Files Updated**

#### Lambda Handler
**File**: `LogManager/glue_jobs/generate_ai_log/lambda/generate_ai_log.py`
- Updated `QAPlannerRow` class with new fields
- All QA planner lambda types automatically use the new schema

#### Frontend LogViewer
**File**: `src/components/SpecGpt/components/Chat/LogViewer/index.js`
- Added new field mappings for sorting/filtering
- Updated column definitions for QA planner table
- Optimized column widths for 7-column layout

### **PromptLayer Template Updates Needed**

When creating the PromptLayer templates, ensure they output all 7 fields:

```python
# Example output structure for templates:
{
    "Spec Section #": "03 30 00",
    "Spec Section Name": "Cast-in-Place Concrete", 
    "Paragraph Number": "3.1.2",
    "Item Type": "inspections",
    "Requirement Text": "Concrete strength testing required at 7 and 28 days",
    "Responsible Party": "Testing Laboratory",
    "Date Due": "Prior to formwork removal"
}
```

### **Status**
✅ **Lambda Schema**: Updated with 7 fields
✅ **Frontend Table**: Updated to display all 7 columns  
✅ **Field Mapping**: Added for sorting/filtering
✅ **Django Check**: Passes without errors
🔄 **PromptLayer Templates**: Need to be updated to output new fields

The QA Planner now provides much more detailed and useful information for each QA requirement!
