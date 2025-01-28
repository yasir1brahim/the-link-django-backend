from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views


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


urlpatterns = [
    path('', include(router.urls)),
    path('upload-file/', views.upload_file, name='upload_file'),
    path('spec-status-webhook/', views.spec_status_webhook, name='spec_status_webhook'),
    path('excel-export-header/upsert/', views.UpsertExcelExportHeaderView.as_view(), name='upsert_excel_export_header'),
    path('excel-export-header/', views.GetExcelExportHeaderView.as_view(), name='get_excel_export_header'),
    path('combine-rows/', views.combine_rows, name='combine_rows'),

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
]


single_project_urlpatterns = [
    path('', include(single_project_router.urls)),
]
