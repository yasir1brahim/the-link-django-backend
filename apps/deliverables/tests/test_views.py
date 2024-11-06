from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from apps.teams.models import Team, Membership as TeamMembership
from apps.teams.roles import ROLE_ADMIN, ROLE_MEMBER
from apps.deliverables.models import Project, ProjectMembership, SubmittalItem, MasterFormatSection, ROLE_PROJECT_ADMIN, ROLE_PROJECT_MEMBER
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

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
            role=ROLE_PROJECT_MEMBER
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
            role=ROLE_PROJECT_MEMBER
        )
        ProjectMembership.objects.create(
            project=self.project2,
            user=self.member_of_both_teams,
            role=ROLE_PROJECT_MEMBER
        )
        ProjectMembership.objects.create(
            project=self.project3,
            user=self.member_of_both_teams,
            role=ROLE_PROJECT_MEMBER
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

    def test_team_admin_can_access_project_detail(self):
        """Test that team admins can access project detail"""
        self.client.force_authenticate(user=self.team1_admin)
        response = self.client.get(reverse('project-detail', kwargs={'pk': self.project1.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_project_member_can_access_project_detail(self):
        """Test that project members can access project detail"""
        self.client.force_authenticate(user=self.member_of_both_teams)
        ProjectMembership.objects.create(
            project=self.project1,
            user=self.member_of_both_teams,
            role=ROLE_PROJECT_MEMBER
        )
        response = self.client.get(reverse('project-detail', kwargs={'pk': self.project1.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        unauthorized_response = self.client.get(reverse('project-detail', kwargs={'pk': self.project2.id}))
        self.assertEqual(unauthorized_response.status_code, status.HTTP_403_FORBIDDEN)

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


class ProjectViewSetTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.User = get_user_model()

        self.company_admin = self.User.objects.create_user(
            username='company_admin', 
            password='password123'
        )
        self.company_member = self.User.objects.create_user(
            username='company_member', 
            password='password123'
        )
        self.team = Team.objects.create(name='Team 1', slug='team-1')
        TeamMembership.objects.create(
            user=self.company_admin,
            team=self.team,
            role=ROLE_ADMIN
        )
        TeamMembership.objects.create(
            user=self.company_member,
            team=self.team,
            role=ROLE_MEMBER
        )

        self.existing_project = Project.objects.create(
            name='Existing Project',
            project_number='123456',
            team=self.team,
        )

    def test_company_admin_can_create_project(self):
        """Test that a company admin can create a project"""
        self.client.force_authenticate(user=self.company_admin)
        response = self.client.post(reverse('project-list'), {
            'name': 'New Project',
            'project_number': '789012',
            'project_type': 'Test Type',
            'team': self.team.id,
        })
        print(f"response.data: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        project = Project.objects.get(id=response.data['id'])
        self.assertEqual(project.name, 'New Project')
        self.assertEqual(project.project_number, '789012')
        self.assertEqual(project.project_type, 'Test Type')
        self.assertEqual(project.team, self.team)

    def test_company_non_admin_cannot_create_project(self):
        """Test that a company non-admin cannot create a project"""
        self.client.force_authenticate(user=self.company_member)
        response = self.client.post(reverse('project-list'), {
            'name': 'New Project',
            'project_number': '789012',
            'project_type': 'Test Type',
            'team': self.team.id,
        })
        print(f"response.data: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


    def test_company_admin_can_update_project(self):
        """Test that a company admin can update a project"""
        self.client.force_authenticate(user=self.company_admin)
        response = self.client.put(reverse('project-detail', kwargs={'pk': self.existing_project.id}), {
            'name': 'Updated Project',
            'project_number': '111111',
            'project_type': 'Updated Type',
            'team': self.team.id,
        })
        print(f"response.data: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        project = Project.objects.get(id=response.data['id'])
        self.assertEqual(project.name, 'Updated Project')
        self.assertEqual(project.project_number, '111111')
        self.assertEqual(project.project_type, 'Updated Type')
        self.assertEqual(project.team, self.team)

    def test_project_admin_can_update_project(self):
        """Test that a project admin can update a project"""
        ProjectMembership.objects.create(
            project=self.existing_project,
            user=self.company_member,
            role=ROLE_PROJECT_ADMIN
        )
        self.client.force_authenticate(user=self.company_member)
        response = self.client.put(reverse('project-detail', kwargs={'pk': self.existing_project.id}), {
            'name': 'Updated Project',
            'project_number': '111111',
            'project_type': 'Updated Type',
            'team': self.team.id,
        })
        print(f"response.data: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        project = Project.objects.get(id=response.data['id'])
        self.assertEqual(project.name, 'Updated Project')
        self.assertEqual(project.project_number, '111111')
        self.assertEqual(project.project_type, 'Updated Type')
        self.assertEqual(project.team, self.team)

    def test_project_member_cannot_update_project(self):
        """Test that a project admin can update a project"""
        ProjectMembership.objects.create(
            project=self.existing_project,
            user=self.company_member,
            role=ROLE_PROJECT_MEMBER
        )
        self.client.force_authenticate(user=self.company_member)
        response = self.client.put(reverse('project-detail', kwargs={'pk': self.existing_project.id}), {
            'name': 'Updated Project',
            'project_number': '111111',
            'project_type': 'Updated Type',
            'team': self.team.id,
        })
        print(f"response.data: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_company_admin_can_delete_project(self):
        """Test that a company admin can delete a project"""
        self.client.force_authenticate(user=self.company_admin)
        response = self.client.delete(reverse('project-detail', kwargs={'pk': self.existing_project.id}))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.assertFalse(Project.objects.filter(id=self.existing_project.id).exists())

    def test_company_member_cannot_delete_project(self):
        """Test that a company member cannot delete a project"""
        self.client.force_authenticate(user=self.company_member)
        response = self.client.delete(reverse('project-detail', kwargs={'pk': self.existing_project.id}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_company_member_cannot_delete_project_even_if_project_admin(self):
        """Test that a company member cannot delete a project even if they are a project admin"""
        ProjectMembership.objects.create(
            project=self.existing_project,
            user=self.company_member,
            role=ROLE_PROJECT_ADMIN
        )
        self.client.force_authenticate(user=self.company_member)
        response = self.client.delete(reverse('project-detail', kwargs={'pk': self.existing_project.id}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class UploadFileTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.User = get_user_model()

        self.company_admin = self.User.objects.create_user(
            username='company_admin', 
            password='password123'
        )
        self.company_member = self.User.objects.create_user(
            username='company_member', 
            password='password123'
        )
        self.team = Team.objects.create(name='Team 1', slug='team-1')
        TeamMembership.objects.create(
            user=self.company_admin,
            team=self.team,
            role=ROLE_ADMIN
        )
        TeamMembership.objects.create(
            user=self.company_member,
            team=self.team,
            role=ROLE_MEMBER
        )

        self.existing_project = Project.objects.create(
            name='Existing Project',
            project_number='123456',
            team=self.team,
        )

        self.mock_file = SimpleUploadedFile(
            name='test_file.txt',
            content=b'This is some test file content',
            content_type='text/plain'
        )

    def test_unauthenticated_user_cannot_upload_file(self):
        """Test that an unauthenticated user cannot upload a file"""
        response = self.client.post(reverse('upload_file'), {
            'project_id': self.existing_project.id,
            'files': [self.mock_file],
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_project_member_can_upload_file_to_their_project(self):
        """Test that a project member can upload a file to their project"""
        ProjectMembership.objects.create(
            project=self.existing_project,
            user=self.company_member,
            role=ROLE_PROJECT_MEMBER
        )
        self.client.force_authenticate(user=self.company_member)
        response = self.client.post(reverse('upload_file'), {
            'project_id': self.existing_project.id,
            'files': [self.mock_file],
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_company_admin_can_upload_file_to_project(self):
        """Test that a company admin can upload a file to a project"""
        self.client.force_authenticate(user=self.company_admin)
        response = self.client.post(reverse('upload_file'), {
            'project_id': self.existing_project.id,
            'files': [self.mock_file],
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_company_member_cannot_upload_file_to_project_they_are_not_a_member_of(self):
        """Test that a company member cannot upload a file to a project they are not a member of"""
        self.client.force_authenticate(user=self.company_member)
        response = self.client.post(reverse('upload_file'), {
            'project_id': self.existing_project.id,
            'files': [self.mock_file],
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class SubmittalItemViewSetTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.User = get_user_model()

        self.user = self.User.objects.create_user(
            username='user1', 
            password='password123'
        )
        self.non_member = self.User.objects.create_user(
            username='non_member', 
            password='password123'
        )

        self.team = Team.objects.create(name='Team 1', slug='team-1')
        TeamMembership.objects.create(
            user=self.user,
            team=self.team,
            role=ROLE_MEMBER
        )

        self.project = Project.objects.create(
            name='Project 1',
            team=self.team,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ROLE_PROJECT_MEMBER
        )

        self.submittal_item = SubmittalItem.objects.create(
            project=self.project,
            masterformat_section=MasterFormatSection.objects.create(masterformat_number='033000'),
        )

    def test_user_can_see_submittal_items_for_their_project(self):
        """Test that users can see submittal items for their project"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse('submittal-item-list', kwargs={'project_id': self.project.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print(f"response.data: {response.data}")
        self.assertEqual(len(response.data['message']), 1)
        self.assertEqual(response.data['message'][0]['id'], self.submittal_item.id)

    def test_user_cannot_see_submittal_items_for_other_projects(self):
        """Test that users cannot see submittal items for projects they are not a member of"""
        self.client.force_authenticate(user=self.non_member)
        response = self.client.get(reverse('submittal-item-list', kwargs={'project_id': self.project.id}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
