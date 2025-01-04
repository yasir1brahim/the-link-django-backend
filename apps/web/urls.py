from django.urls import path
from django.views.generic import TemplateView

from . import views

app_name = "web"
urlpatterns = [
    path("", views.home, name="home"),
    path("health/", views.HealthCheck.as_view(), name="health_check"),
]
