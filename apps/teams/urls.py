from django.urls import path
from . import views

from rest_framework import routers


app_name = "teams"

urlpatterns = [
    path("", views.manage_teams, name="teams_home"),
    path("manage/", views.manage_teams, name="manage_teams"),
    path("manage/<path:path>", views.manage_teams, name="manage_teams"),
    # invitation acceptance views
    path("invitation/<slug:invitation_id>/", views.accept_invitation, name="accept_invitation"),
    path("invitation/<slug:invitation_id>/signup/", views.SignupAfterInvite.as_view(), name="signup_after_invite"),
]

team_urlpatterns = (
    [
        # team management views
        path("", views.manage_team, name="manage_team"),
        path("members/<int:membership_id>/", views.team_membership_details, name="team_membership_details"),
        path("members/<int:membership_id>/remove/", views.remove_team_membership, name="remove_team_membership"),
        path("invite/<slug:invitation_id>/", views.resend_invitation, name="resend_invitation"),
        path("api/invitations/<slug:invitation_id>/accept/", views.api_accept_invitation, name="api_accept_invitation"),
    ],
    "single_team",
)


# DRF config for API views (required for React Teams, implementation, optional otherwise)
router = routers.DefaultRouter()
router.register("api/teams", views.TeamViewSet)
router.register("api/memberships", views.MembershipViewSet)
router.register("api/invited-user", views.InvitedUserResetPasswordViewSet, basename="invited-user")
urlpatterns += router.urls

single_team_router = routers.DefaultRouter()
single_team_router.register("api/invitations", views.InvitationViewSet)
team_urlpatterns[0].extend(single_team_router.urls)
