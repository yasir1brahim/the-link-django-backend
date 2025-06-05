import uuid
from enum import Enum
from datetime import datetime, timedelta, timezone
from typing import List

from django.db import models
from apps.utils.models import BaseModel
from django.conf import settings
from langchain.schema.messages import BaseMessage, AIMessage, _message_to_dict, messages_from_dict
from langchain.schema import BaseChatMessageHistory


class Project(BaseModel):
    legacy_id = models.IntegerField(blank=True, null=True)

    name = models.CharField(max_length=256)
    project_number = models.CharField(max_length=256)
    project_type = models.CharField(max_length=256, blank=True, null=True)
    description = models.TextField(blank=True)
    team = models.ForeignKey("teams.Team", on_delete=models.CASCADE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_projects", blank=True, null=True)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="projects", through="ProjectMembership")
    
    is_archived = models.BooleanField(default=False)
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
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            ProjectVersion.objects.create(
                project=self,
                version_number=1,
                version_name=f"Version 1",
                created_by=self.created_by,
            )
    

class ProjectVersion(BaseModel):
    project = models.ForeignKey("Project", on_delete=models.CASCADE, related_name="versions")
    is_archived = models.BooleanField(default=False)
    version_number = models.PositiveSmallIntegerField(blank=True, null=True)
    version_name = models.CharField(max_length=256, blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="created_project_versions", blank=True, null=True)
    last_updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="updated_project_versions", blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['project', 'version_number'], name='unique_project_version_number'),
            models.UniqueConstraint(fields=['project', 'version_name'], name='unique_project_version_name'),
        ]
        ordering = ['created_at']

    def __str__(self):
        return f"{self.project.name} - {self.version_number}: {self.version_name}"


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
    


class DocProcessingStatus(str, Enum):
    PENDING_PROCESSING = "PENDING_PROCESSING"
    PROCESSING = "PROCESSING"
    SUBSECTIONS_EXTRACTED = "SUBSECTIONS_EXTRACTED"
    PROCESSED = "PROCESSED"
    PROCESSED_SECTION = "PROCESSED_SECTION"
    SECTION_PROCESSING_FAILED = "SECTION_PROCESSING_FAILED"
    FAILED = "FAILED"
    

class UploadedFile(BaseModel):
    class ProcessingMethodChoices(models.TextChoices):
        V1 = "V1", "V1"
        V2 = "V2", "V2"
        FULL_SPEC_PROCESSING = "FULL_SPEC_PROCESSING", "Full Spec Processing"

    class SpecgptProcessingStatusChoices(models.TextChoices):
        UPLOADING = "UPLOADING", "Uploading"
        IN_QUEUE = "IN_QUEUE", "In Queue"
        PROCESSING = "PROCESSING", "Processing"
        PROCESSED = "PROCESSED", "Processed"
        FAILED = "FAILED", "Failed"
        NONE = "NONE", "None"

    legacy_id = models.IntegerField(blank=True, null=True)

    project = models.ForeignKey("Project", on_delete=models.CASCADE)
    project_version = models.ForeignKey("ProjectVersion", on_delete=models.CASCADE)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, blank=True, null=True)

    document_path = models.CharField(max_length=256)
    parsed_document_path = models.CharField(max_length=256, blank=True, null=True)
    name = models.CharField(max_length=256)
    md5 = models.CharField(max_length=256)
    processing_status = models.CharField(max_length=256)
    processing_method = models.CharField(max_length=256, choices=ProcessingMethodChoices.choices, default=ProcessingMethodChoices.V1)
    
    last_retry = models.DateTimeField(blank=True, null=True)

    specgpt_embedding_enabled = models.BooleanField(default=False)
    specgpt_processing_status = models.CharField(max_length=256, choices=SpecgptProcessingStatusChoices.choices, default=SpecgptProcessingStatusChoices.NONE)

    def __str__(self):
        return self.document_path


class MasterFormatSection(BaseModel):
    masterformat_number = models.CharField(max_length=256, unique=True)
    masterformat_description = models.CharField(max_length=256, blank=True, null=True)

    def __str__(self):
        return f"{self.masterformat_number}"


class SpecSection(BaseModel):
    class ProcessingMethod(models.TextChoices):
        REGEX_UNABLE_TO_DETECT = 'REGEX_UNABLE_TO_DETECT_SUBMITTALS', 'Regex Unable to Detect Submittals'
        REGEX_SUCCESS = 'REGEX_SUCCESS', 'Regex Success'

        @classmethod
        def get_order(cls):
            return {
                cls.REGEX_SUCCESS: 1,
                cls.REGEX_UNABLE_TO_DETECT: 2,
            }
    masterformat_section = models.ForeignKey("MasterFormatSection", on_delete=models.CASCADE)
    document = models.ForeignKey("UploadedFile", on_delete=models.CASCADE)
    processing_status = models.CharField(max_length=256, blank=True, null=True)
    processing_method = models.CharField(max_length=256, blank=True, null=True, choices=ProcessingMethod.choices)
    specgpt_embedding_status = models.CharField(max_length=256, blank=True, null=True, choices=UploadedFile.SpecgptProcessingStatusChoices.choices)
    file_s3_key = models.CharField(max_length=1024, blank=True, null=True)

    def __str__(self):
        return f"{self.document.name} - {self.masterformat_section.masterformat_number}"


class BaseSpecItem(BaseModel):
    project = models.ForeignKey("Project", on_delete=models.CASCADE)
    project_version = models.ForeignKey("ProjectVersion", on_delete=models.CASCADE)
    document = models.ForeignKey("UploadedFile", on_delete=models.CASCADE, blank=True, null=True)
    masterformat_section = models.ForeignKey("MasterFormatSection", on_delete=models.PROTECT)
    spec_section = models.ForeignKey("SpecSection", on_delete=models.PROTECT, blank=True, null=True)
    paragraph_number = models.CharField(max_length=256)
    heirarchical_paragraph_number = models.CharField(max_length=256, default="", blank=True)

    text_location = models.JSONField(blank=True, null=True)
    additional_text_locations = models.JSONField(blank=True, null=True)

    parsing_method = models.CharField(max_length=256)
    parsing_version = models.CharField(max_length=256)

    class Meta:
        abstract = True


class SubmittalItem(BaseSpecItem):
    legacy_id = models.IntegerField(blank=True, null=True)
    legacy_updated_at = models.DateTimeField(blank=True, null=True)

    submittal_type = models.CharField(max_length=256)
    submittal_description = models.CharField(max_length=256)
    submittal_content = models.TextField()

    submittal_number = models.DecimalField(max_digits=10, decimal_places=1, blank=True, null=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="created_submittal_items", blank=True, null=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="updated_submittal_items", blank=True, null=True)

    procore_submittal_id = models.CharField(max_length=256, blank=True, null=True)
    procore_export_date = models.DateTimeField(blank=True, null=True)

    added_under_submittal = models.ForeignKey("SubmittalItem", on_delete=models.SET_NULL, blank=True, null=True)
    manually_added = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['project']),
            models.Index(fields=['masterformat_section']),
            models.Index(fields=['submittal_type']),
            models.Index(fields=['submittal_description']),
        ]

    def convert_paragraph_number_to_heirarchical_number(self):
        if self.paragraph_number is None:
            return ""
        split_paragraph_number = self.paragraph_number.split('-')
        period_separated_parts = split_paragraph_number[0]
        if len(split_paragraph_number) > 1:
            appendage = split_paragraph_number[1]
        else:
            appendage = ""

        period_separated_parts = [part.zfill(5) for part in period_separated_parts.split('.')]
        heirarchical_period_part = '.'.join(period_separated_parts)
        if appendage:
            return heirarchical_period_part + '-' + appendage.zfill(5)
        else:
            return heirarchical_period_part
        
    def save(self, *args, **kwargs):
        self.heirarchical_paragraph_number = self.convert_paragraph_number_to_heirarchical_number()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.document.name if self.document else ''} - {self.masterformat_section.masterformat_number} - {self.paragraph_number}: {self.submittal_description}"


class SemanticallyProcessedSpecItem(BaseSpecItem):
    spec_section_part = models.CharField(max_length=256)
    topic = models.JSONField()
    item_type = models.JSONField()
    item_content = models.TextField()


class SubmittalItemList(BaseModel):
    name = models.CharField(max_length=256)
    description = models.TextField(blank=True)
    project = models.ForeignKey("Project", on_delete=models.CASCADE)
    project_version = models.ForeignKey("ProjectVersion", on_delete=models.CASCADE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, blank=True, null=True)
    submittals = models.ManyToManyField("SubmittalItem", blank=True, related_name="submittal_lists")

    def __str__(self):
        return self.name


class ExcelExportHeader(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="excel_export_header")
    options = models.JSONField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", )


# region notices
# TODO:
#   - Split `models.py` into a module
#   - move this region into a separate file

class NoticeExcerpt(BaseModel):
    document = models.ForeignKey(
        "UploadedFile",
        on_delete=models.CASCADE,
        related_name="notice_excerpts",
    )
    anchor = models.CharField(max_length=256)
    lines = models.JSONField()


class NoticeMatch(BaseModel):
    project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        related_name="notice_matches",
    )
    project_version = models.ForeignKey(
        "ProjectVersion",
        on_delete=models.CASCADE,
    )
    document = models.ForeignKey(
        "UploadedFile",
        on_delete=models.CASCADE,
        related_name="notice_matches",
    )

    notice_type = models.CharField(max_length=256, null=True, blank=True)
    notice_type_match = models.CharField(max_length=256, blank=True, null=True)

    highlight_heuristic_match = models.TextField(blank=True, null=True)
    highlight_discriminators = models.JSONField()

    excerpt_anchors = models.ManyToManyField(
        "NoticeExcerpt",
        related_name="matches",
    )
    leading_anchor = models.CharField(max_length=256)

    masterformat_section = models.ForeignKey(
        "MasterFormatSection",
        on_delete=models.CASCADE,
        # This one is NULL for now, but it will be filled out when we update
        # the parsers.
        null=True,
        default=None,
    )

# endregion notices


# region Procore

class ProcoreToken(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="procore_tokens")
    access_token = models.CharField(max_length=1020)
    refresh_token = models.CharField(max_length=1020)
    expires_in = models.IntegerField()
    token_type = models.CharField(max_length=256)
    redirect_uri = models.CharField(max_length=1020, blank=True, null=True)
    code = models.CharField(max_length=1020)

    def is_expired(self):
        return datetime.now(tz=timezone.utc) > (self.created_at + timedelta(seconds=self.expires_in))
    

class ProcoreSubmittalTypeMapping(BaseModel):
    company = models.ForeignKey("teams.Team", on_delete=models.CASCADE)
    procore_company_id = models.CharField(max_length=256)
    link_type = models.CharField(max_length=256)
    procore_type = models.CharField(max_length=256)

    class Meta:
        unique_together = ("company", "link_type")

    def __str__(self):
        return f"{self.link_type} -> {self.procore_type}"

# endregion Procore

# region SpecGPT

class Chat(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey("Project", on_delete=models.CASCADE)
    project_version = models.ForeignKey("ProjectVersion", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

class ChatMessage(BaseModel):
    class ChatMessageType(models.TextChoices):
        AI = "ai", "ai"
        HUMAN = "human", "human"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chat = models.ForeignKey("Chat", on_delete=models.CASCADE, related_name="messages")
    type = models.CharField(max_length=256, choices=ChatMessageType.choices)
    message = models.TextField()
    raw_message = models.JSONField(blank=True, null=True)
    sources = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"{self.chat.project.name} - {self.chat.project_version.version_number} - {self.chat.user.email}"
    

class CustomPostgresChatMessageHistory(BaseChatMessageHistory):
    def __init__(self, chat: Chat):
        self.chat = chat
        self.message_db_object = None

    @property
    def messages(self) -> List[BaseMessage]:
        messages = ChatMessage.objects.filter(chat=self.chat).order_by('created_at').values_list('raw_message', flat=True)
        return messages_from_dict(messages)
    
    def add_message(self, message: BaseMessage):
        try:
            chat_message = ChatMessage.objects.create(
                chat=self.chat,
                type=message.type,
                message=message.content,
                raw_message=_message_to_dict(message)
            )
            self.message_db_object = chat_message
        except Exception as e:
            print(f"Error adding message to chat: {e}")

    def clear(self):
        ChatMessage.objects.filter(chat=self.chat).delete()

    
    

# endregion SpecGPT