from allauth.mfa.totp.internal.auth import TOTP
from allauth.mfa.utils import is_mfa_enabled
from allauth.mfa.models import Authenticator
from apps.teams.permissions import TeamAccessPermissions
from apps.teams.roles import ROLE_ADMIN
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

from django.conf import settings
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

# First define a view class for Microsoft login
class MicrosoftLogin(SocialLoginView):
    adapter_class = MicrosoftGraphOAuth2Adapter
    client_class = CustomOAuth2Client
    callback_url = settings.FRONTEND_BASE_URL + '/microsoft/login/callback/'
    # callback_url = None  # This will be set from the request data
    
    # def get_client(self, request, app):
    #     callback_url = request.data.get('redirect_uri')
    #     return self.client_class(
    #         request,
    #         app.client_id,
    #         app.secret,
    #         self.adapter_class.access_token_url,
    #         callback_url
    #     )


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
    client_id = request.GET.get('client_id')
    
    try:
        if client_id:
            # Use specific client_id if provided
            app = get_adapter().get_app(request, provider='microsoft', client_id=client_id)
        else:
            # Otherwise, get the default Microsoft app
            app = get_adapter().get_app(request, provider='microsoft')
            
        provider = MicrosoftGraphProvider(request, app=app)
        oauth2_adapter = provider.get_oauth2_adapter(request)
        client = oauth2_adapter.get_client(request, app)
        # Override the callback URL to use the frontend URL
        client.callback_url = settings.FRONTEND_BASE_URL + '/microsoft/login/callback/'

        auth_params = provider.get_auth_params()
        pkce_params = provider.get_pkce_params()
        code_verifier = pkce_params.pop("code_verifier", None)
        auth_params.update(pkce_params)

        scope = provider.get_scope()

        auth_url = client.get_redirect_url(oauth2_adapter.authorize_url, scope, auth_params)
        return Response({'auth_url': auth_url})
    except SocialApp.DoesNotExist:
        return Response(
            {'error': 'Microsoft authentication is not configured correctly.'},
            status=500
        )

@api_view(['POST'])
@permission_classes([AllowAny])
def microsoft_callback(request):
    """
    Handle the Microsoft OAuth callback using dj-rest-auth
    """
    # code = request.data.get('code')
    # redirect_uri = request.data.get('redirect_uri')
    
    # if not code:
    #     return Response({'error': 'Authorization code is required'}, status=400)
    
    # # Prepare data for SocialLoginView
    # data = {
    #     'code': code,
    #     'redirect_uri': redirect_uri
    # }
    # print(data)
    
    # # Create request with the code
    # request.data.update(data)
    
    # Use the SocialLoginView to handle the login
    view = MicrosoftLogin.as_view()
    response = view(request._request)
    print(response)
    
    return response