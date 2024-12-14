from rest_framework import serializers

class ProcoreFetchAccessTokenSerializer(serializers.Serializer):
    code = serializers.CharField()
    redirect_uri = serializers.CharField()


class ProcoreAccessTokenSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    expires_in = serializers.IntegerField()
    token_type = serializers.CharField()
    created_at = serializers.IntegerField()

