from unittest.mock import patch, Mock
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from ..models import ProcoreToken
from apps.teams.models import Team
class TestProcoreFetchAccessTokenView(APITestCase):
    def setUp(self):
        # Create a test user
        self.user = get_user_model().objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse('deliverables:procore-fetch-access-token')
        
        # Test data
        self.valid_payload = {
            'code': 'test_code',
            'redirect_uri': 'http://test.com/callback'
        }
        
        self.mock_token_response = {
            'access_token': 'test_access_token',
            'refresh_token': 'test_refresh_token',
            'expires_in': 7200,
            'token_type': 'Bearer',
            'created_at': 1718361600
        }

    @patch('apps.deliverables.views.get_procore_access_token')
    def test_successful_token_fetch(self, mock_get_token):
        # Mock the API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.mock_token_response
        mock_get_token.return_value = mock_response

        # Make request
        response = self.client.post(self.url, self.valid_payload)

        # Assert response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.mock_token_response)

        # Assert token was created in database
        token = ProcoreToken.objects.first()
        self.assertIsNotNone(token)
        self.assertEqual(token.user, self.user)
        self.assertEqual(token.access_token, 'test_access_token')
        self.assertEqual(token.refresh_token, 'test_refresh_token')
        self.assertEqual(token.expires_in, 7200)
        self.assertEqual(token.token_type, 'Bearer')
        self.assertEqual(token.code, 'test_code')

    def test_unauthenticated_request(self):
        # Remove authentication
        self.client.force_authenticate(user=None)
        
        response = self.client.post(self.url, self.valid_payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_request_data(self):
        # Missing required fields
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('apps.deliverables.views.get_procore_access_token')
    def test_procore_api_error(self, mock_get_token):
        # Mock failed API response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = 'Invalid authorization code'
        mock_get_token.return_value = mock_response

        response = self.client.post(self.url, self.valid_payload)
        
        # Assert response
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, 'Invalid authorization code')
        
        # Assert no token was created
        self.assertEqual(ProcoreToken.objects.count(), 0)


class TestGetProcoreCompanyMappingView(APITestCase):
    def setUp(self):
        # Create test user
        self.user = get_user_model().objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Create test company/team with Procore data
        self.company = Team.objects.create(
            name='Test Company',
            slug='test-company',
            procore_id='12345',
            procore_name='Test Procore Company'
        )
        
        # Create company without Procore mapping
        self.company_no_procore = Team.objects.create(
            name='Company Without Procore',
            slug='company-without-procore',
            procore_id=None,
            procore_name=None
        )

        # URLs with company ID parameter
        self.url = reverse('deliverables:procore-company-mapping', kwargs={'company_id': self.company.id})
        self.url_no_procore = reverse('deliverables:procore-company-mapping', kwargs={'company_id': self.company_no_procore.id})
        
        # Authenticate the test client
        self.client.force_authenticate(user=self.user)

    def test_get_company_mapping_success(self):
        """Test successful retrieval of company mapping with Procore data"""
        # Mock user as admin
        with patch.object(self.user, 'is_admin_for_team', return_value=True):
            response = self.client.get(self.url)
            
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data, {
                'procore_company_id': 12345,
                'procore_company_name': 'Test Procore Company'
            })

    def test_get_company_mapping_no_procore(self):
        """Test retrieval of company mapping without Procore data"""
        # Mock user as admin
        with patch.object(self.user, 'is_admin_for_team', return_value=True):
            response = self.client.get(self.url_no_procore)
            
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertEqual(response.data, {
                'procore_company_id': None,
                'procore_company_name': None
            })

    def test_get_company_mapping_not_admin(self):
        """Test access denied when user is not company admin"""
        # Mock user as non-admin
        with patch.object(self.user, 'is_admin_for_team', return_value=False):
            response = self.client.get(self.url)
            
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_company_mapping_unauthenticated(self):
        """Test access denied when user is not authenticated"""
        # Remove authentication
        self.client.force_authenticate(user=None)
        
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_company_mapping_not_found(self):
        """Test response when company does not exist"""
        # Mock user as admin
        with patch.object(self.user, 'is_admin_for_team', return_value=True):
            url = reverse('deliverables:procore-company-mapping', kwargs={'company_id': 99999})
            response = self.client.get(url)
            
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_company_mapping_invalid_data(self):
        """Test handling of invalid data from serializer"""
        # Create a company with invalid Procore data
        company_invalid = Team.objects.create(
            name='Invalid Company',
            procore_id=123,  # Assuming serializer expects string
            procore_name=''  # Assuming serializer requires non-empty string
        )
        url = reverse('deliverables:procore-company-mapping', kwargs={'company_id': company_invalid.id})
        
        # Mock user as admin
        with patch.object(self.user, 'is_admin_for_team', return_value=True):
            response = self.client.get(url)
            
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)