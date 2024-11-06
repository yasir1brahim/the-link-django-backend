from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from drf_writable_nested import WritableNestedModelSerializer

from apps.subscriptions.serializers import SubscriptionSerializer

from .helpers import get_next_unique_team_slug
from .models import Team, Membership, Invitation, TeamProfile
from .roles import is_admin
from django.contrib.auth import get_user_model

class MembershipSerializer(serializers.ModelSerializer):
    user_id = serializers.ReadOnlyField(source="user.id")
    first_name = serializers.ReadOnlyField(source="user.first_name")
    last_name = serializers.ReadOnlyField(source="user.last_name")
    display_name = serializers.ReadOnlyField(source="user.get_display_name")
    email = serializers.ReadOnlyField(source="user.email")

    class Meta:
        model = Membership
        fields = ("id", "user_id", "first_name", "last_name", "display_name", "role", "email")


class InvitationSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField()
    invited_by = serializers.ReadOnlyField(source="invited_by.get_display_name")

    class Meta:
        model = Invitation
        fields = ("id", "team", "email", "role", "invited_by", "is_accepted")


User = get_user_model()
class TeamProfileSerializer(serializers.ModelSerializer):
    account_owner_name = serializers.CharField(write_only=False, required=False)
    class Meta:
        model = TeamProfile
        fields = ['account_owner', 'account_owner_name', 'email_id', 'address', 'account_id', 'password', 'phone']
        extra_kwargs = {'password': {'write_only': True}}

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        owner = instance.account_owner
        representation['account_owner_name'] = (owner.get_full_name() or owner.username or owner.email if owner else None )
        return representation
    
    def _get_user_by_email(self, email):
        try:
            return User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email_id": "User with this email does not exist."})

    def _update_user_name(self, user, full_name):
        name_parts = full_name.split(" ", 1)
        user.first_name = name_parts[0]
        user.last_name = name_parts[1] if len(name_parts) > 1 else ""
        user.save()

    def update(self, instance, validated_data):
        account_owner_name = validated_data.pop('account_owner_name', None)
        account_owner_email = validated_data.get('email_id')
        if account_owner_email:
            owner = self._get_user_by_email(account_owner_email)
        if account_owner_name:
            self._update_user_name(owner, account_owner_name)
        instance.account_owner = owner
        return super().update(instance, validated_data)
    
class TeamSerializer(WritableNestedModelSerializer, serializers.ModelSerializer):
    slug = serializers.SlugField(
        required=False,
        validators=[UniqueValidator(queryset=Team.objects.all())],
    )
    members = serializers.SerializerMethodField()
    invitations = InvitationSerializer(many=True, read_only=True, source="pending_invitations")
    project_count = serializers.SerializerMethodField()
    dashboard_url = serializers.ReadOnlyField()
    is_admin = serializers.SerializerMethodField()
    subscription = SubscriptionSerializer(source="wrapped_subscription", read_only=True)
    profile = TeamProfileSerializer()

    class Meta:
        model = Team
        fields = (
            "id",
            "name",
            "slug",
            "members",
            "invitations",
            "project_count",
            "dashboard_url",
            "is_admin",
            "subscription",
            "has_active_subscription",
            "profile",
            "legacy_logo_url",
        )

    def get_members(self, obj) -> list[Membership]:
        if is_admin(self.context["request"].user, obj):
            return MembershipSerializer(obj.sorted_memberships, many=True).data
        return MembershipSerializer(
            [m for m in obj.sorted_memberships if m.user == self.context["request"].user],
            many=True,
        ).data

    def get_project_count(self, obj) -> int:
        return obj.project_set.count()

    def get_is_admin(self, obj) -> bool:
        return is_admin(self.context["request"].user, obj)

    def create(self, validated_data):
        team_name = validated_data.get("name", None)
        validated_data["slug"] = validated_data.get("slug", get_next_unique_team_slug(team_name))
        return super().create(validated_data)
