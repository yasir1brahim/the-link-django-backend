from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseRedirect, Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import DisallowedHost
from health_check.views import MainView

from apps.teams.decorators import login_and_team_required


def home(request):
    return HttpResponse("The Link API")


@login_and_team_required
def team_home(request, team_slug):
    assert request.team.slug == team_slug
    return render(
        request,
        "web/app_home.html",
        context={
            "team": request.team,
            "active_tab": "dashboard",
            "page_title": _("{team} Dashboard").format(team=request.team),
        },
    )


def simulate_error(request):
    raise Exception("This is a simulated error.")


def simulate_invalid_http_host_error(request):
    raise DisallowedHost("This is a simulated invalid HTTP host error.")


class HealthCheck(MainView):
    def get(self, request, *args, **kwargs):
        tokens = settings.HEALTH_CHECK_TOKENS
        if tokens and request.GET.get("token") not in tokens:
            raise Http404
        return super().get(request, *args, **kwargs)
