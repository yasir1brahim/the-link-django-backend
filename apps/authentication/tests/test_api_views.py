from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.teams.models import Team, Membership as TeamMembership
from apps.teams.roles import ROLE_ADMIN, ROLE_MEMBER
from apps.users.models import CustomUser
from django.urls import reverse

class TestLogin(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(username='testuser', email='testuser@example.com', password='testpassword')
        self.capitalized_email_user = CustomUser.objects.create_user(username='testuser2', email='TestUser2@example.com', password='testpassword')

    def test_login(self):
        url = reverse('authentication:rest_login')
        response = self.client.post(url, data={'email': 'testuser@example.com', 'password': 'testpassword'})
        print(response.data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['jwt']['user']['id'], self.user.id)
        self.assertEqual(response.data['jwt']['user']['email'], self.user.email)
        self.assertEqual(response.data['jwt']['user']['first_name'], self.user.first_name)
        self.assertEqual(response.data['jwt']['user']['last_name'], self.user.last_name)
        self.assertEqual(response.data['jwt']['user']['get_display_name'], self.user.get_display_name())
        self.assertEqual(response.data['jwt']['user']['avatar_url'], self.user.avatar_url)
        self.assertEqual(response.data['jwt']['user']['is_superuser'], self.user.is_superuser)
        self.assertEqual(response.data['jwt']['user']['active_flags'], [])

    def test_login_with_capitalized_email(self):
        url = reverse('authentication:rest_login')
        response = self.client.post(url, data={'email': 'TestUser2@example.com', 'password': 'testpassword'})
        print(response.data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')

        

class UserStatusUpdateViewTests(APITestCase):

    def setUp(self):
        self.client = APIClient()
        self.team_a = Team.objects.create(name='Team A', slug="team-a")
        self.team_b = Team.objects.create(name='Team B', slug="team-b")
        self.team_a_admin = CustomUser.objects.create_user(username='admin_a', password='password123')
        self.team_a_member = CustomUser.objects.create_user(username='member_a', password='password123')
        self.team_b_admin = CustomUser.objects.create_user(username='admin_b', password='password123')

        TeamMembership.objects.create(user=self.team_a_admin, team=self.team_a, role=ROLE_ADMIN)
        TeamMembership.objects.create(user=self.team_a_member, team=self.team_a, role=ROLE_MEMBER)
        TeamMembership.objects.create(user=self.team_b_admin, team=self.team_b, role=ROLE_ADMIN)

        self.url = reverse('authentication:update_user_status')

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_admin_can_update_user_status(self):
        """Test that an admin of a team can update the status of a user in the same team"""
        self.authenticate(self.team_a_admin)
        response = self.client.patch(self.url, data={
            'user_id': self.team_a_member.id,
            'is_active': False
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"message": "User status updated successfully"})

    def test_member_cannot_update_user_status(self):
        """Test that a non-admin member cannot update the status of a user in the same team"""
        self.authenticate(self.team_a_member)
        response = self.client.patch(self.url, data={
            'user_id': self.team_a_member.id,
            'is_active': False
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_of_other_team_cannot_update_user_status(self):
        """Test that an admin of another team cannot update the status of a user in a different team"""
        self.authenticate(self.team_b_admin)
        response = self.client.patch(self.url, data={
            'user_id': self.team_a_member.id,
            'is_active': False
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)