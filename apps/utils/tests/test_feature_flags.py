from django.conf import settings
from django.test import TestCase

from apps.users.models import CustomUser
from apps.teams.models import Team, Flag
from apps.utils.feature_flags import is_notices_feature_flag_active


class FeatureFlagsTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(username="test", password="test")
        self.team = Team.objects.create(name="test")
        self.team.members.add(self.user)
        self.flag: Flag = Flag.objects.create(name=settings.NOTICES_FEATURE_FLAG_NAME)

    def test_is_notices_feature_flag_active_returns_false_when_not_set(self):
        self.assertFalse(is_notices_feature_flag_active(self.user, self.team))
    
    def test_is_notices_feature_flag_active_returns_true_when_set_for_superusers(self):
        self.user.is_superuser = True
        self.user.save()
        self.flag.superusers = True
        self.flag.save()
        self.assertTrue(is_notices_feature_flag_active(self.user, self.team))
        self.user.is_superuser = False
        self.user.save()
        self.assertFalse(is_notices_feature_flag_active(self.user, self.team))

    def test_is_notices_feature_flag_active_returns_true_when_set_active_for_user(self):
        self.assertFalse(is_notices_feature_flag_active(self.user, self.team))
        self.flag.users.add(self.user)
        self.flag.save()
        self.assertTrue(is_notices_feature_flag_active(self.user, self.team))

    def test_is_notices_feature_flag_active_returns_true_when_set_active_for_team(self):
        self.assertFalse(is_notices_feature_flag_active(self.user, self.team))
        self.flag.teams.add(self.team)
        self.flag.save()
        self.assertTrue(is_notices_feature_flag_active(self.user, self.team))

    def test_is_notices_feature_flag_active_returns_true_when_set_active_for_user_and_team(self):
        self.assertFalse(is_notices_feature_flag_active(self.user, self.team))
        self.flag.users.add(self.user)
        self.flag.teams.add(self.team)
        self.flag.save()
        self.assertTrue(is_notices_feature_flag_active(self.user, self.team))
