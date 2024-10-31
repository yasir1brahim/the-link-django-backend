from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from apps.teams.models import Team, Membership as TeamMembership
from apps.teams.roles import ROLE_ADMIN, ROLE_MEMBER
from apps.deliverables.models import Project, ProjectMembership
from rest_framework.exceptions import PermissionDenied, ValidationError

class ProjectViewSetQuerySetTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.User = get_user_model()
        
        # Create users
        self.member_of_both_teams = self.User.objects.create_user(
            username='user1', 
            password='password123'
        )
        self.member_of_team2 = self.User.objects.create_user(
            username='user2', 
            password='password123'
        )
        self.team1_admin = self.User.objects.create_user(
            username='team1_admin',
            password='password123'
        )
        
        # Create teams
        self.team1 = Team.objects.create(name='Team 1', slug='team-1')
        self.team2 = Team.objects.create(name='Team 2', slug='team-2')
        
        # Add user1 to team1
        TeamMembership.objects.create(
            user=self.member_of_both_teams,
            team=self.team1,
            role=ROLE_MEMBER
        )
        TeamMembership.objects.create(
            user=self.member_of_both_teams,
            team=self.team2,
            role=ROLE_MEMBER
        )
        TeamMembership.objects.create(
            user=self.team1_admin,
            team=self.team1,
            role=ROLE_ADMIN
        )
        TeamMembership.objects.create(
            user=self.member_of_team2,
            team=self.team2,
            role=ROLE_MEMBER
        )
        
        # Create projects
        self.project1 = Project.objects.create(
            name='Project 1',
            team=self.team1,
        )
        self.project2 = Project.objects.create(
            name='Project 2',
            team=self.team1,
        )
        self.project3 = Project.objects.create(
            name='Project 3',
            team=self.team2,
        )

        # URL for project list
        self.url = reverse('project-list')  # Adjust based on your URL configuration

    def test_user_can_see_member_projects(self):
        """Test that users can see projects where they are members"""
        self.client.force_authenticate(user=self.member_of_both_teams)
        # Add user1 as member to project2
        ProjectMembership.objects.create(
            project=self.project2,
            user=self.member_of_both_teams,
            role=ROLE_MEMBER
        )
        
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print(f"response.data: {response.data}")
        self.assertEqual(len(response.data['results']), 1)
        project_names = {project['name'] for project in response.data['results']}
        self.assertEqual(project_names, {'Project 2'})

    def test_filter_by_team_id(self):
        """Test filtering projects by team_id"""
        self.client.force_authenticate(user=self.member_of_both_teams)
        ProjectMembership.objects.create(
            project=self.project1,
            user=self.member_of_both_teams,
            role=ROLE_MEMBER
        )
        ProjectMembership.objects.create(
            project=self.project2,
            user=self.member_of_both_teams,
            role=ROLE_MEMBER
        )
        ProjectMembership.objects.create(
            project=self.project3,
            user=self.member_of_both_teams,
            role=ROLE_MEMBER
        )
        response = self.client.get(f"{self.url}?team_id={self.team1.id}")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
        project_names = {project['name'] for project in response.data['results']}
        self.assertEqual(project_names, {'Project 1', 'Project 2'})

        response = self.client.get(f"{self.url}?team_id={self.team2.id}")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        project_names = {project['name'] for project in response.data['results']}
        self.assertEqual(project_names, {'Project 3'})

    def test_team_admin_can_see_all_projects(self):
        """Test that team admins can see all projects even if they are not members of the project"""
        self.client.force_authenticate(user=self.team1_admin)
        response = self.client.get(f"{self.url}?team_id={self.team1.id}")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_invalid_team_id_returns_400(self):
        """Test that invalid team_id returns 400 error"""
        self.client.force_authenticate(user=self.member_of_both_teams)
        response = self.client.get(f"{self.url}?team_id=invalid")
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_member_team_access_denied(self):
        """Test that accessing projects from non-member team is denied"""
        self.client.force_authenticate(user=self.member_of_team2)
        response = self.client.get(f"{self.url}?team_id={self.team1.id}")
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_projects_ordered_by_name(self):
        """Test that projects are returned ordered by name"""
        self.client.force_authenticate(user=self.member_of_both_teams)
        # Create projects with different names to test ordering
        Project.objects.create(
            name='A Project',
            team=self.team1,
        )
        Project.objects.create(
            name='Z Project',
            team=self.team1,
        )
        
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [project['name'] for project in response.data['results']]
        self.assertEqual(names, sorted(names))

    def test_unauthenticated_user_denied(self):
        """Test that unauthenticated users cannot access projects"""
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)