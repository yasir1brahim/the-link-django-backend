from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError as DRFValidationError
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from apps.api.permissions import IsAuthenticatedOrHasUserAPIKey

from ..invitations import send_invitation, process_invitation
from ..models import Team, Invitation
from ..permissions import TeamAccessPermissions, TeamModelAccessPermissions
from ..roles import is_admin, is_member, ROLE_ADMIN
from ..serializers import TeamSerializer, InvitationSerializer


class AnonymousRetrieveOnlyPermission(BasePermission):
    def has_permission(self, request, view):
        if view.action == 'retrieve':
            return True
        return request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        if view.action == 'retrieve':
            return True
        return request.user.is_authenticated and request.user.is_member_of_team(obj.team)



@extend_schema_view(
    create=extend_schema(operation_id="teams_create"),
    list=extend_schema(operation_id="teams_list"),
    retrieve=extend_schema(operation_id="teams_retrieve"),
    update=extend_schema(operation_id="teams_update"),
    partial_update=extend_schema(operation_id="teams_partial_update"),
    destroy=extend_schema(operation_id="teams_destroy"),
)
class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = (IsAuthenticatedOrHasUserAPIKey, TeamAccessPermissions)

    def get_queryset(self):
        # filter queryset based on logged in user
        return self.request.user.teams.order_by("name")

    def perform_create(self, serializer):
        # ensure logged in user is set on the model during creation
        team = serializer.save()
        team.members.add(self.request.user, through_defaults={"role": ROLE_ADMIN})


@extend_schema(tags=["teams"])
@extend_schema_view(
    create=extend_schema(operation_id="invitations_create"),
    list=extend_schema(operation_id="invitations_list"),
    retrieve=extend_schema(operation_id="invitations_retrieve"),
    update=extend_schema(operation_id="invitations_update"),
    partial_update=extend_schema(operation_id="invitations_partial_update"),
    destroy=extend_schema(operation_id="invitations_destroy"),
)
class InvitationViewSet(viewsets.ModelViewSet):
    queryset = Invitation.objects.all()
    serializer_class = InvitationSerializer
    permission_classes = (AnonymousRetrieveOnlyPermission,)

    @property
    def team(self):
        return get_object_or_404(Team, id=self.kwargs["team_id"])

    def _ensure_team_match(self, team):
        if team != self.team:
            raise DRFValidationError("Team set in invitation must match URL")

    def _ensure_no_pending_invite(self, team, email):
        if Invitation.objects.filter(team=team, email=email, is_accepted=False):
            raise DRFValidationError(
                {
                    # this mimics the same validation format used by the serializer so it can work easily on the front end.
                    "email": [
                        _(
                            'There is already a pending invitation for {}. You can resend it by clicking "Resend Invitation".'
                        ).format(email)
                    ]
                }
            )

    def get_queryset(self):
        # filter queryset based on logged in user and team
        return self.queryset.filter(team=self.team)

    def perform_create(self, serializer):
        # ensure logged in user is set on the model during creation
        # and can access the underlying team
        team = serializer.validated_data["team"]
        self._ensure_team_match(team)
        self._ensure_no_pending_invite(team, serializer.validated_data["email"])

        # unfortunately, the permissions class doesn't handle creation well
        # https://www.django-rest-framework.org/api-guide/permissions/#limitations-of-object-level-permissions
        if not is_admin(self.request.user, team):
            raise PermissionDenied()

        invitation = serializer.save(invited_by=self.request.user)
        send_invitation(invitation)


@api_view(['POST'])
def api_accept_invitation(request, team_id, invitation_id):
    print(request)
    print(team_id)
    print(invitation_id)
    invitation = get_object_or_404(Invitation, id=invitation_id)

    if invitation.is_accepted:
        return Response({'detail': 'Invitation already accepted.'}, status=status.HTTP_400_BAD_REQUEST)
    user = request.user
    if is_member(user, invitation.team):
        return Response({'detail': 'User is already a member of the team.'}, status=status.HTTP_400_BAD_REQUEST)
    process_invitation(invitation, user)
    invitation.is_accepted = True
    invitation.save()
    return Response({'detail': 'Invitation accepted.'}, status=status.HTTP_200_OK)
