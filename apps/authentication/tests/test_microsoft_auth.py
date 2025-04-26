import json
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from rest_framework import status


from allauth.socialaccount.models import SocialApp, SocialAccount, SocialToken
from allauth.socialaccount.providers.microsoft.views import MicrosoftGraphOAuth2Adapter

User = get_user_model()

@override_settings(SOCIALACCOUNT_PROVIDERS={
    'microsoft': {
        'TENANT': 'organizations',
        # No APP config to prevent automatic app creation
    }
})
@override_settings(FRONTEND_BASE_URL='http://testfrontendurl.com')
class MicrosoftSSOTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser', 
            email='testuser@example.com',
            password='password'
        )
        
        # Create a site
        self.site = Site.objects.get_current()
        
        # Create Microsoft social app
        if not SocialApp.objects.filter(provider='microsoft').exists():
            self.social_app = SocialApp.objects.create(
                provider='microsoft',
                name='Microsoft',
                client_id='test-client-id',
                secret='test-client-secret'
            )
            self.social_app.sites.add(self.site)
        
        # Mock user data from Microsoft
        self.microsoft_user_data = {
            'id': '12345',
            'displayName': 'Test User',
            'givenName': 'Test',
            'surname': 'User',
            'mail': 'testuser@example.com',
            'userPrincipalName': 'testuser@example.com'
        }
        # URL endpoints
        self.login_url = reverse('authentication:api_microsoft_login')
        self.callback_url = reverse('authentication:api_microsoft_callback')
    
    def tearDown(self):
        # Clean up the social app created in this test
        SocialApp.objects.filter(
            provider='microsoft',
            client_id='test-client-id'
        ).delete()

    def test_microsoft_login(self):
        response = self.client.get(reverse('authentication:api_microsoft_login'))
        self.assertEqual(response.status_code, 200)
        print(response.data)
        self.assertTrue('login.microsoftonline.com' in response.data['auth_url'])
        self.assertTrue('testfrontendurl.com' in response.data['auth_url'])

    def test_microsoft_callback(self):
        response = self.client.get(reverse('authentication:api_microsoft_callback'))
        self.assertEqual(response.status_code, 200)
        print(response.data)

    @patch('allauth.socialaccount.providers.microsoft.views.get_adapter')
    @patch('allauth.socialaccount.providers.microsoft.views.MicrosoftGraphOAuth2Adapter.get_access_token_for_code')
    @patch('allauth.socialaccount.providers.microsoft.views.MicrosoftGraphOAuth2Adapter.complete_login')
    @patch('allauth.socialaccount.helpers.complete_social_login')
    def test_microsoft_callback_successful_authentication(self, mock_complete_social_login, mock_complete_login, 
                                                     mock_get_token, mock_get_adapter):
        """Test successful flow through the microsoft_callback view"""
        # Set up mocks
        mock_adapter = MagicMock()
        mock_adapter.get_app.return_value = self.social_app
        mock_get_adapter.return_value = mock_adapter
        
        # Mock the token response
        token = SocialToken(token='test-access-token')
        mock_get_token.return_value = token
        
        # Mock the login completion
        login_data = MagicMock()
        login_data.account.provider = 'microsoft'
        login_data.account.uid = 'ms-test-user-id'
        mock_complete_login.return_value = login_data
        
        # Mock the social login completion
        social_login = MagicMock()
        social_login.user = self.user
        mock_complete_social_login.return_value = social_login
        
        # Make the request with a test code
        request_data = {
            'code': 'test-authorization-code',
            'redirect_uri': 'http://localhost:3000/microsoft-callback'
        }
        response = self.client.post(self.callback_url, request_data, format='json')
        
        # Assertions
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertIn('user', response.data)
        self.assertEqual(response.data['user']['email'], 'test@example.com')
        
        # Verify mocks were called correctly
        mock_get_adapter.assert_called()
        mock_get_token.assert_called_once()
        mock_complete_login.assert_called_once()
        mock_complete_social_login.assert_called_once()

    def test_microsoft_callback_missing_code(self):
        """Test that callback returns an error when code is missing"""
        response = self.client.post(self.callback_url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertEqual(response.data['error'], 'Authorization code is required')

    @patch('allauth.socialaccount.adapter.get_adapter')
    def test_microsoft_callback_missing_app(self, mock_get_adapter):
        """Test handling when the Social App doesn't exist"""
        # Set up mock to raise exception
        mock_adapter = MagicMock()
        mock_adapter.get_app.side_effect = SocialApp.DoesNotExist
        mock_get_adapter.return_value = mock_adapter
        
        # Make request
        request_data = {
            'code': 'test-authorization-code',
            'redirect_uri': 'http://localhost:3000/microsoft-callback'
        }
        response = self.client.post(self.callback_url, request_data, format='json')
        
        # Assertions
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn('error', response.data)
        self.assertEqual(response.data['error'], 'Microsoft authentication is not configured correctly.')

    @patch('allauth.socialaccount.adapter.get_adapter')
    @patch('allauth.socialaccount.providers.microsoft.views.MicrosoftGraphOAuth2Adapter.get_access_token_for_code')
    def test_microsoft_callback_oauth_error(self, mock_get_token, mock_get_adapter):
        """Test handling of OAuth errors"""
        # Set up mocks
        mock_adapter = MagicMock()
        mock_adapter.get_app.return_value = self.social_app
        mock_get_adapter.return_value = mock_adapter
        
        # Mock token fetching to raise an exception
        mock_get_token.side_effect = Exception("Invalid code")
        
        # Make request
        request_data = {
            'code': 'invalid-code',
            'redirect_uri': 'http://localhost:3000/microsoft-callback'
        }
        response = self.client.post(self.callback_url, request_data, format='json')
        
        # Assertions
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertEqual(response.data['error'], 'Authentication failed. Please try again.')


    def test_new_user_created_from_microsoft_login(self):
        # Use the sociallogin_from_response method to simulate creation
        with patch('allauth.socialaccount.providers.microsoft.views.get_adapter'):
            adapter = MicrosoftGraphOAuth2Adapter(MagicMock())
            provider = adapter.get_provider()
            
            # Create a login using the provider's method
            login = provider.sociallogin_from_response(
                MagicMock(),
                self.microsoft_user_data
            )
            
            # Save the user
            login.lookup()
            login.save(MagicMock(), connect=True)
            
            # Assertions
            self.assertTrue(
                User.objects.filter(email='testuser@example.com').exists()
            )
            social_account = SocialAccount.objects.get(
                provider='microsoft',
                uid='12345'
            )
            self.assertEqual(social_account.extra_data, self.microsoft_user_data)
