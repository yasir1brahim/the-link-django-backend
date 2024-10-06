from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

app_name = "deliverables"

router = DefaultRouter()
router.register(r'projects', views.ProjectViewSet, basename='project')
router.register(r'<int:project_id>/submittal-items', views.SubmittalItemViewSet, basename='submittal-item')

urlpatterns = [
    path('', include(router.urls)),
    path('upload_file', views.upload_file, name='upload_file'),
]