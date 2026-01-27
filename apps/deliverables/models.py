import uuid
from enum import Enum
from datetime import datetime, timedelta, timezone
from typing import List

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
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
        SUBSECTIONS_EXTRACTED = "SUBSECTIONS_EXTRACTED", "Subsections Extracted"
        SECTION_PROCESSING_FAILED = "SECTION_PROCESSING_FAILED", "Section Processing Failed"
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
    custom_section_title = models.CharField(max_length=256, blank=True, null=True)
    document = models.ForeignKey("UploadedFile", on_delete=models.CASCADE)
    processing_status = models.CharField(max_length=256, blank=True, null=True)
    processing_method = models.CharField(max_length=256, blank=True, null=True, choices=ProcessingMethod.choices)
    specgpt_embedding_status = models.CharField(max_length=256, blank=True, null=True, choices=UploadedFile.SpecgptProcessingStatusChoices.choices)
    file_s3_key = models.CharField(max_length=1024, blank=True, null=True)

    class Meta:
        ordering = ['masterformat_section__masterformat_number', 'document__name']

    def __str__(self):
        return f"{self.document.name} - {self.masterformat_section.masterformat_number}"


class BaseSpecItem(BaseModel):
    project = models.ForeignKey("Project", on_delete=models.CASCADE)
    project_version = models.ForeignKey("ProjectVersion", on_delete=models.CASCADE)
    document = models.ForeignKey("UploadedFile", on_delete=models.CASCADE, blank=True, null=True)
    masterformat_section = models.ForeignKey("MasterFormatSection", on_delete=models.PROTECT)
    spec_section = models.ForeignKey("SpecSection", on_delete=models.CASCADE, blank=True, null=True)
    paragraph_number = models.CharField(max_length=256, blank=True, null=True)
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
        SYSTEM = "system", "system"
        ERROR = "error", "error"
        AI_INSPECTION_LOG = "ai_inspection_log", "ai_inspection_log"
        AI_OWNER_DELIVERABLES_LOG = "ai_owner_deliverables_log", "ai_owner_deliverables_log"
        
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


class AiGeneratedLog(BaseModel):
    project = models.ForeignKey("Project", on_delete=models.CASCADE)
    project_version = models.ForeignKey("ProjectVersion", on_delete=models.CASCADE)
    log_type = models.CharField(max_length=256)
    log_status = models.CharField(max_length=256)
    log_table = models.TextField(blank=True, null=True)
    log_data = models.JSONField(blank=True, null=True, help_text="Structured data for inspection logs and owner deliverables logs")
    qa_options_selected = models.JSONField(blank=True, null=True, help_text="Selected QA options for qa_planner log type")
    completion_status = models.JSONField(blank=True, null=True, help_text="Status of each QA option processing")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_generated_logs',
        help_text="User who triggered this AI log generation (null for system-generated)"
    )

    def __str__(self):
        return f"{self.project.name} - {self.project_version.version_number} - {self.log_type} - {self.log_status}"


class ExtractionSource(models.TextChoices):
    """Source of the extracted data"""
    AI = "AI", "AI Generated"
    HUMAN = "HUMAN", "Human Created"


class ExtractionItemType(models.TextChoices):
    """Types of extracted items users can categorize"""
    SUBMITTAL = "submittal", "Submittal"
    INSPECTION = "inspection", "Inspection"
    OWNER_DELIVERABLE = "owner_deliverable", "Owner Deliverable"
    QA_INSPECTION = "qa_inspection", "QA Inspection"
    QA_WARRANTY = "qa_warranty", "QA Warranty"
    QA_CERTIFICATE = "qa_certificate", "QA Certificate"
    QA_CLOSEOUT = "qa_closeout", "QA Closeout"
    QA_TEST_REPORT = "qa_test_report", "QA Test Report"
    QA_COMMISSIONING = "qa_commissioning", "QA Commissioning"
    QA_DELEGATED_DESIGN = "qa_delegated_design", "QA Delegated Design"
    QA_MOCKUP = "qa_mockup", "QA Mock-up/Sample"
    QA_PRE_INSTALL = "qa_pre_install", "QA Pre-Installation Meeting"


class ExtractedData(BaseModel):
    """Individual row extracted from AI-generated logs or manually created via Apryse highlights"""

    # Foreign keys
    ai_generated_log = models.ForeignKey(
        'AiGeneratedLog',
        on_delete=models.CASCADE,
        related_name='extracted_items',
        null=True,
        blank=True,
        help_text="AI log this was extracted from (null for human-created)"
    )
    project = models.ForeignKey('Project', on_delete=models.CASCADE)
    project_version = models.ForeignKey('ProjectVersion', on_delete=models.CASCADE)
    spec_section = models.ForeignKey(
        'SpecSection',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    custom_item_type = models.ForeignKey(
        'CustomItemType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='extracted_data_items',
        help_text="User-defined grouping (only valid for custom highlights)"
    )

    # Creation metadata
    source = models.CharField(
        max_length=10,
        choices=ExtractionSource.choices,
        default=ExtractionSource.AI,
        help_text="Whether this was AI-generated or human-created"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_extractions',
        help_text="User who created this extraction (for HUMAN source) or triggered AI generation"
    )

    # Core data fields
    spec_section_number = models.CharField(max_length=256)
    spec_section_name = models.CharField(max_length=512)
    paragraph_number = models.CharField(max_length=256, blank=True, null=True)

    # Type classification
    extraction_type = models.CharField(
        max_length=256,
        help_text="For AI: log type (inspection_log, owner_deliverables_log, qa_planner). For HUMAN: user-selected base type"
    )
    item_type = models.CharField(
        max_length=256,
        blank=True,
        null=True,
        help_text="Specific categorization - for QA planner subtypes or user-selected type for highlights"
    )

    # Content fields
    requirement_text = models.TextField()
    responsible_party = models.CharField(max_length=512, blank=True, null=True)

    # PDF location data
    pdf_locations = models.JSONField(
        blank=True,
        null=True,
        help_text="PDF coordinate data for highlighting"
    )

    # Flexible metadata for type-specific fields
    metadata = models.JSONField(
        blank=True,
        null=True,
        default=dict,
        help_text="Type-specific data: inspection_frequency, when_due, deliverable_type, etc."
    )

    class Meta:
        db_table = 'deliverables_extracted_data'
        indexes = [
            models.Index(fields=['project', 'project_version']),
            models.Index(fields=['spec_section_number']),
            models.Index(fields=['extraction_type', 'item_type']),
            models.Index(fields=['source']),
            models.Index(fields=['created_by']),
        ]
        ordering = ['spec_section_number', 'id']

    def __str__(self):
        return f"{self.spec_section_number} - {self.requirement_text[:50]}"

    def validate_custom_highlight_consistency(self):
        """
        Ensure custom tags belong to the same project as the extraction.
        """
        if self.custom_item_type and self.custom_item_type.project_id != self.project_id:
            raise ValidationError(
                {"custom_item_type": "Custom item type must belong to the same project."}
            )

    def clean(self):
        super().clean()

        if self.custom_item_type and self.extraction_type != "custom_highlights":
            raise ValidationError({
                "custom_item_type": 'When custom_item_type is set, extraction_type must be "custom_highlights".'
            })

        if self.extraction_type == "custom_highlights" and not self.custom_item_type:
            raise ValidationError({
                "custom_item_type": 'Extraction type "custom_highlights" requires a custom_item_type.'
            })

    def save(self, *args, **kwargs):
        """Override save to set created_by for AI sources from ai_generated_log"""
        if self.custom_item_type:
            self.extraction_type = "custom_highlights"

        if self.extraction_type == "custom_highlights" and not self.custom_item_type:
            raise ValidationError({
                "custom_item_type": 'Extraction type "custom_highlights" requires a custom_item_type.'
            })

        self.validate_custom_highlight_consistency()

        if self.source == ExtractionSource.AI and not self.created_by_id:
            # Try to get user from ai_generated_log if available
            if self.ai_generated_log and hasattr(self.ai_generated_log, 'created_by'):
                self.created_by = self.ai_generated_log.created_by

        super().save(*args, **kwargs)


class ExtractionNote(BaseModel):
    """Text notes attached to ExtractedData highlights"""

    extracted_data = models.ForeignKey(
        'ExtractedData',
        on_delete=models.CASCADE,
        related_name='notes',
        help_text="The highlight this note is attached to"
    )

    text = models.TextField(
        help_text="Note content"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='extraction_notes',
        help_text="User who created this note"
    )

    class Meta:
        db_table = 'deliverables_extraction_note'
        indexes = [
            models.Index(fields=['extracted_data', 'created_at']),
            models.Index(fields=['created_by']),
        ]
        ordering = ['created_at']

    def __str__(self):
        preview = self.text[:50] + '...' if len(self.text) > 50 else self.text
        return f"Note on {self.extracted_data.spec_section_number}: {preview}"


# endregion SpecGPT


class CustomItemType(BaseModel):
    """
    Project-scoped, user-created tags for grouping ExtractedData entries.
    """

    name = models.CharField(
        max_length=100,
        help_text="Readable label (e.g. 'Safety Requirements')."
    )
    color = models.CharField(
        max_length=7,
        default="#3B82F6",
        validators=[
            RegexValidator(
                regex=r"^#[0-9A-Fa-f]{6}$",
                message="Color must be in HEX format (#RRGGBB)."
            )
        ],
        help_text="HEX code used by the frontend for highlight color."
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Optional explanation of how this tag should be used."
    )
    project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        related_name="custom_item_types",
        help_text="Owning project."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_custom_item_types",
        help_text="User who defined this custom type."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Soft-delete flag so we can hide a type without losing history."
    )

    class Meta:
        db_table = "deliverables_custom_item_type"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"],
                name="unique_custom_item_type_per_project"
            )
        ]
        indexes = [
            models.Index(fields=["project", "is_active"]),
            models.Index(fields=["created_by"]),
        ]

    def __str__(self) -> str:
        project_label = self.project.project_number or self.project.name
        return f"{self.name} ({project_label})"


class UserHighlightPreference(BaseModel):
    """
    Stores the user's last used highlight type per project for quick reuse.
    Allows cross-device persistence of the "Repeat Last Highlight" feature.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="highlight_preferences",
        help_text="User who owns this preference."
    )
    project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        related_name="user_highlight_preferences",
        help_text="Project context for this preference."
    )

    is_custom_type = models.BooleanField(
        default=False,
        help_text="True if last highlight was a custom type, False if standard type."
    )
    custom_item_type = models.ForeignKey(
        "CustomItemType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_preferences",
        help_text="Reference to custom type if is_custom_type=True."
    )
    standard_item_type = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Standard type name (e.g., 'inspections', 'warranties') if is_custom_type=False."
    )
    extraction_type = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="The extraction_type used (e.g., 'qa_planner', 'custom_highlights')."
    )

    # Store display information for quick access
    type_display_name = models.CharField(
        max_length=200,
        help_text="Human-readable name to display (e.g., 'Inspections', 'Safety Requirements')."
    )
    type_color = models.CharField(
        max_length=7,
        help_text="HEX color code for visual display."
    )

    class Meta:
        db_table = "deliverables_user_highlight_preference"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "project"],
                name="unique_highlight_preference_per_user_project"
            )
        ]
        indexes = [
            models.Index(fields=["user", "project"]),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} - {self.project.name}: {self.type_display_name}"


class PDFAnnotation(BaseModel):
    annotation_id = models.CharField(
        max_length=255,
        unique=True,
        null=False,
        blank=False,
        help_text="Frontend-generated annotation ID"
    )
    project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        related_name="pdf_annotations",
    )
    project_version = models.ForeignKey(
        "ProjectVersion",
        on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_pdf_annotations",
        blank=True,
        null=True
    )
    spec_section = models.ForeignKey(
        "SpecSection",
        on_delete=models.CASCADE,
        related_name="pdf_annotations"
    )
    page_number = models.PositiveIntegerField()
    color = models.CharField(
        max_length=7,
        help_text="Highlight color in HEX (e.g., #FFDD00)"
    )
    quads = models.JSONField(
        default=list,
        blank=True,
        help_text="Array of text quads for highlight annotation (each quad = [x1,y1,x2,y2,x3,y3,x4,y4])"
    )
    xfdf_data = models.TextField(
        help_text="Full XFDF string for this annotation. It will be used for import/exporting-ing the annotations"
    )
    tag = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Optional label or tag for categorizing annotations"
    )

    def __str__(self):
        user_display = self.user.email if self.user else "Unknown user"
        return f"Annotation (Page {self.page_number}) by {user_display}"


# region Drawing Parser Models

class DrawingExtractionStatus(models.TextChoices):
    """Status of a drawing extraction run"""
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    SUCCESS = "SUCCESS", "Success"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS", "Partial Success"
    FAILED = "FAILED", "Failed"


class DrawingPageType(models.TextChoices):
    """Type of page in a drawing"""
    DRAWING = "drawing", "Drawing"
    SPEC = "spec", "Specification"


class DrawingPageExtractionStatus(models.TextChoices):
    """Extraction status for individual pages"""
    SUCCESS = "success", "Success"
    NO_NOTES_FOUND = "no_notes_found", "No Notes Found"
    FAILED = "failed", "Failed"


class DrawingFile(BaseModel):
    """Uploaded drawing document (e.g., mechanical drawings PDF)"""

    project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        related_name="drawing_files"
    )
    project_version = models.ForeignKey(
        "ProjectVersion",
        on_delete=models.CASCADE,
        related_name="drawing_files"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_drawing_files"
    )

    file_name = models.CharField(max_length=512)
    file_s3_key = models.CharField(max_length=1024)
    md5 = models.CharField(max_length=64)
    total_pages = models.IntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['project', 'project_version']),
        ]

    def __str__(self):
        return f"{self.file_name} ({self.project.name})"

    @property
    def latest_extraction(self):
        return self.extractions.order_by('-created_at').first()

    @property
    def extraction_status(self):
        extraction = self.latest_extraction
        return extraction.status if extraction else None


class DrawingExtraction(BaseModel):
    """Tracks each extraction attempt for a drawing file"""

    drawing_file = models.ForeignKey(
        "DrawingFile",
        on_delete=models.CASCADE,
        related_name="extractions"
    )

    status = models.CharField(
        max_length=32,
        choices=DrawingExtractionStatus.choices,
        default=DrawingExtractionStatus.PENDING
    )

    # Processing metadata
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    model_version = models.CharField(max_length=128, null=True, blank=True)
    processing_time_ms = models.IntegerField(null=True, blank=True)
    output_s3_key = models.CharField(max_length=1024, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    failure_summary = models.CharField(max_length=256, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['drawing_file', 'status']),
        ]

    def __str__(self):
        return f"Extraction {self.id} for {self.drawing_file.file_name} ({self.status})"


class DrawingPage(BaseModel):
    """Individual page from a drawing file"""

    drawing_file = models.ForeignKey(
        "DrawingFile",
        on_delete=models.CASCADE,
        related_name="pages"
    )
    extraction = models.ForeignKey(
        "DrawingExtraction",
        on_delete=models.CASCADE,
        related_name="pages"
    )

    page_number = models.IntegerField()
    page_type = models.CharField(
        max_length=32,
        choices=DrawingPageType.choices
    )
    rotation = models.IntegerField(default=0)
    rotated_width = models.FloatField(null=True, blank=True)
    rotated_height = models.FloatField(null=True, blank=True)
    unrotated_width = models.FloatField(null=True, blank=True)
    unrotated_height = models.FloatField(null=True, blank=True)
    extraction_status = models.CharField(
        max_length=32,
        choices=DrawingPageExtractionStatus.choices
    )
    spec_content = models.TextField(null=True, blank=True)
    sheet_number = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
        help_text="The sheet number from the drawing title block (e.g., 'A-101', 'M-203')"
    )
    sheet_title = models.CharField(
        max_length=512,
        null=True,
        blank=True,
        db_index=True,
        help_text="The sheet title from the drawing title block (e.g., 'FLOOR PLAN - DRAINAGE - MAIN')"
    )

    class Meta:
        ordering = ['page_number']

    def __str__(self):
        return f"Page {self.page_number} of {self.drawing_file.file_name}"


class DrawingNoteSection(BaseModel):
    """A section header containing notes on a drawing page (e.g., 'GENERAL NOTES:')"""

    page = models.ForeignKey(
        "DrawingPage",
        on_delete=models.CASCADE,
        related_name="note_sections"
    )

    header = models.CharField(max_length=512)
    header_bbox = models.JSONField(null=True, blank=True)  # [x1, y1, x2, y2] - Deprecated, use unrotated_header_bbox
    rotated_header_bbox = models.JSONField(null=True, blank=True)
    unrotated_header_bbox = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.header} (Page {self.page.page_number})"


class DrawingNote(BaseModel):
    """Individual note extracted from a drawing"""

    section = models.ForeignKey(
        "DrawingNoteSection",
        on_delete=models.CASCADE,
        related_name="notes"
    )

    note_number = models.IntegerField()
    category = models.CharField(max_length=256)
    text = models.TextField()
    bounding_box = models.JSONField(null=True, blank=True) # Deprecated, use unrotated_bounding_box
    raw_bounding_box = models.JSONField(null=True, blank=True) # Deprecated, use rotated_bounding_box
    rotated_bounding_box = models.JSONField(null=True, blank=True)
    unrotated_bounding_box = models.JSONField(null=True, blank=True)
    source_blocks = models.JSONField(null=True, blank=True)
    drawing_references = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['note_number']
        indexes = [
            models.Index(fields=['category']),
        ]

    def __str__(self):
        preview = self.text[:50] + '...' if len(self.text) > 50 else self.text
        return f"Note {self.note_number}: {preview}"


class DrawingExtractionWebhookEvent(BaseModel):
    """
    Store each webhook delivery for idempotency and retry safety.
    The unique event_id ensures duplicate deliveries are ignored.
    """

    extraction = models.ForeignKey(
        "DrawingExtraction",
        on_delete=models.CASCADE,
        related_name="webhook_events",
    )

    # Provided by the caller; unique per webhook delivery
    event_id = models.CharField(max_length=128, unique=True)

    # Helps debug ordering/retries without storing entire payload forever
    new_status = models.CharField(max_length=32)
    output_s3_key = models.CharField(max_length=1024, null=True, blank=True)
    payload = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["extraction", "new_status"]),
        ]

    def __str__(self):
        return f"Webhook {self.event_id} -> {self.new_status}"


# endregion Drawing Parser Models
