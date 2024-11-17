from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse

from apps.teams.models import Team, Membership as TeamMembership, Invitation
from apps.teams.roles import ROLE_ADMIN, ROLE_MEMBER
from apps.users.models import CustomUser

from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile

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

    def test_team_admin_cannot_delete_team(self):
        self.client.force_authenticate(user=self.team_admin)
        response = self.client.delete(reverse('teams:team-detail', kwargs={'pk': self.team.id}))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_team_member_cannot_delete_team(self):
        self.client.force_authenticate(user=self.team_member)
        response = self.client.delete(reverse('teams:team-detail', kwargs={'pk': self.team.id}))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class MembershipViewSetTest(APITestCase):
    def setUp(self):
        self.client = APIClient()

        self.team = Team.objects.create(name='Team 1', slug='team-1')
        self.other_team = Team.objects.create(name='Team 2', slug='team-2')
        self.team_admin = CustomUser.objects.create_user(username='team_admin', password='password123')
        self.team_member1 = CustomUser.objects.create_user(username='team_member1', password='password123')
        self.team_member2 = CustomUser.objects.create_user(username='team_member2', password='password123')

        self.team_membership_admin = TeamMembership.objects.create(user=self.team_admin, team=self.team, role=ROLE_ADMIN)
        self.team_membership_member1 = TeamMembership.objects.create(user=self.team_member1, team=self.team, role=ROLE_MEMBER)
        self.team_membership_member2 = TeamMembership.objects.create(user=self.team_member2, team=self.team, role=ROLE_MEMBER)

        self.other_team_membership = TeamMembership.objects.create(user=self.team_member1, team=self.other_team, role=ROLE_MEMBER)

    def test_team_admin_can_delete_team_membership(self):
        self.client.force_authenticate(user=self.team_admin)
        response = self.client.delete(reverse('teams:membership-detail', kwargs={'pk': self.team_membership_member1.id}))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_team_member_cannot_delete_team_membership(self):
        self.client.force_authenticate(user=self.team_member1)
        response = self.client.delete(reverse('teams:membership-detail', kwargs={'pk': self.team_membership_member1.id}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_team_admin_can_update_team_membership(self):
        self.client.force_authenticate(user=self.team_admin)
        response = self.client.put(reverse('teams:membership-detail', kwargs={'pk': self.team_membership_member1.id}), {'role': ROLE_ADMIN})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['role'], ROLE_ADMIN)

    def test_team_member_cannot_update_team_membership(self):
        self.client.force_authenticate(user=self.team_member1)
        response = self.client.put(reverse('teams:membership-detail', kwargs={'pk': self.team_membership_member1.id}), {'role': ROLE_ADMIN})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_team_admin_cannot_update_other_team_memberships(self):
        self.client.force_authenticate(user=self.team_admin)
        response = self.client.put(reverse('teams:membership-detail', kwargs={'pk': self.other_team_membership.id}), {'role': ROLE_ADMIN})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_team_member_cannot_update_other_team_memberships(self):
        self.client.force_authenticate(user=self.team_member2)
        response = self.client.put(reverse('teams:membership-detail', kwargs={'pk': self.other_team_membership.id}), {'role': ROLE_ADMIN})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    
class InvitationViewSetTest(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.team = Team.objects.create(name='Team 1', slug='team-1')
        self.other_team = Team.objects.create(name='Team 2', slug='team-2')
        self.team_admin = CustomUser.objects.create_user(username='team_admin', password='password123')
        self.team_member = CustomUser.objects.create_user(username='team_member', password='password123')

        self.team_membership_admin = TeamMembership.objects.create(user=self.team_admin, team=self.team, role=ROLE_ADMIN)
        self.team_membership_member = TeamMembership.objects.create(user=self.team_member, team=self.team, role=ROLE_MEMBER)

    def test_team_admin_can_create_invitation(self):
        self.client.force_authenticate(user=self.team_admin)
        response = self.client.post(reverse('single_team:invitation-list', kwargs={'team_id': self.team.id}), {'team': self.team.id, 'email': 'test@example.com', 'role': ROLE_MEMBER})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_invitation_role_defaults_to_member(self):
        self.client.force_authenticate(user=self.team_admin)
        response = self.client.post(reverse('single_team:invitation-list', kwargs={'team_id': self.team.id}), {'team': self.team.id, 'email': 'test@example.com'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['role'], ROLE_MEMBER)

    def test_team_member_cannot_create_invitation(self):
        self.client.force_authenticate(user=self.team_member)
        response = self.client.post(reverse('single_team:invitation-list', kwargs={'team_id': self.team.id}), {'team': self.team.id, 'email': 'test@example.com'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_team_admin_can_view_their_team_invitations(self):
        self.client.force_authenticate(user=self.team_admin)
        response = self.client.get(reverse('single_team:invitation-list', kwargs={'team_id': self.team.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_team_member_cannot_view_their_team_invitations(self):
        self.client.force_authenticate(user=self.team_member)
        response = self.client.get(reverse('single_team:invitation-list', kwargs={'team_id': self.team.id}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_team_admin_can_delete_their_team_invitations(self):
        self.client.force_authenticate(user=self.team_admin)
        invitation = Invitation.objects.create(email='test@example.com', team=self.team, invited_by=self.team_admin, role=ROLE_MEMBER)
        response = self.client.delete(reverse('single_team:invitation-detail', kwargs={'team_id': self.team.id, 'pk': invitation.id}))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_team_member_cannot_delete_team_invitations(self):
        self.client.force_authenticate(user=self.team_member)
        invitation = Invitation.objects.create(email='test@example.com', team=self.team, invited_by=self.team_admin, role=ROLE_MEMBER)
        response = self.client.delete(reverse('single_team:invitation-detail', kwargs={'team_id': self.team.id, 'pk': invitation.id}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_team_admin_can_update_their_team_invitations(self):
        self.client.force_authenticate(user=self.team_admin)
        invitation = Invitation.objects.create(email='test@example.com', team=self.team, invited_by=self.team_admin, role=ROLE_MEMBER)
        response = self.client.patch(reverse('single_team:invitation-detail', kwargs={'team_id': self.team.id, 'pk': invitation.id}), {'email': 'test2@example.com'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'test2@example.com')

    def test_team_member_cannot_update_team_invitations(self):
        self.client.force_authenticate(user=self.team_member)
        invitation = Invitation.objects.create(email='test@example.com', team=self.team, invited_by=self.team_admin, role=ROLE_MEMBER)
        response = self.client.patch(reverse('single_team:invitation-detail', kwargs={'team_id': self.team.id, 'pk': invitation.id}), {'email': 'test2@example.com'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_team_admin_cannot_update_or_create_other_team_invitations(self):
        self.client.force_authenticate(user=self.team_admin)
        response = self.client.post(reverse('single_team:invitation-list', kwargs={'team_id': self.other_team.id}), {'team': self.other_team.id, 'email': 'test@example.com'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        other_team_invitation = Invitation.objects.create(email='test@example.com', team=self.other_team, invited_by=self.team_admin, role=ROLE_MEMBER)
        response = self.client.patch(reverse('single_team:invitation-detail', kwargs={'team_id': self.other_team.id, 'pk': other_team_invitation.id}), {'email': 'test2@example.com'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_user_cannot_create_or_view_invitations(self):
        response = self.client.post(reverse('single_team:invitation-list', kwargs={'team_id': self.team.id}), {'team': self.team.id, 'email': 'test@example.com'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.get(reverse('single_team:invitation-list', kwargs={'team_id': self.team.id}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

class UploadLogoTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.team = Team.objects.create(name='Team 1', slug='team-1')
        self.team_admin = CustomUser.objects.create_user(username='team_admin', password='password123')
        self.team_member = CustomUser.objects.create_user(username='team_member', password='password123')

        TeamMembership.objects.create(user=self.team_admin, team=self.team, role=ROLE_ADMIN)
        TeamMembership.objects.create(user=self.team_member, team=self.team, role=ROLE_MEMBER)

        self.image = BytesIO()
        Image.new('RGB', (100, 100)).save(self.image, format='PNG')
        self.image.seek(0)
        self.logo_file = SimpleUploadedFile("logo.png", self.image.read(), content_type="image/png")

        self.upload_logo_url = reverse('teams:team-upload-logo', args=[self.team.id])

    def test_unauthenticated_user_cannot_upload_logo(self):
        """Test that an unauthenticated user cannot upload a logo"""
        response = self.client.post(self.upload_logo_url, {'file': self.logo_file})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_team_admin_can_upload_logo(self):
        """Test that a team member can uplaod the logo"""
        self.client.force_authenticate(user=self.team_admin)
        response = self.client.post(self.upload_logo_url, {'file': self.logo_file}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_team_member_cannot_upload_logo(self):
        """Test that a team member cannot upload the logo"""
        self.client.force_authenticate(user=self.team_member)
        response = self.client.post(self.upload_logo_url, {'file': self.logo_file}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_admin_upload_logo_no_file(self):
        """Test that an admin cannot upload an empty logo file"""
        self.client.force_authenticate(user=self.team_admin)
        response = self.client.post(self.upload_logo_url, {}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'No file uploaded.')