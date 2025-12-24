import logging
from django.contrib import admin
from django.db.models import Count, Q
from waffle.admin import FlagAdmin as WaffleFlagAdmin

from .models import Team, Membership, Invitation, Flag

from django.conf import settings
from apps.users.serializers import CustomPasswordResetSerializer
from apps.utils.constants import WELCOME_RESET_SUBJECT
from .emails import send_team_added_notification

logger = logging.getLogger(__name__)

@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "team", "role", "created_at"]
    list_filter = ["team"]
    autocomplete_fields = ["user"]

    def save_model(self, request, obj, form, change):
        is_new = obj.pk is None
        super().save_model(request, obj, form, change)
        # Only act on creations done via the Membership admin
        if is_new:
            self._send_membership_created_email(obj)

    def _send_membership_created_email(self, membership: Membership):
        user = membership.user
        team = membership.team
        role = membership.role
        total_memberships = Membership.objects.filter(user=user).count()

        if total_memberships > 1:
            # Existing user being added to another team → send notification email
            send_team_added_notification(user, team, role, source="admin")
        else:
            # First team for this user → send password reset email (no default password)
            serializer = CustomPasswordResetSerializer(
                data={'email': user.email, 'subject_line': WELCOME_RESET_SUBJECT},
                context={'request': None}
            )
            if serializer.is_valid():
                serializer.save()


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ["id", "team", "email", "role", "is_accepted"]
    list_filter = ["team", "is_accepted"]


class MembershipInlineAdmin(admin.TabularInline):
    model = Membership
    list_display = ["user", "role"]
    autocomplete_fields = ["user"]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "active_members", "subscription"]
    list_filter = ["created_at"]
    ordering = ("-created_at",)
    search_fields = ["name", "slug"]
    inlines = (MembershipInlineAdmin,)
    filter_horizontal = ("entitlements",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(active_member_count=Count("members", filter=Q(members__is_active=True)))

    def active_members(self, obj):
        return obj.active_member_count

    active_members.admin_order_field = "active_member_count"

    def save_formset(self, request, form, formset, change):
        if formset.model is Membership:
            instances = formset.save(commit=False)
            new_memberships = []
            for obj in instances:
                is_new = obj.pk is None
                obj.save()
                if is_new:
                    new_memberships.append(obj)
            try:
                for obj in getattr(formset, "deleted_objects", []) or []:
                    logger.info(f"Deleting Membership instance: {obj}")
                    obj.delete()
            except Exception as e:
                # If something goes wrong during deletion, don't block rest of save
                logger.error(f"Error Deleting Membership instance: {str(e)}")
                pass

            formset.save_m2m()

            # Send emails for newly created memberships via Team admin
            for membership in new_memberships:
                # Reuse same logic as MembershipAdmin
                MembershipAdmin._send_membership_created_email(self, membership)
        else:
            formset.save()


MAX_TEAMS_DISPLAY = 3


@admin.display(description="Teams")
def teams_list(flag):
    """Return set of teams, for display in admin list. If there are more than
    MAX_TEAMS_DISPLAY, show that many followed by ellipsis."""
    if flag.teams.count() > MAX_TEAMS_DISPLAY:
        return list([team.name for team in flag.teams.all()][:MAX_TEAMS_DISPLAY] + ["..."])
    return [team.name for team in flag.teams.all()]



@admin.display(description="Projects")
def projects_list(flag):
    """Return set of projects, for display in admin list. If there are more than
    MAX_TEAMS_DISPLAY, show that many followed by ellipsis."""
    if flag.projects.count() > MAX_TEAMS_DISPLAY:
        return list([project.name for project in flag.projects.all()][:MAX_TEAMS_DISPLAY] + ["..."])
    return [project.name for project in flag.projects.all()]


class ProjectInlineAdmin(admin.TabularInline):
    model = Flag.projects.through
    extra = 1
    verbose_name = "Project"
    verbose_name_plural = "Projects"
    autocomplete_fields = ['project']

class TeamInlineAdmin(admin.TabularInline):
    model = Flag.teams.through
    extra = 1
    verbose_name = "Team"
    verbose_name_plural = "Teams"
    autocomplete_fields = ['team']


class UserInlineAdmin(admin.TabularInline):
    model = Flag.users.through
    extra = 1
    verbose_name = "User"
    verbose_name_plural = "Users"
    autocomplete_fields = ["customuser"]

@admin.display(description="Active Teams")
def active_teams_count(flag):
    return flag.teams.count()

@admin.display(description="Active Projects")
def active_projects_count(flag):
    return flag.projects.count()

@admin.display(description="Active Users")
def active_users_count(flag):
    return flag.users.count()


@admin.register(Flag)
class FlagAdmin(WaffleFlagAdmin):
    list_display = [
        field for field in WaffleFlagAdmin.list_display
        if field not in ['teams', 'projects', 'users']
    ] + [active_teams_count, active_projects_count, active_users_count]
    inlines = [UserInlineAdmin, ProjectInlineAdmin, TeamInlineAdmin]

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields.pop('teams', None)
        form.base_fields.pop('projects', None)
        form.base_fields.pop('users', None)
        return form