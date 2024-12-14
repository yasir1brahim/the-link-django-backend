from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from apps.teams.models import Team, Membership as TeamMembership
from apps.teams.roles import ROLE_ADMIN, ROLE_MEMBER
from apps.deliverables.models import Project, ProjectMembership, SubmittalItemList, SubmittalItem, MasterFormatSection, ROLE_PROJECT_ADMIN, ROLE_PROJECT_MEMBER
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
        response = self.client.put(reverse('deliverables:project-detail', kwargs={'pk': self.existing_project.id}), {
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
        response = self.client.put(reverse('deliverables:project-detail', kwargs={'pk': self.existing_project.id}), {
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
        response = self.client.put(reverse('deliverables:project-detail', kwargs={'pk': self.existing_project.id}), {
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
        response = self.client.put(reverse('deliverables:project-detail', kwargs={'pk': self.existing_project.id}), {
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

    def test_project_member_can_upload_file_to_their_project(self):
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

    def test_company_admin_can_upload_file_to_project(self):
        """Test that a company admin can upload a file to a project"""
        self.client.force_authenticate(user=self.company_admin)
        response = self.client.post(reverse('deliverables:upload_file'), {
            'project_id': self.existing_project.id,
            'files': [self.mock_file],
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_superuser_can_upload_file_to_project(self):
        """Test that a superuser can upload a file to a project"""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(reverse('deliverables:upload_file'), {
            'project_id': self.existing_project.id,
            'files': [self.mock_file],
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_company_member_cannot_upload_file_to_project_they_are_not_a_member_of(self):
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