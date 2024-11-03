from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse

from apps.teams.models import Team, Membership as TeamMembership
from apps.teams.roles import ROLE_ADMIN, ROLE_MEMBER
from apps.users.models import CustomUser

class TeamViewSetTest(APITestCase):
    def setUp(self):
        self.client = APIClient()

        self.team = Team.objects.create(name='Team 1', slug='team-1')
        self.other_team = Team.objects.create(name='Team 2', slug='team-2')
        self.team_admin = CustomUser.objects.create_user(username='team_admin', password='password123')
        self.team_member = CustomUser.objects.create_user(username='team_member', password='password123')

        TeamMembership.objects.create(user=self.team_admin, team=self.team, role=ROLE_ADMIN)
        TeamMembership.objects.create(user=self.team_member, team=self.team, role=ROLE_MEMBER)

    def test_team_admin_can_only_view_their_team(self):
        self.client.force_authenticate(user=self.team_admin)
        response = self.client.get(reverse('teams:team-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print(response.data)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], self.team.id)

    def test_team_member_can_only_view_their_team(self):
        self.client.force_authenticate(user=self.team_member)
        response = self.client.get(reverse('teams:team-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], self.team.id)

    def test_unauthenticated_user_cannot_view_teams(self):
        response = self.client.get(reverse('teams:team-list'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_team_admin_can_view_their_team_details(self):
        self.client.force_authenticate(user=self.team_admin)
        response = self.client.get(reverse('teams:team-detail', kwargs={'pk': self.team.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.team.id)

    def test_team_member_can_view_their_team_details(self):
        self.client.force_authenticate(user=self.team_member)
        response = self.client.get(reverse('teams:team-detail', kwargs={'pk': self.team.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.team.id)

    def test_team_admin_cannot_view_other_teams_details(self):
        self.client.force_authenticate(user=self.team_admin)
        response = self.client.get(reverse('teams:team-detail', kwargs={'pk': self.other_team.id}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_team_member_cannot_view_other_teams_details(self):
        self.client.force_authenticate(user=self.team_member)
        response = self.client.get(reverse('teams:team-detail', kwargs={'pk': self.other_team.id}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_team_admin_can_update_their_team(self):
        self.client.force_authenticate(user=self.team_admin)
        response = self.client.put(reverse('teams:team-detail', kwargs={'pk': self.team.id}), {'name': 'Updated Team 1'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Updated Team 1')

    def test_team_member_cannot_update_their_team(self):
        self.client.force_authenticate(user=self.team_member)
        response = self.client.put(reverse('teams:team-detail', kwargs={'pk': self.team.id}), {'name': 'Updated Team 1'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_team_admin_can_view_all_team_memberships(self):
        self.client.force_authenticate(user=self.team_admin)
        response = self.client.get(reverse('teams:team-detail', kwargs={'pk': self.team.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print(response.data)
        self.assertEqual(len(response.data['members']), 2)
        self.assertEqual(response.data['members'][0]['user_id'], self.team_admin.id)
        self.assertEqual(response.data['members'][1]['user_id'], self.team_member.id)
        self.assertEqual(response.data['members'][0]['role'], ROLE_ADMIN)
        self.assertEqual(response.data['members'][1]['role'], ROLE_MEMBER)

    def test_team_member_can_only_view_their_own_team_memberships(self):
        self.client.force_authenticate(user=self.team_member)
        response = self.client.get(reverse('teams:team-detail', kwargs={'pk': self.team.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['members']), 1)
        self.assertEqual(response.data['members'][0]['user_id'], self.team_member.id)
        self.assertEqual(response.data['members'][0]['role'], ROLE_MEMBER)

class MembershipViewSetTest(APITestCase):
    def setUp(self):
        self.client = APIClient()

        self.team = Team.objects.create(name='Team 1', slug='team-1')
        self.other_team = Team.objects.create(name='Team 2', slug='team-2')
        self.team_admin = CustomUser.objects.create_user(username='team_admin', password='password123')
        self.team_member1 = CustomUser.objects.create_user(username='team_member1', password='password123')
        self.team_member2 = CustomUser.objects.create_user(username='team_member2', password='password123')

        TeamMembership.objects.create(user=self.team_admin, team=self.team, role=ROLE_ADMIN)
        TeamMembership.objects.create(user=self.team_member1, team=self.team, role=ROLE_MEMBER)
        TeamMembership.objects.create(user=self.team_member2, team=self.team, role=ROLE_MEMBER)
