from unittest import mock
from unittest.mock import patch, Mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.http import Http404

from apps.deliverables.integrations.procore import (get_procore_access_token, get_fresh_token_for_user,
                                                     GRANT_TYPE_ACCESS_TOKEN, ProcoreException, create_spec_division)
from apps.deliverables.models import ProcoreToken

class TestProcoreIntegration(TestCase):
    def setUp(self):
        self.test_code = 'test_auth_code'
        self.test_redirect_uri = 'https://test.redirect/uri'
        self.expected_url = settings.PROCORE_AUTH_BASE_URL + '/oauth/token'
        self.expected_data = {
            'grant_type': GRANT_TYPE_ACCESS_TOKEN,
            'client_id': settings.PROCORE_CLIENT_ID,
            'client_secret': settings.PROCORE_CLIENT_SECRET,
            'code': self.test_code,
            'redirect_uri': self.test_redirect_uri
        }

    @patch('requests.post')
    def test_get_procore_access_token_success(self, mock_post):
        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'access_token': 'test_token'}
        mock_post.return_value = mock_response

        # Call function
        response = get_procore_access_token(self.test_code, self.test_redirect_uri)

        # Verify requests.post was called correctly
        mock_post.assert_called_once_with(self.expected_url, data=self.expected_data)
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'access_token': 'test_token'})

    @patch('requests.post')
    def test_get_procore_access_token_uses_default_redirect_uri(self, mock_post):
        # Setup mock response
        mock_response = Mock()
        mock_post.return_value = mock_response

        # Call function with no redirect_uri
        get_procore_access_token(self.test_code, None)

        # Verify default redirect URI was used
        expected_data = self.expected_data.copy()
        expected_data['redirect_uri'] = settings.PROCORE_REDIRECT_URL
        mock_post.assert_called_once_with(self.expected_url, data=expected_data)

    @patch('requests.post')
    def test_get_procore_access_token_failure(self, mock_post):
        # Setup mock response for failure case
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {'error': 'invalid_grant'}
        mock_post.return_value = mock_response

        # Call function
        response = get_procore_access_token(self.test_code, self.test_redirect_uri)

        # Verify response contains error
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'invalid_grant'})

    @patch('requests.post')
    def test_create_spec_division(self, mock_post):
        expected_data = {
            "id": 209260,
            "number": "15",
            "description": "Mechanical",
            "url": "string"
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = expected_data
        mock_post.return_value = mock_response

        # Call function
        response = create_spec_division(15, 1, "token")

        # Verify response contains error
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected_data)


class TestGetFreshTokenForUser(TestCase):
    def setUp(self):
        # Create real user with unique username
        self.user = get_user_model().objects.create_user(
            username='test_user',
            email='test_user@example.com',  # Assuming email is the main identifier
            password='testpassword'
        )
        
        # Create initial token
        self.existing_token = ProcoreToken.objects.create(
            user=self.user,
            code="test_code",
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_in=3600
        )

    def test_returns_existing_token_if_not_expired(self):
        # Act
        result = get_fresh_token_for_user(self.user)  # Use self.user instead of self.mock_user
        
        # Assert
        self.assertEqual(result, self.existing_token)

    def test_raises_404_if_token_not_found(self):
        # Create a user without a token
        new_user = get_user_model().objects.create_user(
            username='no_token_user',
            email='no_token@example.com',
            password='testpassword'
        )
            
        # Act & Assert
        with self.assertRaises(Http404):
            get_fresh_token_for_user(new_user)

    def test_returns_latest_token_if_multiple_tokens_exist(self):
        newest_token = ProcoreToken.objects.create(
            user=self.user,
            code="test_code_2",
            access_token="test_access_token_2",
            refresh_token="test_refresh_token_2",
            expires_in=3600
        )
        # Act
        result = get_fresh_token_for_user(self.user)  # Use self.user instead of self.mock_user
        
        # Assert
        self.assertEqual(result, newest_token)

    def test_creates_new_token_if_existing_expired(self):
        # Patch the is_expired method of ProcoreToken
        with mock.patch.object(ProcoreToken, 'is_expired', return_value=True), \
             mock.patch('apps.deliverables.integrations.procore.get_procore_access_token') as mock_get_token:
            
            # Setup mock response
            mock_response = mock.Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'access_token': 'new_token',
                'refresh_token': 'new_refresh',
                'expires_in': 3600,
                'token_type': 'bearer',
                'created_at': 1718361600
            }
            mock_get_token.return_value = mock_response
            
            # Act
            result = get_fresh_token_for_user(self.user)
            
            # Assert
            self.assertEqual(result.access_token, 'new_token')
            self.assertEqual(result.refresh_token, 'new_refresh')
            mock_get_token.assert_called_once_with(
                self.existing_token.code, 
                self.existing_token.redirect_uri
            )
    
    def test_raises_exception_on_failed_procore_response(self):
        # Patch the is_expired method of ProcoreToken
        with mock.patch.object(ProcoreToken, 'is_expired', return_value=True), \
             mock.patch('apps.deliverables.integrations.procore.get_procore_access_token') as mock_get_token:
            
            mock_response = mock.Mock()
            mock_response.status_code = 400
            mock_response.text = "Error message"
            mock_get_token.return_value = mock_response
            
            # Act & Assert
            with self.assertRaises(ProcoreException) as context:
                get_fresh_token_for_user(self.user)
            
            self.assertEqual(str(context.exception), "Error message")