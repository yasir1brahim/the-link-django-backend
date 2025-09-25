import logging
from unittest.mock import Mock, patch
from django.test import TestCase
from apps.web.filtered_email_handler import FilteredAdminEmailHandler


class FilteredAdminEmailHandlerTest(TestCase):
    """Test the FilteredAdminEmailHandler to ensure it filters bot HTTP_HOST errors."""
    
    def setUp(self):
        self.handler = FilteredAdminEmailHandler()
    
    def test_filters_http_host_error(self):
        """Test that HTTP_HOST errors are filtered out."""
        # Create a mock record that simulates an HTTP_HOST error
        record = Mock()
        record.getMessage.return_value = "Invalid HTTP_HOST header: 'example.com'. You may need to add 'example.com' to ALLOWED_HOSTS."
        
        # Mock the parent emit method to ensure it's not called
        with patch.object(FilteredAdminEmailHandler.__bases__[0], 'emit') as mock_parent_emit:
            with patch('logging.getLogger') as mock_logger:
                mock_logger_instance = Mock()
                mock_logger.return_value = mock_logger_instance
                
                # Call emit
                self.handler.emit(record)
                
                # Verify that the parent emit was not called (filtered out)
                mock_parent_emit.assert_not_called()
                
                # Verify that an info log was created
                mock_logger_instance.info.assert_called_once()
    
    def test_filters_all_http_host_errors(self):
        """Test that ALL HTTP_HOST errors are filtered (as per current implementation)."""
        # Create a mock record that simulates any HTTP_HOST error
        record = Mock()
        record.getMessage.return_value = "Invalid HTTP_HOST header: 'malicious.com'. You may need to add 'malicious.com' to ALLOWED_HOSTS."
        
        # Mock the parent emit method to ensure it's not called
        with patch.object(FilteredAdminEmailHandler.__bases__[0], 'emit') as mock_parent_emit:
            with patch('logging.getLogger') as mock_logger:
                mock_logger_instance = Mock()
                mock_logger.return_value = mock_logger_instance
                
                # Call emit
                self.handler.emit(record)
                
                # Verify that the parent emit was not called (filtered out)
                mock_parent_emit.assert_not_called()
                
                # Verify that an info log was created
                mock_logger_instance.info.assert_called_once()
    
    def test_allows_non_http_host_errors(self):
        """Test that non-HTTP_HOST errors are not filtered."""
        # Create a mock record that simulates a different type of error
        record = Mock()
        record.getMessage.return_value = "Database connection failed"
        
        # Mock the parent emit method
        with patch.object(FilteredAdminEmailHandler.__bases__[0], 'emit') as mock_parent_emit:
            # Call emit
            self.handler.emit(record)
            
            # Verify that the parent emit was called (not filtered)
            mock_parent_emit.assert_called_once_with(record)
    
    def test_various_http_host_error_formats(self):
        """Test various HTTP_HOST error message formats are all filtered."""
        error_messages = [
            "Invalid HTTP_HOST header: 'example.com'. You may need to add 'example.com' to ALLOWED_HOSTS.",
            "Invalid HTTP_HOST header: 'malicious.com'. You may need to add 'malicious.com' to ALLOWED_HOSTS.",
            "Invalid HTTP_HOST header: 'bot.example.com'. You may need to add 'bot.example.com' to ALLOWED_HOSTS.",
        ]
        
        for message in error_messages:
            record = Mock()
            record.getMessage.return_value = message
            
            with patch.object(FilteredAdminEmailHandler.__bases__[0], 'emit') as mock_parent_emit:
                with patch('logging.getLogger') as mock_logger:
                    mock_logger_instance = Mock()
                    mock_logger.return_value = mock_logger_instance
                    
                    # Call emit
                    self.handler.emit(record)
                    
                    # Verify that the parent emit was not called (filtered out)
                    mock_parent_emit.assert_not_called()
                    
                    # Verify that an info log was created
                    mock_logger_instance.info.assert_called_once()
