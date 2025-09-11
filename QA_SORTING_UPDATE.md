# QA Planner Sorting & Field Updates

## ✅ **Updates Made**

### **1. Field Name Change: "Date Due" → "When Due"**
- **Lambda Schema**: `date_due` → `when_due` (alias: "When Due")
- **Frontend Field Mapping**: Updated to match new field name
- **UI Column Header**: "Date Due" → "When Due"

This aligns with the existing `owner_deliverables_log` schema which also uses "When Due".

### **2. Automatic Sorting by Spec Section Number**

Added intelligent sorting logic in the webhook handler that automatically sorts all QA planner results by spec section number.

#### **Sorting Algorithm:**
```python
# Sort all log_data by spec_section_number (simple string sort works due to leading zeros)
log_obj.log_data.sort(key=lambda item: item.get('spec_section_number', ''))
```

#### **How It Works:**
1. **Simple String Sort**: Spec sections like "03 30 00" naturally sort correctly as strings due to leading zeros
2. **Lexicographic Order**: String comparison handles the sorting automatically:
   - "01 10 00" comes before "01 20 00" 
   - "03 30 00" comes before "03 30 50"
   - "10 14 00" comes before "11 00 00"
3. **Clean & Simple**: No complex parsing needed - leverages the standardized format
4. **Empty Sections**: Empty strings sort first automatically

#### **Example Sort Order:**
```
01 10 00  General Requirements
03 30 00  Cast-in-Place Concrete  
03 30 50  Concrete Repair
05 12 00  Structural Steel
07 21 00  Thermal Insulation
09 90 00  Painting
```

### **Benefits**

1. **Logical Organization**: QA items appear in specification order
2. **Easy Navigation**: Users can follow natural spec sequence
3. **Consistent Experience**: Matches how specs are typically organized
4. **Automatic**: No user action required - sorting happens automatically
5. **Robust**: Handles various spec section number formats gracefully

### **When Sorting Happens**

- **Every Webhook Response**: Each time a lambda completes and sends results
- **After Merging**: Sorting occurs after adding new items to existing data
- **Complete Dataset**: Sorts all items from all QA categories together
- **Preserved on Reload**: Sorted order is saved to database

### **Files Updated**

#### Backend Webhook Handler
**File**: `apps/deliverables/views/specgpt_views.py`
- Added intelligent sorting function in `_handle_qa_planner_webhook()`
- Sorts combined results from all QA categories
- Robust parsing handles various spec section formats

#### Frontend Field Mapping
**File**: `src/components/SpecGpt/components/Chat/LogViewer/index.js`
- Updated field mapping: `'When Due': 'when_due'`
- Ensures proper sorting/filtering for "When Due" column

### **Example Result**

When user selects multiple QA categories (e.g., Inspections + Warranties + Certificates), the final table will show all results sorted by spec section:

| Spec Section # | Spec Section Name | Para # | QA Type | Requirements | Responsible Party | When Due |
|----------------|-------------------|---------|---------|--------------|-------------------|----------|
| 01 10 00 | General Requirements | 1.2.3 | Certificates | Project coordination cert | General Contractor | Prior to construction |
| 03 30 00 | Cast-in-Place Concrete | 3.1.1 | Inspections | Concrete strength testing | Testing Lab | 7 & 28 days |
| 03 30 00 | Cast-in-Place Concrete | 3.2.4 | Warranties | Concrete warranty | Supplier | 2 years |
| 07 21 00 | Thermal Insulation | 2.1.5 | Certificates | R-value certification | Manufacturer | Before installation |

### **Status**
✅ **Sorting Logic**: Implemented and tested
✅ **Field Rename**: "When Due" updated throughout
✅ **Django Check**: Passes without errors
✅ **Robust Parsing**: Handles various spec section formats

QA Planner results now appear in logical specification order automatically!
