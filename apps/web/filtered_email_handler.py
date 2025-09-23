import logging
import re
from django.utils.log import AdminEmailHandler


class FilteredAdminEmailHandler(AdminEmailHandler):
    """
    Custom AdminEmailHandler that filters out HTTP_HOST header errors from bot requests.
    This prevents unnecessary error notification emails when bots send invalid HTTP_HOST headers.
    """
    
    def emit(self, record):
        # Check if this is an HTTP_HOST header error from a bot
        if self._is_bot_http_host_error(record):
            # Log the filtered error but don't send email
            logger = logging.getLogger(__name__)
            logger.info(f"Filtered bot HTTP_HOST error: {record.getMessage()}")
            return
        
        # For all other errors, use the default behavior
        super().emit(record)
    
    def _is_bot_http_host_error(self, record):
        """
        Check if this is an HTTP_HOST header error from a bot request.
        """
        if not hasattr(record, 'getMessage'):
            return False
            
        message = record.getMessage()
        
        # Check for HTTP_HOST header errors
        if 'Invalid HTTP_HOST header' in message:
            return True
        
        return False
