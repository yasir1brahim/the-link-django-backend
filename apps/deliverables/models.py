from django.db import models
from apps.utils.models import BaseModel
from django.conf import settings


class Project(BaseModel):
    PROJECT_STATUS_OPEN = "open"
    PROJECT_STATUS_CLOSED = "closed"
    PROJECT_STATUS_CHOICES = (
        (PROJECT_STATUS_OPEN, "Open"),
        (PROJECT_STATUS_CLOSED, "Closed"),
    )

    legacy_id = models.IntegerField(blank=True, null=True)

    name = models.CharField(max_length=256)
    description = models.TextField(blank=True)
    team = models.ForeignKey("teams.Team", on_delete=models.CASCADE)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_projects", blank=True, null=True)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="projects", through="ProjectMembership")

    is_archived = models.BooleanField(default=False)
    status = models.CharField(max_length=256, choices=PROJECT_STATUS_CHOICES, default=PROJECT_STATUS_OPEN)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    procore_id = models.IntegerField(blank=True, null=True)
    procore_name = models.CharField(max_length=256, blank=True, null=True)
    procore_submittal_manager_id = models.CharField(max_length=256, blank=True, null=True)
    procore_submittal_manager_name = models.CharField(max_length=256, blank=True, null=True)

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
    project = models.ForeignKey("Project", on_delete=models.CASCADE, related_name="project_memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="project_memberships")
    role = models.CharField(max_length=256, choices=PROJECT_MEMBERSHIP_ROLE_CHOICES)

    class Meta:
        # Ensure a user can only be associated with a project once.
        unique_together = ("project", "user")


class Entitlement(BaseModel):
    """
    An entitlement is a feature or resource that a user or project can have access to.
    """
    code_name = models.CharField(max_length=256)
    readable_name = models.CharField(max_length=256)
    description = models.TextField(blank=True)
    
    def __str__(self):
        return self.readable_name
    

class UploadedFile(BaseModel):
    legacy_id = models.IntegerField(blank=True, null=True)

    project = models.ForeignKey("Project", on_delete=models.CASCADE)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, blank=True, null=True)

    document_path = models.CharField(max_length=256)
    parsed_document_path = models.CharField(max_length=256, blank=True, null=True)
    name = models.CharField(max_length=256)
    md5 = models.CharField(max_length=256)
    processing_status = models.CharField(max_length=256)


    def __str__(self):
        return self.document_path


class MasterFormatSection(BaseModel):
    masterformat_number = models.CharField(max_length=256, unique=True)
    masterformat_description = models.CharField(max_length=256, blank=True, null=True)

    def __str__(self):
        return f"{self.masterformat_number}"


class SpecSection(BaseModel):
    masterformat_section = models.ForeignKey("MasterFormatSection", on_delete=models.CASCADE)
    document = models.ForeignKey("UploadedFile", on_delete=models.CASCADE)
    processing_status = models.CharField(max_length=256, blank=True, null=True)

    def __str__(self):
        return f"{self.document.name} - {self.masterformat_section.masterformat_number}"


class SavedSubmittalItemList(BaseModel):
    name = models.CharField(max_length=256)
    description = models.TextField(blank=True)
    project = models.ForeignKey("Project", on_delete=models.CASCADE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    submittal_items = models.ManyToManyField("SubmittalItem", blank=True)

    def __str__(self):
        return self.name


class SubmittalItem(BaseModel):
    legacy_id = models.IntegerField(blank=True, null=True)
    legacy_updated_at = models.DateTimeField(blank=True, null=True)

    project = models.ForeignKey("Project", on_delete=models.CASCADE)
    document = models.ForeignKey("UploadedFile", on_delete=models.CASCADE)
    spec_section = models.ForeignKey("SpecSection", on_delete=models.CASCADE)
    paragraph_number = models.CharField(max_length=256)
    submittal_type = models.CharField(max_length=256)
    submittal_description = models.CharField(max_length=256)
    submittal_content = models.TextField()

    submittal_number = models.DecimalField(max_digits=10, decimal_places=1, blank=True, null=True)

    text_location = models.JSONField(blank=True, null=True)
    additional_text_locations = models.JSONField(blank=True, null=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_submittal_items", blank=True, null=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="updated_submittal_items", blank=True, null=True)

    procore_submittal_id = models.CharField(max_length=256, blank=True, null=True)
    procore_export_date = models.DateTimeField(blank=True, null=True)

    parsing_method = models.CharField(max_length=256)
    parsing_version = models.CharField(max_length=256)


    def __str__(self):
        return f"{self.document.name} - {self.spec_section.masterformat_section.masterformat_number} - {self.paragraph_number}: {self.submittal_description}"
    
class SubmittalItemList(BaseModel):
    name = models.CharField(max_length=256)
    description = models.TextField(blank=True)
    project = models.ForeignKey("Project", on_delete=models.CASCADE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, blank=True, null=True)
    submittals = models.ManyToManyField("SubmittalItem", blank=True)

    def __str__(self):
        return self.name