from unittest import TestCase
from unittest.mock import patch, Mock

from django.conf import settings

from apps.deliverables.integrations.procore import get_procore_access_token, GRANT_TYPE_ACCESS_TOKEN

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