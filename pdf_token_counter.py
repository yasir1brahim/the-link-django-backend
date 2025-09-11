#!/usr/bin/env python3
"""
PDF Token Counter Script

This script reads PDF files from a directory and counts the number of tokens in each.
Uses PyMuPDF for PDF text extraction and tiktoken for token counting.

Usage:
    python pdf_token_counter.py <directory_path> [--model MODEL_NAME]

Example:
    python pdf_token_counter.py ./pdfs --model gpt-4o
"""

import os
import sys
import argparse
import statistics
from pathlib import Path
from typing import Dict, List, Tuple
import tiktoken
import pymupdf


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count the number of tokens in a text string."""
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except KeyError:
        # Fallback to cl100k_base encoding for unknown models
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text content from a PDF file using PyMuPDF."""
    try:
        # Open the PDF document
        doc = pymupdf.open(str(pdf_path))
        
        text_content = ""
        
        # Extract text from each page
        for page_num in range(doc.page_count):
            page = doc[page_num]
            page_text = page.get_text()
            text_content += page_text + "\n"
        
        # Close the document
        doc.close()
        
        return text_content.strip()
        
    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")
        return ""


def process_pdf_directory(directory_path: Path, model: str = "gpt-4o") -> List[Tuple[str, int, int]]:
    """Process all PDF files in a directory and return token counts."""
    results = []
    
    if not directory_path.exists():
        print(f"Error: Directory '{directory_path}' does not exist.")
        return results
    
    if not directory_path.is_dir():
        print(f"Error: '{directory_path}' is not a directory.")
        return results
    
    # Find all PDF files
    pdf_files = list(directory_path.glob("*.pdf")) + list(directory_path.glob("*.PDF"))
    
    if not pdf_files:
        print(f"No PDF files found in '{directory_path}'")
        return results
    
    print(f"Found {len(pdf_files)} PDF files to process...")
    print(f"Using token counting model: {model}")
    print("-" * 80)
    
    total_tokens = 0
    total_files = len(pdf_files)
    
    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"Processing {i}/{total_files}: {pdf_path.name}")
        
        # Extract text from PDF
        text_content = extract_text_from_pdf(pdf_path)
        
        if text_content:
            # Count tokens
            token_count = count_tokens(text_content, model)
            total_tokens += token_count
            
            # Store results
            results.append((pdf_path.name, len(text_content), token_count))
            
            print(f"  Text length: {len(text_content):,} characters")
            print(f"  Token count: {token_count:,} tokens")
        else:
            print(f"  Failed to extract text")
            results.append((pdf_path.name, 0, 0))
        
        print()
    
    # Print summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total files processed: {total_files}")
    print(f"Total tokens across all files: {total_tokens:,}")
    print(f"Average tokens per file: {total_tokens / total_files:,.0f}")
    
    # Calculate additional statistics
    if results:
        token_counts = [token_count for _, _, token_count in results if token_count > 0]
        if token_counts:
            max_tokens = max(token_counts)
            min_tokens = min(token_counts)
            
            # Calculate standard deviation
            if len(token_counts) > 1:
                std_dev = statistics.stdev(token_counts)
                print(f"Min tokens per file: {min_tokens:,}")
                print(f"Max tokens per file: {max_tokens:,}")
                print(f"Standard deviation: {std_dev:,.1f}")
            else:
                print(f"Min tokens per file: {min_tokens:,}")
                print(f"Max tokens per file: {max_tokens:,}")
                print("Standard deviation: N/A (only one file)")
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Count tokens in PDF files using PyMuPDF and tiktoken",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "directory",
        help="Directory containing PDF files to process"
    )
    
    parser.add_argument(
        "--model",
        default="gpt-4o",
        help="Model name for token counting (default: gpt-4o)"
    )
    
    parser.add_argument(
        "--output",
        help="Output file to save results (CSV format)"
    )
    
    args = parser.parse_args()
    
    # Convert to Path object
    directory_path = Path(args.directory)
    
    # Process PDFs
    results = process_pdf_directory(directory_path, args.model)
    
    # Save results to CSV if requested
    if args.output:
        try:
            import csv
            output_path = Path(args.output)
            
            with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Filename', 'Character Count', 'Token Count'])
                
                for filename, char_count, token_count in results:
                    writer.writerow([filename, char_count, token_count])
                
                # Add summary statistics row
                if results:
                    token_counts = [token_count for _, _, token_count in results if token_count > 0]
                    if token_counts:
                        total_chars = sum(char_count for _, char_count, _ in results)
                        total_tokens = sum(token_counts)
                        avg_tokens = total_tokens / len(token_counts)
                        max_tokens = max(token_counts)
                        min_tokens = min(token_counts)
                        
                        # Calculate standard deviation
                        if len(token_counts) > 1:
                            std_dev = statistics.stdev(token_counts)
                            writer.writerow([])  # Empty row for separation
                            writer.writerow(['SUMMARY STATISTICS', '', ''])
                            writer.writerow(['Total Files', len(results), ''])
                            writer.writerow(['Total Characters', total_chars, ''])
                            writer.writerow(['Total Tokens', total_tokens, ''])
                            writer.writerow(['Average Tokens', f'{avg_tokens:.1f}', ''])
                            writer.writerow(['Min Tokens', min_tokens, ''])
                            writer.writerow(['Max Tokens', max_tokens, ''])
                            writer.writerow(['Standard Deviation', f'{std_dev:.1f}', ''])
            
            print(f"Results saved to: {output_path}")
            
        except Exception as e:
            print(f"Error saving results to CSV: {e}")


if __name__ == "__main__":
    main()
