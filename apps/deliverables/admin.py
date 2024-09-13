from django.contrib import admin
from .models import Project, ProjectMembership, Entitlement


class ProjectMembershipInlineAdmin(admin.TabularInline):
    model = ProjectMembership
    list_display = ["user", "role"]


class EntitlementInlineAdmin(admin.TabularInline):
    model = Entitlement
    list_display = ["code_name", "readable_name"]



@admin.register(ProjectMembership)
class ProjectMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "project", "role"]
    list_filter = ["project", "role"]
    search_fields = ["user__email", "project__name"]


@admin.register(Entitlement)
class EntitlementAdmin(admin.ModelAdmin):
    list_display = ["id", "code_name", "readable_name"]
    search_fields = ["code_name", "readable_name"]
    list_filter = ["code_name", "readable_name"]



@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "team", "owner"]
    list_filter = ["name", "team", "owner"]
    search_fields = ["name", "team__name", "owner__email"]
    inlines = (ProjectMembershipInlineAdmin,)
    filter_horizontal = ("entitlements",)