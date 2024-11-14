from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.teams.models import Team, Membership as TeamMembership
from apps.teams.roles import ROLE_ADMIN, ROLE_MEMBER
from apps.users.models import CustomUser
from django.urls import reverse

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