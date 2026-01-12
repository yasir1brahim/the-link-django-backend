from django.contrib import admin
from django.contrib.auth.models import User, Group
from apps.teams import models as teams_models
from apps.users import models as users_models
from django.contrib.sites import models as sites_models
from apps.deliverables.models import (Project, ProjectMembership, Entitlement, SubmittalItem,
    UploadedFile, SpecSection, MasterFormatSection,
    SubmittalItemList, ExcelExportHeader
)

class TheLinkAdminSite(admin.AdminSite):
    site_header = 'The Link Admin'

the_link_admin_site = TheLinkAdminSite(name='the_link_admin')

the_link_admin_site.register(User)

the_link_admin_site.register(teams_models.Team)
the_link_admin_site.register(teams_models.Membership)
the_link_admin_site.register(teams_models.Invitation)
the_link_admin_site.register(teams_models.Flag)


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
    list_display = ["id", "name", "team"]
    list_filter = ["name", "team"]
    search_fields = ["name", "team__name"]
    inlines = (ProjectMembershipInlineAdmin,)
    filter_horizontal = ("entitlements",)


@admin.register(SubmittalItem)
class SubmittalItemAdmin(admin.ModelAdmin):
    list_display = ["id", "project", "document", "masterformat_section", "paragraph_number", "submittal_type", "submittal_description"]
    list_filter = ["project", "document", "masterformat_section", "paragraph_number", "submittal_type", "submittal_description"]
    search_fields = ["project__name", "document__name", "masterformat_section__masterformat_number", "paragraph_number", "submittal_type", "submittal_description"]


class SubmittalItemInlineAdmin(admin.TabularInline):
    model = SubmittalItem
    list_display = ["id", "project", "document", "masterformat_section", "paragraph_number", "submittal_type", "submittal_description"]
    list_filter = ["project", "document", "masterformat_section", "paragraph_number", "submittal_type", "submittal_description"]
    search_fields = ["project__name", "document__name", "masterformat_section__masterformat_number", "paragraph_number", "submittal_type", "submittal_description"]


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ["id", "project", "name", "uploaded_by", "created_at"]
    list_filter = ["project", "uploaded_by"]
    search_fields = ["name", "uploaded_by__email", "project__name"]


@admin.register(SpecSection)
class SpecSectionAdmin(admin.ModelAdmin):
    list_display = ["id", "masterformat_section"]
    list_filter = ["masterformat_section"]
    search_fields = ["masterformat_section__masterformat_number"]

@admin.register(MasterFormatSection)
class MasterFormatSectionAdmin(admin.ModelAdmin):
    list_display = ["id", "masterformat_number", "masterformat_description"]
    search_fields = ["masterformat_number", "masterformat_description"]

@admin.register(SubmittalItemList)
class SubmittalItemListAdmin(admin.ModelAdmin):
    list_display = ["id", "project", "name", "created_by"]
    list_filter = ["project", "created_by"]
    search_fields = ["project__name", "name", "created_by__email"]
    filter_horizontal = ("submittals",)

@admin.register(ExcelExportHeader)
class ExcelExportHeaderAdmin(admin.ModelAdmin):
    list_display = ["user", "updated_at"]
    search_fields = ["user__email", ]


the_link_admin_site.register(sites_models.Site)

from allauth.account.models import EmailAddress
the_link_admin_site.register(EmailAddress)
the_link_admin_site.unregister(EmailAddress)
the_link_admin_site.register(EmailAddress)
the_link_admin_site.unregister(EmailAddress)

from rest_framework_api_key.models import APIKey
the_link_admin_site.register(APIKey)
the_link_admin_site.unregister(APIKey)

from django.contrib.auth.models import Group
the_link_admin_site.register(Group)
the_link_admin_site.unregister(Group)


