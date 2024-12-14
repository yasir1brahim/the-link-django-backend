from unittest import TestCase, mock
from unittest.mock import patch, Mock

from django.conf import settings

from apps.deliverables.integrations.procore import (get_procore_access_token, get_fresh_token_for_user,
                                                     GRANT_TYPE_ACCESS_TOKEN, ProcoreException)
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


class TestGetFreshTokenForUser(TestCase):
    def setUp(self):
        self.mock_user = mock.Mock()
        self.mock_existing_token = mock.Mock(spec=ProcoreToken)
        self.mock_existing_token.code = "test_code"
        self.mock_existing_token.redirect_uri = "test_uri"

    def test_returns_existing_token_if_not_expired(self):
        # Arrange
        self.mock_existing_token.is_expired.return_value = False
        with mock.patch('apps.deliverables.integrations.procore.get_object_or_404') as mock_get:
            mock_get.return_value = self.mock_existing_token
            
            # Act
            result = get_fresh_token_for_user(self.mock_user)
            
            # Assert
            self.assertEqual(result, self.mock_existing_token)
            mock_get.assert_called_once_with(ProcoreToken, user=self.mock_user)
            self.mock_existing_token.is_expired.assert_called_once()

    def test_raises_404_if_token_not_found(self):
        # Arrange
        with mock.patch('apps.deliverables.integrations.procore.get_object_or_404') as mock_get:
            mock_get.side_effect = ProcoreException("Test error")
            
            # Act & Assert
            with self.assertRaises(ProcoreException):
                get_fresh_token_for_user(self.mock_user)

    def test_creates_new_token_if_existing_expired(self):
        # Arrange
        self.mock_existing_token.is_expired.return_value = True
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'access_token': 'new_token',
            'refresh_token': 'new_refresh',
            'expires_in': 3600,
            'token_type': 'bearer'
        }
        
        # Create mock serializer instance
        mock_serializer = mock.Mock()
        mock_serializer.is_valid.return_value = True
        mock_serializer.validated_data = mock_response.json()
        mock_serializer_class = mock.Mock(return_value=mock_serializer)
        
        # Use individual patches instead of patch.multiple for better control
        with mock.patch('apps.deliverables.integrations.procore.get_object_or_404') as mock_get_404, \
             mock.patch('apps.deliverables.integrations.procore.get_procore_access_token') as mock_get_token, \
             mock.patch('apps.deliverables.integrations.procore.ProcoreAccessTokenSerializer', mock_serializer_class):
            
            # Setup mock returns
            mock_get_404.return_value = self.mock_existing_token
            mock_get_token.return_value = mock_response
            
            new_token = mock.Mock(spec=ProcoreToken)
            with mock.patch.object(ProcoreToken.objects, 'create', return_value=new_token):
                # Act
                result = get_fresh_token_for_user(self.mock_user)
                
                # Assert
                self.assertEqual(result, new_token)
                mock_get_token.assert_called_once_with(
                    self.mock_existing_token.code, 
                    self.mock_existing_token.redirect_uri
                )
    
    def test_raises_exception_on_failed_procore_response(self):
        # Arrange
        self.mock_existing_token.is_expired.return_value = True
        mock_response = mock.Mock()
        mock_response.status_code = 400
        mock_response.text = "Error message"
        
        with mock.patch('apps.deliverables.integrations.procore.get_object_or_404') as mock_get_404, \
             mock.patch('apps.deliverables.integrations.procore.get_procore_access_token') as mock_get_token:
            
            mock_get_404.return_value = self.mock_existing_token
            mock_get_token.return_value = mock_response
            
            # Act & Assert
            with self.assertRaises(ProcoreException) as context:
                get_fresh_token_for_user(self.mock_user)
            
            self.assertEqual(str(context.exception), "Error message")
    