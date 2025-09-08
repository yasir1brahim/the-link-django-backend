# PDF Token Counter

A Python script that reads PDF files from a directory and counts the number of tokens in each using PyMuPDF for text extraction and tiktoken for token counting.

## Features

- **PDF Text Extraction**: Uses PyMuPDF (fitz) for reliable PDF text extraction
- **Token Counting**: Supports multiple OpenAI models with fallback to cl100k_base encoding
- **Batch Processing**: Processes entire directories of PDFs at once
- **Progress Tracking**: Shows progress and detailed results for each file
- **Statistical Analysis**: Provides min, max, average, and standard deviation of token counts
- **CSV Export**: Optional CSV output with summary statistics for further analysis
- **Error Handling**: Gracefully handles PDFs that can't be processed

## Requirements

- Python 3.7+
- PyMuPDF
- tiktoken

## Installation

1. Install the required dependencies:

```bash
pip install -r requirements_pdf_counter.txt
```

Or install manually:

```bash
pip install pymupdf tiktoken
```

## Usage

### Basic Usage

```bash
python pdf_token_counter.py <directory_path>
```

### Advanced Usage

```bash
# Specify a different model for token counting
python pdf_token_counter.py ./pdfs --model gpt-3.5-turbo

# Save results to CSV file
python pdf_token_counter.py ./pdfs --output results.csv

# Combine both options
python pdf_token_counter.py ./pdfs --model gpt-4o --output token_counts.csv
```

### Command Line Arguments

- `directory`: Path to directory containing PDF files (required)
- `--model`: Model name for token counting (default: gpt-4o)
- `--output`: Output CSV file path (optional)

### Supported Models

The script supports all OpenAI models that tiktoken recognizes, including:
- `gpt-4o` (default)
- `gpt-4-turbo`
- `gpt-3.5-turbo`
- `gpt-4`
- `gpt-3.5-turbo-16k`

For unknown models, it falls back to the `cl100k_base` encoding.

## Example Output

```
Found 5 PDF files to process...
Using token counting model: gpt-4o
--------------------------------------------------------------------------------
Processing 1/5: document1.pdf
  Text length: 15,234 characters
  Token count: 3,456 tokens

Processing 2/5: document2.pdf
  Text length: 8,901 characters
  Token count: 2,123 tokens

...

================================================================================
SUMMARY
================================================================================
Total files processed: 5
Total tokens across all files: 12,345
Average tokens per file: 2,469
Min tokens per file: 1,234
Max tokens per file: 4,567
Standard deviation: 1,234.5
```

## Testing

Run the test suite to verify functionality:

```bash
python test_pdf_counter.py
```

This will test:
- Token counting with various text lengths
- PDF processing (if test PDFs are available)

## CSV Output Format

When using the `--output` option, the script generates a CSV file with columns:
- `Filename`: Name of the PDF file
- `Character Count`: Number of characters in extracted text
- `Token Count`: Number of tokens according to the specified model

The CSV also includes a summary section with:
- Total files processed
- Total characters and tokens
- Average, minimum, and maximum token counts
- Standard deviation of token counts

## Error Handling

The script handles various error conditions:
- **Invalid directories**: Shows clear error messages
- **PDF processing errors**: Continues with other files, reports failures
- **Missing dependencies**: Provides helpful error messages
- **File access issues**: Gracefully handles permission problems

## Performance Notes

- **Memory usage**: Each PDF is processed individually to minimize memory usage
- **Processing speed**: Depends on PDF size and complexity
- **Large files**: Very large PDFs may take longer to process

## Troubleshooting

### Common Issues

1. **ImportError: No module named 'pymupdf'**
   - Install PyMuPDF: `pip install pymupdf`

2. **ImportError: No module named 'tiktoken'**
   - Install tiktoken: `pip install tiktoken`

3. **PDF text extraction fails**
   - Check if PDF is password-protected or corrupted
   - Verify PDF contains extractable text (not just images)

4. **Permission denied errors**
   - Check file permissions
   - Ensure you have read access to the directory

### Getting Help

If you encounter issues:
1. Check the error messages for specific details
2. Verify all dependencies are installed
3. Test with a simple PDF first
4. Run the test script to verify basic functionality

## License

This script is provided as-is for internal use. It uses the same token counting logic as your existing codebase.
