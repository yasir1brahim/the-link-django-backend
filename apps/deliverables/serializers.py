import json
import boto3

from rest_framework import serializers
from apps.users.serializers import CustomUserSerializer
from apps.users.models import CustomUser
from apps.teams.models import Team
from apps.deliverables.models import SubmittalItem, UploadedFile, SpecSection, SubmittalItemList, MasterFormatSection, DocProcessingStatus
from drf_spectacular.utils import extend_schema_field
from django.conf import settings
from django.db.models import Case, When, IntegerField

from .constants import masterformat_to_section_title_map
from .models import (
    PROJECT_MEMBERSHIP_ROLE_CHOICES,
    Project,
    ProjectMembership,
    ExcelExportHeader,

    NoticeExcerpt,
    NoticeMatch,
)


s3 = boto3.client(
    "s3",
    region_name=settings.AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
)


class ProjectMembershipSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(source="user.id", queryset=CustomUserSerializer.Meta.model.objects.all())
    first_name = serializers.ReadOnlyField(source="user.first_name")
    last_name = serializers.ReadOnlyField(source="user.last_name")
    display_name = serializers.ReadOnlyField(source="user.get_display_name")

    class Meta:
        model = ProjectMembership
        fields = ['user_id', 'first_name', 'last_name', 'display_name', 'role']


class BaseProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['id', 'name', 'description', 'team', 'members', 'entitlements',
                   'user_limit', 'status', 'start_date', 'end_date', 'is_archived', 
                   'project_number', 'project_type']

    members = ProjectMembershipSerializer(source="project_memberships", many=True, required=False)
    team = serializers.ReadOnlyField(source="team.id")
    entitlements = serializers.SerializerMethodField(read_only=True)
    user_limit = serializers.ReadOnlyField()

    def get_entitlements(self, obj) -> list[str]:
        # Handle case when obj is a dictionary (during validation)
        if isinstance(obj, dict):
            return []
        project_level_entitlements = obj.entitlements.values_list('code_name', flat=True)
        if project_level_entitlements:
            return project_level_entitlements
        else:
            return obj.team.entitlements.values_list('code_name', flat=True)


class ProjectWriteSerializer(BaseProjectSerializer):
    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all())

    def validate(self, data):
        team = data.get('team')
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
        print(validated_data)
        memberships_data = validated_data.pop('project_memberships', [])
        # Update project fields
        for attr, value in validated_data.items():
            print(attr, value)
            setattr(instance, attr, value)
        instance.save()

        # Update project memberships
        existing_members = {membership.user.id: membership for membership in instance.project_memberships.all()}
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
        fields = ['id', 'masterformat_number', 'processing_status']

class DocumentSerializer(serializers.ModelSerializer):
    document_id = serializers.IntegerField(source="id")
    document_name = serializers.CharField(source="name")
    document_status = serializers.CharField(source="processing_status")
    document_subsections = DocumentSubsectionSerializer(source="specsection_set", many=True)
    
    class Meta:
        model = UploadedFile
        fields = ['document_id', 'document_name', 'document_status', 'created_at', 'updated_at', 'document_subsections']

class ProjectReadSerializer(BaseProjectSerializer):
    doc_parsed = serializers.SerializerMethodField()
    document_details = serializers.SerializerMethodField()

    def get_doc_parsed(self, obj):
        return obj.uploadedfile_set.count()
    
    def get_document_details(self, obj):
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
        ).order_by("status_order", '-created_at')
        return DocumentSerializer(queryset, many=True).data

    
    class Meta:
        model = Project
        fields = BaseProjectSerializer.Meta.fields + ['doc_parsed', 'document_details']


class FileUploadSerializer(serializers.Serializer):
    files = serializers.ListField(child=serializers.FileField())
    project_id = serializers.IntegerField()



class SubmittalItemReadSerializer(serializers.ModelSerializer):
    additional_text_locations = serializers.JSONField()
    doc_id = serializers.IntegerField(source='document.id', allow_null=True)
    doc_link = serializers.SerializerMethodField()
    full_edit = serializers.SerializerMethodField()
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

    def get_section_title(self, obj):
        return obj.masterformat_section.masterformat_description or masterformat_to_section_title_map.get(obj.masterformat_section.masterformat_number, 'Custom Title')
        
    def get_doc_link(self, obj):
        # TBL-76: Older documents using the legacy parsing approach have a full cloudfront URL stored in the doc_link column.
        # New documents just store the S3 object key in the doc_link column. To handle this, we return the Cloudfront URL if it exists,
        # and if not, we return a presigned URL generated from the S3 object key
        if not obj.document:
            return ""
        if obj.document.document_path.startswith("https://") and "cloudfront.net" in obj.document.document_path:
            return obj.document.document_path
        else:
            return s3.generate_presigned_url('get_object', Params={'Bucket': settings.S3_BUCKET, 'Key': obj.document.document_path}, ExpiresIn=3600)
            
    def get_full_edit(self, obj):
        try:
            if obj.updated_by.id != 1:
                return "true"
        except AttributeError:
            return "false"
        return "false"

    class Meta:
        model = SubmittalItem
        fields = [
            'additional_text_locations',
            'doc_id',
            'doc_link',
            'full_edit',
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
        ]


class SubmittalItemWriteSerializer(serializers.ModelSerializer):
    document = serializers.PrimaryKeyRelatedField(queryset=UploadedFile.objects.all(), required=False)
    updated_by = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all(), required=False)

    spec_section = serializers.CharField(required=False)
    item_desc = serializers.CharField(required=False)
    para_context = serializers.CharField(required=False)
    para_no = serializers.CharField(required=False)
    type = serializers.CharField(required=False)

    def create(self, validated_data):
        mf_section = MasterFormatSection.objects.get(masterformat_number=validated_data.get('spec_section'))
        return SubmittalItem.objects.create(
            project_id=validated_data.get('project_id'),
            updated_by=validated_data.get('updated_by'),
            submittal_description=validated_data.get('item_desc'),
            submittal_content=validated_data.get('para_context'),
            paragraph_number=validated_data.get('para_no'),
            submittal_type=validated_data.get('type'),
            masterformat_section=mf_section,
        )

    def update(self, instance, validated_data):
        if validated_data.get('spec_section'):
            mf_section, created = MasterFormatSection.objects.get_or_create(masterformat_number=validated_data.get('spec_section'))
        instance.masterformat_section = mf_section
        if validated_data.get('item_desc'):
            instance.submittal_description = validated_data.get('item_desc')
        if validated_data.get('para_context'):
            instance.submittal_content = validated_data.get('para_context')
        if validated_data.get('para_no'):
            instance.paragraph_number = validated_data.get('para_no')
        if validated_data.get('type'):
            instance.submittal_type = validated_data.get('type')
        instance.save()
        return instance

    class Meta:
        model = SubmittalItem
        fields = [
            'document',
            'updated_by',
            'spec_section',
            'item_desc',
            'para_context',
            'para_no',
            'type',
        ]


class SubmittalItemListSerializer(serializers.ModelSerializer):
    project_id = serializers.IntegerField(source='project.id', required=False)
    name = serializers.CharField()
    created_by = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all(), required=False)
    submittals = serializers.PrimaryKeyRelatedField(queryset=SubmittalItem.objects.all(), many=True, required=False)

    def create(self, validated_data):
        validated_data['project'] = Project.objects.get(id=self.context['view'].kwargs.get('project_id'))
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)

    class Meta:
        model = SubmittalItemList
        fields = ['id', 'project_id', 'name', 'created_by', 'submittals']


class ExcelExportHeaderSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExcelExportHeader
        fields = ['user', 'options', 'updated_at']


# region notices
# TODO:
#   - Split `serializers.py` into a module
#   - move this region into a separate file

class NoticeExcerptSerializer(serializers.ModelSerializer):

    class Meta:
        model = NoticeExcerpt
        fields = [
            'anchor',
            'lines',
        ]


class NoticeMatchSerializer(serializers.ModelSerializer):
    document = serializers.PrimaryKeyRelatedField(
        queryset=UploadedFile.objects.all(),
        required=True,
    )
    project = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.all(),
        required=True,
    )
    notice_type = serializers.CharField(required=False)
    notice_type_match = serializers.CharField(required=False)

    class Meta:
        model = NoticeMatch
        fields = [
            'document',
            'project',
            'notice_type',
            'notice_type_match',
        ]


class NoticeProcessingCallbackSerializer(serializers.Serializer):
    document = serializers.PrimaryKeyRelatedField(
        queryset=UploadedFile.objects.all(),
        required=True,
    )
    excerpts = NoticeExcerptSerializer(many=True, required=True)
    matches = NoticeMatchSerializer(many=True, required=True)

    def validate(self, attrs):
        # TODO: Validate `excerpt_ids` match to provided local IDs
        pass

    def create(self, validated_data):
        # TODO: Save `validated_data['document']` to all the matches & excerpts
        pass

# endregion notices
