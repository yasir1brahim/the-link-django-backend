import os

from allauth.account import app_settings
from allauth.account.models import EmailAddress
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

def require_email_confirmation():
    return settings.ACCOUNT_EMAIL_VERIFICATION == app_settings.EmailVerificationMethod.MANDATORY


def user_has_confirmed_email_address(user, email):
    try:
        email_obj = EmailAddress.objects.get_for_user(user, email)
        return email_obj.verified
    except EmailAddress.DoesNotExist:
        return False


def validate_profile_picture(value):
    valid_extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".tif",
        ".tiff",
        ".webp",
        ".bmp",
    }
    file_extension = os.path.splitext(value.name)[1].lower()
    if file_extension not in valid_extensions:
        raise ValidationError(
            _("Please upload a valid image file! Supported types are {types}").format(
                types=", ".join(valid_extensions),
            )
        )
    max_file_size = 5242880  # 5 MB limit
    if value.size > max_file_size:
        size_in_mb = value.size // 1024**2
        raise ValidationError(
            _("Maximum file size allowed is 5 MB. Provided file is {size} MB.").format(
                size=size_in_mb,
            )
        )


def get_next_unique_username(model_class, username_value = None):
    base_username = username_value or "user"
    suffix = 1
    while True:
        username = f"{base_username}{suffix}"
        if not model_class.objects.filter(username=username).exists():
            return username
        suffix += 1
    
