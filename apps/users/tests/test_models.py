from django.test import TestCase

from apps.users.models import CustomUser
from apps.deliverables.models import Project, ProjectMembership, ROLE_PROJECT_ADMIN, ROLE_PROJECT_MEMBER
from apps.teams.models import Team, Membership as TeamMembership
from apps.teams.roles import ROLE_ADMIN, ROLE_MEMBER


class CustomUserModelTest(TestCase):
    def setUp(self):
        self.team_admin = CustomUser.objects.create(
            username="team_admin",
            first_name="Team",
            last_name="Admin"
        )
        self.team_member = CustomUser.objects.create(
            username="team_member",
            first_name="Team",
            last_name="Member"
        )
        self.team_member_not_project_member = CustomUser.objects.create(
            username="team_member_not_project_member",
            first_name="Team",
            last_name="Member Not Project Member"
        )
        self.project_admin_not_team_admin = CustomUser.objects.create(
            username="project_admin_not_team_admin",
            first_name="Project",
            last_name="Admin Not Team Admin"
        )
        self.not_team_member = CustomUser.objects.create(
            username="not_team_member",
            first_name="Not",
            last_name="Team Member"
        )
        self.team = Team.objects.create(
            name="Test Team"
        )

        TeamMembership.objects.create(
            user=self.team_admin,
            team=self.team,
            role=ROLE_ADMIN
        )
        TeamMembership.objects.create(
            user=self.team_member,
            team=self.team,
            role=ROLE_MEMBER
        )
        TeamMembership.objects.create(
            user=self.team_member_not_project_member,
            team=self.team,
            role=ROLE_MEMBER
        )
        TeamMembership.objects.create(
            user=self.project_admin_not_team_admin,
            team=self.team,
            role=ROLE_MEMBER
        )

        self.project = Project.objects.create(
            name="Test Project",
            description="Test Description",
            team=self.team
        )
        ProjectMembership.objects.create(
            user=self.project_admin_not_team_admin,
            project=self.project,
            role=ROLE_PROJECT_ADMIN
        )
        ProjectMembership.objects.create(
            user=self.team_member,
            project=self.project,
            role=ROLE_PROJECT_MEMBER
        )

    
    def test_is_admin_for_team(self):
        self.assertTrue(self.team_admin.is_admin_for_team(self.team))
        self.assertFalse(self.project_admin_not_team_admin.is_admin_for_team(self.team))
        self.assertFalse(self.team_member.is_admin_for_team(self.team))
        self.assertFalse(self.not_team_member.is_admin_for_team(self.team))
        self.assertFalse(self.team_member_not_project_member.is_admin_for_team(self.team))

    def test_is_member_of_team(self):
        self.assertTrue(self.team_admin.is_member_of_team(self.team))
        self.assertTrue(self.project_admin_not_team_admin.is_member_of_team(self.team))
        self.assertTrue(self.team_member.is_member_of_team(self.team))
        self.assertFalse(self.not_team_member.is_member_of_team(self.team))
        self.assertTrue(self.team_member_not_project_member.is_member_of_team(self.team))

    def test_is_admin_for_project(self):
        # Team admins are admins for all projects
        self.assertTrue(self.team_admin.is_admin_for_project(self.project))

        self.assertTrue(self.project_admin_not_team_admin.is_admin_for_project(self.project))
        self.assertFalse(self.team_member.is_admin_for_project(self.project))
        self.assertFalse(self.not_team_member.is_admin_for_project(self.project))
        self.assertFalse(self.team_member_not_project_member.is_admin_for_project(self.project))


    def test_is_member_of_project(self):
        # Team admins are members of all projects
        self.assertTrue(self.team_admin.is_member_of_project(self.project))

        self.assertTrue(self.project_admin_not_team_admin.is_member_of_project(self.project))
        self.assertTrue(self.team_member.is_member_of_project(self.project))
        self.assertFalse(self.not_team_member.is_member_of_project(self.project))
        self.assertFalse(self.team_member_not_project_member.is_member_of_project(self.project))