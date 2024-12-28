from unittest.mock import patch, Mock, MagicMock
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from ..models import ProcoreToken
from apps.teams.models import Team, Membership
from apps.deliverables.integrations.procore import ProcoreException
from apps.deliverables.models import Project, MasterFormatSection, SubmittalItem, ProcoreSubmittalTypeMapping
from apps.users.models import CustomUser
from apps.teams.roles import ROLE_ADMIN

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


class TestGetProcoreCompaniesView(APITestCase):
    def setUp(self):
        self.url = reverse('deliverables:procore-companies')
        self.user = get_user_model().objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)

        self.mock_procore_company_response = [
            {
                'id': 1,
                'name': 'Company 1',
                'is_active': True,
                'logo_url': 'https://pro-core.com/prostore/logo.gif',
                'pcn_business_experience': True,
                'my_company': True
            },
            {
                'id': 2,
                'name': 'Company 2',
                'is_active': True,
                'logo_url': 'https://pro-core.com/prostore/logo.gif',
                'pcn_business_experience': True,
                'my_company': True
            }
        ]
    

    @patch('apps.deliverables.views.get_fresh_token_for_user')
    @patch('apps.deliverables.views.get_companies') 
    def test_get_companies_success(self, mock_get_companies, mock_get_token):
        # Arrange
        mock_token = Mock(access_token='fake-token')
        mock_get_token.return_value = mock_token
        
        mock_response = Mock()
        mock_response.json.return_value = self.mock_procore_company_response
        mock_get_companies.return_value = mock_response

        # Act
        response = self.client.get(self.url)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_get_token.assert_called_once_with(self.user)
        mock_get_companies.assert_called_once_with('fake-token')
        self.assertEqual(response.data, self.mock_procore_company_response)

    def test_get_companies_unauthenticated(self):
        # Arrange
        self.client.force_authenticate(user=None)

        # Act
        response = self.client.get(self.url)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.deliverables.views.get_fresh_token_for_user')
    def test_get_companies_token_error(self, mock_get_token):
        # Arrange
        mock_get_token.side_effect = ProcoreException('Token error')

        # Act
        response = self.client.get(self.url)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, 'Token error')

    @patch('apps.deliverables.views.get_fresh_token_for_user')
    @patch('apps.deliverables.views.get_companies')
    def test_get_companies_invalid_response(self, mock_get_companies, mock_get_token):
        # Arrange
        mock_token = Mock(access_token='fake-token')
        mock_get_token.return_value = mock_token
        
        mock_response = Mock()
        mock_response.json.return_value = {'invalid': 'data'}
        mock_get_companies.return_value = mock_response

        # Act
        response = self.client.get(self.url)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)



class TestGetCurrentUserProcoreInfoView(APITestCase):
    def setUp(self):
        # Create a test user
        self.user = get_user_model().objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse('deliverables:get-current-user-procore-info')  # Update with your actual URL name

    @patch('apps.deliverables.views.get_fresh_token_for_user')
    @patch('apps.deliverables.views.get_me')
    def test_get_current_user_procore_info_success(self, mock_get_me, mock_get_fresh_token):
        # Mock the token response
        mock_token = Mock(access_token='fake-token')
        mock_get_fresh_token.return_value = mock_token

        # Mock the Procore API response
        mock_procore_response = Mock()
        mock_procore_response.json.return_value = {
            'id': 123,
            'login': 'test@example.com',
            'name': 'Test User'
        }
        mock_get_me.return_value = mock_procore_response

        # Make the request
        response = self.client.get(self.url)

        # Assertions
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], 123)
        self.assertEqual(response.data['login'], 'test@example.com')
        self.assertEqual(response.data['name'], 'Test User')

        # Verify our mocks were called correctly
        mock_get_fresh_token.assert_called_once_with(self.user)
        mock_get_me.assert_called_once_with('fake-token')

    @patch('apps.deliverables.views.get_fresh_token_for_user')
    def test_get_current_user_procore_info_token_error(self, mock_get_fresh_token):
        # Mock the token error
        mock_get_fresh_token.side_effect = ProcoreException('Token error')

        # Make the request
        response = self.client.get(self.url)

        # Assertions
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, 'Token error')

    def test_get_current_user_procore_info_unauthorized(self):
        # Remove authentication
        self.client.force_authenticate(user=None)

        # Make the request
        response = self.client.get(self.url)

        # Assertions
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.deliverables.views.get_fresh_token_for_user')
    @patch('apps.deliverables.views.get_me')
    def test_get_current_user_procore_info_invalid_response(self, mock_get_me, mock_get_fresh_token):
        # Mock the token response
        mock_token = Mock(access_token='fake-token')
        mock_get_fresh_token.return_value = mock_token

        # Mock an invalid Procore API response
        mock_procore_response = Mock()
        mock_procore_response.json.return_value = {
            'invalid_field': 'invalid_data'
        }
        mock_get_me.return_value = mock_procore_response

        # Make the request
        response = self.client.get(self.url)

        # Assertions
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestGetProcoreProjectMappingView(APITestCase):
    def setUp(self):
        # Create test user
        self.user = get_user_model().objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test team
        self.team = Team.objects.create(
            name='Test Team',
            procore_id='123',
            procore_name='Test Procore Team'
        )
        
        # Create test project
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team,
            procore_id='456',
            procore_name='Test Procore Project',
            procore_submittal_manager_id='789',
            procore_submittal_manager_name='Test Manager'
        )
        
        # Add user as project member
        self.project.members.add(self.user)
        
        # URL for the view
        self.url = reverse('deliverables:procore-project-mapping', kwargs={'project_id': self.project.id})

    def test_get_project_mapping_success(self):
        """Test successful retrieval of project mapping"""
        # Authenticate user
        self.client.force_authenticate(user=self.user)
        
        # Make request
        response = self.client.get(self.url)
        
        # Assert response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['procore_project_id'], 456)
        self.assertEqual(response.data['procore_project_name'], 'Test Procore Project')
        self.assertEqual(response.data['submittal_manager_id'], '789')
        self.assertEqual(response.data['procore_submittal_manager_name'], 'Test Manager')
        self.assertEqual(response.data['procore_company_id'], 123)
        self.assertEqual(response.data['procore_company_name'], 'Test Procore Team')

    def test_get_project_mapping_unauthenticated(self):
        """Test unauthenticated access is denied"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_project_mapping_unauthorized(self):
        """Test unauthorized access is denied"""
        # Create another user not associated with the project
        other_user = get_user_model().objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123'
        )
        
        self.client.force_authenticate(user=other_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_project_mapping_not_found(self):
        """Test response when project doesn't exist"""
        self.client.force_authenticate(user=self.user)
        url = reverse('deliverables:procore-project-mapping', kwargs={'project_id': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_returns_status_204_when_no_procore_project_mapping(self):
        """Test response when no procore project mapping exists"""
        self.client.force_authenticate(user=self.user)
        # Create test project
        self.project = Project.objects.create(
            name='Test No Procore Project',
            team=self.team,
            procore_id=None,
            procore_name=None,
            procore_submittal_manager_id=None,
            procore_submittal_manager_name=None
        )
        self.project.members.add(self.user)
        url = reverse('deliverables:procore-project-mapping', kwargs={'project_id': self.project.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class TestCreateProcoreSubmittalsView(APITestCase):
    def setUp(self):
        # Create test user
        self.user = get_user_model().objects.create_user(
            username='test_user',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test team
        self.team = Team.objects.create(
            name='Test Team',
            procore_id='123',
            procore_name='Test Procore Team'
        )
        
        # Create test project
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team,
            procore_id='456',
            procore_submittal_manager_id='789'
        )
        self.project.members.add(self.user)
        
        # Create test masterformat section
        self.masterformat_section = MasterFormatSection.objects.create(
            masterformat_number='123456'
        )
        
        # Create test submittal item
        self.submittal_item = SubmittalItem.objects.create(
            project=self.project,
            masterformat_section=self.masterformat_section,
            submittal_type='Test Type',
            submittal_description='Test Description',
            submittal_content='Test Content',
            paragraph_number='1.1'
        )
        
        # Set up API client
        self.client.force_authenticate(user=self.user)
        
        # URL for the view
        self.url = reverse('deliverables:procore-create-submittals')  # Update with your actual URL name

    @patch('apps.deliverables.views.get_fresh_token_for_user')
    @patch('apps.deliverables.views.get_status')
    @patch('apps.deliverables.views.get_spec_divisions')
    @patch('apps.deliverables.views.get_spec_sections')
    @patch('apps.deliverables.views.create_submittal')
    def test_successful_submittal_creation(
        self, 
        mock_create_submittal,
        mock_get_spec_sections,
        mock_get_spec_divisions,
        mock_get_status,
        mock_get_fresh_token
    ):
        # Mock responses
        mock_get_fresh_token.return_value = MagicMock(access_token='fake-token')
        mock_get_status.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"name": "Open", "id": "123"}]
        )
        mock_get_spec_divisions.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"number": "12", "id": "div-123"}]
        )
        mock_get_spec_sections.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"number": "123456", "id": "sec-123"}]
        )
        mock_create_submittal.return_value = MagicMock(
            status_code=201,
            json=lambda: {"id": "sub-123"}
        )

        # Test data
        data = {
            'project_id': self.project.id,
            'records': [self.submittal_item.id],
            'export_all': False
        }

        # Make request
        response = self.client.post(self.url, data, format='json')

        # Assertions
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Submittal created')
        self.assertIn(str(self.submittal_item.id), response.data['submittals'])

        mock_create_submittal.assert_called_once_with(
            submittal_content='Test Content',
            paragraph_number='1.1',
            procore_spec_section_id='sec-123',
            procore_status_id='123',
            procore_submittal_manager_id='789',
            submittal_title='Test Description',
            submittal_type='Test Type',
            project_id=456,
            procore_token='fake-token'
        )
        
        # Verify submittal was updated
        updated_submittal = SubmittalItem.objects.get(id=self.submittal_item.id)
        self.assertEqual(updated_submittal.procore_submittal_id, 'sub-123')
        self.assertIsNotNone(updated_submittal.procore_export_date)

    @patch('apps.deliverables.views.get_fresh_token_for_user')
    @patch('apps.deliverables.views.get_status')
    @patch('apps.deliverables.views.get_spec_divisions')
    @patch('apps.deliverables.views.get_spec_sections')
    @patch('apps.deliverables.views.create_submittal')
    def test_successful_submittal_creation_with_defined_mapping(
        self, 
        mock_create_submittal,
        mock_get_spec_sections,
        mock_get_spec_divisions,
        mock_get_status,
        mock_get_fresh_token
    ):
        # Mock responses
        mock_get_fresh_token.return_value = MagicMock(access_token='fake-token')
        mock_get_status.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"name": "Open", "id": "123"}]
        )
        mock_get_spec_divisions.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"number": "12", "id": "div-123"}]
        )
        mock_get_spec_sections.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"number": "123456", "id": "sec-123"}]
        )
        mock_create_submittal.return_value = MagicMock(
            status_code=201,
            json=lambda: {"id": "sub-123"}
        )

        # Create a test mapping
        ProcoreSubmittalTypeMapping.objects.create(
            link_type='Test Type',
            procore_type='Test Procore Type',
            company=self.team,
            procore_company_id="1"
        )

        # Test data
        data = {
            'project_id': self.project.id,
            'records': [self.submittal_item.id],
            'export_all': False
        }

        # Make request
        response = self.client.post(self.url, data, format='json')

        # Assertions
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Submittal created')
        self.assertIn(str(self.submittal_item.id), response.data['submittals'])

        mock_create_submittal.assert_called_once_with(
            submittal_content='Test Content',
            paragraph_number='1.1',
            procore_spec_section_id='sec-123',
            procore_status_id='123',
            procore_submittal_manager_id='789',
            submittal_title='Test Description',
            submittal_type='Test Procore Type',
            project_id=456,
            procore_token='fake-token'
        )
        
        # Verify submittal was updated
        updated_submittal = SubmittalItem.objects.get(id=self.submittal_item.id)
        self.assertEqual(updated_submittal.procore_submittal_id, 'sub-123')
        self.assertIsNotNone(updated_submittal.procore_export_date)

    def test_unauthorized_access(self):
        # Test with unauthenticated user
        self.client.force_authenticate(user=None)
        
        data = {
            'project_id': self.project.id,
            'records': [self.submittal_item.id],
            'export_all': False
        }
        
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_project_member_access(self):
        # Create non-member user
        non_member = get_user_model().objects.create_user(
            username='nonmember',
            email='nonmember@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=non_member)
        
        data = {
            'project_id': self.project.id,
            'records': [self.submittal_item.id],
            'export_all': False
        }
        
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.deliverables.views.get_fresh_token_for_user')
    def test_procore_token_error(self, mock_get_fresh_token):
        mock_get_fresh_token.side_effect = ProcoreException('Token error')
        
        data = {
            'project_id': self.project.id,
            'records': [self.submittal_item.id],
            'export_all': False
        }
        
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('apps.deliverables.views.get_fresh_token_for_user')
    @patch('apps.deliverables.views.get_status')
    def test_status_api_error(self, mock_get_status, mock_get_fresh_token):
        mock_get_fresh_token.return_value = MagicMock(access_token='fake-token')
        mock_get_status.return_value = MagicMock(
            status_code=400,
            text='Status API error'
        )
        
        data = {
            'project_id': self.project.id,
            'records': [self.submittal_item.id],
            'export_all': False
        }
        
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, 'Status API error')



class TestDeleteProcoreTokenView(APITestCase):
    def setUp(self):
        
        # Create test user
        self.user = get_user_model().objects.create_user(
            username='test_user',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test token
        self.token = ProcoreToken.objects.create(
            user=self.user,
            access_token='test_access_token',
            refresh_token='test_refresh_token',
            expires_in=3600,
            token_type='Bearer',
            code='test_code'
        )

        # Login the test user
        self.client.force_authenticate(user=self.user)

    def test_successful_token_deletion(self):
        """Test successful deletion of a Procore token"""
        # Make request
        response = self.client.get(
            reverse('deliverables:delete-procore-token'),
            {'user_id': self.user.id}
        )

        # Assert response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify token was deleted
        self.assertFalse(
            ProcoreToken.objects.filter(user=self.user).exists()
        )

    def test_delete_nonexistent_token(self):
        """Test attempting to delete a non-existent token"""
        # Create another user without token
        other_user = get_user_model().objects.create_user(
            username='other_user',
            email='other@example.com',
            password='testpass123'
        )

        # Make request
        response = self.client.get(
            reverse('deliverables:delete-procore-token'),
            {'user_id': other_user.id}
        )

        # Assert response
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_token_unauthenticated(self):
        """Test attempting to delete token while unauthenticated"""
        # Logout user
        self.client.force_authenticate(user=None)

        # Make request
        response = self.client.get(
            reverse('deliverables:delete-procore-token'),
            {'user_id': self.user.id}
        )

        # Assert response
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_token_invalid_user_id(self):
        """Test attempting to delete token with invalid user ID"""
        # Make request with non-existent user ID
        response = self.client.get(
            reverse('deliverables:delete-procore-token'),
            {'user_id': 99999}
        )

        # Assert response
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)



class TestGetProcoreProjectsView(APITestCase):
    def setUp(self):
        # Create test user and company
        self.user = CustomUser.objects.create_user(
            username='test_user',
            email='test@example.com',
            password='testpass123'
        )
        self.company = Team.objects.create(
            name='Test Company',
            procore_id='12345'
        )
        self.url = reverse('deliverables:procore-projects', kwargs={'company_id': self.company.id})

    def test_unauthenticated_user(self):
        """Test that unauthenticated users cannot access the endpoint"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthorized_company_access(self):
        """Test that users who aren't company members cannot access projects"""
        self.client.force_authenticate(user=self.user)
        # Mock is_member_of_team to return False
        with patch.object(CustomUser, 'is_member_of_team', return_value=False):
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_procore_token_exception(self):
        """Test handling of ProcoreException when getting token"""
        self.client.force_authenticate(user=self.user)
        # Mock necessary methods
        with patch.object(CustomUser, 'is_member_of_team', return_value=True), \
             patch('apps.deliverables.views.get_fresh_token_for_user') as mock_token:
            mock_token.side_effect = ProcoreException("Token error")
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(response.data, "Token error")

    def test_procore_api_error(self):
        """Test handling of error response from Procore API"""
        self.client.force_authenticate(user=self.user)
        mock_token = MagicMock(access_token='fake-token')
        
        # Mock API response with error
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "API Error"

        with patch.object(CustomUser, 'is_member_of_team', return_value=True), \
             patch('apps.deliverables.views.get_fresh_token_for_user', return_value=mock_token), \
             patch('apps.deliverables.views.get_projects', return_value=mock_response):
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(response.data, "API Error")

    def test_successful_projects_fetch(self):
        """Test successful retrieval of projects"""
        self.client.force_authenticate(user=self.user)
        mock_token = MagicMock(access_token='fake-token')
        
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {'id': '1', 'display_name': 'Project 1'},
            {'id': '2', 'display_name': 'Project 2'}
        ]

        with patch.object(CustomUser, 'is_member_of_team', return_value=True), \
             patch('apps.deliverables.views.get_fresh_token_for_user', return_value=mock_token), \
             patch('apps.deliverables.views.get_projects', return_value=mock_response):
            response = self.client.get(self.url)
            
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['message'], 'List of projects')
            self.assertEqual(response.data['data'], [
                {'key': '1', 'value': 'Project 1'},
                {'key': '2', 'value': 'Project 2'}
            ])


class TestGetProcoreManagersView(APITestCase):
    def setUp(self):
        # Create test user
        self.user = CustomUser.objects.create_user(
            username='test_user',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test team and project
        self.team = Team.objects.create(name='Test Team')
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team,
            procore_id='123'
        )
        
        # Add user as project member
        self.project.members.add(self.user)
        
        # URL for the view
        self.url = reverse('deliverables:procore-managers', kwargs={'project_id': self.project.id})
        
        # Authenticate the user
        self.client.force_authenticate(user=self.user)

    def test_unauthorized_access(self):
        """Test that unauthenticated users cannot access the endpoint"""
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_project_member_access(self):
        """Test that non-project members cannot access the endpoint"""
        other_user = CustomUser.objects.create_user(
            username='other_user',
            email='other@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=other_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.deliverables.views.get_fresh_token_for_user')
    @patch('apps.deliverables.views.get_managers')
    def test_successful_managers_retrieval(self, mock_get_managers, mock_get_token):
        """Test successful retrieval of managers list"""
        # Mock the token response
        mock_token = MagicMock()
        mock_token.access_token = 'fake-token'
        mock_get_token.return_value = mock_token

        # Mock the managers response
        mock_managers_response = MagicMock()
        mock_managers_response.status_code = 200
        mock_managers_response.json.return_value = [
            {'id': '1', 'name': 'Manager 1'},
            {'id': '2', 'name': 'Manager 2'}
        ]
        mock_get_managers.return_value = mock_managers_response

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'List of managers')
        self.assertEqual(len(response.data['data']), 2)
        self.assertEqual(response.data['data'][0], {'key': '1', 'value': 'Manager 1'})
        self.assertEqual(response.data['data'][1], {'key': '2', 'value': 'Manager 2'})

    @patch('apps.deliverables.views.get_fresh_token_for_user')
    def test_procore_token_exception(self, mock_get_token):
        """Test handling of ProcoreException when getting token"""
        mock_get_token.side_effect = ProcoreException('Token error')
        
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, 'Token error')

    @patch('apps.deliverables.views.get_fresh_token_for_user')
    @patch('apps.deliverables.views.get_managers')
    def test_managers_api_error(self, mock_get_managers, mock_get_token):
        """Test handling of error response from managers API"""
        # Mock the token response
        mock_token = MagicMock()
        mock_token.access_token = 'fake-token'
        mock_get_token.return_value = mock_token

        # Mock error response from managers API
        mock_error_response = MagicMock()
        mock_error_response.status_code = 400
        mock_error_response.text = 'API Error'
        mock_get_managers.return_value = mock_error_response

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, 'API Error')
    
class TestSetProcoreProjectMappingView(APITestCase):
    def setUp(self):
        # Create test user
        self.user = CustomUser.objects.create_user(
            username='test_user',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test team
        self.team = Team.objects.create(
            name='Test Team'
        )
        
        # Create test project
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team
        )
        self.project.members.add(self.user)
        # Setup API client
        self.url = reverse('deliverables:set-procore-project-mapping')
        
        # Valid payload
        self.valid_payload = {
            'project_id': self.project.id,
            'procore_project_id': '12345',
            'procore_project_name': 'Procore Project',
            'procore_submittal_manager_id': '67890',
            'procore_submittal_manager_name': 'Manager Name',
            'procore_company_id': 11111,
            'procore_company_name': 'Procore Company'
        }

    def test_unauthenticated_request(self):
        """Test that unauthenticated requests are rejected"""
        response = self.client.post(self.url, self.valid_payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_admin_user_can_update_mapping(self):
        """Test that non-admin users can update project mapping"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, self.valid_payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_successful_mapping_update(self):
        """Test successful procore mapping update"""
        # Make user admin for project
        self.user.is_admin_for_project = lambda x: True
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.url, self.valid_payload)
        print(response.data)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Refresh project from database
        self.project.refresh_from_db()
        self.team.refresh_from_db()
        
        # Verify project updates
        self.assertEqual(str(self.project.procore_id), self.valid_payload['procore_project_id'])
        self.assertEqual(self.project.procore_name, self.valid_payload['procore_project_name'])
        self.assertEqual(self.project.procore_submittal_manager_id, 
                        self.valid_payload['procore_submittal_manager_id'])
        self.assertEqual(self.project.procore_submittal_manager_name, 
                        self.valid_payload['procore_submittal_manager_name'])
        
        # Verify company updates
        self.assertEqual(self.team.procore_id, self.valid_payload['procore_company_id'])
        self.assertEqual(self.team.procore_name, self.valid_payload['procore_company_name'])

    def test_invalid_project_id(self):
        """Test request with invalid project ID"""
        self.user.is_admin_for_project = lambda x: True
        self.client.force_authenticate(user=self.user)
        
        invalid_payload = self.valid_payload.copy()
        invalid_payload['project_id'] = 99999  # Non-existent project ID
        
        response = self.client.post(self.url, invalid_payload)
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_required_fields(self):
        """Test request with missing required fields"""
        self.user.is_admin_for_project = lambda x: True
        self.client.force_authenticate(user=self.user)
        
        invalid_payload = {
            'project_id': self.project.id
            # Missing other required fields
        }
        
        response = self.client.post(self.url, invalid_payload)
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestCreateProcoreCompanyMappingView(APITestCase):
    def setUp(self):
        # Create test user
        self.user = CustomUser.objects.create_user(
            username='test_user',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test team
        self.team = Team.objects.create(
            name='Test Team'
        )
        
        # URL for the view
        self.url = reverse('deliverables:create-procore-company-mapping')
        
        # Valid payload for testing
        self.valid_payload = {
            'link_company_id': self.team.id,
            'procore_company_id': 123,
            'procore_company_name': 'Procore Test Company'
        }

    def test_create_mapping_success(self):
        """Test successful company mapping creation when user is admin"""
        # Make user admin of the team
        self.user.is_admin_for_team = lambda x: True
        self.user.is_member_of_team = lambda x: True
        
        # Authenticate user
        self.client.force_authenticate(user=self.user)
        
        # Make request
        response = self.client.post(self.url, self.valid_payload, format='json')
        
        # Assert response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify team was updated
        self.team.refresh_from_db()
        self.assertEqual(self.team.procore_id, 123)
        self.assertEqual(self.team.procore_name, 'Procore Test Company')

    def test_create_mapping_unauthorized(self):
        """Test mapping creation fails when user is not authenticated"""
        response = self.client.post(self.url, self.valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_admin_can_create_mapping(self):
        """Test non-admin users can create company mappings"""
        # Authenticate user but don't make them admin
        self.client.force_authenticate(user=self.user)
        self.user.is_member_of_team = lambda x: True
        
        response = self.client.post(self.url, self.valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_mapping_invalid_team(self):
        """Test mapping creation fails with non-existent team"""
        # Make user admin of the team
        self.user.is_admin_for_team = lambda x: True
        
        # Authenticate user
        self.client.force_authenticate(user=self.user)
        
        # Use invalid team id
        invalid_payload = self.valid_payload.copy()
        invalid_payload['link_company_id'] = 99999
        
        response = self.client.post(self.url, invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_mapping_invalid_data(self):
        """Test mapping creation fails with invalid data"""
        # Make user admin of the team
        self.user.is_admin_for_team = lambda x: True
        
        # Authenticate user
        self.client.force_authenticate(user=self.user)
        
        # Missing required fields
        invalid_payload = {
            'link_company_id': self.team.id
        }
        
        response = self.client.post(self.url, invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

class TestGetProcoreSubmittalMappingsView(APITestCase):
    def setUp(self):
        # Create test user
        self.user = CustomUser.objects.create_user(
            username='test_user',
            email='test@example.com',
            password='testpass123'
        )
        # Create test company/team
        self.company = Team.objects.create(
            name='Test Company',
            procore_id='123',
        )
        self.company.members.add(self.user)
        self.project = Project.objects.create(
            name='Test Project',
            team=self.company,
            procore_id='456',
            procore_name='Test Procore Project',
            procore_submittal_manager_id='789',
            procore_submittal_manager_name='Test Manager'
        )
        self.project.members.add(self.user)
        
        # Create some test data
        self.submittal_type_mapping = ProcoreSubmittalTypeMapping.objects.create(
            company=self.company,
            link_type='Shop Drawing',
            procore_type='Drawing'
        )

        masterformat_section = MasterFormatSection.objects.create(
            masterformat_number='123',
            masterformat_description='Concrete'
        )
        
        self.submittal_item = SubmittalItem.objects.create(
            submittal_type='Shop Drawing',
            project_id=self.project.id,
            masterformat_section=masterformat_section,
            submittal_description='Test Description',
            submittal_content='Test Content',
            paragraph_number='1.1'
        )

        self.submittal_item_2 = SubmittalItem.objects.create(
            submittal_type='Action/Information Submittal',
            project_id=self.project.id,
            masterformat_section=masterformat_section,
            submittal_description='Test Description',
            submittal_content='Test Content',
            paragraph_number='1.1'
        )
        
        # URL for the view
        self.url = reverse('deliverables:procore-submittal-mappings', kwargs={'company_id': self.company.id})

    def test_unauthorized_access(self):
        """Test that unauthorized users cannot access the endpoint"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_forbidden_access(self):
        """Test that users who aren't company members cannot access the endpoint"""
        other_user = CustomUser.objects.create_user(
            username='other_user',
            email='other@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=other_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.deliverables.views.get_fresh_token_for_user')
    @patch('apps.deliverables.views.get_submittal_types')
    def test_successful_request(self, mock_get_submittal_types, mock_get_fresh_token):
        """Test successful retrieval of submittal types"""
        # Mock the token response
        mock_token = MagicMock()
        mock_token.access_token = 'fake-token'
        mock_get_fresh_token.return_value = mock_token
        
        # Mock the Procore API response
        mock_procore_types = [
            {
                'id': 1,
                'name': 'Drawing',
                'translated_name': 'Drawing'
            }
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_procore_types
        mock_get_submittal_types.return_value = mock_response

        # Authenticate and make request
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        # Assertions
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'List of submittal types')
        
        # Check that the response contains both Procore and Link submittal types
        data = response.data['data']
        print("MAPPING DATA: ", data)
        self.assertIn('link_sub_mapping', data)
        self.assertIn('procore_submittal_types', data)
        
        # Verify the existing mapping is included
        self.assertEqual(len(data['link_sub_mapping']), 3)
        self.assertEqual(data['link_sub_mapping'][0]['link_submittal'], 'Shop Drawing')
        self.assertEqual(data['link_sub_mapping'][0]['procore_type'], 'Drawing')

        # Verify that the other submittal types are mapped with identity
        self.assertEqual(data['link_sub_mapping'][1]['link_submittal'], 'Drawing')
        self.assertEqual(data['link_sub_mapping'][1]['procore_type'], 'Drawing')
        self.assertEqual(data['link_sub_mapping'][2]['link_submittal'], 'Action/Information Submittal')
        self.assertEqual(data['link_sub_mapping'][2]['procore_type'], 'Action/Information Submittal')
        
        # Verify both Procore and Link types are included
        self.assertTrue(len(data['procore_submittal_types']) > 1)  # Should include both Procore and Link types

    @patch('apps.deliverables.views.get_fresh_token_for_user')
    def test_procore_token_error(self, mock_get_fresh_token):
        """Test handling of Procore token error"""
        mock_get_fresh_token.side_effect = ProcoreException("Token error")
        
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, "Token error")

    @patch('apps.deliverables.views.get_fresh_token_for_user')
    @patch('apps.deliverables.views.get_submittal_types')
    def test_procore_api_error(self, mock_get_submittal_types, mock_get_fresh_token):
        """Test handling of Procore API error"""
        # Mock the token response
        mock_token = MagicMock()
        mock_token.access_token = 'fake-token'
        mock_get_fresh_token.return_value = mock_token
        
        # Mock the Procore API error response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "API Error"
        mock_get_submittal_types.return_value = mock_response

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, "API Error")


class TestUpdateProcoreSubmittalTypesView(APITestCase):
    def setUp(self):
        # Create test users
        self.admin_user = CustomUser.objects.create_user(
            username='admin_user',
            email='admin@test.com',
            password='testpass123'
        )
        self.non_admin_user = CustomUser.objects.create_user(
            username='non_admin_user',
            email='user@test.com',
            password='testpass123'
        )
        
        # Create test company
        self.company = Team.objects.create(
            name='Test Company',
            procore_id='123',
        )
        
        # Add admin user to company
        Membership.objects.create(
            user=self.admin_user,
            team=self.company,
            role=ROLE_ADMIN
        )
        
        # Add non-admin user to company
        self.company.members.add(self.non_admin_user)
        
        # Create initial mapping
        self.existing_mapping = ProcoreSubmittalTypeMapping.objects.create(
            company=self.company,
            link_type='Shop Drawings',
            procore_type='Drawings'
        )
        
        # URL for the view
        self.url = reverse('deliverables:procore-submittal-mappings', kwargs={'company_id': self.company.id})
        
    def test_successful_update_mapping(self):
        """Test successful update of submittal type mappings"""
        self.client.force_authenticate(user=self.admin_user)
        
        data = {
            'mappings': [
                {
                    'id': self.existing_mapping.id,
                    'link_submittal': 'Product Data',
                    'procore_type': 'Product Info'
                },
                {
                    'id': None,
                    'link_submittal': 'Samples',
                    'procore_type': 'Sample'
                }
            ]
        }
        
        response = self.client.post(self.url, data, format='json')
        print("RESPONSE: ", response.data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify the existing mapping was updated
        updated_mapping = ProcoreSubmittalTypeMapping.objects.get(id=self.existing_mapping.id)
        self.assertEqual(updated_mapping.link_type, 'Product Data')
        self.assertEqual(updated_mapping.procore_type, 'Product Info')
        
        # Verify new mapping was created
        new_mapping = ProcoreSubmittalTypeMapping.objects.get(link_type='Samples')
        self.assertEqual(new_mapping.procore_type, 'Sample')
        self.assertEqual(new_mapping.link_type, 'Samples')
        
    def test_unauthorized_user(self):
        """Test that non-admin users cannot update mappings"""
        self.client.force_authenticate(user=self.non_admin_user)
        
        data = {
            'mappings': [
                {
                    'id': self.existing_mapping.id,
                    'link_submittal': 'Product Data',
                    'procore_type': 'Product Info'
                }
            ]
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Verify the mapping wasn't changed
        unchanged_mapping = ProcoreSubmittalTypeMapping.objects.get(id=self.existing_mapping.id)
        self.assertEqual(unchanged_mapping.link_type, 'Shop Drawings')
        
    def test_unauthenticated_user(self):
        """Test that unauthenticated users cannot access the view"""
        data = {
            'company_id': self.company.id,
            'mappings': []
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
    def test_invalid_company_id(self):
        """Test handling of invalid company ID"""
        self.client.force_authenticate(user=self.admin_user)
        
        data = {
            'company_id': 99999,  # Non-existent company ID
            'mappings': []
        }
        url = reverse('deliverables:procore-submittal-mappings', kwargs={'company_id': 99999})

        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
    def test_missing_required_fields(self):
        """Test handling of missing required fields in mapping data"""
        self.client.force_authenticate(user=self.admin_user)
        
        data = {
            'company_id': self.company.id,
            'mappings': [
                {
                    'id': self.existing_mapping.id,
                    # Missing link_submittal
                    'procore_type': 'Product Info'
                }
            ]
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
