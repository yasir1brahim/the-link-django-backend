from django.conf import settings
from django.test import TestCase

from apps.users.models import CustomUser
from apps.teams.models import Team, Flag
from apps.deliverables.models import Project
from apps.utils.feature_flags import is_drawings_feature_flag_active


class DrawingsFeatureFlagTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(username="test", password="test")
        self.team = Team.objects.create(name="test", slug="test-team")
        self.team.members.add(self.user)
        self.project = Project.objects.create(
            name="Test Project",
            project_number="P-001",
            team=self.team,
            created_by=self.user
        )
        self.flag: Flag = Flag.objects.create(name=settings.DRAWINGS_FEATURE_FLAG_NAME)

    def test_is_drawings_feature_flag_active_returns_false_when_not_set(self):
        self.assertFalse(is_drawings_feature_flag_active(self.user, self.team, self.project))

    def test_is_drawings_feature_flag_active_returns_true_when_set_for_superusers(self):
        self.user.is_superuser = True
        self.user.save()
        self.flag.superusers = True
        self.flag.save()
        self.assertTrue(is_drawings_feature_flag_active(self.user, self.team, self.project))
        self.user.is_superuser = False
        self.user.save()
        self.assertFalse(is_drawings_feature_flag_active(self.user, self.team, self.project))

    def test_is_drawings_feature_flag_active_returns_true_when_set_for_user(self):
        self.assertFalse(is_drawings_feature_flag_active(self.user, self.team, self.project))
        self.flag.users.add(self.user)
        self.flag.save()
        self.assertTrue(is_drawings_feature_flag_active(self.user, self.team, self.project))

    def test_is_drawings_feature_flag_active_returns_true_when_set_for_team(self):
        self.assertFalse(is_drawings_feature_flag_active(self.user, self.team, self.project))
        self.flag.teams.add(self.team)
        self.flag.save()
        self.assertTrue(is_drawings_feature_flag_active(self.user, self.team, self.project))

    def test_is_drawings_feature_flag_active_returns_true_when_set_for_project(self):
        self.assertFalse(is_drawings_feature_flag_active(self.user, self.team, self.project))
        self.flag.projects.add(self.project)
        self.flag.save()
        self.assertTrue(is_drawings_feature_flag_active(self.user, self.team, self.project))
