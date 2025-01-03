from datetime import datetime, timedelta
from django.test import TestCase
from unittest.mock import patch
from apps.deliverables.models import ProcoreToken
from apps.users.models import CustomUser

class ProcoreTokenTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(
            username="test_user",
            email="test@test.com",
            password="test_password"
        )
        self.token = ProcoreToken.objects.create(
            user=self.user,
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_in=3600,  # 1 hour in seconds
            token_type="Bearer",
            code="test_code"
        )

    @patch('apps.deliverables.models.datetime')
    def test_token_not_expired(self, mock_datetime):
        """Token should not be expired when within expiration window"""
        # Mock datetime.now() to return a time 30 minutes after token creation
        mock_now = self.token.created_at + timedelta(minutes=30)
        mock_datetime.now.return_value = mock_now
        
        self.assertFalse(self.token.is_expired())

    @patch('apps.deliverables.models.datetime')
    def test_token_is_expired(self, mock_datetime):
        """Token should be expired when past expiration window"""
        # Mock datetime.now() to return a time 2 hours after token creation
        mock_now = self.token.created_at + timedelta(hours=2)
        mock_datetime.now.return_value = mock_now
        
        self.assertTrue(self.token.is_expired())