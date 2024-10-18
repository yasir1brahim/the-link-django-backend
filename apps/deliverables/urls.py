from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

app_name = "deliverables"

router = DefaultRouter()
router.register(r'projects', views.ProjectViewSet, basename='project')

single_project_router = DefaultRouter()
single_project_router.register('submittal-items', views.SubmittalItemViewSet, basename='submittal-item')
single_project_router.register('submittal-lists', views.SubmittalItemListViewSet, basename='submittal-list')

urlpatterns = [
    path('', include(router.urls)),
    path('upload-file/', views.upload_file, name='upload_file'),
]

single_project_urlpatterns = [
    path('', include(single_project_router.urls)),
]
