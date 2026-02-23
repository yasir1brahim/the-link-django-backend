from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views
from .views.spec_centric_views import SpecCentricViewSet
from .views import bulk_operations
from .views.pdf_annotation_views import PDFAnnotationViewSet
from .views.extracted_data_views import ExtractedDataViewSet
from .views.custom_item_type_views import CustomItemTypeViewSet
from .views.user_highlight_preference_views import UserHighlightPreferenceViewSet
from .views import extraction_note_views
from .views import drawing_views
from .views.drawing_views import DrawingNoteViewSet
from .views.spec_comparison_views import (
    spec_comparison_webhook,
    trigger_spec_comparison,
    get_spec_conflicts,
    get_skipped_notes,
    list_spec_comparisons,
    export_spec_conflicts,
    update_spec_conflict_status,
    spec_conflict_comments,
    spec_conflict_comment_detail,
)


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
# extracted data view
single_project_router.register(
    'extracted-data',
    ExtractedDataViewSet,
    basename='extracted-data'
)
single_project_router.register(
    'custom-item-types',
    CustomItemTypeViewSet,
    basename='custom-item-type'
)
single_project_router.register(
    'highlight-preference',
    UserHighlightPreferenceViewSet,
    basename='highlight-preference'
)
single_project_router.register(
    'drawing-notes',
    DrawingNoteViewSet,
    basename='drawing-note',
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
    path('webhooks/drawing-extraction/', drawing_views.drawing_extraction_webhook, name='drawing-extraction-webhook'),
    path('webhooks/spec-comparison/', spec_comparison_webhook, name='spec-comparison-webhook'),
    path('projects/<int:project_id>/trigger-spec-comparison/', trigger_spec_comparison, name='trigger-spec-comparison'),
    path('projects/<int:project_id>/spec-conflicts/export/', export_spec_conflicts, name='spec-conflicts-export'),
    path('projects/<int:project_id>/spec-conflicts/', get_spec_conflicts, name='spec-conflicts'),
    path('projects/<int:project_id>/spec-conflicts/<int:conflict_id>/status/', update_spec_conflict_status, name='spec-conflict-status-update'),
    path('projects/<int:project_id>/spec-conflicts/<int:conflict_id>/comments/', spec_conflict_comments, name='spec-conflict-comments'),
    path('projects/<int:project_id>/spec-conflicts/<int:conflict_id>/comments/<int:comment_id>/', spec_conflict_comment_detail, name='spec-conflict-comment-detail'),
    path('projects/<int:project_id>/skipped-notes/', get_skipped_notes, name='skipped-notes'),
    path('projects/<int:project_id>/spec-comparisons/', list_spec_comparisons, name='spec-comparisons-list'),
    path('projects/<int:project_id>/spec-sections/', views.get_project_spec_sections, name='get-project-spec-sections'),
    path('spec-sections/<int:section_id>/download/', views.download_spec_section, name='download-spec-section'),
    path('spec-sections/download-multiple/', views.bulk_download_spec_sections, name='download-multiple-spec-sections'),
    path('documents/download-multiple/', views.bulk_download_documents, name='download-multiple-documents'),
    path('documents/reprocess-multiple/', bulk_operations.bulk_reprocess_documents, name='reprocess-multiple-documents'),
    path('documents/delete-multiple/', bulk_operations.bulk_delete_documents, name='delete-multiple-documents'),
    
    # Compass processing for old projects
    path('projects/<int:project_id>/compass-processing-status/', views.get_compass_processing_status, name='compass-processing-status'),
    path('projects/<int:project_id>/trigger-compass-processing/', views.trigger_compass_processing, name='trigger-compass-processing'),
    
    path('projects/<int:project_id>/', include(single_project_router.urls)),

    # Extraction notes (manual nested routes)
    path('projects/<int:project_pk>/extracted-data/<int:extracteddata_pk>/notes/',
         extraction_note_views.ExtractionNoteViewSet.as_view({'get': 'list', 'post': 'create'}),
         name='extractionnote-list'),
    path('projects/<int:project_pk>/extracted-data/<int:extracteddata_pk>/notes/<int:pk>/',
         extraction_note_views.ExtractionNoteViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'put': 'update', 'delete': 'destroy'}),
         name='extractionnote-detail'),
]


single_project_urlpatterns = [
    path('', include(single_project_router.urls)),
]
