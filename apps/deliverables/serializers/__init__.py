import boto3
from django.conf import settings
from django.db.models import Case, When, IntegerField, Max
from rest_framework import serializers
from apps.utils.feature_flags import get_active_flags_for_project
from apps.users.serializers import CustomUserSerializer
from apps.users.models import CustomUser
from apps.teams.models import Team
from ..utils import get_next_submittal_number
from ..models import (
    SubmittalItem,
    UploadedFile,
    SpecSection,
    SubmittalItemList,
    MasterFormatSection,
    DocProcessingStatus,
    Project,
    ProjectMembership,
    ProjectVersion,
    ExcelExportHeader,
    SemanticallyProcessedSpecItem,
)
from ..constants import masterformat_to_section_title_map


s3 = boto3.client(
    "s3",
    region_name=settings.AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
)


class ProjectMembershipSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(source="user.id",
                                                 queryset=CustomUserSerializer.Meta.model.objects.all())
    first_name = serializers.ReadOnlyField(source="user.first_name")
    last_name = serializers.ReadOnlyField(source="user.last_name")
    display_name = serializers.ReadOnlyField(source="user.get_display_name")

    class Meta:
        model = ProjectMembership
        fields = ['user_id', 'first_name', 'last_name', 'display_name', 'role']


class ProjectMembershipAddSerializer(serializers.Serializer):
    user_ids = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all(), many=True)

    def validate(self, data):
        project_id = self.context['view'].kwargs.get('pk')
        project = Project.objects.get(id=project_id)
        if data.get('user_ids'):
            for user in data.get('user_ids'):
                if not user.is_member_of_team(project.team):
                    raise serializers.ValidationError("All members must be a member of the team.")
        return data


class ProjectVersionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    version_number = serializers.IntegerField(read_only=True)
    version_name = serializers.CharField(required=True)

    class Meta:
        model = ProjectVersion
        fields = ['id', 'version_number', 'version_name']


class BaseProjectSerializer(serializers.ModelSerializer):
    project_versions = serializers.SerializerMethodField()
    members = ProjectMembershipSerializer(source="project_memberships", many=True, required=False)
    team = serializers.ReadOnlyField(source="team.id")
    team_name = serializers.ReadOnlyField(source="team.name")
    team_logo_url = serializers.ReadOnlyField(source="team.legacy_logo_url")
    user_limit = serializers.ReadOnlyField()
    active_flags = serializers.SerializerMethodField(read_only=True)
    current_user_role = serializers.SerializerMethodField(read_only=True)
    current_user_team_role = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Project
        fields = ['id', 'name', 'description', 'team', 'team_name', 'team_logo_url', 'members',
                   'user_limit', 'start_date', 'end_date', 'is_archived',
                   'project_number', 'project_type', 'project_versions', 'active_flags',
                   'current_user_role', 'current_user_team_role']
        
    def get_project_versions(self, obj):
        versions = obj.versions.filter(is_archived=False)
        return ProjectVersionSerializer(versions, many=True).data

    def get_entitlements(self, obj) -> list[str]:
        # Handle case when obj is a dictionary (during validation)
        if isinstance(obj, dict):
            return []
        project_level_entitlements = obj.entitlements.values_list('code_name', flat=True)
        if project_level_entitlements:
            return project_level_entitlements
        else:
            return obj.team.entitlements.values_list('code_name', flat=True)
        
    def get_active_flags(self, obj):
        return get_active_flags_for_project(obj)

    def get_current_user_role(self, obj):
        """
        Get the current user's role in this project.
        Returns 'project_admin', 'project_member', or None if not a member.
        """
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return None

        # Check if user is superuser
        if request.user.is_superuser:
            return 'project_admin'

        # Find the user's membership in this project
        membership = obj.project_memberships.filter(user=request.user).first()
        if membership:
            return membership.role

        return None

    def get_current_user_team_role(self, obj):
        """
        Get the current user's role in the team that owns this project.
        Returns 'admin', 'member', or None if user is not a team member.
        """
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return None

        # Check if user is actually a member of the team
        if not request.user.is_member_of_team(obj.team):
            return None

        # Use the user's team role helper method
        if request.user.is_admin_for_team(obj.team):
            return 'admin'

        return 'member'


class ProjectWriteSerializer(BaseProjectSerializer):
    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all())

    def validate(self, data):
        team: Team = data.get('team')
        members = data.get('project_memberships')

        if self.instance:
            team = team or self.instance.team
        else:
            if not team:
                raise serializers.ValidationError("Team is required to create a project.")
            
        if members:
            for member in members:
                member_user = member.get('user').get('id')
                if not member_user.is_member_of_team(team):
                    raise serializers.ValidationError("All members must be a member of the team.")
        return data

    def update(self, instance, validated_data):
        memberships_data = validated_data.pop('project_memberships', [])
        # Update project fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update project memberships
        existing_members = {membership.user.id: membership for membership in
                            instance.project_memberships.all()}
        new_members = []

        for membership_data in memberships_data:
            user_id = membership_data.get('user').get('id').id
            role = membership_data.get('role')

            if user_id in existing_members:
                # Update existing membership
                membership = existing_members.pop(user_id)
                membership.role = role
                membership.save()
            else:
                # Create new membership
                new_members.append(ProjectMembership(user_id=user_id, project=instance, role=role))
        # Remove memberships not in the update data
        for membership in existing_members.values():
            membership.delete()

        # Add new memberships
        ProjectMembership.objects.bulk_create(new_members)
        return instance

    def create(self, validated_data):
        memberships_data = validated_data.pop('project_memberships', [])
        project = Project.objects.create(**validated_data)

        for membership_data in memberships_data:
            user_id = membership_data.get('user').get('id').id
            role = membership_data.get('role')
            ProjectMembership.objects.create(project=project, user_id=user_id, role=role)

        return project


class DocumentSubsectionSerializer(serializers.ModelSerializer):
    masterformat_number = serializers.CharField(source="masterformat_section.masterformat_number")

    class Meta:
        model = SpecSection
        fields = ['id', 'masterformat_number', 'processing_status', 'specgpt_embedding_status']


class EmbedDocumentSerializer(serializers.ModelSerializer):
    document_id = serializers.IntegerField(source="id")
    document_name = serializers.CharField(source="name")
    document_status = serializers.CharField(source="processing_status")
    document_link = serializers.SerializerMethodField()

    def get_document_link(self, obj):
        return s3.generate_presigned_url('get_object', Params={'Bucket': settings.S3_BUCKET, 'Key': obj.document_path}, ExpiresIn=3600)

    class Meta:
        model = UploadedFile
        fields = [
            'document_id',
            'document_name',
            'document_status',
            'document_link',
        ]


class DocumentSerializer(EmbedDocumentSerializer):
    document_status = serializers.CharField(source="processing_status")
    specgpt_processing_status = serializers.CharField()
    document_subsections = DocumentSubsectionSerializer(source="specsection_set", many=True)
    project_version = ProjectVersionSerializer(many=False)

    class Meta(EmbedDocumentSerializer.Meta):
        fields = [
            *EmbedDocumentSerializer.Meta.fields,
            'specgpt_processing_status',
            'document_status',
            'project_version',
            'document_subsections',
            'created_at',
            'updated_at',
        ]


class ProjectListSerializer(BaseProjectSerializer):
    class Meta:
        model = Project
        fields = BaseProjectSerializer.Meta.fields


class ProjectOverviewSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for project list/overview pages.
    Returns only essential fields to minimize payload size and improve performance.
    """
    members_count = serializers.SerializerMethodField()
    current_user_role = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ['id', 'name', 'project_number', 'start_date', 'end_date',
                  'is_archived', 'members_count', 'current_user_role']

    def get_members_count(self, obj):
        """
        Return the count of members without fetching member details.
        Uses prefetched data if available to avoid N+1 queries.
        """
        # Check if members are prefetched (will be an attribute)
        if hasattr(obj, '_members_count'):
            return obj._members_count
        # Fallback to counting related objects
        return obj.project_memberships.count()

    def get_current_user_role(self, obj):
        """
        Get the current user's role in this project.
        Returns 'project_admin', 'project_member', or None if not a member.
        Uses prefetched data if available to avoid N+1 queries.
        """
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return None

        # Check if user is superuser
        if request.user.is_superuser:
            return 'project_admin'

        # Use prefetched data if available (set by overview endpoint)
        if hasattr(obj, '_current_user_memberships'):
            memberships = obj._current_user_memberships
            if memberships:
                return memberships[0].role
            return None

        # Fallback to querying if not prefetched
        membership = obj.project_memberships.filter(user=request.user).first()
        if membership:
            return membership.role

        return None


class ProjectDetailsSerializer(BaseProjectSerializer):
    doc_parsed = serializers.SerializerMethodField()
    document_details = serializers.SerializerMethodField()

    def get_doc_parsed(self, obj):
        """
        Return the count of documents, optionally filtered by project_version_id.
        """
        request = self.context.get("request")
        queryset = obj.uploadedfile_set.all()

        project_version_id = request.query_params.get("project_version_id") if request else None
        if project_version_id:
            queryset = queryset.filter(project_version_id=project_version_id)

        return queryset.count()

    def get_document_details(self, obj):
        """
        Return the serialized list of documents, optionally filtered by project_version_id.
        """
        request = self.context.get("request")
        queryset = obj.uploadedfile_set.all().annotate(
            status_order=Case(
                When(processing_status=DocProcessingStatus.PENDING_PROCESSING, then=1),
                When(processing_status=DocProcessingStatus.PROCESSING, then=2),
                When(processing_status=DocProcessingStatus.SUBSECTIONS_EXTRACTED, then=3),
                When(processing_status=DocProcessingStatus.SECTION_PROCESSING_FAILED, then=4),
                When(processing_status=DocProcessingStatus.FAILED, then=5),
                When(processing_status=DocProcessingStatus.PROCESSED, then=6),
                When(processing_status=DocProcessingStatus.PROCESSED_SECTION, then=7),
                default=8,
                output_field=IntegerField(),
            )
        ).order_by("status_order", "-created_at")

        # Apply version filter if present
        project_version_id = request.query_params.get("project_version_id") if request else None
        if project_version_id:
            queryset = queryset.filter(project_version_id=project_version_id)

        return DocumentSerializer(queryset, many=True).data

    class Meta:
        model = Project
        fields = BaseProjectSerializer.Meta.fields + ["doc_parsed", "document_details"]


class FileUploadSerializer(serializers.Serializer):
    files = serializers.ListField(child=serializers.FileField())
    project_id = serializers.IntegerField()
    project_version_id = serializers.IntegerField(required=False)
    extract_notices = serializers.BooleanField(required=False)
    full_spec_processing = serializers.BooleanField(required=False)
    file_type = serializers.ChoiceField(
        choices=['spec', 'drawing'],
        required=False,
        default='spec'
    )


class CombineSubmittalItemsSerializer(serializers.Serializer):
    lst_all_logs = serializers.ListField(child=serializers.DictField())
    project_id = serializers.IntegerField()
    prepared_object = serializers.DictField()


class SemanticallyProcessedSpecItemSerializer(serializers.ModelSerializer):
    additional_text_locations = serializers.JSONField()
    text_location = serializers.JSONField()
    document = EmbedDocumentSerializer()
    document_section_link = serializers.SerializerMethodField()

    project_id = serializers.IntegerField(source='project.id')
    spec_section = serializers.CharField(source='masterformat_section.masterformat_number')
    section_title = serializers.SerializerMethodField()

    def get_section_title(self, obj):
        title_override = obj.spec_section.custom_section_title if obj.spec_section else None
        return title_override or obj.masterformat_section.masterformat_description or masterformat_to_section_title_map.get(
            obj.masterformat_section.masterformat_number, 'Custom Title')
    
    def get_document_section_link(self, obj):
        if obj.spec_section:
            if obj.spec_section.file_s3_key:
                return s3.generate_presigned_url('get_object', Params={'Bucket': settings.S3_BUCKET, 'Key': obj.spec_section.file_s3_key}, ExpiresIn=3600)
        if obj.document:
            return s3.generate_presigned_url('get_object', Params={'Bucket': settings.S3_BUCKET, 'Key': obj.document.document_path}, ExpiresIn=3600)
        return ""

    class Meta:
        model = SemanticallyProcessedSpecItem
        fields = [
            'id', 'project_id', 'project_version', 'document', 
            'masterformat_section', 'section_title', 'spec_section_part', 
            'topic', 'spec_section', 'document_section_link',
            'item_type', 'item_content', 'paragraph_number',
            'parsing_method', 'parsing_version',
            'additional_text_locations', 'text_location',
        ]


class SubmittalItemReadSerializer(serializers.ModelSerializer):
    additional_text_locations = serializers.JSONField()
    doc_id = serializers.IntegerField(source='document.id', allow_null=True)
    doc_link = serializers.SerializerMethodField()
    id = serializers.IntegerField()
    item_desc = serializers.CharField(source='submittal_description')
    para_context = serializers.CharField(source='submittal_content')
    para_no = serializers.CharField(source='paragraph_number')
    project_id = serializers.IntegerField(source='project.id')
    section_title = serializers.SerializerMethodField()
    spec_section = serializers.CharField(source='masterformat_section.masterformat_number')
    submittal_number = serializers.CharField()
    text_loc = serializers.JSONField(source='text_location')
    type = serializers.CharField(source='submittal_type')
    parsing_method = serializers.CharField()
    manually_added = serializers.BooleanField()

    def get_section_title(self, obj):
        title_override = obj.spec_section.custom_section_title if obj.spec_section else None
        return title_override or obj.masterformat_section.masterformat_description or masterformat_to_section_title_map.get(
            obj.masterformat_section.masterformat_number, 'Custom Title')

    def get_doc_link(self, obj):
        if obj.spec_section:
            if obj.spec_section.file_s3_key:
                return s3.generate_presigned_url('get_object', Params={'Bucket': settings.S3_BUCKET, 'Key': obj.spec_section.file_s3_key}, ExpiresIn=3600)

        # TBL-76: Older documents using the legacy parsing approach have a full cloudfront URL stored in the doc_link column.
        # New documents just store the S3 object key in the doc_link column. To handle this, we return the Cloudfront URL if it exists,
        # and if not, we return a presigned URL generated from the S3 object key
        if not obj.document:
            return ""
        if obj.document.document_path.startswith(
                "https://") and "cloudfront.net" in obj.document.document_path:
            return obj.document.document_path
        else:
            return s3.generate_presigned_url('get_object', Params={'Bucket': settings.S3_BUCKET, 'Key': obj.document.document_path}, ExpiresIn=3600)

    class Meta:
        model = SubmittalItem
        fields = [
            'additional_text_locations',
            'doc_id',
            'doc_link',
            'id',
            'item_desc',
            'para_context',
            'para_no',
            'project_id',
            'section_title',
            'spec_section',
            'submittal_number',
            'text_loc',
            'type',
            'parsing_method',
            'manually_added',
        ]


class SubmittalItemWriteSerializer(serializers.ModelSerializer):
    document = serializers.PrimaryKeyRelatedField(queryset=UploadedFile.objects.all(),
                                                  required=False)
    updated_by = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all(),
                                                    required=False)
    project_version = serializers.PrimaryKeyRelatedField(queryset=ProjectVersion.objects.all(),
                                                    required=False)

    spec_section = serializers.CharField(required=False)
    spec_section_title = serializers.CharField(required=False)
    item_desc = serializers.CharField(required=False)
    para_context = serializers.CharField(required=False)
    para_no = serializers.CharField(required=False, allow_null=True)
    type = serializers.CharField(required=False)
    added_under_submittal_id = serializers.IntegerField(required=False, allow_null=True)



    def create(self, validated_data):
        mf_section, created = MasterFormatSection.objects.get_or_create(
            masterformat_number=validated_data.get('spec_section')
        )
        if validated_data.get('added_under_submittal_id'):
            try:
                added_under_submittal = SubmittalItem.objects.get(id=validated_data.get('added_under_submittal_id'))
                if added_under_submittal.project_id != validated_data.get('project_id'):
                    raise SubmittalItem.DoesNotExist
                document = added_under_submittal.document
                spec_sections = SpecSection.objects.filter(masterformat_section=mf_section, document=document)
                if spec_sections.count() > 0:
                    spec_section = spec_sections.first()
                else:
                    spec_section = SpecSection.objects.create(
                        masterformat_section=mf_section,
                        document=document,
                        custom_section_title=validated_data.get('spec_section_title'),
                    )
            except SubmittalItem.DoesNotExist:
                added_under_submittal = None
                document = None
                spec_section = None
        else:
            added_under_submittal = None
            document = None
            spec_section = None

        if not document:
            sentinel_document = UploadedFile.objects.create(
                project_id=validated_data.get('project_id'),
                project_version=validated_data.get('project_version'),
                name=validated_data.get('spec_section'),
                document_path=validated_data.get('spec_section'),
            )
            document = sentinel_document
            spec_sections = SpecSection.objects.filter(masterformat_section=mf_section, document=document)
            if spec_sections.count() > 0:
                spec_section = spec_sections.first()
            else:
                spec_section = SpecSection.objects.create(
                    masterformat_section=mf_section,
                    document=document,
                    custom_section_title=validated_data.get('spec_section_title'),
                )

        return SubmittalItem.objects.create(
            project_id=validated_data.get('project_id'),
            project_version=validated_data.get('project_version'),
            updated_by=validated_data.get('updated_by'),
            submittal_description=validated_data.get('item_desc'),
            submittal_content=validated_data.get('para_context'),
            paragraph_number=validated_data.get('para_no'),
            submittal_type=validated_data.get('type'),
            masterformat_section=mf_section,
            document=document,
            spec_section=spec_section,
            added_under_submittal=added_under_submittal,
            manually_added=True,
            submittal_number=get_next_submittal_number(
                validated_data.get('project_id'),
                validated_data.get('project_version').id if validated_data.get('project_version') else None
            ),
        )

    def update(self, instance, validated_data):
        if validated_data.get('spec_section'):
            mf_section, created = MasterFormatSection.objects.get_or_create(
                masterformat_number=validated_data.get('spec_section'))
            if not instance.document:
                sentinel_document = UploadedFile.objects.create(
                    project_id=instance.project_id,
                    project_version=instance.project_version,
                    name=validated_data.get('spec_section'),
                    document_path=validated_data.get('spec_section'),
                )
                instance.document = sentinel_document
            spec_sections = SpecSection.objects.filter(masterformat_section=mf_section, document=instance.document)
            if spec_sections.count() > 0:
                spec_section = spec_sections.first()
            else:
                spec_section = SpecSection.objects.create(
                    masterformat_section=mf_section,
                    document=instance.document,
                    custom_section_title=validated_data.get('spec_section_title'),
                )
            instance.masterformat_section = mf_section
            instance.spec_section = spec_section
        if validated_data.get('spec_section_title'):
            if instance.spec_section:
                instance.spec_section.custom_section_title = validated_data.get('spec_section_title')
                instance.spec_section.save()
            else:
                mf_section, created = MasterFormatSection.objects.get_or_create(
                    masterformat_number=validated_data.get('spec_section'))
                if not instance.document:
                    sentinel_document = UploadedFile.objects.create(
                        project=instance.project,
                        project_version=instance.project_version,
                        name=validated_data.get('spec_section_title'),
                        document_path=validated_data.get('spec_section_title'),
                    )
                    instance.document = sentinel_document
                spec_sections = SpecSection.objects.filter(masterformat_section=mf_section, document=instance.document)
                if spec_sections.count() > 0:
                    spec_section = spec_sections.first()
                else:
                    spec_section = SpecSection.objects.create(
                        masterformat_section=mf_section,
                        document=instance.document,
                        custom_section_title=validated_data.get('spec_section_title'),
                    )
                instance.spec_section = spec_section
        if validated_data.get('item_desc'):
            instance.submittal_description = validated_data.get('item_desc')
        if validated_data.get('para_context'):
            instance.submittal_content = validated_data.get('para_context')
        if validated_data.get('para_no'):
            instance.paragraph_number = validated_data.get('para_no')
        if validated_data.get('type'):
            instance.submittal_type = validated_data.get('type')
        instance.updated_by = validated_data.get('updated_by')
        instance.save()
        return instance

    class Meta:
        model = SubmittalItem
        fields = [
            'document',
            'updated_by',
            'spec_section',
            'spec_section_title',
            'item_desc',
            'para_context',
            'project_version',
            'para_no',
            'type',
            'added_under_submittal_id',
        ]


class SubmittalItemListSerializer(serializers.ModelSerializer):
    project_id = serializers.IntegerField(source='project.id', required=False)
    project_version = serializers.PrimaryKeyRelatedField(queryset=ProjectVersion.objects.all(),
                                                    required=False)
    name = serializers.CharField()
    created_by = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all(),
                                                    required=False)
    submittals = serializers.PrimaryKeyRelatedField(queryset=SubmittalItem.objects.all(), many=True,
                                                    required=False)

    def create(self, validated_data):
        validated_data['project'] = Project.objects.get(
            id=self.context['view'].kwargs.get('project_id'))
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)

    class Meta:
        model = SubmittalItemList
        fields = ['id', 'project_id', 'name', 'created_by', 'submittals', 'project_version']


class SubmittalItemFromHighlightSerializer(serializers.ModelSerializer):
    """
    Dedicated serializer for creating SubmittalItems from PDF highlights.
    Uses existing SpecSection to avoid duplicates.
    """
    # Accept SpecSection ID directly
    spec_section_id = serializers.IntegerField(required=True)

    # Submittal item fields
    item_desc = serializers.CharField(required=True)
    para_context = serializers.CharField(required=True)
    type = serializers.CharField(required=True)
    para_no = serializers.CharField(required=False, allow_null=True)

    # Text location fields for PDF highlighting
    text_location = serializers.JSONField(required=False, allow_null=True)
    additional_text_locations = serializers.JSONField(required=False, allow_null=True)

    # Optional fields
    added_under_submittal_id = serializers.IntegerField(required=False, allow_null=True)
    project_version = serializers.PrimaryKeyRelatedField(
        queryset=ProjectVersion.objects.all(),
        required=False,
        allow_null=True
    )



    def create(self, validated_data):
        # Get the spec section by ID
        spec_section_id = validated_data.pop('spec_section_id')
        try:
            spec_section = SpecSection.objects.get(id=spec_section_id)
        except SpecSection.DoesNotExist:
            raise serializers.ValidationError(f"SpecSection with id {spec_section_id} does not exist")

        # Get masterformat_section and document from the spec_section
        mf_section = spec_section.masterformat_section
        document = spec_section.document

        # Get project_id from context (set by view)
        project_id = self.context.get('project_id')

        # Handle added_under_submittal_id if provided
        added_under_submittal = None
        if validated_data.get('added_under_submittal_id'):
            try:
                added_under_submittal = SubmittalItem.objects.get(
                    id=validated_data.pop('added_under_submittal_id')
                )
                if added_under_submittal.project_id != project_id:
                    added_under_submittal = None
            except SubmittalItem.DoesNotExist:
                validated_data.pop('added_under_submittal_id', None)
                added_under_submittal = None

        # Create the SubmittalItem
        return SubmittalItem.objects.create(
            project_id=project_id,
            project_version=validated_data.get('project_version'),
            updated_by=self.context.get('request').user if self.context.get('request') else None,
            submittal_description=validated_data.get('item_desc'),
            submittal_content=validated_data.get('para_context'),
            paragraph_number=validated_data.get('para_no'),
            submittal_type=validated_data.get('type'),
            masterformat_section=mf_section,
            document=document,
            spec_section=spec_section,
            added_under_submittal=added_under_submittal,
            manually_added=True,
            submittal_number=get_next_submittal_number(
                project_id,
                validated_data.get('project_version').id if validated_data.get('project_version') else None
            ),
            text_location=validated_data.get('text_location'),
            additional_text_locations=validated_data.get('additional_text_locations', []),
            parsing_method='UNKNOWN',
            parsing_version='UNKNOWN',
        )

    class Meta:
        model = SubmittalItem
        fields = [
            'spec_section_id',
            'item_desc',
            'para_context',
            'type',
            'para_no',
            'text_location',
            'additional_text_locations',
            'added_under_submittal_id',
            'project_version',
        ]


class TextDiffSerializer(serializers.Serializer):
    type = serializers.CharField()
    value = serializers.CharField()

class SubmittalItemDifferenceSerializer(serializers.Serializer):
    difference_type = serializers.ChoiceField(choices=[
        ('addition', 'Addition'),
        ('deletion', 'Deletion'),
        ('modification', 'Modification'),
        ('unchanged', 'Unchanged'),
    ], read_only=True)
    old_submittal = SubmittalItemReadSerializer(read_only=True, required=False)
    new_submittal = SubmittalItemReadSerializer(read_only=True, required=False)
    content_differences = TextDiffSerializer(many=True, read_only=True, required=False)
    paragraph_number_differences = TextDiffSerializer(many=True, read_only=True, required=False)


class VersionComparisonSerializer(serializers.Serializer):
    old_version = serializers.PrimaryKeyRelatedField(queryset=ProjectVersion.objects.all())
    new_version = serializers.PrimaryKeyRelatedField(queryset=ProjectVersion.objects.all())
    masterformat_number = serializers.CharField()
    differences = SubmittalItemDifferenceSerializer(many=True, read_only=True)


class FilteredVersionComparisonSerializer(serializers.Serializer):
    keyword = serializers.CharField(allow_null=True, required=False)
    only_differences = serializers.BooleanField(default=False)
    old_version = serializers.PrimaryKeyRelatedField(queryset=ProjectVersion.objects.all())
    new_version = serializers.PrimaryKeyRelatedField(queryset=ProjectVersion.objects.all())
    masterformat_numbers_with_desired_differences = serializers.ListField(child=serializers.CharField(), read_only=True)
    comparison = VersionComparisonSerializer(read_only=True, many=True)



class ExcelExportHeaderSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExcelExportHeader
        fields = ['user', 'options', 'updated_at']


# TODO: This should be moved to the top when all the serializers within the file
#       are moved to their own files
from .notices import (
    NoticeMatchSerializer,
    NoticeProcessingCallbackSerializer,
)
