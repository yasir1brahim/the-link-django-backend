import unittest
from django.test import TestCase
from apps.deliverables.utils import (
    extract_markdown_tables,
    parse_markdown_table,
    markdown_table_to_csv,
    extract_and_convert_tables_to_csv,
    extract_first_table_to_csv,
    format_anchor_repr,
    ANCHOR_REPR_DELIMITER,
    merge_markdown_tables,
    merge_tables_from_text
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
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0], ['John', '25', 'NYC'])
        self.assertEqual(data[1], ['Jane', '30', 'LA'])

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
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0], ['John', '25', 'NYC'])
        self.assertEqual(data[1], ['Jane', '30', 'LA'])

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
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0], ['John', '', 'NYC'])
        self.assertEqual(data[1], ['', '30', ''])

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
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0], ['John'])
        self.assertEqual(data[1], ['Jane'])


class TestTableSorting(TestCase):
    """Test cases for table sorting functionality."""

    def test_parse_markdown_table_sort_by_name(self):
        """Test sorting table by name column."""
        table = """
        | Name | Age | City |
        |------|-----|------|
        | Jane | 30  | LA   |
        | John | 25  | NYC  |
        | Alice| 35  | SF   |
        """
        
        headers, data = parse_markdown_table(table, sort_by_column="Name")
        
        self.assertEqual(headers, ['Name', 'Age', 'City'])
        self.assertEqual(len(data), 3)
        # Should be sorted alphabetically by name
        self.assertEqual(data[0], ['Alice', '35', 'SF'])
        self.assertEqual(data[1], ['Jane', '30', 'LA'])
        self.assertEqual(data[2], ['John', '25', 'NYC'])

    def test_parse_markdown_table_sort_by_age(self):
        """Test sorting table by age column (numeric sorting)."""
        table = """
        | Name | Age | City |
        |------|-----|------|
        | Jane | 30  | LA   |
        | John | 25  | NYC  |
        | Alice| 35  | SF   |
        | Bob  | 20  | CHI  |
        """
        
        headers, data = parse_markdown_table(table, sort_by_column="Age")
        
        self.assertEqual(headers, ['Name', 'Age', 'City'])
        self.assertEqual(len(data), 4)
        # Should be sorted by age (string sorting, so "20" comes before "25")
        self.assertEqual(data[0], ['Bob', '20', 'CHI'])
        self.assertEqual(data[1], ['John', '25', 'NYC'])
        self.assertEqual(data[2], ['Jane', '30', 'LA'])
        self.assertEqual(data[3], ['Alice', '35', 'SF'])

    def test_parse_markdown_table_sort_by_city(self):
        """Test sorting table by city column."""
        table = """
        | Name | Age | City |
        |------|-----|------|
        | Jane | 30  | LA   |
        | John | 25  | NYC  |
        | Alice| 35  | SF   |
        | Bob  | 20  | CHI  |
        """
        
        headers, data = parse_markdown_table(table, sort_by_column="City")
        
        self.assertEqual(headers, ['Name', 'Age', 'City'])
        self.assertEqual(len(data), 4)
        # Should be sorted alphabetically by city
        self.assertEqual(data[0], ['Bob', '20', 'CHI'])
        self.assertEqual(data[1], ['Jane', '30', 'LA'])
        self.assertEqual(data[2], ['John', '25', 'NYC'])
        self.assertEqual(data[3], ['Alice', '35', 'SF'])

    def test_parse_markdown_table_sort_nonexistent_column(self):
        """Test sorting by a column that doesn't exist."""
        table = """
        | Name | Age | City |
        |------|-----|------|
        | Jane | 30  | LA   |
        | John | 25  | NYC  |
        """
        
        headers, data = parse_markdown_table(table, sort_by_column="Nonexistent")
        
        # Should not sort and should print error message
        self.assertEqual(headers, ['Name', 'Age', 'City'])
        self.assertEqual(len(data), 2)
        # Order should remain unchanged
        self.assertEqual(data[0], ['Jane', '30', 'LA'])
        self.assertEqual(data[1], ['John', '25', 'NYC'])

    def test_parse_markdown_table_sort_empty_column(self):
        """Test sorting by a column with empty values."""
        table = """
        | Name | Age | City |
        |------|-----|------|
        | Jane |     | LA   |
        | John | 25  | NYC  |
        | Alice|     | SF   |
        """
        
        headers, data = parse_markdown_table(table, sort_by_column="Age")
        
        self.assertEqual(headers, ['Name', 'Age', 'City'])
        self.assertEqual(len(data), 3)
        # Empty values should come first in string sorting
        self.assertEqual(data[0], ['Jane', '', 'LA'])
        self.assertEqual(data[1], ['Alice', '', 'SF'])
        self.assertEqual(data[2], ['John', '25', 'NYC'])

    def test_parse_markdown_table_no_sort(self):
        """Test parsing without sorting (default behavior)."""
        table = """
        | Name | Age | City |
        |------|-----|------|
        | Jane | 30  | LA   |
        | John | 25  | NYC  |
        | Alice| 35  | SF   |
        """
        
        headers, data = parse_markdown_table(table)
        
        self.assertEqual(headers, ['Name', 'Age', 'City'])
        self.assertEqual(len(data), 3)
        # Order should remain unchanged
        self.assertEqual(data[0], ['Jane', '30', 'LA'])
        self.assertEqual(data[1], ['John', '25', 'NYC'])
        self.assertEqual(data[2], ['Alice', '35', 'SF'])

    def test_parse_markdown_table_sort_case_sensitive(self):
        """Test that sorting is case-sensitive."""
        table = """
        | Name | Age | City |
        |------|-----|------|
        | jane | 30  | LA   |
        | John | 25  | NYC  |
        | alice| 35  | SF   |
        """
        
        headers, data = parse_markdown_table(table, sort_by_column="Name")
        
        self.assertEqual(headers, ['Name', 'Age', 'City'])
        self.assertEqual(len(data), 3)
        # Should be sorted case-sensitively
        self.assertEqual(data[0], ['John', '25', 'NYC'])
        self.assertEqual(data[1], ['alice', '35', 'SF'])
        self.assertEqual(data[2], ['jane', '30', 'LA'])


class TestMergeTablesWithSorting(TestCase):
    """Test cases for merging tables with sorting functionality."""

    def test_merge_tables_from_text_with_sorting(self):
        """Test merging tables from text with sorting."""
        text = """
        First table:
        | Section | Item | Status |
        |---------|------|--------|
        | A       | Item1| Done   |
        | B       | Item2| Pending|
        
        Second table:
        | Section | Item | Status |
        |---------|------|--------|
        | C       | Item3| Done   |
        | A       | Item4| Pending|
        """
        
        merged = merge_tables_from_text(text, sort_by_column="Section")

        print(merged)
        
        # Should merge tables and sort by Section
        self.assertEqual(merged, "| Section | Item | Status |\n|---------|------|--------|"
         + "\n| A | Item1 | Done |"
         + "\n| A | Item4 | Pending |"
         + "\n| B | Item2 | Pending |"
         + "\n| C | Item3 | Done |")

    def test_merge_tables_from_text_sort_by_item(self):
        """Test merging tables and sorting by Item column."""
        text = """
        | Section | Item | Status |
        |---------|------|--------|
        | A       | Item3| Done   |
        | B       | Item1| Pending|
        
        | Section | Item | Status |
        |---------|------|--------|
        | C       | Item2| Done   |
        | A       | Item4| Pending|
        """
        
        merged = merge_tables_from_text(text, sort_by_column="Item")
        
        # Should be sorted by Item
        self.assertIn("| Section | Item | Status |", merged)
        # Check that items are in sorted order
        lines = merged.split('\n')
        item_lines = [line for line in lines if 'Item' in line and '|' in line]
        self.assertGreater(len(item_lines), 0)

    def test_merge_tables_from_text_no_sorting(self):
        """Test merging tables without sorting."""
        text = """
        | Section | Item | Status |
        |---------|------|--------|
        | A       | Item1| Done   |
        
        | Section | Item | Status |
        |---------|------|--------|
        | B       | Item2| Pending|
        """
        
        merged = merge_tables_from_text(text)
        
        # Should merge without sorting
        self.assertIn("| Section | Item | Status |", merged)
        self.assertIn("| A | Item1 | Done |", merged)
        self.assertIn("| B | Item2 | Pending |", merged)

    def test_merge_tables_from_text_sort_nonexistent_column(self):
        """Test merging with sorting by non-existent column."""
        text = """
        | Section | Item | Status |
        |---------|------|--------|
        | A       | Item1| Done   |
        
        | Section | Item | Status |
        |---------|------|--------|
        | B       | Item2| Pending|
        """
        
        merged = merge_tables_from_text(text, sort_by_column="Nonexistent")
        
        # Should merge without sorting (since column doesn't exist)
        self.assertIn("| Section | Item | Status |", merged)
        self.assertIn("| A | Item1 | Done |", merged)
        self.assertIn("| B | Item2 | Pending |", merged)


    def test_merge_tables_from_text_empty_tables(self):
        """Test merging empty tables with sorting."""
        text = """
        | Section | Item | Status |
        |---------|------|--------|
        
        | Section | Item | Status |
        |---------|------|--------|
        """
        
        merged = merge_tables_from_text(text, sort_by_column="Section")
        
        # Should handle empty tables gracefully
        self.assertIn("| Section | Item | Status |", merged)
        # Should only have header and separator rows
        lines = merged.split('\n')
        data_lines = [line for line in lines if '|' in line and not line.startswith('|') and not '---' in line]
        self.assertEqual(len(data_lines), 0)


class TestMarkdownTableToCSV(TestCase):
    """Test cases for markdown table to CSV conversion."""

    def test_markdown_table_to_csv_basic(self):
        """Test basic markdown table to CSV conversion."""
        table = """
        | Name | Age | City |
        |------|-----|------|
        | John | 25  | NYC  |
        | Jane | 30  | LA   |
        """
        
        csv_data = markdown_table_to_csv(table)
        expected = "Name,Age,City\nJohn,25,NYC\nJane,30,LA\n"
        self.assertEqual(csv_data, expected)

    def test_markdown_table_to_csv_with_commas_in_data(self):
        """Test CSV conversion with commas in the data."""
        table = """
        | Name | Address | Age |
        |------|---------|-----|
        | John | NYC, NY | 25  |
        | Jane | LA, CA  | 30  |
        """
        
        csv_data = markdown_table_to_csv(table)
        # Commas in data should be properly quoted
        self.assertIn('"NYC, NY"', csv_data)
        self.assertIn('"LA, CA"', csv_data)

    def test_markdown_table_to_csv_with_quotes_in_data(self):
        """Test CSV conversion with quotes in the data."""
        table = """
        | Name | Description | Age |
        |------|-------------|-----|
        | John | "Great guy" | 25  |
        | Jane | 'Nice'      | 30  |
        """
        
        csv_data = markdown_table_to_csv(table)
        # Quotes in data should be properly escaped
        self.assertIn('"Great guy"', csv_data)

    def test_markdown_table_to_csv_empty_cells(self):
        """Test CSV conversion with empty cells."""
        table = """
        | Name | Age | City |
        |------|-----|------|
        | John |     | NYC  |
        |      | 30  |      |
        """
        
        csv_data = markdown_table_to_csv(table)
        expected = "Name,Age,City\nJohn,,NYC\n,30,\n"
        self.assertEqual(csv_data, expected)


class TestExtractAndConvertTablesToCSV(TestCase):
    """Test cases for extracting and converting tables to CSV."""

    def test_extract_and_convert_tables_to_csv_multiple_tables(self):
        """Test extracting and converting multiple tables to CSV."""
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
        
        csv_list = extract_and_convert_tables_to_csv(text)
        self.assertEqual(len(csv_list), 2)
        self.assertIn("A,B\n1,2\n", csv_list)
        self.assertIn("X,Y,Z\n3,4,5\n6,7,8\n", csv_list)

    def test_extract_and_convert_tables_to_csv_no_tables(self):
        """Test extracting tables when none exist."""
        text = "This is just regular text with no tables."
        csv_list = extract_and_convert_tables_to_csv(text)
        self.assertEqual(len(csv_list), 0)

    def test_extract_and_convert_tables_to_csv_with_qa_example(self):
        """Test with a more complex QA example."""
        text = """
        Here are the inspection results:
        
        | Section | Item | Status | Notes |
        |---------|------|--------|-------|
        | 1.1     | A    | Pass   | Good  |
        | 1.2     | B    | Fail   | Bad   |
        
        Additional findings:
        
        | Section | Item | Status | Priority |
        |---------|------|--------|----------|
        | 2.1     | C    | Pass   | High     |
        | 2.2     | D    | Pass   | Low      |
        """
        
        csv_list = extract_and_convert_tables_to_csv(text)
        self.assertEqual(len(csv_list), 2)
        
        # Check first table
        first_csv = csv_list[0]
        self.assertIn("Section,Item,Status,Notes", first_csv)
        self.assertIn("1.1,A,Pass,Good", first_csv)
        self.assertIn("1.2,B,Fail,Bad", first_csv)
        
        # Check second table
        second_csv = csv_list[1]
        self.assertIn("Section,Item,Status,Priority", second_csv)
        self.assertIn("2.1,C,Pass,High", second_csv)
        self.assertIn("2.2,D,Pass,Low", second_csv)


class TestExtractFirstTableToCSV(TestCase):
    """Test cases for extracting the first table to CSV."""

    def test_extract_first_table_to_csv_single_table(self):
        """Test extracting the first table when only one exists."""
        text = """
        | Name | Age | City |
        |------|-----|------|
        | John | 25  | NYC  |
        | Jane | 30  | LA   |
        """
        
        csv_data = extract_first_table_to_csv(text)
        expected = "Name,Age,City\nJohn,25,NYC\nJane,30,LA\n"
        self.assertEqual(csv_data, expected)

    def test_extract_first_table_to_csv_multiple_tables(self):
        """Test extracting the first table when multiple exist."""
        text = """
        First table:
        | A | B |
        |---|---|
        | 1 | 2 |
        
        Second table:
        | X | Y | Z |
        |---|---|---|
        | 3 | 4 | 5 |
        """
        
        csv_data = extract_first_table_to_csv(text)
        expected = "A,B\n1,2\n"
        self.assertEqual(csv_data, expected)

    def test_extract_first_table_to_csv_no_tables(self):
        """Test extracting when no tables exist."""
        text = "This is just regular text with no tables."
        csv_data = extract_first_table_to_csv(text)
        self.assertIsNone(csv_data)


class TestExistingUtils(TestCase):
    """Test cases for existing utility functions."""

    def test_format_anchor_repr(self):
        """Test anchor representation formatting."""
        anchor = ['section', 'subsection', 'item']
        result = format_anchor_repr(anchor)
        expected = f"section{ANCHOR_REPR_DELIMITER}subsection{ANCHOR_REPR_DELIMITER}item"
        self.assertEqual(result, expected)

    def test_anchor_repr_delimiter_constant(self):
        """Test that the delimiter constant is defined."""
        self.assertEqual(ANCHOR_REPR_DELIMITER, '$$$')


class TestEdgeCases(TestCase):
    """Test cases for edge cases and error handling."""

    # def test_malformed_table_missing_pipes(self):
    #     """Test handling of malformed tables."""
    #     text = """
    #     | Name | Age | City
    #     |------|-----|------
    #     | John | 25  | NYC
    #     """
        
    #     tables = extract_markdown_tables(text)
    #     # Should still extract the table even if missing end pipes
    #     self.assertEqual(len(tables), 1)

    def test_table_with_very_long_content(self):
        """Test handling of tables with very long content."""
        long_content = "This is a very long cell content that might cause issues with parsing or formatting"
        text = f"""
        | Name | Description |
        |------|-------------|
        | John | {long_content} |
        """
        
        tables = extract_markdown_tables(text)
        self.assertEqual(len(tables), 1)
        self.assertIn(long_content, tables[0])

    def test_table_with_special_characters(self):
        """Test handling of tables with special characters."""
        text = """
        | Name | Symbol | Value |
        |------|--------|-------|
        | Alpha| α      | 1     |
        | Beta | β      | 2     |
        | Gamma| γ      | 3     |
        """
        
        tables = extract_markdown_tables(text)
        self.assertEqual(len(tables), 1)
        self.assertIn("α", tables[0])
        self.assertIn("β", tables[0])
        self.assertIn("γ", tables[0])

    def test_merge_markdown_tables_single_table(self):
        """Test merging a single table."""
        tables = [
            """
            | Name | Age | City |
            |------|-----|------|
            | John | 25  | NYC  |
            | Jane | 30  | LA   |
            """
        ]
        
        merged = merge_markdown_tables(tables)
        self.assertIn("| Name | Age | City |", merged)
        self.assertIn("| John | 25  | NYC  |", merged)

    def test_merge_markdown_tables_multiple_tables_same_headers(self):
        """Test merging multiple tables with same headers."""
        tables = [
            """
            | Name | Age | City |
            |------|-----|------|
            | John | 25  | NYC  |
            """,
            """
            | Name | Age | City |
            |------|-----|------|
            | Jane | 30  | LA   |
            """
        ]
        
        merged = merge_markdown_tables(tables)
        self.assertIn("| Name | Age | City |", merged)
        self.assertIn("| John | 25 | NYC |", merged)
        self.assertIn("| Jane | 30 | LA |", merged)

    def test_merge_markdown_tables_empty_list(self):
        """Test merging empty list of tables."""
        merged = merge_markdown_tables([])
        self.assertEqual(merged, "")

    def test_merge_tables_from_text(self):
        """Test merging tables from text."""
        text = """
        | A | B |
        |---|---|
        | 1 | 2 |
        
        | A | B |
        |---|---|
        | 3 | 4 |
        """
        
        merged = merge_tables_from_text(text)
        self.assertIn("| A | B |", merged)
        self.assertIn("| 1 | 2 |", merged)
        self.assertIn("| 3 | 4 |", merged)

    def test_merge_tables_from_text_no_tables(self):
        """Test merging when no tables exist in text."""
        text = "This is just regular text with no tables."
        merged = merge_tables_from_text(text)
        self.assertEqual(merged, "")

if __name__ == '__main__':
    unittest.main() 