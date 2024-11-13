from dj_rest_auth.serializers import JWTSerializer
from rest_framework import serializers


class LoginResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    detail = serializers.CharField()
    jwt = JWTSerializer(required=False)
    temp_otp_token = serializers.CharField(required=False)


class OtpRequestSerializer(serializers.Serializer):
    temp_otp_token = serializers.CharField()
    otp = serializers.CharField()

class UserStatusUpdateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=True, help_text="The ID of the user to update.")
    is_active = serializers.BooleanField(required=True, help_text="Set to true to activate, false to deactivate.")