from rest_framework import serializers

from .models import CustomUser

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.models import Site

class CustomUserSerializer(serializers.ModelSerializer):
    """
    Basic serializer to pass CustomUser details to the front end.
    Extend with any fields your app needs.
    """

    class Meta:
        model = CustomUser
        fields = ("id", "first_name", "last_name", "email", "avatar_url", "get_display_name", "is_superuser")

class CustomPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, required=False)

    def validate_email(self, value):
        """Validate the provided email to ensure it is associated with an existing user."""
        try:
            user = get_user_model().objects.get(email=value)
        except get_user_model().DoesNotExist:
            raise serializers.ValidationError("No user associated with this email address.")
        return user

    def get_protocol(self):
        """Get the protocol (http or https) based on the settings."""
        return "https" if settings.USE_HTTPS else "http"

    def save(self):
        """Generate a password reset URL and send a password reset email to the user."""
        user = self.validated_data['email']
        default_password = self.validated_data.get('password')
        
        uidb64 = urlsafe_base64_encode(str(user.pk).encode('utf-8'))
        token = default_token_generator.make_token(user)

        current_site = Site.objects.get(id=settings.SITE_ID)
        domain = current_site.domain
        protocol = self.get_protocol()
        
        password_reset_url = f"{protocol}://{domain}/password-reset/confirm/{uidb64}/{token}/"

        subject = "Password Reset Request"
        context = {
            'user': user,
            'password_reset_url': password_reset_url,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'password': default_password
        }

        email_template = 'account/email/password_reset_key_message.html'
        body = render_to_string(email_template, context)
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)

class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password1 = serializers.CharField(min_length=8)
    new_password2 = serializers.CharField(min_length=8)

    def validate(self, attrs):
        """Ensure that the two password fields match"""
        if attrs['new_password1'] != attrs['new_password2']:
            raise serializers.ValidationError("Passwords don't match.")
        return attrs

    def validate_token(self, value):
        """Validate the reset token and user"""
        uidb64 = self.initial_data.get('uid')
        token = self.initial_data.get('token')

        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = get_user_model().objects.get(pk=uid)
        except (TypeError, ValueError, get_user_model().DoesNotExist):
            raise serializers.ValidationError("Invalid user or token.")

        if not default_token_generator.check_token(user, token):
            raise serializers.ValidationError("Invalid or expired token.")
        return value

    def save(self):
        """Save the new password to the user"""
        user = self.instance
        user.set_password(self.validated_data['new_password1'])
        user.save()