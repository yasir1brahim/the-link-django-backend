from allauth.mfa.totp.internal.auth import TOTP
from allauth.mfa.utils import is_mfa_enabled
from allauth.mfa.models import Authenticator
from apps.teams.permissions import TeamAccessPermissions
from apps.teams.roles import ROLE_ADMIN, ROLE_MEMBER
from apps.teams.models import Team, Membership as TeamMembership
from dj_rest_auth.serializers import JWTSerializer
from dj_rest_auth.views import LoginView
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from allauth.socialaccount.adapter import get_adapter
from allauth.core import context
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from dj_rest_auth.registration.views import SocialLoginView
from allauth.socialaccount.providers.microsoft.views import MicrosoftGraphOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client


from apps.users.models import CustomUser
from .serializers import LoginResponseSerializer, OtpRequestSerializer, UserStatusUpdateSerializer
import uuid
from django.core.cache import cache


class LoginViewWith2fa(LoginView):
    """
    Custom login view that checks if 2FA is enabled for the user.
    """

    @extend_schema(
        responses={
            status.HTTP_200_OK: LoginResponseSerializer,
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.user = serializer.validated_data["user"]
        if is_mfa_enabled(self.user, [Authenticator.Type.TOTP]):
            # Generate a temporary token and store it with the user object
            temp_token = str(uuid.uuid4())
            cache.set(temp_token, self.user.id, timeout=300)  # set a token that will be valid for 5 minutes
            api_auth_serializer = LoginResponseSerializer(
                data={
                    "status": "otp_required",
                    "detail": "OTP required for 2FA",
                    "temp_otp_token": temp_token,
                }
            )
            api_auth_serializer.is_valid(raise_exception=True)
            # use a different status code to make it easier for API clients to handle this case
            return Response(api_auth_serializer.data, status=200)
        else:
            super_response = super().post(request, *args, **kwargs)
            if super_response.status_code == status.HTTP_200_OK:
                # rewrap login responses to match our serializer schema
                wrapped_jwt_data = {
                    "status": "success",
                    "detail": "User logged in.",
                    "jwt": super_response.data,
                }
                return Response(wrapped_jwt_data, status=200)
            return super_response


@extend_schema(tags=["api"])
class VerifyOTPView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = OtpRequestSerializer

    @extend_schema(
        responses={200: JWTSerializer},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        temp_token = serializer.validated_data["temp_otp_token"]
        otp = serializer.validated_data["otp"]

        user_id = cache.get(temp_token)
        if not user_id:
            return Response(
                {"status": "token_expired", "detail": "Invalid temporary token"}, status=status.HTTP_401_UNAUTHORIZED
            )

        user = CustomUser.objects.get(id=user_id)
        if user and TOTP(Authenticator.objects.get(user=user, type=Authenticator.Type.TOTP)).validate_code(otp):
            # OTP is valid, generate JWT tokens
            refresh = RefreshToken.for_user(user)
            return Response(
                JWTSerializer(
                    {
                        "user": user,
                        "refresh": str(refresh),
                        "access": str(refresh.access_token),
                    }
                ).data,
                status=status.HTTP_200_OK,
            )
        else:
            # OTP is invalid
            return Response({"status": "invalid_otp", "detail": "Invalid OTP code"}, status=status.HTTP_400_BAD_REQUEST)


class UserStatusUpdateView(APIView):
    permission_classes = [IsAuthenticated, TeamAccessPermissions]

    def patch(self, request, *args, **kwargs):
        status_serializer = UserStatusUpdateSerializer(data=request.data)
        if status_serializer.is_valid():
            target_user_id = status_serializer.validated_data['user_id']
            new_active_status = status_serializer.validated_data['is_active']
            
            try:
                target_user = CustomUser.objects.get(id=target_user_id)
                target_user_memberships = TeamMembership.objects.filter(user=target_user)
                if not target_user_memberships.exists():
                    return Response({"error": "User is not part of any team"}, status=status.HTTP_400_BAD_REQUEST)
                admin_team_memberships = TeamMembership.objects.filter(user=request.user, role=ROLE_ADMIN, team__in=target_user_memberships.values_list('team', flat=True))
                
                if not admin_team_memberships.exists():
                    return Response({"error": "You do not have permission to update this user's status"}, status=status.HTTP_403_FORBIDDEN)
                
                target_user.is_active = new_active_status
                target_user.save()
                return Response({"message": "User status updated successfully"}, status=status.HTTP_200_OK)
            except CustomUser.DoesNotExist:
                return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response(status_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class CustomOAuth2Client(OAuth2Client):
    def __init__(
        self,
        request,
        consumer_key,
        consumer_secret,
        access_token_method,
        access_token_url,
        callback_url,
        _scope,  # This is fix for incompatibility between django-allauth==65.3.1 and dj-rest-auth==7.0.1
        scope_delimiter=" ",
        headers=None,
        basic_auth=False,
    ):
        super().__init__(
            request,
            consumer_key,
            consumer_secret,
            access_token_method,
            access_token_url,
            callback_url,
            scope_delimiter,
            headers,
            basic_auth,
        )


class MicrosoftSSOSocialAccountAdapter(DefaultSocialAccountAdapter):
    # force return True for email authentication to fix issue with multple apps
    # This is fine since we are using SSO and the email is verified by Microsoft
    def can_authenticate_by_email(self, login, email):
        return True
    
    def get_provider(self, request, provider, client_id=None):
        if request.path and '/ellisdon/microsoft/login/callback/' in request.path.lower():
            return super().get_provider(request, provider, client_id=settings.ELLIS_DON_SSO_CLIENT_ID)
        elif request.path and '/the_link/microsoft/login/callback/' in request.path.lower():
            return super().get_provider(request, provider, client_id=settings.THE_LINK_SSO_CLIENT_ID)
        else:
            return super().get_provider(request, provider, client_id)

    


class EllisDonMicrosoftGraphOAuth2Adapter(MicrosoftGraphOAuth2Adapter):
    def get_provider(self):
        return get_adapter(self.request).get_provider(
            self.request, provider=self.provider_id, client_id=settings.ELLIS_DON_SSO_CLIENT_ID
        )
    
    def _build_tenant_url(self, path):
        app = get_adapter().get_app(context.request, provider=self.provider_id, client_id=settings.ELLIS_DON_SSO_CLIENT_ID)
        tenant = app.settings.get("tenant", "common")
        login_url = app.settings.get("login_url", "https://login.microsoftonline.com")
        return f"{login_url}/{tenant}{path}"
    
    @property
    def profile_url(self):
        app = get_adapter().get_app(context.request, provider=self.provider_id, client_id=settings.ELLIS_DON_SSO_CLIENT_ID)
        graph_url = app.settings.get("graph_url", "https://graph.microsoft.com")
        return f"{graph_url}/v1.0/me"
    
    def can_authenticate_by_email(self, login, email):
        """
        Returns ``True`` iff  authentication by email is active for this login/email.

        This can be configured with a ``"email_authentication"`` key in the provider
        app settings, or a ``"VERIFIED_EMAIL"`` in the global provider settings
        (``SOCIALACCOUNT_PROVIDERS``).
        """
        ret = None
        provider = self.get_provider()
        if provider.app:
            ret = provider.app.settings.get("email_authentication")
        if ret is None:
            ret = settings.EMAIL_AUTHENTICATION or provider.get_settings().get(
                "EMAIL_AUTHENTICATION", False
            )
        return ret


class TheLinkMicrosoftGraphOAuth2Adapter(MicrosoftGraphOAuth2Adapter):
    def get_provider(self):
        return get_adapter(self.request).get_provider(
            self.request, provider=self.provider_id, client_id=settings.THE_LINK_SSO_CLIENT_ID
        )
    
    def _build_tenant_url(self, path):
        app = get_adapter().get_app(context.request, provider=self.provider_id, client_id=settings.THE_LINK_SSO_CLIENT_ID)
        tenant = app.settings.get("tenant", "common")
        login_url = app.settings.get("login_url", "https://login.microsoftonline.com")
        return f"{login_url}/{tenant}{path}"
    
    @property
    def profile_url(self):
        app = get_adapter().get_app(context.request, provider=self.provider_id, client_id=settings.THE_LINK_SSO_CLIENT_ID)
        graph_url = app.settings.get("graph_url", "https://graph.microsoft.com")
        return f"{graph_url}/v1.0/me"
    
    def can_authenticate_by_email(self, login, email):
        """
        Returns ``True`` iff  authentication by email is active for this login/email.

        This can be configured with a ``"email_authentication"`` key in the provider
        app settings, or a ``"VERIFIED_EMAIL"`` in the global provider settings
        (``SOCIALACCOUNT_PROVIDERS``).
        """
        ret = None
        provider = self.get_provider()
        if provider.app:
            ret = provider.app.settings.get("email_authentication")
        if ret is None:
            ret = settings.EMAIL_AUTHENTICATION or provider.get_settings().get(
                "EMAIL_AUTHENTICATION", False
            )
        return ret

# First define a view class for Microsoft login
class EllisDonMicrosoftLogin(SocialLoginView):
    adapter_class = EllisDonMicrosoftGraphOAuth2Adapter
    client_class = CustomOAuth2Client
    callback_url = settings.FRONTEND_BASE_URL + '/ellisdon/microsoft/login/callback/'
    
class TheLinkMicrosoftLogin(SocialLoginView):
    adapter_class = TheLinkMicrosoftGraphOAuth2Adapter
    client_class = CustomOAuth2Client
    callback_url = settings.FRONTEND_BASE_URL + '/the_link/microsoft/login/callback/'

@api_view(['GET'])
@permission_classes([AllowAny])
def microsoft_login(request):
    """
    Initiate Microsoft login and return authorization URL
    """
    from allauth.socialaccount.providers.microsoft.provider import MicrosoftGraphProvider
    from allauth.socialaccount.models import SocialApp
    from allauth.socialaccount.adapter import get_adapter
    
    # Get client_id from request params if provided
    organization_domain = request.GET.get('organization_domain')
    authorize_url = None
    callback_url = None
    
    try:
        if not organization_domain or  organization_domain not in settings.DOMAINS_CONFIGURED_FOR_SSO:
            return Response({'error': f"Organization domain {organization_domain} not configured for SSO"}, status=400)
        
        if organization_domain == 'ellisdon.com':
            client_id = settings.ELLIS_DON_SSO_CLIENT_ID
            provider = 'microsoft'
            callback_url = settings.FRONTEND_BASE_URL + '/ellisdon/microsoft/login/callback/'
        elif organization_domain == 'thelink.ai':
            client_id = settings.THE_LINK_SSO_CLIENT_ID
            provider = 'microsoft'
            callback_url = settings.FRONTEND_BASE_URL + '/the_link/microsoft/login/callback/'
        else:
            raise ValueError(f"Organization domain {organization_domain} not configured for SSO")
        
        app = get_adapter().get_app(request, provider=provider, client_id=client_id)
        
        if provider == 'microsoft':
            provider = MicrosoftGraphProvider(request, app=app)
            oauth2_adapter = provider.get_oauth2_adapter(request)

            def _build_tenant_url_with_specific_app(app, path):
                tenant = app.settings.get("tenant", "common")
                login_url = app.settings.get("login_url", "https://login.microsoftonline.com")
                return f"{login_url}/{tenant}{path}"
            access_token_url = _build_tenant_url_with_specific_app(app, "/oauth2/v2.0/token")
            authorize_url = _build_tenant_url_with_specific_app(app, "/oauth2/v2.0/authorize")
            # Constructing a custom OAuth2Client so we can set the access_token_url manually
            # The default MicrosoftGraphOAuth2Adapter does not work with multiple Microsoft apps
            client = OAuth2Client(
                request,
                app.client_id,
                app.secret,
                oauth2_adapter.access_token_method,
                access_token_url,
                callback_url,
                scope_delimiter=oauth2_adapter.scope_delimiter,
                headers=oauth2_adapter.headers,
                basic_auth=oauth2_adapter.basic_auth,
            )
            # Override the callback URL to use the frontend URL
            client.callback_url = callback_url

        auth_params = provider.get_auth_params()
        pkce_params = provider.get_pkce_params()
        code_verifier = pkce_params.pop("code_verifier", None)
        auth_params.update(pkce_params)

        scope = provider.get_scope()

        auth_url = client.get_redirect_url(authorize_url or oauth2_adapter.authorize_url, scope, auth_params)
        return Response({'auth_url': auth_url})
    except SocialApp.DoesNotExist:
        return Response(
            {'error': 'SSO Authentication is not configured correctly.'},
            status=500
        )


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def the_link_microsoft_callback(request):
    """
    Handle the Microsoft OAuth callback using dj-rest-auth
    """

    view = TheLinkMicrosoftLogin.as_view()
    response = view(request._request)
    if response.status_code == status.HTTP_200_OK:
        user_id = response.data['user']['id']
        user = CustomUser.objects.get(id=user_id)
        if user.email.endswith(settings.THE_LINK_SSO_ORGANIZATION_DOMAIN):
            the_link_organization = Team.objects.get(sso_domain=settings.THE_LINK_SSO_ORGANIZATION_DOMAIN)
            the_link_team_membership, created = TeamMembership.objects.get_or_create(user=user, team=the_link_organization, role=ROLE_MEMBER)
            # rewrap login responses to match our serializer schema
            wrapped_jwt_data = {
                "status": "success",
                "detail": "User logged in.",
                "jwt": response.data,
            }
            return Response(wrapped_jwt_data, status=200)
        else:
            return Response({"error": "User email address is not registered at thelink.ai"}, status=status.HTTP_403_FORBIDDEN)
    return response
    

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def ellisdon_microsoft_callback(request):
    """
    Handle the Microsoft OAuth callback using dj-rest-auth
    """

    view = EllisDonMicrosoftLogin.as_view()
    response = view(request._request)
    if response.status_code == status.HTTP_200_OK:
        user_id = response.data['user']['id']
        user = CustomUser.objects.get(id=user_id)
        if user.email.endswith(settings.ELLIS_DON_SSO_ORGANIZATION_DOMAIN):
            ellis_don_organization = Team.objects.get(sso_domain=settings.ELLIS_DON_SSO_ORGANIZATION_DOMAIN)
            ellis_don_team_membership, created = TeamMembership.objects.get_or_create(user=user, team=ellis_don_organization, role=ROLE_MEMBER)
            # rewrap login responses to match our serializer schema
            wrapped_jwt_data = {
                "status": "success",
                "detail": "User logged in.",
                "jwt": response.data,
            }
            return Response(wrapped_jwt_data, status=200)
        else:
            return Response({"error": "User email address is not registered at ellisdon.com"}, status=status.HTTP_403_FORBIDDEN)
    return response
    