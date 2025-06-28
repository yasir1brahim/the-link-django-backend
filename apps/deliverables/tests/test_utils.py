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