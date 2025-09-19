from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets, mixins
from rest_framework.exceptions import PermissionDenied, ValidationError as DRFValidationError
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework import status
from apps.api.permissions import IsAuthenticatedOrHasUserAPIKey
from rest_framework.decorators import action
from django.core.files.storage import default_storage
from apps.utils.constants import WELCOME_RESET_SUBJECT

from ..invitations import send_invitation, process_invitation
from ..models import Team, Invitation, Membership
from ..permissions import TeamAccessPermissions, TeamModelAccessPermissions
from ..roles import is_admin, is_member, ROLE_ADMIN
from ..serializers import TeamSerializer, TeamListSerializer, InvitationSerializer, MembershipSerializer, InvitedUserResetPasswordSerializer
from apps.users.serializers import CustomPasswordResetSerializer
from rest_framework.viewsets import ViewSet
from apps.users.models import CustomUser as User
import secrets 
import string
from ..emails import send_team_added_notification


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
    list=extend_schema(operation_id="teams_list"),
    retrieve=extend_schema(operation_id="teams_retrieve"),
    update=extend_schema(operation_id="teams_update"),
    partial_update=extend_schema(operation_id="teams_partial_update"),
    upload_logo=extend_schema(operation_id="upload_logo"),
)
class TeamViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet
):
    queryset = Team.objects.all().prefetch_related('flag_set')
    permission_classes = (IsAuthenticatedOrHasUserAPIKey, TeamAccessPermissions)

    def get_serializer_class(self):
        if self.action == 'list':
            return TeamListSerializer
        return TeamSerializer

    def get_queryset(self):
        if self.action == 'list':
            # For list action, use optimized queryset with minimal prefetching
            if self.request.user.is_superuser:
                return Team.objects.all().order_by("name")
            return self.request.user.teams.order_by("name")
        
        # For other actions, use the full queryset with prefetching
        if self.request.user.is_superuser:
            return self.queryset.order_by("name")
        return self.request.user.teams.order_by("name")
    
    
    @action(detail=True, methods=['post'], url_path='upload-logo')
    def upload_logo(self, request, pk=None):
        team = self.get_object()
        file = request.FILES.get('file')

        if not file:
            return Response({'error': 'No file uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

        # Save the file to the media directory
        file_path = default_storage.save(f'logos/{file.name}', file)
        file_url = f"{request.build_absolute_uri('/media/')}{file_path}"

        # Update the team's legacy_logo_url
        team.legacy_logo_url = file_url
        team.save()

        return Response({'file_url': file_url}, status=status.HTTP_201_CREATED)
            
    
@extend_schema_view(
    update=extend_schema(operation_id="memberships_update"),
    partial_update=extend_schema(operation_id="memberships_partial_update"),
    destroy=extend_schema(operation_id="memberships_destroy"),
)
class MembershipViewSet(
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet
):
    queryset = Membership.objects.all()
    serializer_class = MembershipSerializer
    permission_classes = (IsAuthenticatedOrHasUserAPIKey, TeamModelAccessPermissions)

    def get_queryset(self):
        if self.request.user.is_superuser:
            return self.queryset
        # filter queryset based on logged in user
        return self.queryset.filter(team__in=self.request.user.teams.all())


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
    permission_classes = (AnonymousRetrieveOnlyPermission, TeamModelAccessPermissions)

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

    def list(self, request, *args, **kwargs):
        if not request.user.is_admin_for_team(self.team):
            raise PermissionDenied()
        return super().list(request, *args, **kwargs)


@api_view(['POST'])
def api_accept_invitation(request, team_id, invitation_id):
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

class InvitedUserResetPasswordViewSet(ViewSet):
    permission_classes = (AnonymousRetrieveOnlyPermission, TeamModelAccessPermissions)

    def create(self, request):
        """Handle user creation and send password reset email."""
        serializer = InvitedUserResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            email = data['email']
            team_id = data['team_id']
            first_name = data['first_name']
            last_name = data['last_name']
            role = data['role']
            team = self._get_team(team_id)
            user_exists = self._check_user_exists(email)
            if user_exists:
                self._add_existing_user_to_team(request, email, team, role, first_name, last_name)
                return Response({"message": "User has been added to the company. A notification email has been sent."}, 
                                status=status.HTTP_200_OK)
            
            default_password = self._generate_password()
            user = self._create_user(data, default_password)
            self._create_membership(user, team, data['role'])
            self._send_password_reset_email(request, email, default_password)
            return Response({"message": "User created successfully. A password reset email has been sent."}, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def _get_team(self, team_id):
        """Fetch the team or raise a 404 if not found."""
        return get_object_or_404(Team, id=team_id)

    def _check_user_exists(self, email):
        """Check if user exists by email."""
        return User.objects.filter(email=email).exists()
    
    def _generate_password(self):
        """Generate a random password."""
        return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))

    def _create_user(self, data, password):
        """Create and return a new user."""
        return User.objects.create_user(
            username=data['email'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            email=data['email'],
            password=password
        )

    def _create_membership(self, user, team, role):
        """Create team membership."""
        Membership.objects.create(user=user, team=team, role=role)

    def _send_password_reset_email(self, request, email, default_password):
        """Send password reset email."""
        password_reset_serializer = CustomPasswordResetSerializer(data={'email': email, 'password': default_password, 'subject_line': WELCOME_RESET_SUBJECT }, context={'request': request})
        if password_reset_serializer.is_valid():
            password_reset_serializer.save()
        else:
            return Response({"error": "Password reset email failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _send_team_added_notification_email(self, request, user, team, role):
        """Send notification email that user has been added to a team (delegated to helper)."""
        send_team_added_notification(user, team, role, source="api")
        
    def _add_existing_user_to_team(self, request, email, team, role, first_name, last_name):
        """Add existing user to team and send notification email."""
        user = User.objects.get(email=email)
        updates = {}
        if user.first_name != first_name:
            updates['first_name'] = first_name
        if user.last_name != last_name:
            updates['last_name'] = last_name
        if updates:
            for field, value in updates.items():
                setattr(user, field, value)
            user.save()
        membership = Membership.objects.filter(user=user, team=team).first()
        if membership:
            if membership.role != role:
                membership.role = role
                membership.save()
        else:
            Membership.objects.create(user=user, team=team, role=role)
        # Send notification email that user has been added to the team
        self._send_team_added_notification_email(request, user, team, role)