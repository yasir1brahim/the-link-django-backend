import unittest
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.conf import settings

from apps.deliverables.views.specgpt_views import (
    count_tokens, 
    split_file_content_into_chunks, 
)


class ChunkingTestCase(TestCase):
    """Test cases for content chunking functionality."""
    
    def test_count_tokens(self):
        """Test token counting functionality."""
        # Test with a simple string
        text = "Hello world"
        token_count = count_tokens(text)
        self.assertIsInstance(token_count, int)
        self.assertGreater(token_count, 0)
        
        # Test with empty string
        empty_count = count_tokens("")
        self.assertEqual(empty_count, 0)
        
        # Test with longer text
        long_text = "This is a longer piece of text that should have more tokens than the short one."
        long_count = count_tokens(long_text)
        self.assertGreater(long_count, token_count)
    
    def test_split_content_into_chunks_small_content(self):
        """Test that small content doesn't get split unnecessarily."""
        system_prompt = "You are a helpful assistant."
        user_prompt_template = "Please analyze this content: {file_content}"
        content = "This is a small piece of content that should not be split."
        
        chunks = split_file_content_into_chunks(content, max_tokens_per_chunk=10000000, preferred_separator="-"*100)
        
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], "-"*100 + content)
    
    def test_split_content_into_chunks_large_content(self):
        """Test that large content gets split appropriately."""
        system_prompt = "You are a helpful assistant."
        user_prompt_template = "Please analyze this content: {file_content}"
        
        # Create content that exceeds the token limit
        # Each line is about 10-15 tokens, so we need many lines
        lines = [f"This is line number {i} with some additional content to make it longer." 
                for i in range(1000)]  # This should be well over the token limit
        content = "\n".join(lines)
        
        chunks = split_file_content_into_chunks(
            content,
            max_tokens_per_chunk=5000  # Use a small limit for testing
        )
        
        self.assertGreater(len(chunks), 1)
        
        # Verify each chunk is within the token limit
        for chunk in chunks:
            chunk_tokens = count_tokens(chunk)
            self.assertLessEqual(chunk_tokens, 5000)
    
    def test_split_content_into_chunks_preserves_structure(self):
        """Test that chunking preserves some structure."""
        system_prompt = "You are a helpful assistant."
        user_prompt_template = "Please analyze this content: {file_content}"
        
        content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
        
        chunks = split_file_content_into_chunks(
            content,
            max_tokens_per_chunk=50  # Small limit to force splitting
        )
        
        # Verify that lines are preserved
        for chunk in chunks:
            self.assertIn('\n', chunk or '')
    
    
    def test_split_content_into_chunks_with_custom_max_tokens(self):
        """Test splitting with custom max tokens."""
        system_prompt = "You are a helpful assistant."
        user_prompt_template = "Please analyze this content: {file_content}"
        content = "This is a test content that should be split into chunks."
        
        chunks = split_file_content_into_chunks(
            content,
            max_tokens_per_chunk=100  # Very small limit
        )
        
        self.assertGreaterEqual(len(chunks), 1)
        
        # Verify each chunk respects the token limit
        for chunk in chunks:
            chunk_tokens = count_tokens(chunk)
            self.assertLessEqual(chunk_tokens, 100)
    