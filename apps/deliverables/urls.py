from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views
from .views.spec_centric_views import SpecCentricViewSet
from .views import bulk_operations
from .views.pdf_annotation_views import PDFAnnotationViewSet


app_name = "deliverables"


router = DefaultRouter()
router.register(r'projects', views.ProjectViewSet, basename='project')


single_project_router = DefaultRouter()
# submittals
single_project_router.register(
    'submittal-items',
    views.SubmittalItemViewSet,
    basename='submittal-item',
)
single_project_router.register(
    'submittal-lists',
    views.SubmittalItemListViewSet,
    basename='submittal-list',
)
single_project_router.register(
    'semantically-processed-spec-items',
    views.SemanticallyProcessedSpecItemViewSet,
    basename='semantically-processed-spec-item',
)
single_project_router.register(
    'specgpt-chats',
    views.ChatViewSet,
    basename='specgpt-chat',
)
single_project_router.register(
    'ai-generated-logs',
    views.AiGeneratedLogViewSet,
    basename='ai-generated-log',
)
# notices
single_project_router.register(
    'notices',
    views.NoticeViewSet,
    basename='notice-list',
)
# project versions
single_project_router.register(
    'project-versions',
    views.ProjectVersionViewSet,
    basename='project-version',
)
# spec centric view
single_project_router.register(
    'spec-sections',
    SpecCentricViewSet,
    basename='spec-section',
)

#annotation view
single_project_router.register(
    'pdf-annotations',
    PDFAnnotationViewSet,
    basename="pdf-annotations"
)

urlpatterns = [
    path('', include(router.urls)),
    path('upload-file/', views.upload_file, name='upload_file'),
    path('reprocess-document/', views.reprocess_document, name='reprocess_document'),
    path('delete-document/', views.delete_document, name='delete_document'),
    path('download-document/', views.download_document, name='download_document'),
    path('spec-status-webhook/', views.spec_status_webhook, name='spec_status_webhook'),
    path('excel-export-header/upsert/', views.UpsertExcelExportHeaderView.as_view(), name='upsert_excel_export_header'),
    path('excel-export-header/', views.GetExcelExportHeaderView.as_view(), name='get_excel_export_header'),
    path('combine-rows/', views.combine_rows, name='combine_rows'),
    path('version-comparison/', views.get_version_comparison, name='get_version_comparison'),
    path('filtered-version-comparison/', views.get_filtered_version_comparison, name='get_filtered_version_comparison'),
    path('version-comparison-pdf/', views.get_pdf_version_comparison, name='get_pdf_version_comparison'),

    # Notices
    path(
        'webhooks/notice-processing/',
        views.NoticeProcessingWebhookView.as_view(),
        name='webhook-notice-processing',
    ),
    path('procore/access_token/', views.ProcoreFetchAccessTokenView.as_view(), name='procore-fetch-access-token'),
    path('procore/refresh_token/', views.ProcoreRefreshAccessTokenView.as_view(), name='procore-refresh-access-token'),
    path('procore/company_mapping/<int:company_id>/', views.GetProcoreCompanyMappingView.as_view(), name='procore-company-mapping'),
    path('procore/companies/', views.GetProcoreCompaniesView.as_view(), name='procore-companies'),
    path('procore/me/', views.GetCurrentUserProcoreInfoView.as_view(), name='get-current-user-procore-info'),
    path('procore/project_mapping/<int:project_id>/', views.GetProcoreProjectMappingView.as_view(), name='procore-project-mapping'),
    path('procore/project_mapping/', views.SetProcoreProjectMappingView.as_view(), name='set-procore-project-mapping'),
    path('procore/create_submittals/', views.CreateProcoreSubmittalsView.as_view(), name='procore-create-submittals'),
    path('procore/delete_token/', views.DeleteProcoreTokenView.as_view(), name='delete-procore-token'),
    path('procore/projects/<int:procore_company_id>/', views.GetProcoreProjectsView.as_view(), name='procore-projects'),
    path('procore/managers/<int:procore_project_id>/', views.GetProcoreManagersView.as_view(), name='procore-managers'),
    path('procore/company_mapping/', views.CreateProcoreCompanyMappingView.as_view(), name='create-procore-company-mapping'),
    path('procore/submittal_mappings/<int:company_id>/', views.ProcoreSubmittalMappingsView.as_view(), name='procore-submittal-mappings'),

    path('webhooks/full-spec-processing/', views.full_spec_processing_webhook, name='webhook-full-spec-processing'),
    path('webhooks/specgpt-embedding/', views.specgpt_embedding_webhook, name='webhook-specgpt-embedding'),
    path('webhooks/ai-log-generation/', views.ai_log_generation_webhook, name='webhook-ai-log-generation'),
    path('projects/<int:project_id>/spec-sections/', views.get_project_spec_sections, name='get-project-spec-sections'),
    path('spec-sections/<int:section_id>/download/', views.download_spec_section, name='download-spec-section'),
    path('spec-sections/download-multiple/', views.bulk_download_spec_sections, name='download-multiple-spec-sections'),
    path('documents/download-multiple/', views.bulk_download_documents, name='download-multiple-documents'),
    path('documents/reprocess-multiple/', bulk_operations.bulk_reprocess_documents, name='reprocess-multiple-documents'),
    path('documents/delete-multiple/', bulk_operations.bulk_delete_documents, name='delete-multiple-documents'),
    path('projects/<int:project_id>/', include(single_project_router.urls)),
]


single_project_urlpatterns = [
    path('', include(single_project_router.urls)),
]
