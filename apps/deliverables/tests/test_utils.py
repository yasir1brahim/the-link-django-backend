import unittest
from django.test import TestCase
from apps.deliverables.utils import (
    extract_markdown_tables,
    parse_markdown_table,
    markdown_table_to_csv,
    extract_and_convert_tables_to_csv,
    extract_first_table_to_csv,
    format_anchor_repr,
    ANCHOR_REPR_DELIMITER
)


class TestMarkdownTableExtraction(TestCase):
    """Test cases for markdown table extraction functionality."""

    def test_extract_markdown_tables_single_table(self):
        """Test extracting a single markdown table from text."""
        text = """
        Here's some text before the table.
        
        | Name | Age | City |
        |------|-----|------|
        | John | 25  | NYC  |
        | Jane | 30  | LA   |
        
        And some text after the table.
        """
        
        tables = extract_markdown_tables(text)
        self.assertEqual(len(tables), 1)
        self.assertIn("| Name | Age | City |", tables[0])
        self.assertIn("| John | 25  | NYC  |", tables[0])

    def test_extract_markdown_tables_multiple_tables(self):
        """Test extracting multiple markdown tables from text."""
        text = """
        First table:
        | A | B |
        |---|---|
        | 1 | 2 |
        
        Second table:
        | X | Y | Z |
        |---|---|---|
        | 3 | 4 | 5 |
        | 6 | 7 | 8 |
        """
        
        tables = extract_markdown_tables(text)
        self.assertEqual(len(tables), 2)
        self.assertIn("| A | B |", tables[0])
        self.assertIn("| X | Y | Z |", tables[1])

    def test_extract_markdown_tables_no_tables(self):
        """Test extracting tables when none exist."""
        text = "This is just regular text with no tables."
        tables = extract_markdown_tables(text)
        self.assertEqual(len(tables), 0)

    def test_extract_markdown_tables_incomplete_table(self):
        """Test handling of incomplete table structures."""
        text = """
        | Name | Age |
        |------|-----|
        """
        tables = extract_markdown_tables(text)
        self.assertEqual(len(tables), 1)

    def test_extract_markdown_tables_with_extra_spaces(self):
        """Test extracting tables with various spacing patterns."""
        text = """
        |  Name   |  Age  |  City   |
        |---------|-------|---------|
        |  John   |  25   |  NYC    |
        |  Jane   |  30   |  LA     |
        """
        
        tables = extract_markdown_tables(text)
        self.assertEqual(len(tables), 1)
        self.assertIn("|  Name   |  Age  |  City   |", tables[0])


class TestMarkdownTableParsing(TestCase):
    """Test cases for parsing markdown table structure."""

    def test_parse_markdown_table_basic(self):
        """Test basic table parsing."""
        table = """
        | Name | Age | City |
        |------|-----|------|
        | John | 25  | NYC  |
        | Jane | 30  | LA   |
        """
        
        headers, data = parse_markdown_table(table)
        
        self.assertEqual(headers, ['Name', 'Age', 'City'])
        self.assertEqual(data, [
            ['John', '25', 'NYC'],
            ['Jane', '30', 'LA']
        ])

    def test_parse_markdown_table_with_spaces(self):
        """Test parsing table with extra spaces."""
        table = """
        |  Name   |  Age  |  City   |
        |---------|-------|---------|
        |  John   |  25   |  NYC    |
        |  Jane   |  30   |  LA     |
        """
        
        headers, data = parse_markdown_table(table)
        
        self.assertEqual(headers, ['Name', 'Age', 'City'])
        self.assertEqual(data, [
            ['John', '25', 'NYC'],
            ['Jane', '30', 'LA']
        ])

    def test_parse_markdown_table_empty_cells(self):
        """Test parsing table with empty cells."""
        table = """
        | Name | Age | City |
        |------|-----|------|
        | John |     | NYC  |
        |      | 30  |      |
        """
        
        headers, data = parse_markdown_table(table)
        
        self.assertEqual(headers, ['Name', 'Age', 'City'])
        self.assertEqual(data, [
            ['John', '', 'NYC'],
            ['', '30', '']
        ])

    def test_parse_markdown_table_single_column(self):
        """Test parsing single column table."""
        table = """
        | Name |
        |------|
        | John |
        | Jane |
        """
        
        headers, data = parse_markdown_table(table)
        
        self.assertEqual(headers, ['Name'])
        self.assertEqual(data, [['John'], ['Jane']])


class TestMarkdownTableToCSV(TestCase):
    """Test cases for converting markdown tables to CSV."""

    def test_markdown_table_to_csv_basic(self):
        """Test basic markdown to CSV conversion."""
        table = """
        | Name | Age | City |
        |------|-----|------|
        | John | 25  | NYC  |
        | Jane | 30  | LA   |
        """
        
        csv_content = markdown_table_to_csv(table)
        expected = "Name,Age,City\nJohn,25,NYC\nJane,30,LA\n"
        self.assertEqual(csv_content, expected)

    def test_markdown_table_to_csv_with_commas_in_data(self):
        """Test CSV conversion with commas in the data."""
        table = """
        | Name | Description | Location |
        |------|-------------|----------|
        | John | Hello, world | NYC, NY |
        | Jane | No commas here | LA, CA |
        """
        
        csv_content = markdown_table_to_csv(table)
        # CSV should properly escape commas
        self.assertIn('"Hello, world"', csv_content)
        self.assertIn('"NYC, NY"', csv_content)

    def test_markdown_table_to_csv_with_quotes_in_data(self):
        """Test CSV conversion with quotes in the data."""
        table = """
        | Name | Quote |
        |------|-------|
        | John | "Hello" |
        | Jane | No quotes |
        """
        
        csv_content = markdown_table_to_csv(table)
        # CSV should properly escape quotes
        self.assertIn('"""Hello"""', csv_content)

    def test_markdown_table_to_csv_empty_cells(self):
        """Test CSV conversion with empty cells."""
        table = """
        | Name | Age | City |
        |------|-----|------|
        | John |     | NYC  |
        |      | 30  |      |
        """
        
        csv_content = markdown_table_to_csv(table)
        expected = "Name,Age,City\nJohn,,NYC\n,30,\n"
        self.assertEqual(csv_content, expected)


class TestExtractAndConvertTablesToCSV(TestCase):
    """Test cases for extracting and converting multiple tables to CSV."""

    def test_extract_and_convert_tables_to_csv_multiple_tables(self):
        """Test extracting and converting multiple tables."""
        text = """
        First table:
        | A | B |
        |---|---|
        | 1 | 2 |
        
        Second table:
        | X | Y |
        |---|---|
        | 3 | 4 |
        """
        
        csv_tables = extract_and_convert_tables_to_csv(text)
        
        self.assertEqual(len(csv_tables), 2)
        self.assertEqual(csv_tables[0], "A,B\n1,2\n")
        self.assertEqual(csv_tables[1], "X,Y\n3,4\n")

    def test_extract_and_convert_tables_to_csv_no_tables(self):
        """Test when no tables are found."""
        text = "This is just regular text with no tables."
        csv_tables = extract_and_convert_tables_to_csv(text)
        self.assertEqual(len(csv_tables), 0)

    def test_extract_and_convert_tables_to_csv_with_qa_example(self):
        text = """Spec Section # | Spec Section Name | Deliverable Type | When Due | Responsible Party | Exact Requirement Text
--- | --- | --- | --- | --- | ---
01 2600 | CONTRACT MODIFICATION PROCEDURES | Survey Data | If requested | Contractor | If requested, furnish survey data to substantiate quantities.
01 3100 | PROJECT MANAGEMENT AND COORDINATION | Field Report Log | Submit log weekly | Contractor | Field Report Log: Prepare, maintain, and submit a tabular log of Architect’s Field Report items organized by each item number. Submit log weekly. Include the following: [list omitted for brevity].
01 3200 | CONSTRUCTION PROGRESS DOCUMENTATION | Daily Construction Report | Submit at monthly intervals | Contractor | Daily Construction Reports: Submit at monthly intervals.
01 3200 | CONSTRUCTION PROGRESS DOCUMENTATION | Field Condition Reports | Submit at time of discovery of differing conditions | Contractor | Field Condition Reports: Submit at time of discovery of differing conditions.
01 3200 | CONSTRUCTION PROGRESS DOCUMENTATION | Special Reports | Submit at time of unusual event | Contractor | Special Reports: Submit at time of unusual event.
01 3200 | CONSTRUCTION PROGRESS DOCUMENTATION | Contractor's Construction Schedule Updating | At monthly intervals | Contractor | Contractor's Construction Schedule Updating: At monthly intervals, update schedule to reflect actual construction progress and activities.
01 3233 | PHOTOGRAPHIC DOCUMENTATION | Key Plan | Submit with photographic documentation | Contractor | Key Plan: Submit key plan of Project site and building with notation of vantage points marked for location and direction of each photograph and video recording.
01 3233 | PHOTOGRAPHIC DOCUMENTATION | Digital Photographs | Submit image files within three days of taking photographs | Contractor | Digital Photographs: Submit image files within three days of taking photographs.
01 3233 | PHOTOGRAPHIC DOCUMENTATION | Construction Photographs | Submit two prints of each photographic view within seven days of taking photographs | Contractor | Construction Photographs: Submit two prints of each photographic view within seven days of taking photographs.
01 3233 | PHOTOGRAPHIC DOCUMENTATION | Video Recordings | Submit video recordings within seven days of recording | Contractor | Video Recordings: Submit video recordings within seven days of recording.
01 4000 | QUALITY REQUIREMENTS | Contractor's Quality-Control Plan | Within 10 days of Notice to Proceed, and not less than five days prior to preconstruction conference | Contractor | Quality-Control Plan, General: Submit quality-control plan within 10 days of Notice to Proceed, and not less than five days prior to preconstruction conference.
01 4000 | QUALITY REQUIREMENTS | Schedule of Tests and Inspections | Submit in tabular form concurrent with Contractor's construction schedule | Contractor | Schedule of Tests and Inspections: Prepare in tabular form and include the following: [list omitted for brevity].
01 4000 | QUALITY REQUIREMENTS | Test and Inspection Reports | Prepare and submit certified written reports specified in other Sections | Not stated | "Test and Inspection Reports: Prepare and submit certified written reports specified in other Sections."
01 4000 | QUALITY REQUIREMENTS | Manufacturer's Technical Representative's Field Reports | Prepare written information documenting manufacturer's technical representative's tests and inspections | Not stated | Manufacturer's Technical Representative's Field Reports: Prepare written information documenting manufacturer's technical representative's tests and inspections specified in other Sections.
01 4000 | QUALITY REQUIREMENTS | Factory-Authorized Service Representative's Reports | Prepare written information documenting manufacturer's factory-authorized service representative's tests and inspections | Not stated | Factory-Authorized Service Representative's Reports: Prepare written information documenting manufacturer's factory-authorized service representative's tests and inspections specified in other Sections.
01 4000 | QUALITY REQUIREMENTS | Permits, Licenses, and Certificates | For Owner's records | Contractor | Permits, Licenses, and Certificates: For Owner's records, submit copies of permits, licenses, certifications, inspection reports, releases, jurisdictional settlements, notices, receipts for fee payments, judgments, correspondence, records, and similar documents, established for compliance with standards and regulations bearing on performance of the Work.
01 4000 | QUALITY REQUIREMENTS | Test and Inspection Log | Maintain log at Project site | Contractor | Test and Inspection Log: Prepare a record of tests and inspections [list omitted for brevity]. Maintain log at Project site. Post changes and modifications as they occur. Provide access to test and inspection log for Architect's reference during normal working hours.
01 7700 | CLOSEOUT PROCEDURES | Project Record Documents, O&M Manuals, etc. | Before requesting inspection for determining date of Substantial Completion | Contractor | Prepare and submit Project Record Documents, operation and maintenance manuals, final completion construction photographic documentation, damage or settlement surveys, property surveys, and similar final record information.
01 7700 | CLOSEOUT PROCEDURES | List of Incomplete Items (Punch List) | With request for Substantial Completion inspection | Contractor | Prepare a list of items to be completed and corrected (punch list), the value of items on the list, and reasons why the Work is not complete.
01 7700 | CLOSEOUT PROCEDURES | Certified Copy of Architect's Substantial Completion inspection list | Submit before requesting final inspection for determining final completion | Contractor | Submit certified copy of Architect's Substantial Completion inspection list of items to be completed or corrected (punch list), endorsed and dated by Architect. The certified copy of the list shall state that each item has been completed or otherwise resolved for acceptance.
01 7823 | OPERATION AND MAINTENANCE DATA | Operation and Maintenance Manuals (Initial Draft) | At least 30 days before commencing demonstration and training | Contractor | Initial Manual Submittal: Submit draft copy of each manual at least 30 days before commencing demonstration and training.
01 7823 | OPERATION AND MAINTENANCE DATA | Operation and Maintenance Manuals (Final) | Prior to requesting inspection for Substantial Completion and at least 15 days before commencing demonstration and training | Contractor | Final Manual Submittal: Submit each manual in final form prior to requesting inspection for Substantial Completion and at least 15 days before commencing demonstration and training.
01 7839 | PROJECT RECORD DOCUMENTS | Record Drawings, Specifications, Product Data, etc. | At Project closeout | Contractor | Submit (as required): one set(s) of marked-up record prints [for Record Drawings], one paper copy and annotated PDF electronic files [for Record Specifications/Product Data], and other record submittals as specified.
01 7900 | DEMONSTRATION AND TRAINING | Instruction Program Outline, Attendance Record, Evaluations | Prior to training modules | Contractor | Instruction Program: Submit outline of instructional program for demonstration and training, including a list of training modules and a schedule of proposed dates, times, length of instruction time, and instructors' names for each training module.
01 7900 | DEMONSTRATION AND TRAINING | Demonstration and Training Video Recordings | Submit two copies within seven days of end of each training module | Contractor | Demonstration and Training Video Recordings: Submit two copies within seven days of end of each training module.
02 4119 | SELECTIVE STRUCTURE DEMOLITION | Inventory | After selective demolition is complete | Contractor | Inventory: After selective demolition is complete, submit a list of items that have been removed and salvaged.
02 4119 | SELECTIVE STRUCTURE DEMOLITION | Predemolition Photographs | Submit before Work begins | Contractor | Predemolition Photographs: Show existing conditions of adjoining construction and site improvements, including finish surfaces, that might be misconstrued as damage caused by selective demolition operations. Submit before Work begins.
03 30 01 | CAST-IN-PLACE CONCRETE FOR LANDSCAPE APPLICATIONS | Minutes of Pre-Concrete Conference | Submit before start of work | Contractor | Submit Minutes of Pre-Concrete Conference.
05 1200 | STRUCTURAL STEEL FRAMING | Welding certificates | Not stated | Not stated | Welding certificates.
05 1200 | STRUCTURAL STEEL FRAMING | Paint Compatibility Certificates | Not stated | Not stated | Paint Compatibility Certificates: From manufacturers of topcoats applied over shop primers, certifying that shop primers are compatible with topcoats.
05 1200 | STRUCTURAL STEEL FRAMING | Mill test reports for structural steel | Not stated | Not stated | Mill test reports for structural steel, including chemical and physical properties.
05 1200 | STRUCTURAL STEEL FRAMING | Product Test Reports (Bolts, Connectors, etc.) | Not stated | Not stated | Product Test Reports: For the following: Bolts, nuts, and washers including mechanical properties and chemical analysis. Direct-tension indicators. Tension-control, high-strength, bolt-nut-washer assemblies. Shear stud connectors. Shop primers. Nonshrink grout.
05 1200 | STRUCTURAL STEEL FRAMING | Survey of existing conditions | Not stated | Not stated | Survey of existing conditions.
05 1200 | STRUCTURAL STEEL FRAMING | Shop Tests and Inspections Reports | Not stated | Not stated | Testing Agency: Owner will engage a qualified testing agency to perform shop tests and inspections. Prepare test and inspection reports.
05 1200 | STRUCTURAL STEEL FRAMING | Field Test and Inspection Reports | Not stated | Not stated | Welded Connections: Visually inspect field welds according to AWS D1.1/D1.1M and the following inspection procedures, at testing agency's option: Magnetic Particle Inspection: ASTM E 709; performed on root pass and on finished weld. Cracks or zones of incomplete fusion or penetration are not accepted. Ultrasonic Inspection: ASTM E 164.
05 1200 | STRUCTURAL STEEL FRAMING | Special Inspections | Not stated | Not stated | Special Inspections: Owner will engage a qualified special inspector to perform the following special inspections: Verify structural-steel materials and inspect steel frame joint details. Verify weld materials and inspect welds. Verify connection materials and inspect high-strength bolted connections.
05 1517 | AUTOMOTIVE GUARDRAIL SYSTEM | Certified calibration curve for each jack | Not stated | Installer | Certified calibration curve for each jack to show the gauge pressure corresponding to the required jacking force.
05 1517 | AUTOMOTIVE GUARDRAIL SYSTEM | Certification from Installer on stressing | Not stated | Installer | Certification from Installer that stressing process and records have been reviewed and that forces specified have been provided.
05 1517 | AUTOMOTIVE GUARDRAIL SYSTEM | Stressing Records | Not stated | Installer | Stressing Records.
05 1517 | AUTOMOTIVE GUARDRAIL SYSTEM | Maintenance Data | At closeout | Contractor | Maintenance Data: Maintenance Manual: Assemble into binder. Methods for maintaining cable guardrail system, including periodic testing of stressed cable, methods of re-stressing and manufacturer's recommended maintenance schedule.
05 7000 | DECORATIVE METAL | Shop Drawings, Templates, Instructions for Embedded Items | Coordinate delivery of such items to the project site | Contractor | Furnish setting drawings, templates, and directions for installation of anchorages, including sleeves, concrete inserts, anchor bolts, and items with integral anchors, that are to be embedded in concrete or masonry. Coordinate delivery of such items to Project site in time for installation.
05 7500 | DECORATIVE FORMED METAL | Shop Drawings, Templates, Instructions for Embedded Items | Coordinate delivery of such items to the project site | Contractor | Coordinate and Furnish: Anchorages, setting drawings, diagrams, templates, instructions, and directions for installation of items having integral anchors embedded in concrete or masonry construction. Coordinate delivery of such items to the project site.
05 5100 | METAL STAIRS AND RAILINGS | Shop Drawings, Templates, Instructions for Embedded Items | Coordinate delivery of such items to the project site | Contractor | Coordinate and Furnish: Anchorages, setting drawings, diagrams, templates, instructions, and directions for installation of items having integral anchors embedded in concrete or masonry construction. Coordinate delivery of such items to the project site.
05 4000 | COLD-FORMED METAL FRAMING | Delegated-Design Submittal: Calculations | Not stated | Delegated Designer | Delegated-Design Submittal: Delegated Design Services Certification for installed products indicated to comply with performance requirements and design criteria, signed and sealed by the qualified Delegated Designer responsible for their preparation. Complete calculations signed and sealed by the delegated designer.
06 1053 | MISCELLANEOUS ROUGH CARPENTRY | FSC Chain-of-custody Documentation | Not stated | Contractor | Submit certificates for FSC compliance: Chain-of-custody certificates indicating that products specified to be made from certified wood comply with forest certification requirements. Include documentation that manufacturer is certified for chain of custody by an FSC-accredited certification body. Include statement indicating cost for each certified wood product.
08 9000 | FIXED LOUVERS | Delegated-Design Submittal: Calculations | Not stated | Delegated Designer | Delegated-Design Submittal: Delegated Design Services Certification for installed products indicated to comply with performance requirements and design criteria, signed and sealed by the qualified Delegated Designer responsible for their preparation. Including analysis data signed and sealed by the qualified professional engineer responsible for their preparation.
08 9000 | FIXED LOUVERS | Product Test Reports | Not stated | Not stated | Product Test Reports: Based on evaluation of comprehensive tests performed according to AMCA 500-L by a qualified testing agency or by manufacturer and witnessed by a qualified testing agency, for each type of louver and showing compliance with performance requirements specified.
08 4233 | REVOLVING DOOR ENTRANCES | Manufacturer's Certification of Emergency Exiting | Not stated | Manufacturer | Submit manufacturer's certification that doors comply with emergency exiting requirements.
08 4233 | REVOLVING DOOR ENTRANCES | Certified Test Results Showing Performance | Not stated | Manufacturer | Submit certified test results showing that revolving door units have been tested by a recognized testing laboratory or agency and comply with specified performance characteristics.
08 4233 | REVOLVING DOOR ENTRANCES | Maintenance Contracts | At Substantial Completion | Installer | Maintenance Contracts: Initial Maintenance Service: Beginning at Substantial Completion, provide 12 months' full maintenance by skilled employees of revolving door entrance Installer.
08 4233 | REVOLVING DOOR ENTRANCES | Warranty Documentation | At closeout | Contractor | Warranty Documentation [Section 1.5A(3)]: Submit warranty documentation to Owner.
08 4129 | ALUMINUM ENTRANCE DOORS & FRAMES | Certified Test Reports Showing Performance | Not stated | Not stated | Submit certified test reports showing compliance with the wind load, air infiltration, U-value, and CRF performance requirements certified by an independent test laboratory.
08 4129 | ALUMINUM ENTRANCE DOORS & FRAMES | Warranties | At closeout | Contractor | Warranties: 3 signed copies of the following: Entrance door warranty, Paint Finish, Stainless-steel warranty.
09 3000 | TILING | Field Report: Results of In-Place Waterproof Testing | Not stated | Not stated | Field Report: Results of in-place waterproof testing.
09 6300 | STONE FLOORING | Shop Drawings | Not stated | Contractor | Shop Drawings: Submit cutting and setting drawings indicating sizes, dimensions, sections and profiles of stone units, arrangement and provisions for jointing, supporting, anchoring and bonding stonework; and other details showing relationships with, attachment to related work.
09 7814 | METAL ACOUSTICAL PANEL WALLS | Extra Stock Material | At closeout | Contractor | Extra Stock Material: Furnish for each size, pattern and color installed in the Work. Deliver in manufacturer’s original packaging and store at the project site where directed by the Owner.
09 7814 | METAL ACOUSTICAL PANEL WALLS | Record documents | At closeout | Contractor | Record documents
09 5113 | ACOUSTICAL PANEL CEILINGS | Extra Stock Material | At closeout | Contractor | Extra Stock Material: Furnish for each size, pattern and color installed in the Work. Deliver in manufacturer’s original packaging and store at the project site where directed by the Owner.
09 5113 | ACOUSTICAL PANEL CEILINGS | Maintenance Manual | At closeout | Contractor | Maintenance Manual: Assemble into binder. Maintenance Practices: Manufacturer's recommended maintenance practices describing the materials, devices and procedures to be followed in cleaning and maintaining the Work.
09 5113 | ACOUSTICAL PANEL CEILINGS | Field Test Reports | Not stated | Testing Laboratory | Field Test: Testing laboratory, engaged at the Owner’s expense, will perform the following activities at the Owner’s discretion. Work not meeting specified requirements and other units having similar deficiencies shall be corrected at no cost to the Owner. Perform the following tests and inspections of completed installations of acoustical panel ceiling hangers and anchors and fasteners in successive stages.

(Note: Only the first 50 distinct deliverables were listed above. For brevity, repetitive, non-deliverable, or plainly referenced items without explicit submission instructions have been omitted, as required. If all report requirements from every section, including all recurring submittals across sections, are needed, more rows will be provided per the source text.)"""

        csv_tables = extract_and_convert_tables_to_csv(text)
        assert(len(csv_tables) > 0)
        print(csv_tables)


class TestExtractFirstTableToCSV(TestCase):
    """Test cases for extracting the first table to CSV."""

    def test_extract_first_table_to_csv_single_table(self):
        """Test extracting first table when only one exists."""
        text = """
        Here's a table:
        | Name | Age |
        |------|-----|
        | John | 25  |
        """
        
        csv_content = extract_first_table_to_csv(text)
        expected = "Name,Age\nJohn,25\n"
        self.assertEqual(csv_content, expected)

    def test_extract_first_table_to_csv_multiple_tables(self):
        """Test extracting first table when multiple exist."""
        text = """
        First table:
        | A | B |
        |---|---|
        | 1 | 2 |
        
        Second table:
        | X | Y |
        |---|---|
        | 3 | 4 |
        """
        
        csv_content = extract_first_table_to_csv(text)
        expected = "A,B\n1,2\n"
        self.assertEqual(csv_content, expected)

    def test_extract_first_table_to_csv_no_tables(self):
        """Test when no tables are found."""
        text = "This is just regular text with no tables."
        csv_content = extract_first_table_to_csv(text)
        self.assertIsNone(csv_content)


class TestExistingUtils(TestCase):
    """Test cases for existing utility functions."""

    def test_format_anchor_repr(self):
        """Test the existing format_anchor_repr function."""
        anchor = ['section1', 'subsection2', 'item3']
        result = format_anchor_repr(anchor)
        expected = ANCHOR_REPR_DELIMITER.join(anchor)
        self.assertEqual(result, expected)

    def test_anchor_repr_delimiter_constant(self):
        """Test that the delimiter constant is defined."""
        self.assertEqual(ANCHOR_REPR_DELIMITER, '$$$')


class TestEdgeCases(TestCase):
    """Test edge cases and error conditions."""

    # def test_malformed_table_missing_separator(self):
    #     """Test handling of malformed table without separator line."""
    #     text = """
    #     | Name | Age |
    #     | John | 25  |
    #     """
        
    #     tables = extract_markdown_tables(text)
    #     self.assertEqual(len(tables), 0)

    def test_malformed_table_missing_pipes(self):
        """Test handling of malformed table with missing pipes."""
        text = """
        Name | Age
        -----|-----
        John | 25
        """
        
        tables = extract_markdown_tables(text)
        self.assertEqual(len(tables), 0)

    def test_table_with_very_long_content(self):
        """Test handling of table with very long content."""
        long_name = "A" * 1000
        table = f"""
        | Name | Age |
        |------|-----|
        | {long_name} | 25  |
        """
        
        csv_content = markdown_table_to_csv(table)
        self.assertIn(long_name, csv_content)

    def test_table_with_special_characters(self):
        """Test handling of table with special characters."""
        table = """
        | Name | Special Chars |
        |------|---------------|
        | John | !@#$%^&*()   |
        | Jane | ñáéíóú        |
        """
        
        csv_content = markdown_table_to_csv(table)
        self.assertIn("!@#$%^&*()", csv_content)
        self.assertIn("ñáéíóú", csv_content)


if __name__ == '__main__':
    unittest.main() 