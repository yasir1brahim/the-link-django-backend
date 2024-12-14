import requests

from django.conf import settings

GRANT_TYPE_ACCESS_TOKEN = 'authorization_code'
GRANT_TYPE_REFRESH_TOKEN = 'refresh_token'

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