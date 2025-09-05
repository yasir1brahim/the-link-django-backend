#!/usr/bin/env python3
"""
Test script for PDF Token Counter

This script tests the basic functionality of the PDF token counter.
"""

import sys
from pathlib import Path
from pdf_token_counter import count_tokens, extract_text_from_pdf


def test_count_tokens():
    """Test the token counting functionality."""
    print("Testing token counting...")
    
    # Test with simple text
    test_text = "Hello world, this is a test."
    token_count = count_tokens(test_text)
    print(f"Text: '{test_text}'")
    print(f"Tokens: {token_count}")
    
    # Test with longer text
    long_text = "This is a much longer piece of text that should have significantly more tokens than the short one. It contains multiple sentences and should demonstrate that the token counting is working correctly across different text lengths."
    long_token_count = count_tokens(long_text)
    print(f"Long text tokens: {long_token_count}")
    
    # Test with empty string
    empty_count = count_tokens("")
    print(f"Empty string tokens: {empty_count}")
    
    print("Token counting tests completed.\n")


def test_pdf_processing():
    """Test PDF processing if a test PDF is available."""
    print("Testing PDF processing...")
    
    # Look for test PDFs in current directory
    test_pdfs = list(Path(".").glob("*.pdf")) + list(Path(".").glob("*.PDF"))
    
    if test_pdfs:
        test_pdf = test_pdfs[0]
        print(f"Found test PDF: {test_pdf}")
        
        try:
            text_content = extract_text_from_pdf(test_pdf)
            if text_content:
                token_count = count_tokens(text_content)
                print(f"Successfully extracted text from {test_pdf}")
                print(f"Text length: {len(text_content):,} characters")
                print(f"Token count: {token_count:,} tokens")
            else:
                print(f"Failed to extract text from {test_pdf}")
        except Exception as e:
            print(f"Error processing {test_pdf}: {e}")
    else:
        print("No test PDFs found in current directory")
        print("To test PDF processing, place a PDF file in the same directory as this script")
    
    print("PDF processing tests completed.\n")


def main():
    """Run all tests."""
    print("PDF Token Counter - Test Suite")
    print("=" * 40)
    
    test_count_tokens()
    test_pdf_processing()
    
    print("All tests completed!")


if __name__ == "__main__":
    main()


