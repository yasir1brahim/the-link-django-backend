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


urlpatterns = [
    path('', include(router.urls)),
    path('upload-file/', views.upload_file, name='upload_file'),
    path('spec-status-webhook/', views.spec_status_webhook, name='spec_status_webhook'),
    path('excel-export-header/upsert/', views.UpsertExcelExportHeaderView.as_view(), name='upsert_excel_export_header'),
    path('excel-export-header/', views.GetExcelExportHeaderView.as_view(), name='get_excel_export_header'),

    # Notices
    path(
        'webhooks/notice-processing/',
        views.NoticeProcessingWebhookView.as_view(),
        name='webhook-notice-processing',
    ),
]


single_project_urlpatterns = [
    path('', include(single_project_router.urls)),
]
