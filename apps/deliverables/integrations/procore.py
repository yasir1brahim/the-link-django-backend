import requests

from django.conf import settings
from django.shortcuts import get_object_or_404
from apps.deliverables.models import ProcoreToken
from apps.deliverables.serializers.procore import ProcoreAccessTokenSerializer

GRANT_TYPE_ACCESS_TOKEN = 'authorization_code'
GRANT_TYPE_REFRESH_TOKEN = 'refresh_token'
GRANT_TYPE_REFRESH_TOKEN = 'refresh_token'

class ProcoreException(Exception):
    pass

def get_procore_access_token(code, redirect_uri):
    url = settings.PROCORE_AUTH_BASE_URL + '/oauth/token'
    data = {
        'grant_type': GRANT_TYPE_ACCESS_TOKEN,
        'client_id': settings.PROCORE_CLIENT_ID,
        'client_secret': settings.PROCORE_CLIENT_SECRET,
        'code': code,
        'redirect_uri': redirect_uri or settings.PROCORE_REDIRECT_URL
    }
    response = requests.post(url, data=data)
    return response

def get_procore_access_token_from_refresh_token(refresh_token):
    url = settings.PROCORE_AUTH_BASE_URL + '/oauth/token'
    data = {
        'grant_type': GRANT_TYPE_REFRESH_TOKEN,
        'client_id': settings.PROCORE_CLIENT_ID,
        'client_secret': settings.PROCORE_CLIENT_SECRET,
        'redirect_uri': settings.PROCORE_REDIRECT_URL,
        'refresh_token': refresh_token
    }
    response = requests.post(url, data=data)
    return response

def get_fresh_token_for_user(user) -> ProcoreToken:
    existing_token = get_object_or_404(ProcoreToken, user=user)
    if not existing_token.is_expired():
        return existing_token
    
    procore_response = get_procore_access_token(existing_token.code, existing_token.redirect_uri)
    if procore_response.status_code != 200:
        raise ProcoreException(procore_response.text)
    access_token_serializer = ProcoreAccessTokenSerializer(data=procore_response.json())
    access_token_serializer.is_valid(raise_exception=True)
    return ProcoreToken.objects.create(
        user=user,
        access_token=access_token_serializer.validated_data['access_token'],
        refresh_token=access_token_serializer.validated_data['refresh_token'],
        expires_in=access_token_serializer.validated_data['expires_in'],
        token_type=access_token_serializer.validated_data['token_type'],
        code=existing_token.code,
    )

def get_companies(procore_token):
    url = settings.PROCORE_BASE_URL + '/rest/v1.0/companies'
    headers = {'Authorization': "Bearer " + procore_token}
    response = requests.get(url, headers=headers)
    return response
