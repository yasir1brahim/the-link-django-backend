import time
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from apps.teams.models import Team, Membership as TeamMembership
from apps.teams.roles import ROLE_ADMIN, ROLE_MEMBER
from apps.deliverables.models import (Project, ProjectMembership, SubmittalItemList,
    SubmittalItem, MasterFormatSection, ROLE_PROJECT_ADMIN, ROLE_PROJECT_MEMBER,
    SpecSection, DocProcessingStatus, UploadedFile)
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
        self.superuser = self.User.objects.create_superuser(username='superuser', password='password123')
        self.member_of_no_team = self.User.objects.create_user(
            username='member_of_no_team',
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
        self.url = reverse('deliverables:project-list')  # Adjust based on your URL configuration

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

    def test_superuser_can_see_all_projects(self):
        """Test that superusers can see all projects"""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)

    def test_superuser_can_see_all_projects_for_team(self):
        """Test that superusers can see all projects for a team"""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(f"{self.url}?team_id={self.team1.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_team_admin_can_access_project_detail(self):
        """Test that team admins can access project detail"""
        self.client.force_authenticate(user=self.team1_admin)
        response = self.client.get(reverse('deliverables:project-detail', kwargs={'pk': self.project1.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_superuser_can_access_project_detail(self):
        """Test that superusers can access project detail"""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(reverse('deliverables:project-detail', kwargs={'pk': self.project1.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_project_member_can_access_project_detail(self):
        """Test that project members can access project detail"""
        self.client.force_authenticate(user=self.member_of_both_teams)
        ProjectMembership.objects.create(
            project=self.project1,
            user=self.member_of_both_teams,
            role=ROLE_PROJECT_MEMBER
        )
        response = self.client.get(reverse('deliverables:project-detail', kwargs={'pk': self.project1.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        unauthorized_response = self.client.get(reverse('deliverables:project-detail', kwargs={'pk': self.project2.id}))
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
        self.superuser = self.User.objects.create_superuser(username='superuser', password='password123')
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
        response = self.client.post(reverse('deliverables:project-list'), {
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

    def test_superuser_can_create_project(self):
        """Test that a superuser can create a project"""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(reverse('deliverables:project-list'), {
            'name': 'New Project',
            'project_number': '789012',
            'project_type': 'Test Type',
            'team': self.team.id,
        })
        print(f"response.data: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_company_non_admin_cannot_create_project(self):
        """Test that a company non-admin cannot create a project"""
        self.client.force_authenticate(user=self.company_member)
        response = self.client.post(reverse('deliverables:project-list'), {
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
        response = self.client.patch(reverse('deliverables:project-detail', kwargs={'pk': self.existing_project.id}), {
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

    def test_superuser_can_update_project(self):
        """Test that a superuser can update a project"""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(reverse('deliverables:project-detail', kwargs={'pk': self.existing_project.id}), {
            'name': 'Updated Project',
            'project_number': '111111',
            'project_type': 'Updated Type',
            'team': self.team.id,
        })
        print(f"response.data: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)


    def test_project_admin_can_update_project(self):
        """Test that a project admin can update a project"""
        ProjectMembership.objects.create(
            project=self.existing_project,
            user=self.company_member,
            role=ROLE_PROJECT_ADMIN
        )
        self.client.force_authenticate(user=self.company_member)
        response = self.client.patch(reverse('deliverables:project-detail', kwargs={'pk': self.existing_project.id}), {
            'name': 'Updated Project',
            'project_number': '111111',
            'project_type': 'Updated Type',
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
        response = self.client.patch(reverse('deliverables:project-detail', kwargs={'pk': self.existing_project.id}), {
            'name': 'Updated Project',
            'project_number': '111111',
            'project_type': 'Updated Type',
        })
        print(f"response.data: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_company_admin_can_delete_project(self):
        """Test that a company admin can delete a project"""
        self.client.force_authenticate(user=self.company_admin)
        response = self.client.delete(reverse('deliverables:project-detail', kwargs={'pk': self.existing_project.id}))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.assertFalse(Project.objects.filter(id=self.existing_project.id).exists())

    def test_superuser_can_delete_project(self):
        """Test that a superuser can delete a project"""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.delete(reverse('deliverables:project-detail', kwargs={'pk': self.existing_project.id}))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_company_member_cannot_delete_project(self):
        """Test that a company member cannot delete a project"""
        self.client.force_authenticate(user=self.company_member)
        response = self.client.delete(reverse('deliverables:project-detail', kwargs={'pk': self.existing_project.id}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_company_member_cannot_delete_project_even_if_project_admin(self):
        """Test that a company member cannot delete a project even if they are a project admin"""
        ProjectMembership.objects.create(
            project=self.existing_project,
            user=self.company_member,
            role=ROLE_PROJECT_ADMIN
        )
        self.client.force_authenticate(user=self.company_member)
        response = self.client.delete(reverse('deliverables:project-detail', kwargs={'pk': self.existing_project.id}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_project_member_cannot_view_project(self):
        """Test that a non-project member cannot view a project"""
        self.client.force_authenticate(user=self.company_member)
        response = self.client.get(reverse('deliverables:project-detail', kwargs={'pk': self.existing_project.id}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_company_admin_can_update_project_members(self):
        """Test that a company admin can update project members"""
        self.client.force_authenticate(user=self.company_admin)
        new_user = self.User.objects.create_user(
            username='new_user',
            password='password123'
        )
        TeamMembership.objects.create(
            user=new_user,
            team=self.team,
            role=ROLE_MEMBER
        )
        response = self.client.patch(
            reverse('deliverables:project-detail', kwargs={'pk': self.existing_project.id}),
            data={
                'members': [
                    {
                        'user_id': new_user.id,
                        'role': ROLE_PROJECT_MEMBER
                    }
                ]
            },
            format='json'
        )
        print(f"response.data: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        members = ProjectMembership.objects.filter(project=self.existing_project)
        self.assertEqual(members.count(), 1)
        self.assertEqual(members[0].user, new_user)
        self.assertEqual(members[0].role, ROLE_PROJECT_MEMBER)

    def test_update_project_members_requires_members_to_be_in_project_team(self):
        """Test that a company admin can update project members"""
        self.client.force_authenticate(user=self.company_admin)
        new_user = self.User.objects.create_user(
            username='new_user',
            password='password123'
        )
        response = self.client.patch(
            reverse('deliverables:project-detail', kwargs={'pk': self.existing_project.id}),
            data={
                'members': [
                    {
                        'user_id': new_user.id,
                        'role': ROLE_PROJECT_MEMBER
                    }
                ]
            },
            format='json'
        )
        print(f"response.data: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['non_field_errors'][0], "All members must be a member of the team.")

    def test_user_must_be_a_member_of_the_new_team(self):
        """Test that a user must be a member of the new team"""
        self.client.force_authenticate(user=self.company_admin)
        other_team = Team.objects.create(name='Other Team', slug='other-team')
        response = self.client.patch(
            reverse('deliverables:project-detail', kwargs={'pk': self.existing_project.id}),
            data={
                'team': other_team.id,
            },
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


    def test_project_member_can_add_users_to_project_with_addition_endpoint(self):
        """Test that a company member can add users to a project with the addition endpoint"""
        ProjectMembership.objects.create(
            project=self.existing_project,
            user=self.company_member,
            role=ROLE_PROJECT_MEMBER
        )
        new_user = self.User.objects.create_user(
            username='new_user',
            password='password123'
        )
        TeamMembership.objects.create(
            user=new_user,
            team=self.team,
            role=ROLE_MEMBER
        )
        self.client.force_authenticate(user=self.company_member)
        response = self.client.post(reverse('deliverables:project-members-add', kwargs={'pk': self.existing_project.id}), {
            'user_ids': [
                new_user.id
            ]
        })
        print(f"response.data: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(ProjectMembership.objects.filter(project=self.existing_project, user=new_user).count(), 1)
        self.assertEqual(ProjectMembership.objects.get(project=self.existing_project, user=new_user).role, ROLE_PROJECT_MEMBER)

    def test_adding_user_that_is_already_in_project_is_a_no_op(self):
        """Test that adding a user that is already in the project is a no-op"""
        ProjectMembership.objects.create(
            project=self.existing_project,
            user=self.company_member,
            role=ROLE_PROJECT_ADMIN
        )
        self.client.force_authenticate(user=self.company_member)
        response = self.client.post(reverse('deliverables:project-members-add', kwargs={'pk': self.existing_project.id}), {
            'user_ids': [
                self.company_member.id
            ]
        })
        print(f"response.data: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(ProjectMembership.objects.filter(project=self.existing_project).count(), 1)
        self.assertEqual(ProjectMembership.objects.get(project=self.existing_project, user=self.company_member).role, ROLE_PROJECT_ADMIN)

    def test_project_admin_can_add_users_to_project_with_addition_endpoint(self):
        """Test that a company member can add users to a project with the addition endpoint"""
        ProjectMembership.objects.create(
            project=self.existing_project,
            user=self.company_member,
            role=ROLE_PROJECT_ADMIN
        )
        new_user = self.User.objects.create_user(
            username='new_user',
            password='password123'
        )
        TeamMembership.objects.create(
            user=new_user,
            team=self.team,
            role=ROLE_MEMBER
        )
        self.client.force_authenticate(user=self.company_member)
        response = self.client.post(reverse('deliverables:project-members-add', kwargs={'pk': self.existing_project.id}), {
            'user_ids': [
                new_user.id
            ]
        })
        print(f"response.data: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(ProjectMembership.objects.filter(project=self.existing_project, user=new_user).count(), 1)
        self.assertEqual(ProjectMembership.objects.get(project=self.existing_project, user=new_user).role, ROLE_PROJECT_MEMBER)

    def test_project_non_member_cannot_add_users_to_project_with_addition_endpoint(self):
        """Test that a user that is not a member of the project cannot add users to a project with the addition endpoint"""
        new_user = self.User.objects.create_user(
            username='new_user',
            password='password123'
        )
        TeamMembership.objects.create(
            user=new_user,
            team=self.team,
            role=ROLE_MEMBER
        )
        self.client.force_authenticate(user=self.company_member)
        response = self.client.post(reverse('deliverables:project-members-add', kwargs={'pk': self.existing_project.id}), {
            'user_ids': [
                new_user.id
            ]
        })
        print(f"response.data: {response.data}")
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
        self.superuser = self.User.objects.create_superuser(username='superuser', password='password123')
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
        response = self.client.post(reverse('deliverables:upload_file'), {
            'project_id': self.existing_project.id,
            'files': [self.mock_file],
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    @patch('apps.deliverables.views.invoke_lambda')
    def test_project_member_can_upload_file_to_their_project(self, mock_invoke_lambda):
        """Test that a project member can upload a file to their project"""
        ProjectMembership.objects.create(
            project=self.existing_project,
            user=self.company_member,
            role=ROLE_PROJECT_MEMBER
        )
        self.client.force_authenticate(user=self.company_member)
        response = self.client.post(reverse('deliverables:upload_file'), {
            'project_id': self.existing_project.id,
            'files': [self.mock_file],
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('apps.deliverables.views.invoke_lambda')
    def test_project_member_can_upload_upto_250_files_at_once(self, mock_invoke_lambda):
        """Test that a project member can upload a file to their project"""
        ProjectMembership.objects.create(
            project=self.existing_project,
            user=self.company_member,
            role=ROLE_PROJECT_MEMBER
        )
        self.client.force_authenticate(user=self.company_member)
        list_of_files = [SimpleUploadedFile(
            name=f'test_file_{i+1}.txt',
            content=b'This is some test file content',
            content_type='text/plain'
        ) for i in range(250)]
        
        start_time = time.perf_counter()
        response = self.client.post(reverse('deliverables:upload_file'), {
            'project_id': self.existing_project.id,
            'files': list_of_files,
        })
        end_time = time.perf_counter()
        duration = end_time - start_time
        print(f"Upload file request took {duration:.4f} seconds")
        print(f"response.data: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        list_of_files.append(SimpleUploadedFile(
            name='test_file_251.txt',
            content=b'This is some test file content',
            content_type='text/plain'
        ))
        too_many_files_response = self.client.post(reverse('deliverables:upload_file'), {
            'project_id': self.existing_project.id,
            'files': list_of_files,
        })
        self.assertEqual(too_many_files_response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('apps.deliverables.views.invoke_lambda')
    def test_company_admin_can_upload_file_to_project(self, mock_invoke_lambda):
        """Test that a company admin can upload a file to a project"""
        self.client.force_authenticate(user=self.company_admin)
        response = self.client.post(reverse('deliverables:upload_file'), {
            'project_id': self.existing_project.id,
            'files': [self.mock_file],
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('apps.deliverables.views.invoke_lambda')
    def test_superuser_can_upload_file_to_project(self, mock_invoke_lambda):
        """Test that a superuser can upload a file to a project"""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(reverse('deliverables:upload_file'), {
            'project_id': self.existing_project.id,
            'files': [self.mock_file],
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('apps.deliverables.views.invoke_lambda')
    def test_company_member_cannot_upload_file_to_project_they_are_not_a_member_of(self, mock_invoke_lambda):
        """Test that a company member cannot upload a file to a project they are not a member of"""
        self.client.force_authenticate(user=self.company_member)
        response = self.client.post(reverse('deliverables:upload_file'), {
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
        self.superuser = self.User.objects.create_superuser(username='superuser', password='password123')
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
        self.masterformat_section = MasterFormatSection.objects.create(masterformat_number='033000')

        self.submittal_item = SubmittalItem.objects.create(
            project=self.project,
            masterformat_section=self.masterformat_section,
            parsing_method='PLACEHOLDER',
        )
        self.document = UploadedFile.objects.create(
            project=self.project,
            uploaded_by=self.user,
            document_path='test_file.txt',
            md5='1234567890',
            processing_status=DocProcessingStatus.PROCESSED,
        )

    def test_user_can_see_submittal_items_for_their_project(self):
        """Test that users can see submittal items for their project"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse('submittal-item-list', kwargs={'project_id': self.project.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print(f"response.data: {response.data}")
        self.assertEqual(len(response.data['message']), 1)
        self.assertEqual(response.data['message'][0]['id'], self.submittal_item.id)

    def test_superuser_can_see_submittal_items_for_project(self):
        """Test that a superuser can see submittal items for a project"""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(reverse('submittal-item-list', kwargs={'project_id': self.project.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['message']), 1)
        self.assertEqual(response.data['message'][0]['id'], self.submittal_item.id)

    def test_user_cannot_see_submittal_items_for_other_projects(self):
        """Test that users cannot see submittal items for projects they are not a member of"""
        self.client.force_authenticate(user=self.non_member)
        response = self.client.get(reverse('submittal-item-list', kwargs={'project_id': self.project.id}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_submittal_item_list_returns_correct_parsing_method(self):
        """Test that the submittal item list returns the correct parsing method"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse('submittal-item-list', kwargs={'project_id': self.project.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'][0]['parsing_method'], 'PLACEHOLDER')

    def set_up_test_data(self):
        # Create MasterFormatSections
        mf1 = MasterFormatSection.objects.create(masterformat_number="033001")
        mf2 = MasterFormatSection.objects.create(masterformat_number="033002")
        mf3 = MasterFormatSection.objects.create(masterformat_number="033003")
        mf4 = MasterFormatSection.objects.create(masterformat_number="033004")
        
        # Create SpecSections with different processing methods
        spec1 = SpecSection.objects.create(
            masterformat_section=mf1,
            document=self.document,
            processing_method=SpecSection.ProcessingMethod.REGEX_UNABLE_TO_DETECT
        )
        spec2 = SpecSection.objects.create(
            masterformat_section=mf2,
            document=self.document,
            processing_method=SpecSection.ProcessingMethod.REGEX_SUCCESS
        )
        spec3 = SpecSection.objects.create(
            masterformat_section=mf3,
            document=self.document,
            processing_method=SpecSection.ProcessingMethod.REGEX_SUCCESS
        )
        spec4 = SpecSection.objects.create(
            masterformat_section=mf4,
            document=self.document,
            processing_method=SpecSection.ProcessingMethod.REGEX_UNABLE_TO_DETECT
        )

        # Create SubmittalItems in non-ordered sequence
        SubmittalItem.objects.create(
            project=self.project,
            document=self.document,
            masterformat_section=mf2,
            spec_section=spec2,
            paragraph_number="2.1",
            submittal_number="2",
            submittal_type="Shop Drawings"
        )
        SubmittalItem.objects.create(
            project=self.project,
            document=self.document,
            masterformat_section=mf1,
            spec_section=spec1,
            paragraph_number="1.1",
            submittal_number="1",
            submittal_type="Product Data"
        )
        SubmittalItem.objects.create(
            project=self.project,
            document=self.document,
            masterformat_section=mf1,
            spec_section=spec1,
            paragraph_number="1.2",
            submittal_number="3",
            submittal_type="Samples"
        )
        SubmittalItem.objects.create(
            project=self.project,
            document=self.document,
            masterformat_section=mf3,
            spec_section=spec3,
            paragraph_number="3.1",
            submittal_number="3",
            submittal_type="Samples"
        )
        SubmittalItem.objects.create(
            project=self.project,
            document=self.document,
            masterformat_section=mf4,
            spec_section=spec4,
            paragraph_number="4.1",
            submittal_number="4",
            submittal_type="Samples"
        )
        SubmittalItem.objects.create(
            project=self.project,
            document=self.document,
            masterformat_section=mf4,
            spec_section=spec4,
            paragraph_number="4.1",
            submittal_number="5",
            submittal_type="Samples"
        )

    def test_default_ordering(self):
        self.set_up_test_data()

        # Make API request
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse('submittal-item-list', kwargs={'project_id': self.project.id}))
        
        # Verify response status
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify ordering
        results = response.data['message']
        
        # Items should be ordered by:
        # 1. Processing method (REGEX_SUCCESS before AI_SUCCESS)
        # 2. Masterformat number (051200 before 052100)
        # 3. Hierarchical paragraph number (1.1 before 1.2)
        # 4. Submittal number (1 before 2 before 3)

        self.assertEqual(results[0]['spec_section'], "033000")
        self.assertEqual(results[0]['para_no'], '')
        self.assertEqual(results[0]['submittal_number'], None)
        
        print(f"results[1]: {results[1]}")
        self.assertEqual(results[1]['spec_section'], "033002")
        self.assertEqual(results[1]['para_no'], "2.1")
        self.assertEqual(results[1]['submittal_number'], "2.0")
        
        self.assertEqual(results[2]['spec_section'], "033003")
        self.assertEqual(results[2]['para_no'], "3.1")
        self.assertEqual(results[2]['submittal_number'], "3.0")

        self.assertEqual(results[3]['spec_section'], "033001")
        self.assertEqual(results[3]['para_no'], "1.1")
        self.assertEqual(results[3]['submittal_number'], "1.0")

        self.assertEqual(results[4]['spec_section'], "033001")
        self.assertEqual(results[4]['para_no'], "1.2")
        self.assertEqual(results[4]['submittal_number'], "3.0")

        self.assertEqual(results[5]['spec_section'], "033004")
        self.assertEqual(results[5]['para_no'], "4.1")
        self.assertEqual(results[5]['submittal_number'], "4.0")

        self.assertEqual(results[6]['spec_section'], "033004")
        self.assertEqual(results[6]['para_no'], "4.1")
        self.assertEqual(results[6]['submittal_number'], "5.0")

    def test_ordering_by_masterformat_number(self):
        self.set_up_test_data()

        # Make API request
        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            reverse('submittal-item-list', kwargs={'project_id': self.project.id}) + '?order_col=spec_section&order=asc'
        )
        
        # Verify response status
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify ordering
        results = response.data['message']
        
        # Items should be ordered by:
        # 1. Processing method (REGEX_SUCCESS before AI_SUCCESS)
        # 2. Masterformat number (051200 before 052100)
        # 3. Hierarchical paragraph number (1.1 before 1.2)
        # 4. Submittal number (1 before 2 before 3)

        self.assertEqual(results[0]['spec_section'], "033000")
        self.assertEqual(results[0]['para_no'], '')
        self.assertEqual(results[0]['submittal_number'], None)

        self.assertEqual(results[1]['spec_section'], "033001")
        self.assertEqual(results[1]['para_no'], "1.1")
        self.assertEqual(results[1]['submittal_number'], "1.0")

        self.assertEqual(results[2]['spec_section'], "033001")
        self.assertEqual(results[2]['para_no'], "1.2")
        self.assertEqual(results[2]['submittal_number'], "3.0")
        
        self.assertEqual(results[3]['spec_section'], "033002")
        self.assertEqual(results[3]['para_no'], "2.1")
        self.assertEqual(results[3]['submittal_number'], "2.0")
        
        self.assertEqual(results[4]['spec_section'], "033003")
        self.assertEqual(results[4]['para_no'], "3.1")
        self.assertEqual(results[4]['submittal_number'], "3.0")

        self.assertEqual(results[5]['spec_section'], "033004")
        self.assertEqual(results[5]['para_no'], "4.1")
        self.assertEqual(results[5]['submittal_number'], "4.0")

        self.assertEqual(results[6]['spec_section'], "033004")
        self.assertEqual(results[6]['para_no'], "4.1")
        self.assertEqual(results[6]['submittal_number'], "5.0")

    def test_ordering_by_masterformat_number_desc(self):
        self.set_up_test_data()

        # Make API request
        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            reverse('submittal-item-list', kwargs={'project_id': self.project.id}) + '?order_col=spec_section&order=desc'
        )
        
        # Verify response status
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify ordering
        results = response.data['message']
        
        # Items should be ordered by:
        # 1. Processing method (REGEX_SUCCESS before AI_SUCCESS)
        # 2. Masterformat number (051200 before 052100)
        # 3. Hierarchical paragraph number (1.1 before 1.2)
        # 4. Submittal number (1 before 2 before 3)

        self.assertEqual(results[0]['spec_section'], "033004")
        self.assertEqual(results[0]['para_no'], "4.1")
        self.assertEqual(results[0]['submittal_number'], "4.0")

        self.assertEqual(results[1]['spec_section'], "033004")
        self.assertEqual(results[1]['para_no'], "4.1")
        self.assertEqual(results[1]['submittal_number'], "5.0")

        self.assertEqual(results[2]['spec_section'], "033003")
        self.assertEqual(results[2]['para_no'], "3.1")
        self.assertEqual(results[2]['submittal_number'], "3.0")

        self.assertEqual(results[3]['spec_section'], "033002")
        self.assertEqual(results[3]['para_no'], "2.1")
        self.assertEqual(results[3]['submittal_number'], "2.0")

        self.assertEqual(results[4]['spec_section'], "033001")
        self.assertEqual(results[4]['para_no'], "1.1")
        self.assertEqual(results[4]['submittal_number'], "1.0")

        self.assertEqual(results[5]['spec_section'], "033001")
        self.assertEqual(results[5]['para_no'], "1.2")
        self.assertEqual(results[5]['submittal_number'], "3.0")

        self.assertEqual(results[6]['spec_section'], "033000")
        self.assertEqual(results[6]['para_no'], '')
        self.assertEqual(results[6]['submittal_number'], None)

    def test_submittal_item_list_returns_filter_values_in_correct_order(self):
        """Test that the submittal item list returns filter values in lexical order"""
        SubmittalItem.objects.create(
            project=self.project,
            masterformat_section=self.masterformat_section,
            paragraph_number='1.2',
        )
        SubmittalItem.objects.create(
            project=self.project,
            masterformat_section=self.masterformat_section,
            paragraph_number='1.1',
        )
        SubmittalItem.objects.create(
            project=self.project,
            masterformat_section=self.masterformat_section,
            paragraph_number='1.3-1',
        )
        SubmittalItem.objects.create(
            project=self.project,
            masterformat_section=self.masterformat_section,
            paragraph_number='1.3',
        )
        SubmittalItem.objects.create(
            project=self.project,
            masterformat_section=self.masterformat_section,
            paragraph_number='1.3-1',
            submittal_type='ZZZ',
            submittal_description='ZZZ',
        )

        SubmittalItem.objects.create(
            project=self.project,
            masterformat_section=MasterFormatSection.objects.create(masterformat_number='102000'),
            paragraph_number='1.3',
            submittal_type='Type 2',
            submittal_description='Description B',
        )
        
        SubmittalItem.objects.create(
            project=self.project,
            masterformat_section=MasterFormatSection.objects.create(masterformat_number='123456'),
            paragraph_number='1.3',
            submittal_type='Type 1',
            submittal_description='Description A',
        )
        SubmittalItem.objects.create(
            project=self.project,
            masterformat_section=MasterFormatSection.objects.create(masterformat_number='033001'),
            paragraph_number='1.3',
            submittal_type='Type 1',
            submittal_description='Description A',
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse('submittal-item-list', kwargs={'project_id': self.project.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(list(response.data['all_filter_vals']['item_desc']), ['Description A', 'Description B', 'ZZZ'])
        self.assertEqual(list(response.data['all_filter_vals']['para_no']), ['1.1', '1.2', '1.3', '1.3-1'])
        self.assertEqual(list(response.data['all_filter_vals']['spec_section']), ['033000', '033001', '102000', '123456'])
        self.assertEqual(list(response.data['all_filter_vals']['type']), ['Type 1', 'Type 2', 'ZZZ'])

    def test_create_submittal_with_new_masterformat_section_number(self):
        self.client.force_authenticate(user=self.user)
        post_payload = {
            'document': self.document.id,
            'spec_section': "111111",  # new spec section
            'item_desc': "Test",
            'para_context': "Test context",
            'para_no': "1.1",
            'type': "Test type",
        }
        self.assertEqual(0, len(SubmittalItem.objects.filter(masterformat_section__masterformat_number="111111")))
        response = self.client.post(reverse('submittal-item-list', kwargs={'project_id': self.project.id}), post_payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, len(SubmittalItem.objects.filter(masterformat_section__masterformat_number="111111")))



class ProjectArchiveTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.User = get_user_model()

        self.user = self.User.objects.create_user(username='user1', password='password123')
        self.client.force_authenticate(user=self.user)
        self.admin_user = self.User.objects.create_user(username='admin_user', password='adminpass')
        self.superuser = self.User.objects.create_superuser(username='superuser', password='password123')
        self.client.force_authenticate(user=self.admin_user)

        self.team = Team.objects.create(name='Team 1', slug='team-1')
        TeamMembership.objects.create(
            user=self.user,
            team=self.team,
            role=ROLE_MEMBER
        )

        self.project = Project.objects.create(
            name='Project 1',
            team=self.team,
            is_archived=False,
        )

        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ROLE_PROJECT_MEMBER 
        )

        TeamMembership.objects.create(
            user=self.admin_user,
            team=self.team,
            role=ROLE_ADMIN
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.admin_user,
            role=ROLE_ADMIN
        )

        self.team_id = self.team.id

    def test_archive_project_by_admin(self):
        """Test that an admin can archive a project."""
        self.client.force_authenticate(user=self.admin_user)

        url = reverse('deliverables:project-archive', args=[self.project.id])
        response = self.client.post(url, data={'action': 'archive', 'team': self.team_id})
        self.project.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(self.project.is_archived)
        self.assertIn("Project archived successfully.", response.data["status"])

    def test_restore_project_by_admin(self):
        """Test that an admin can restore an archived project."""
        self.project.is_archived = True
        self.project.save()

        self.client.force_authenticate(user=self.admin_user)

        url = reverse('deliverables:project-archive', args=[self.project.id])
        response = self.client.post(url, data={'action': 'restore', 'team': self.team_id})
        self.project.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(self.project.is_archived)
        self.assertIn("Project unarchived successfully.", response.data["status"])

    def test_superuser_can_archive_project(self):
        """Test that a superuser can archive a project"""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(reverse('deliverables:project-archive', args=[self.project.id]), data={'action': 'archive', 'team': self.team_id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertTrue(self.project.is_archived)

    def test_superuser_can_restore_project(self):
        """Test that a superuser can restore an archived project"""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(reverse('deliverables:project-archive', args=[self.project.id]), data={'action': 'restore', 'team': self.team_id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertFalse(self.project.is_archived)

    def test_archive_project_by_member(self):
        """Test that a regular member cannot archive a project."""
        self.client.force_authenticate(user=self.user)

        url = reverse('deliverables:project-archive', args=[self.project.id])
        response = self.client.post(url, data={'action': 'archive', 'team': self.team_id})
        self.project.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(self.project.is_archived) 


class SubmittalItemListViewSetTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.User = get_user_model()
        self.team_member = self.User.objects.create_user(username='team_member', password='password123')
        self.superuser = self.User.objects.create_superuser(username='superuser', password='password123')
        self.team = Team.objects.create(name='Team 1', slug='team-1')
        TeamMembership.objects.create(
            user=self.team_member,
            team=self.team,
            role=ROLE_MEMBER
        )

        self.project = Project.objects.create(
            name='Project 1',
            team=self.team,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.team_member,
            role=ROLE_PROJECT_MEMBER
        )

        self.other_project = Project.objects.create(
            name='Project 2',
            team=self.team,
        )

        self.submittal_item_list = SubmittalItemList.objects.create(
            name='Submittal Item List 1',
            project=self.project,
        )

        self.submittal_item_in_list = SubmittalItem.objects.create(
            project=self.project,
            masterformat_section=MasterFormatSection.objects.create(masterformat_number='033000'),
        )
        self.submittal_item_in_list.submittal_lists.add(self.submittal_item_list)

        self.submittal_item_not_in_list = SubmittalItem.objects.create(
            project=self.project,
            masterformat_section=MasterFormatSection.objects.create(masterformat_number='033001'),
        )

    def test_team_member_can_see_submittal_lists_for_their_project(self):
        """Test that a team member can see submittal lists for their project"""
        self.client.force_authenticate(user=self.team_member)
        response = self.client.get(reverse('submittal-list-list', kwargs={'project_id': self.project.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['id'], self.submittal_item_list.id)
        self.assertEqual(len(response.data['results'][0]['submittals']), 1)
        self.assertEqual(response.data['results'][0]['submittals'][0], self.submittal_item_in_list.id)

    def test_superuser_can_see_submittal_lists_for_project(self):
        """Test that a superuser can see submittal lists for a project"""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(reverse('submittal-list-list', kwargs={'project_id': self.project.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['id'], self.submittal_item_list.id)

    def test_team_member_cannot_see_submittal_lists_for_other_projects(self):
        """Test that a team member cannot see submittal lists for other projects"""
        self.client.force_authenticate(user=self.team_member)
        response = self.client.get(reverse('submittal-list-list', kwargs={'project_id': self.other_project.id}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_team_member_can_create_submittal_list(self):
        """Test that a team member can create a submittal list"""
        self.client.force_authenticate(user=self.team_member)
        response = self.client.post(reverse(
            'submittal-list-list',
            kwargs={'project_id': self.project.id}), 
            data={'name': 'New Submittal Item List', 'submittals': [self.submittal_item_in_list.id]}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_superuser_can_create_submittal_list(self):
        """Test that a superuser can create a submittal list"""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(reverse(
            'submittal-list-list',
            kwargs={'project_id': self.project.id}), 
            data={'name': 'New Submittal Item List', 'submittals': [self.submittal_item_in_list.id]}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_team_member_created_by_is_set_automatically(self):
        """Test that the created_by field is set automatically"""
        self.client.force_authenticate(user=self.team_member)
        response = self.client.post(reverse('submittal-list-list', kwargs={'project_id': self.project.id}), data={'name': 'New Submittal Item List', 'project_id': self.project.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['created_by'], self.team_member.id)


class TestCombineRows(APITestCase):
    def setUp(self):
        # Create test user
        self.user = get_user_model().objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.superuser = get_user_model().objects.create_superuser(username='superuser', password='password123')
        self.team = Team.objects.create(name='Team 1', slug='team-1')
        TeamMembership.objects.create(
            user=self.user,
            team=self.team,
            role=ROLE_MEMBER
        )
        self.client.force_authenticate(user=self.user)
        
        # Create test project
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ROLE_PROJECT_MEMBER
        )
        self.masterformat_section = MasterFormatSection.objects.create(masterformat_number='033000')
        
        # Create test submittal items
        self.submittal_items = []
        for i in range(3):
            item = SubmittalItem.objects.create(
                project=self.project,
                masterformat_section=self.masterformat_section,
                submittal_description=f'Test Description {i}',
                submittal_type=f'Type {i}',
                submittal_content=f'Content {i}',
                text_location={'page': i},
                additional_text_locations=[{'section': f'S{i}'}]
            )
            self.submittal_items.append(item)

    def test_successful_combine(self):
        """Test successful combination of submittal items"""
        url = reverse('deliverables:combine_rows')
        data = {
            'project_id': self.project.id,
            'lst_all_logs': [
                {
                    'id': self.submittal_items[0].id,
                    'spec_section': 'Section A',
                    'index': 0
                },
                {
                    'id': self.submittal_items[1].id,
                    'spec_section': 'Section B',
                    'index': 1
                }
            ],
            'prepared_object': {
                'item_desc': 'Combined Description',
                'type': 'Combined Type'
            }
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Rows combined')
        
        # Verify first item was updated
        first_item = SubmittalItem.objects.get(id=self.submittal_items[0].id)
        self.assertEqual(first_item.submittal_description, 'Combined Description')
        self.assertEqual(first_item.submittal_type, 'Combined Type')
        self.assertEqual(first_item.additional_text_locations, [{'section': 'S0'}, {'page': 1}, {'section': 'S1'}])
        self.assertEqual(first_item.submittal_content, 'Content 0\nContent 1')

        # Verify second item was deleted
        with self.assertRaises(SubmittalItem.DoesNotExist):
            SubmittalItem.objects.get(id=self.submittal_items[1].id)

    def test_superuser_can_combine_rows(self):
        """Test that a superuser can combine rows"""
        url = reverse('deliverables:combine_rows')
        data = {
            'project_id': self.project.id,
            'lst_all_logs': [
                {
                    'id': self.submittal_items[0].id,
                    'spec_section': 'Section A',
                    'index': 0
                },
                {
                    'id': self.submittal_items[1].id,
                    'spec_section': 'Section B',
                    'index': 1
                }
            ],
            'prepared_object': {
                'item_desc': 'Combined Description',
                'type': 'Combined Type'
            }
        }
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unauthorized_user(self):
        """Test unauthorized user cannot combine rows"""
        # Create new user not in project
        unauthorized_user = get_user_model().objects.create_user(
            username='unauthorized',
            password='testpass123'
        )
        self.client.force_authenticate(user=unauthorized_user)
        
        url = reverse('deliverables:combine_rows')
        data = {
            'project_id': self.project.id,
            'lst_all_logs': [
                {'id': self.submittal_items[0].id, 'spec_section': 'A', 'index': 0}
            ],
            'prepared_object': {
                'item_desc': 'Test',
                'type': 'Test'
            }
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_log_id(self):
        """Test combining with non-existent log ID"""
        url = reverse('deliverables:combine_rows')
        data = {
            'project_id': self.project.id,
            'lst_all_logs': [
                {'id': 99999, 'spec_section': 'A', 'index': 0}
            ],
            'prepared_object': {
                'item_desc': 'Test',
                'type': 'Test'
            }
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'Log ID not found')

    def test_combine_with_text_locations(self):
        """Test combining items preserves text locations correctly"""
        url = reverse('deliverables:combine_rows')
        data = {
            'project_id': self.project.id,
            'lst_all_logs': [
                {
                    'id': self.submittal_items[0].id,
                    'spec_section': 'A',
                    'index': 0
                },
                {
                    'id': self.submittal_items[1].id,
                    'spec_section': 'B',
                    'index': 1
                },
                {
                    'id': self.submittal_items[2].id,
                    'spec_section': 'C',
                    'index': 2
                }
            ],
            'prepared_object': {
                'item_desc': 'Combined',
                'type': 'Combined'
            }
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify text locations for the items joined to the first item are preserved
        # in additional_text_locations
        combined_item = SubmittalItem.objects.get(id=self.submittal_items[0].id)
        self.assertIn({'page': 1}, combined_item.additional_text_locations)
        self.assertIn({'section': 'S1'}, combined_item.additional_text_locations)
        self.assertIn({'page': 2}, combined_item.additional_text_locations)
        self.assertIn({'section': 'S2'}, combined_item.additional_text_locations)