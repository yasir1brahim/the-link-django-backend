#!/usr/bin/env python3
"""
Script to analyze corrupted Excel files and find illegal XML characters.
This helps debug Excel export issues by examining the raw XML content.
"""

import zipfile
import sys
import os
from pathlib import Path

def analyze_excel_file(excel_path, line_number=9748, column_number=31, context_lines=10):
    """
    Analyze an Excel file to find illegal XML characters.

    Args:
        excel_path: Path to the Excel file
        line_number: Line number where the error occurs
        column_number: Column number where the error occurs
        context_lines: Number of lines to show before and after the target line
    """
    print(f"Analyzing Excel file: {excel_path}")
    print(f"Looking for error at line {line_number}, column {column_number}")
    print("=" * 60)

    # Check if file exists
    if not os.path.exists(excel_path):
        print(f"Error: File '{excel_path}' does not exist")
        return False

    # Excel files are ZIP archives
    try:
        with zipfile.ZipFile(excel_path, 'r') as zip_ref:
            # List all files in the archive
            file_list = zip_ref.namelist()
            print(f"Files in Excel archive: {len(file_list)}")
            print()

            # Look for the sheet XML file
            sheet_file = None
            for filename in file_list:
                if 'xl/worksheets/sheet' in filename and filename.endswith('.xml'):
                    print(f"Found worksheet file: {filename}")
                    sheet_file = filename
                    break

            if not sheet_file:
                print("Could not find worksheet XML file")
                return False

            # Extract and read the sheet file
            with zip_ref.open(sheet_file) as file:
                content = file.read().decode('utf-8')

            lines = content.split('\n')

            if line_number > len(lines):
                print(f"Error: File only has {len(lines)} lines, but error is at line {line_number}")
                return False

            # Calculate the range of lines to show
            start_line = max(0, line_number - context_lines - 1)  # Convert to 0-based indexing
            end_line = min(len(lines), line_number + context_lines)  # Exclusive end

            print(f"\nShowing lines {start_line + 1}-{end_line} (context around line {line_number}):")
            print("-" * 60)

            # Show the range of lines
            for i in range(start_line, end_line):
                current_line_num = i + 1  # Convert back to 1-based line numbers
                marker = ">>> " if i == line_number - 1 else "    "  # Mark the target line
                print(f"{marker}Line {current_line_num:4d}: {repr(lines[i])}")

            print("-" * 60)

            # Get the specific line for detailed analysis
            target_line = lines[line_number - 1]  # Convert to 0-based indexing

            # Check if column number is valid
            if column_number > len(target_line):
                print(f"Error: Line only has {len(target_line)} characters, but error is at column {column_number}")
                return False

            # Get the character at the specific position
            char_at_position = target_line[column_number - 1]  # Convert to 0-based indexing
            print(f"\nCharacter at line {line_number}, position {column_number}: {repr(char_at_position)} (ord: {ord(char_at_position)})")

            # Show context around the character
            start = max(0, column_number - 20)
            end = min(len(target_line), column_number + 20)
            context = target_line[start:end]
            print(f"Context: ...{repr(context)}...")

            # Check if this character is in our illegal character ranges
            char_code = ord(char_at_position)

            # Standard OpenPyXL illegal characters: 0-8, 13-14, 16-31
            if (0 <= char_code <= 8) or (13 <= char_code <= 14) or (16 <= char_code <= 31):
                print(f"✓ Character {repr(char_at_position)} (ord: {char_code}) is in standard illegal range")
            elif char_code == 127:  # DEL character
                print(f"✓ Character {repr(char_at_position)} (ord: {char_code}) is DEL character")
            else:
                print(f"⚠ Character {repr(char_at_position)} (ord: {char_code}) is NOT in standard illegal ranges")

            # Show all non-printable characters in the target line
            print(f"\nNon-printable characters in line {line_number}:")
            for i, char in enumerate(target_line):
                if ord(char) < 32 or ord(char) == 127 or ord(char) > 126:
                    print(f"  Position {i+1}: {repr(char)} (ord: {ord(char)})")

            return True

    except zipfile.BadZipFile:
        print(f"Error: '{excel_path}' is not a valid ZIP file (Excel files should be valid ZIP archives)")
        return False
    except UnicodeDecodeError as e:
        print(f"Error decoding file content: {e}")
        return False
    except Exception as e:
        print(f"Error analyzing file: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_excel.py <excel_file_path> [line_number] [column_number] [context_lines]")
        print("Example: python analyze_excel.py /path/to/corrupted.xlsx 9748 31 15")
        print("         python analyze_excel.py /path/to/corrupted.xlsx 8191 457 20")
        sys.exit(1)

    excel_path = sys.argv[1]
    line_number = 9748  # Default from error message
    column_number = 31  # Default from error message
    context_lines = 10  # Default context lines

    if len(sys.argv) >= 3:
        try:
            line_number = int(sys.argv[2])
        except ValueError:
            print(f"Error: Invalid line number '{sys.argv[2]}'")
            sys.exit(1)

    if len(sys.argv) >= 4:
        try:
            column_number = int(sys.argv[3])
        except ValueError:
            print(f"Error: Invalid column number '{sys.argv[3]}'")
            sys.exit(1)

    if len(sys.argv) >= 5:
        try:
            context_lines = int(sys.argv[4])
        except ValueError:
            print(f"Error: Invalid context lines '{sys.argv[4]}'")
            sys.exit(1)

    success = analyze_excel_file(excel_path, line_number, column_number, context_lines)

    if success:
        print("\nAnalysis complete!")
    else:
        print("\nAnalysis failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
