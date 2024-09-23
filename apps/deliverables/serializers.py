from rest_framework import serializers
from .models import Project, ProjectMembership, PROJECT_MEMBERSHIP_ROLE_CHOICES
from apps.users.serializers import CustomUserSerializer


class ProjectMembershipSerializer(serializers.ModelSerializer):
    user_id = serializers.ReadOnlyField(source="user.id")
    first_name = serializers.ReadOnlyField(source="user.first_name")
    last_name = serializers.ReadOnlyField(source="user.last_name")

    class Meta:
        model = ProjectMembership
        fields = ['user_id', 'first_name', 'last_name', 'role']


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['id', 'name', 'description', 'team', 'owner', 'members', 'entitlements',
                   'user_limit', 'status', 'start_date', 'end_date', 'is_archived']

    members = ProjectMembershipSerializer(source="project_memberships", many=True)
    team = serializers.ReadOnlyField(source="team.id")
    owner = CustomUserSerializer()
    entitlements = serializers.SerializerMethodField()
    user_limit = serializers.ReadOnlyField()

    def get_entitlements(self, obj):
        project_level_entitlements = obj.entitlements.values_list('code_name', flat=True)
        if project_level_entitlements:
            return project_level_entitlements
        else:
            return obj.team.entitlements.values_list('code_name', flat=True)

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
