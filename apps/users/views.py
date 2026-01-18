from .adapter import user_has_valid_totp_device
from allauth.account.utils import send_email_confirmation
from allauth.socialaccount.models import SocialAccount

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import translation, timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.api.models import UserAPIKey

from .forms import CustomUserChangeForm, UploadAvatarForm
from .helpers import require_email_confirmation, user_has_confirmed_email_address
from .models import CustomUser

from .serializers import CustomPasswordResetSerializer, PasswordResetConfirmSerializer
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth import get_user_model
from django.utils.http import urlsafe_base64_decode
from rest_framework.permissions import AllowAny


def validate_reset_token(uidb64, token):
    """Validate password reset token, return (user, error_type) tuple.

    Returns:
        (user, None) if token is valid
        (None, 'expired') if token is expired or invalid
        (None, 'invalid') if uid is malformed or user doesn't exist
    """
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = get_user_model().objects.get(pk=uid)
        if default_token_generator.check_token(user, token):
            return user, None
        return None, 'expired'
    except (TypeError, ValueError, get_user_model().DoesNotExist):
        return None, 'invalid'


@login_required
def profile(request):
    if request.method == "POST":
        form = CustomUserChangeForm(request.POST, instance=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            user_before_update = CustomUser.objects.get(pk=user.pk)
            need_to_confirm_email = (
                user_before_update.email != user.email
                and require_email_confirmation()
                and not user_has_confirmed_email_address(user, user.email)
            )
            if need_to_confirm_email:
                # don't change it but instead send a confirmation email
                # email will be changed by signal when confirmed
                new_email = user.email
                send_email_confirmation(request, user, signup=False, email=new_email)
                user.email = user_before_update.email
                # recreate the form to avoid populating the previous email in the returned page
                form = CustomUserChangeForm(instance=user)
            user.save()

            user_language = user.language
            if user_language and user_language != translation.get_language():
                translation.activate(user_language)
            if user.timezone != timezone.get_current_timezone():
                if user.timezone:
                    timezone.activate(user.timezone)
                else:
                    timezone.deactivate()
            messages.success(request, _("Profile successfully saved."))
    else:
        form = CustomUserChangeForm(instance=request.user)
    return render(
        request,
        "account/profile.html",
        {
            "form": form,
            "active_tab": "profile",
            "page_title": _("Profile"),
            "api_keys": request.user.api_keys.filter(revoked=False),
            "social_accounts": SocialAccount.objects.filter(user=request.user),
            "user_has_valid_totp_device": user_has_valid_totp_device(request.user),
            "now": timezone.now(),
            "current_tz": timezone.get_current_timezone(),
        },
    )


@login_required
@require_POST
def upload_profile_image(request):
    user = request.user
    form = UploadAvatarForm(request.POST, request.FILES)
    if form.is_valid():
        user.avatar = request.FILES["avatar"]
        user.save()
        return HttpResponse(_("Success!"))
    else:
        readable_errors = ", ".join(str(error) for key, errors in form.errors.items() for error in errors)
        return JsonResponse(status=403, data={"errors": readable_errors})


@login_required
def create_api_key(request):
    api_key, key = UserAPIKey.objects.create_key(
        name=f"{request.user.get_display_name()[:40]} API Key", user=request.user
    )
    messages.success(
        request,
        _("API Key created. Your key is: {key}. Save this somewhere safe - you will only see it once!").format(
            key=key,
        ),
    )
    return HttpResponseRedirect(reverse("users:user_profile"))


@login_required
@require_POST
def revoke_api_key(request):
    key_id = request.POST.get("key_id")
    api_key = request.user.api_keys.get(id=key_id)
    api_key.revoked = True
    api_key.save()
    messages.success(
        request,
        _("API Key {key} has been revoked. It can no longer be used to access the site.").format(
            key=api_key.prefix,
        ),
    )
    return HttpResponseRedirect(reverse("users:user_profile"))

class CustomPasswordResetView(APIView):
    permission_classes = [AllowAny]
    def post(self, request, *args, **kwargs):
        """Handle the POST request for sending a password reset link to the user's email."""
        serializer = CustomPasswordResetSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({'message': 'Password reset link sent to email.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class CustomPasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    def post(self, request, *args, **kwargs):
        """Handle the POST request for resetting the password based on the provided token."""
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            uidb64 = serializer.validated_data['uid']
            token = serializer.validated_data['token']
            new_password = serializer.validated_data['new_password1']

            user, error = validate_reset_token(uidb64, token)
            if user:
                user.set_password(new_password)
                user.save()
                return Response({'message': 'Password reset successfully.'}, status=status.HTTP_200_OK)
            elif error == 'expired':
                return Response({'error': 'Invalid token.'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({'error': 'Invalid user.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetTokenValidationView(APIView):
    """Validate password reset token without resetting password."""
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """Handle GET request to validate token"""
        uidb64 = request.query_params.get('uid')
        token = request.query_params.get('token')

        if not uidb64 or not token:
            return Response(
                {'error': 'Missing uid or token parameter.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user, error = validate_reset_token(uidb64, token)
        if user:
            return Response(
                {'valid': True, 'message': 'Token is valid.'},
                status=status.HTTP_200_OK
            )
        elif error == 'expired':
            return Response(
                {
                    'valid': False,
                    'error': 'expired',
                    'message': 'Password reset link has expired or is invalid.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        else:
            return Response(
                {
                    'valid': False,
                    'error': 'invalid',
                    'message': 'Invalid password reset link.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )