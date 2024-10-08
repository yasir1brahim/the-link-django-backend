import json
import boto3

from rest_framework import serializers
from .models import Project, ProjectMembership, PROJECT_MEMBERSHIP_ROLE_CHOICES
from apps.users.serializers import CustomUserSerializer
from apps.users.models import CustomUser
from apps.teams.models import Team
from apps.deliverables.models import SubmittalItem, UploadedFile, SpecSection, SubmittalItemList
from drf_spectacular.utils import extend_schema_field
from django.conf import settings

from .constants import masterformat_to_section_title_map

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
        fields = ['id', 'name', 'description', 'team', 'owner', 'members', 'entitlements',
                   'user_limit', 'status', 'start_date', 'end_date', 'is_archived']

    members = ProjectMembershipSerializer(source="project_memberships", many=True)
    team = serializers.ReadOnlyField(source="team.id")
    owner = CustomUserSerializer()
    entitlements = serializers.SerializerMethodField()
    user_limit = serializers.ReadOnlyField()

    def get_entitlements(self, obj) -> list[str]:
        project_level_entitlements = obj.entitlements.values_list('code_name', flat=True)
        if project_level_entitlements:
            return project_level_entitlements
        else:
            return obj.team.entitlements.values_list('code_name', flat=True)


class ProjectWriteSerializer(BaseProjectSerializer):
    owner = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all())
    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all())

    def validate(self, data):
        owner = data.get('owner')
        team = data.get('team')
        members = data.get('members')
        
        if owner and team and not owner.is_member_of_team(team):
            raise serializers.ValidationError("The owner must be a member of the team.")
        
        if members:
            for member in members:
                if not member.is_member_of_team(team):
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
            ProjectMembership.objects.create(project=project, **membership_data)

        return project



class ProjectReadSerializer(BaseProjectSerializer):
    pass


class FileUploadSerializer(serializers.Serializer):
    files = serializers.ListField(child=serializers.FileField())
    project_id = serializers.IntegerField()



class SubmittalItemReadSerializer(serializers.ModelSerializer):
    additional_text_locations = serializers.JSONField()
    doc_id = serializers.IntegerField(source='document.id')
    doc_link = serializers.SerializerMethodField()
    full_edit = serializers.SerializerMethodField()
    id = serializers.IntegerField()
    item_desc = serializers.CharField(source='submittal_description')
    para_context = serializers.CharField(source='submittal_content')
    para_no = serializers.CharField(source='paragraph_number')
    project_id = serializers.IntegerField(source='project.id')
    section_title = serializers.SerializerMethodField()
    spec_section = serializers.CharField(source='spec_section.masterformat_section.masterformat_number')
    submittal_number = serializers.CharField()
    text_loc = serializers.JSONField(source='text_location')
    type = serializers.CharField(source='submittal_type')

    def get_section_title(self, obj):
        return obj.spec_section.masterformat_section.masterformat_description or masterformat_to_section_title_map.get(obj.spec_section.masterformat_section.masterformat_number, 'Custom Title')
        
    def get_doc_link(self, obj):
        # TBL-76: Older documents using the legacy parsing approach have a full cloudfront URL stored in the doc_link column.
        # New documents just store the S3 object key in the doc_link column. To handle this, we return the Cloudfront URL if it exists,
        # and if not, we return a presigned URL generated from the S3 object key
        if obj.document.document_path.startswith("https://") and "cloudfront.net" in obj.document.document_path:
            return obj.document.document_path
        else:
            return s3.generate_presigned_url('get_object', Params={'Bucket': settings.S3_BUCKET, 'Key': obj.document.document_path}, ExpiresIn=3600)
            
    def get_full_edit(self, obj):
        if obj.updated_by.id != 1:
            return "true"
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
    document = serializers.PrimaryKeyRelatedField(queryset=UploadedFile.objects.all())
    spec_section = serializers.PrimaryKeyRelatedField(queryset=SpecSection.objects.all())
    updated_by = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all())

    class Meta:
        model = SubmittalItem
        fields = [
            'document',
            'spec_section',
            'paragraph_number',
            'submittal_type',
            'submittal_description',
            'submittal_content',
            'submittal_number',
            'text_location',
            'additional_text_locations',
            'updated_by',
        ]


class SubmittalItemListSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubmittalItemList
        fields = '__all__'