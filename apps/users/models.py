import hashlib
import uuid
from functools import cached_property

from allauth.account.models import EmailAddress
from django.contrib.auth.models import AbstractUser
from django.db import models
from djstripe.models import Customer

from apps.users.helpers import validate_profile_picture


def _get_avatar_filename(instance, filename):
    """Use random filename prevent overwriting existing files & to fix caching issues."""
    return f'profile-pictures/{uuid.uuid4()}.{filename.split(".")[-1]}'


class CustomUser(AbstractUser):
    """
    Add additional fields to the user model here.
    """

    legacy_id = models.IntegerField(blank=True, null=True)
    legacy_role_id = models.IntegerField(blank=True, null=True)

    avatar = models.FileField(upload_to=_get_avatar_filename, blank=True, validators=[validate_profile_picture])
    language = models.CharField(max_length=10, blank=True, null=True)
    timezone = models.CharField(max_length=100, blank=True, default="")
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"{self.get_full_name()} <{self.email or self.username}>"

    def get_display_name(self) -> str:
        if self.get_full_name().strip():
            return self.get_full_name()
        return self.email or self.username

    @property
    def avatar_url(self) -> str:
        if self.avatar:
            return self.avatar.url
        else:
            return "https://www.gravatar.com/avatar/{}?s=128&d=identicon".format(self.gravatar_id)

    @property
    def gravatar_id(self) -> str:
        # https://en.gravatar.com/site/implement/hash/
        return hashlib.md5(self.email.lower().strip().encode("utf-8")).hexdigest()

    @cached_property
    def has_verified_email(self):
        return EmailAddress.objects.filter(user=self, verified=True).exists()
    
    def is_admin_for_team(self, team):
        from apps.teams.roles import ROLE_ADMIN
        return self.teams.through.objects.filter(user=self, team=team, role=ROLE_ADMIN).exists()
    
    def is_member_of_team(self, team):
        return self.teams.filter(id=team.id).exists()
    
    def is_admin_for_project(self, project):
        from apps.deliverables.models import ROLE_PROJECT_ADMIN, Project
        if isinstance(project, int):
            project = Project.objects.get(id=project)
        if self.is_admin_for_team(project.team):
            return True
        return self.projects.through.objects.filter(user=self, project=project, role=ROLE_PROJECT_ADMIN).exists()
    
    def is_member_of_project(self, project):
        from apps.deliverables.models import Project
        if isinstance(project, int):
            project = Project.objects.get(id=project)
        if self.is_admin_for_team(project.team):
            return True
        return self.projects.filter(id=project.id).exists()
