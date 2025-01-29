from django.contrib import admin
from .models import (Project, ProjectMembership, Entitlement, SubmittalItem,
    UploadedFile, SpecSection, MasterFormatSection,
    SubmittalItemList, ExcelExportHeader, ProjectVersion
)


class ProjectMembershipInlineAdmin(admin.TabularInline):
    model = ProjectMembership
    list_display = ["user", "role"]

class ProjectVersionInlineAdmin(admin.TabularInline):
    model = ProjectVersion
    list_display = ["project", "version_name"]

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
    inlines = (ProjectMembershipInlineAdmin, ProjectVersionInlineAdmin)
    filter_horizontal = ("entitlements",)


@admin.register(ProjectVersion)
class ProjectVersionAdmin(admin.ModelAdmin):
    list_display = ["id", "project", "version_name"]
    list_filter = ["project", "version_name"]
    search_fields = ["project__name", "version_name"]


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
