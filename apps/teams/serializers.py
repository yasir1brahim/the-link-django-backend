from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from drf_writable_nested import WritableNestedModelSerializer

from apps.subscriptions.serializers import SubscriptionSerializer

from .helpers import get_next_unique_team_slug
from .models import Team, Membership, Invitation, Flag
from .roles import is_admin
from django.contrib.auth import get_user_model

from apps.deliverables.serializers import BaseProjectSerializer
from apps.utils.feature_flags import get_active_flags_for_team


class MembershipSerializer(serializers.ModelSerializer):
    user_id = serializers.ReadOnlyField(source="user.id")
    first_name = serializers.CharField(source="user.first_name", required=False)
    last_name = serializers.CharField(source="user.last_name", required=False)
    display_name = serializers.ReadOnlyField(source="user.get_display_name")
    email = serializers.ReadOnlyField(source="user.email")
    is_active = serializers.ReadOnlyField(source="user.is_active")

    class Meta:
        model = Membership
        fields = ("id", "user_id", "first_name", "last_name", "display_name", "role", "email", "is_active")

    def update(self, instance, validated_data):
        validated_user_data = validated_data.pop("user", {})
        instance.user.first_name = validated_user_data.pop("first_name", instance.user.first_name)
        instance.user.last_name = validated_user_data.pop("last_name", instance.user.last_name)
        instance.user.save()
        instance.role = validated_data.pop("role", instance.role)
        instance.save()
        return instance


class InvitationSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField()
    invited_by = serializers.ReadOnlyField(source="invited_by.get_display_name")

    class Meta:
        model = Invitation
        fields = ("id", "team", "email", "role", "invited_by", "is_accepted")
    
class TeamSerializer(WritableNestedModelSerializer, serializers.ModelSerializer):
    slug = serializers.SlugField(
        required=False,
        validators=[UniqueValidator(queryset=Team.objects.all())],
    )
    members = serializers.SerializerMethodField()
    invitations = InvitationSerializer(many=True, read_only=True, source="pending_invitations")
    project_count = serializers.SerializerMethodField()
    is_admin = serializers.SerializerMethodField()
    subscription = SubscriptionSerializer(source="wrapped_subscription", read_only=True)
    projects = serializers.SerializerMethodField()
    active_flags = serializers.SerializerMethodField(read_only=True)
    active_count = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = (
            "id",
            "name",
            "slug",
            "members",
            "invitations",
            "project_count",
            "is_admin",
            "subscription",
            "has_active_subscription",
            "legacy_logo_url",
            "projects",
            "active_flags",
            "active_count"
        )

    def get_members(self, obj) -> list[Membership]:
        return MembershipSerializer(obj.sorted_memberships, many=True).data

    def get_project_count(self, obj) -> int:
        return obj.project_set.count()

    def get_is_admin(self, obj) -> bool:
        return is_admin(self.context["request"].user, obj)

    def create(self, validated_data):
        team_name = validated_data.get("name", None)
        validated_data["slug"] = validated_data.get("slug", get_next_unique_team_slug(team_name))
        return super().create(validated_data)
    
    def get_projects(self, obj):
        return BaseProjectSerializer(obj.project_set.all(), many=True).data
    
    def get_active_flags(self, obj):
        return get_active_flags_for_team(obj)

    def get_active_count(self, obj):
        return obj.project_set.filter(is_archived=False).count()

class InvitedUserResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    team_id = serializers.IntegerField()
    role = serializers.CharField()