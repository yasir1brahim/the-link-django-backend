from django.db import models
from apps.utils.models import BaseModel
from django.conf import settings


class Project(BaseModel):
    name = models.CharField(max_length=256)
    description = models.TextField(blank=True)
    team = models.ForeignKey("teams.Team", on_delete=models.CASCADE)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="projects", through="ProjectMembership")

    entitlements = models.ManyToManyField("Entitlement", blank=True)

    user_limit = models.IntegerField(default=None, null=True, blank=True)

    def __str__(self):
        return self.name


ROLE_PROJECT_ADMIN = "project_admin"
ROLE_PROJECT_MEMBER = "project_member"
ROLE_PROJECT_EXTERNAL_USER = "project_external_user"

PROJECT_MEMBERSHIP_ROLE_CHOICES = (
    # customize roles here
    (ROLE_PROJECT_ADMIN, "Project Administrator"),
    (ROLE_PROJECT_MEMBER, "Project Member"),
    (ROLE_PROJECT_EXTERNAL_USER, "Project External User"),
)

class ProjectMembership(BaseModel):
    project = models.ForeignKey("Project", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=256, choices=PROJECT_MEMBERSHIP_ROLE_CHOICES)


class Entitlement(BaseModel):
    """
    An entitlement is a feature or resource that a user or project can have.
    """
    code_name = models.CharField(max_length=256)
    readable_name = models.CharField(max_length=256)
    description = models.TextField(blank=True)
    
    def __str__(self):
        return self.readable_name