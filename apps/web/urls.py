from django.urls import path
from django.views.generic import TemplateView

from . import views

app_name = "web"
urlpatterns = [
    path("", views.home, name="home"),
    path("simulate-generic-500-error/", views.simulate_error, name="simulate_error"),
    path("simulate-invalid-http-host-error/", views.simulate_invalid_http_host_error, name="simulate_invalid_http_host_error"),
    path("health/", views.HealthCheck.as_view(), name="health_check"),
]
