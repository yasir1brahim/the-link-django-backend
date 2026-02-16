import re
import csv
import io
from typing import List, Optional, Tuple, Union
from django.db import transaction
from django.db.models import Max

ANCHOR_REPR_DELIMITER = '$$$'


def get_next_submittal_number(project_id: int, project_version_id: int) -> Optional[int]:
    """
    Calculate the next submittal number for a given project and project version.
    
    This function queries the database to find the maximum submittal number
    for the specified project and version, then returns the next sequential number.
    
    Args:
        project_id: The ID of the project
        project_version_id: The ID of the project version
        
    Returns:
        The next submittal number (as an integer), or None if no submittal numbers
        have been assigned yet for this project version.
        
    Example:
        >>> next_num = get_next_submittal_number(project_id=1, project_version_id=2)
        >>> # If max submittal_number is 5.0, returns 6
    """
    if project_version_id is None:
        return None

    # Import here to avoid circular imports
    from .models import SubmittalItem

    with transaction.atomic():
        current_max_number = (
            SubmittalItem.objects
            .select_for_update()
            .filter(project_id=project_id, project_version_id=project_version_id)
            .aggregate(Max('submittal_number'))
        )['submittal_number__max']

        # If there are no submittal numbers assigned yet, MAX() function
        # will return None
        if current_max_number is None:
            return None

        return int(round(current_max_number, 0)) + 1



def format_anchor_repr(anchor: list) -> str:
    # TODO: Is this good enough? Will this clash with any established practice?
    return ANCHOR_REPR_DELIMITER.join(anchor)


def extract_markdown_tables(text: str) -> List[str]:
    """
    Extract markdown tables from text content.
    
    Args:
        text: The text content that may contain markdown tables
        
    Returns:
        List of markdown table strings found in the text
        
    Example:
        >>> text = "Here's a table:\n| Name | Age |\n|------|-----|\n| John | 25  |\nAnd another:\n| City | State |\n|------|-------|\n| NYC  | NY    |"
        >>> tables = extract_markdown_tables(text)
        >>> len(tables)
        2
    """
    lines = text.split('\n')
    tables = []
    current_table = []
    in_table = False
    
    for line in lines:
        stripped_line = line.strip()
        
        # Check if this line looks like a table row
        # Case 1: Wrapped in pipes (standard markdown)
        if stripped_line.startswith('|') and stripped_line.endswith('|'):
            if not in_table:
                in_table = True
            current_table.append(line)
        # Case 2: Pipe-separated without wrapping (alternative format)
        elif '|' in stripped_line and not stripped_line.startswith('|') and not stripped_line.endswith('|'):
            # Check if it has multiple pipe-separated columns
            parts = stripped_line.split('|')
            if len(parts) >= 3:  # At least 2 columns (3 parts when split by |)
                if not in_table:
                    in_table = True
                # Convert to wrapped format for consistency
                wrapped_line = '|' + '|'.join(parts) + '|'
                current_table.append(wrapped_line)
        elif in_table:
            # Check if this is a separator line (contains dashes and pipes)
            if '|' in stripped_line and any(char in stripped_line for char in ['-', ':']):
                current_table.append(line)
            else:
                # End of table
                if len(current_table) >= 2:  # At least header and separator
                    tables.append('\n'.join(current_table))
                current_table = []
                in_table = False
    
    # Handle table at end of text
    if in_table and len(current_table) >= 2:
        tables.append('\n'.join(current_table))
    
    return [table.strip() for table in tables]


def parse_markdown_table(markdown_table: str, sort_by_column: str = None) -> Tuple[List[str], List[List[str]]]:
    """
    Parse a markdown table string into headers and data rows.
    
    Args:
        markdown_table: A markdown table string
        sort_by_column: The column to sort the data by
    Returns:
        Tuple of (headers, data_rows) where headers is a list of strings
        and data_rows is a list of lists of strings
        
    Example:
        >>> table = "| Name | Age | City |\n|------|-----|------|\n| John | 25  | NYC  |\n| Jane | 30  | LA   |"
        >>> headers, data = parse_markdown_table(table)
        >>> headers
        ['Name', 'Age', 'City']
        >>> data
        [['John', '25', 'NYC'], ['Jane', '30', 'LA']]
    """
    lines = markdown_table.strip().split('\n')
    
    # Extract headers from the first line
    header_line = lines[0]
    headers = [cell.strip() for cell in header_line.split('|')[1:-1]]
    
    # Skip the separator line (second line with dashes)
    data_lines = lines[2:] if len(lines) > 2 else []
    
    # Parse data rows
    data_rows = []
    for line in data_lines:
        if line.strip() and '|' in line:
            cells = [cell.strip() for cell in line.split('|')[1:-1]]
            data_rows.append(cells)
    
    if sort_by_column:
        try:
            headers.index(sort_by_column)
            data_rows.sort(key=lambda x: x[headers.index(sort_by_column)])
        except ValueError:
            print(f"Sort by column {sort_by_column} not found in headers {headers}")
    
    return headers, data_rows


def markdown_table_to_csv(markdown_table: str) -> str:
    """
    Convert a markdown table to CSV format.
    
    Args:
        markdown_table: A markdown table string
        
    Returns:
        CSV formatted string
        
    Example:
        >>> table = "| Name | Age | City |\n|------|-----|------|\n| John | 25  | NYC  |"
        >>> csv_data = markdown_table_to_csv(table)
        >>> print(csv_data)
        Name,Age,City
        John,25,NYC
    """
    headers, data_rows = parse_markdown_table(markdown_table)
    
    # Create CSV output
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write headers
    writer.writerow(headers)
    
    # Write data rows (if any)
    for row in data_rows:
        writer.writerow(row)
    
    csv_content = output.getvalue()
    output.close()
    
    # Normalize line endings to Unix style
    csv_content = csv_content.replace('\r\n', '\n')
    
    return csv_content


def extract_and_convert_tables_to_csv(text: str) -> List[str]:
    """
    Extract all markdown tables from text and convert each to CSV format.
    
    Args:
        text: The text content that may contain markdown tables
        
    Returns:
        List of CSV strings, one for each table found
        
    Example:
        >>> text = "Table 1:\n| A | B |\n|---|---|\n| 1 | 2 |\n\nTable 2:\n| X | Y |\n|---|---|\n| 3 | 4 |"
        >>> csv_list = extract_and_convert_tables_to_csv(text)
        >>> len(csv_list)
        2
        >>> print(csv_list[0])
        A,B
        1,2
    """
    tables = extract_markdown_tables(text)
    csv_tables = []
    
    for table in tables:
        csv_content = markdown_table_to_csv(table)
        csv_tables.append(csv_content)
    
    return csv_tables


def extract_first_table_to_csv(text: str) -> Optional[str]:
    """
    Extract the first markdown table from text and convert it to CSV format.
    
    Args:
        text: The text content that may contain markdown tables
        
    Returns:
        CSV string of the first table found, or None if no tables found
        
    Example:
        >>> text = "Here's a table:\n| Name | Age |\n|------|-----|\n| John | 25  |"
        >>> csv_data = extract_first_table_to_csv(text)
        >>> print(csv_data)
        Name,Age
        John,25
    """
    tables = extract_markdown_tables(text)
    if not tables:
        return None
    
    return markdown_table_to_csv(tables[0])


def merge_markdown_tables(tables: List[str], sort_by_column: str = None) -> str:
    """
    Merge multiple markdown tables into a single table.
    
    This function takes a list of markdown tables and merges them into a single table.
    It handles tables with different headers by creating a union of all headers.
    
    Args:
        tables: List of markdown table strings
        sort_by_column: The column to sort the data by
    Returns:
        A single markdown table string
        
    Example:
        >>> table1 = "| Name | Age |\n|------|-----|\n| John | 25  |"
        >>> table2 = "| Name | City |\n|------|------|\n| Jane | NYC  |"
        >>> merged = merge_markdown_tables([table1, table2])
        >>> print(merged)
        | Name | Age | City |
        |------|-----|------|
        | John | 25  |      |
        | Jane |     | NYC  |
    """
    if not tables:
        return ""
    
    if len(tables) == 1:
        return tables[0]
    
    # Parse all tables to get headers and data
    all_headers = set()
    all_data = []
    header_order = []  # Track the order headers appear
    
    for table in tables:
        headers, data_rows = parse_markdown_table(table)
        all_headers.update(headers)
        all_data.append((headers, data_rows))
        
        # Track header order as they appear
        for header in headers:
            if header not in header_order:
                header_order.append(header)
    
    # Create ordered list of all headers (preserve order of appearance)
    ordered_headers = header_order
    
    # Create the merged table
    merged_rows = []
    
    # Add header row
    header_parts = []
    for header in ordered_headers:
        header_parts.append(f" {header} ")
    header_row = "|" + "|".join(header_parts) + "|"
    merged_rows.append(header_row)
    
    
    # Add separator row (match original table format)
    separator_parts = []
    for header in ordered_headers:
        # Create separator that matches the header length + 2 (standard markdown format)
        separator_length = max(len(header) + 2, 5)
        separator_parts.append("-" * separator_length)
    separator_row = "|" + "|".join(separator_parts) + "|"
    merged_rows.append(separator_row)

    all_data_rows_with_headers = []
    for headers, data_rows in all_data:
        for row in data_rows:
            all_data_rows_with_headers.append((row, headers))
    
    # Add data rows
    merged_data_rows = []
    for row, headers in all_data_rows_with_headers:
        # Create a row with all headers, filling missing values with empty strings
        merged_row = []
        for header in ordered_headers:
            if header in headers:
                index = headers.index(header)
                if index < len(row):
                    cell_value = row[index]
                    # Pad the cell value to match expected format
                    if cell_value.strip():
                        # For non-empty values, add padding with trailing space
                        merged_row.append(str(cell_value))
                    else:
                        # For empty values, add 5 spaces
                        merged_row.append("")
                else:
                    merged_row.append("")
            else:
                merged_row.append("")
        merged_data_rows.append(merged_row)

    if sort_by_column:
        try:
            merged_data_rows.sort(key=lambda x: x[ordered_headers.index(sort_by_column)])
        except ValueError:
            print(f"Sort by column {sort_by_column} not found in headers {headers}")
    
    for row in merged_data_rows:
        row_strs = []
        for cell in row:
            if cell.strip():
                row_strs.append(f" {cell} ")
            else:
                row_strs.append(" " * 5)
        
        # Format the row
        formatted_row = "|" + "|".join(row_strs) + "|"
        merged_rows.append(formatted_row)
        
    return "\n".join(merged_rows)


def merge_tables_from_text(text: str, sort_by_column: str = None) -> str:
    """
    Extract all markdown tables from text and merge them into a single table.
    
    Args:
        text: The text content that may contain markdown tables
        sort_by_column: The column to sort the data by
        
    Returns:
        A single markdown table string, or empty string if no tables found
        
    Example:
        >>> text = "Table 1:\n| A | B |\n|---|---|\n| 1 | 2 |\n\nTable 2:\n| A | C |\n|---|---|\n| 3 | 4 |"
        >>> merged = merge_tables_from_text(text)
        >>> print(merged)
        | A | B | C |
        |---|---|----|
        | 1 | 2 |    |
        | 3 |   | 4  |
    """
    tables = extract_markdown_tables(text)
    for i, table in enumerate(tables):
        print(f"MERGE TABLES: TABLE {i + 1}: {table}")
        headers, data_rows = parse_markdown_table(table, sort_by_column)
        print(f"MERGE TABLES: HEADERS: {headers}")
        print(f"MERGE TABLES: NUMBER OF DATA ROWS: {len(data_rows)}")
    merged_table = merge_markdown_tables(tables, sort_by_column)
    headers, data_rows = parse_markdown_table(merged_table)
    print(f"MERGE TABLES: MERGED TABLE HEADERS: {headers}")
    print(f"MERGE TABLES: MERGED TABLE NUMBER OF DATA ROWS: {len(data_rows)}")
    return merged_table


def convert_to_markdown_table(data: List[dict], model_class) -> str:
    """
    Convert a list of dictionaries to a markdown table using Pydantic model field aliases as headers.
    
    Args:
        data: List of dictionaries containing the data
        model_class: Pydantic model class that defines the structure and field aliases
    
    Returns:
        Markdown table string
    """
    if not data:
        return ""
    
    # Get field aliases from the Pydantic model
    field_aliases = {}
    for field_name, field_info in model_class.model_fields.items():
        alias = field_info.alias or field_name
        field_aliases[field_name] = alias
    
    # Get all field names in the order they appear in the model
    field_names = list(model_class.model_fields.keys())
    
    # Create header row
    headers = [field_aliases[field_name] for field_name in field_names]
    header_row = "| " + " | ".join(headers) + " |"
    
    # Create separator row
    separator_row = "| " + " | ".join(["---"] * len(headers)) + " |"
    
    # Create data rows
    data_rows = []
    for row_data in data:
        # Extract values in the correct order, handling missing keys
        row_values = []
        for field_name in field_names:
            field_alias = field_aliases[field_name]
            value = row_data.get(field_alias, "")
            # Convert to string and escape pipe characters
            value_str = str(value).replace("|", "\\|")
            row_values.append(value_str)
        
        data_row = "| " + " | ".join(row_values) + " |"
        data_rows.append(data_row)
    
    # Combine all parts
    markdown_table = "\n".join([header_row, separator_row] + data_rows)
    
    return markdown_table
