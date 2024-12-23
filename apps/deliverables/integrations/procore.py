import requests
import json

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

def get_me(procore_token):
    url = settings.PROCORE_BASE_URL + '/rest/v1.0/me'
    headers = {'Authorization': "Bearer " + procore_token}
    response = requests.get(url, headers=headers)
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

def get_status(company_id, procore_token):
    url = settings.PROCORE_BASE_URL + '/rest/v1.0/companies/' + str(company_id) + '/submittal_statuses'
    headers = {'Authorization': "Bearer " + procore_token}
    response = requests.get(url, headers=headers)
    return response

def get_spec_divisions(project_id, procore_token):
    url = settings.PROCORE_BASE_URL + '/rest/v1.0/specification_section_divisions?project_id=' + str(project_id)
    headers = {'Authorization': "Bearer " + procore_token}
    response = requests.get(url, headers=headers)
    return response


def get_spec_sections(project_id, procore_token):
    url = settings.PROCORE_BASE_URL + '/rest/v1.0/specification_sections?project_id=' + str(project_id)
    headers = {'Authorization': "Bearer " + procore_token}
    response = requests.get(url, headers=headers)
    return response

def get_projects(company_id, procore_token):
    url = settings.PROCORE_BASE_URL + '/rest/v1.0/projects?company_id=' + str(company_id)
    headers = {'Authorization': "Bearer " + procore_token}
    response = requests.get(url, headers=headers)
    return response

def get_managers(project_id, procore_token):
    url = settings.PROCORE_BASE_URL + '/rest/v1.0/projects/' + str(project_id) + '/submittals/potential_submittal_managers'
    headers = {'Authorization': "Bearer " + procore_token}
    response = requests.get(url, headers=headers)
    return response

def create_spec_division(division_number, project_id, procore_token):
    payload = json.dumps({
        "specification_section_division": {
            "number": division_number,
            "description": "Div " + division_number
        }
    })
    headers = {
        'Content-Type': 'application/json',
        'Authorization': "Bearer " + procore_token
    }
    url = settings.PROCORE_BASE_URL + '/rest/v1.0/specification_section_divisions?project_id=' + str(project_id)
    response = requests.post(url, headers=headers, data=payload)
    return response

def create_spec_section(spec_section, division_id, project_id, procore_token):
    payload = json.dumps({
        "specification_section": {
            "number": spec_section,
            "specification_section_division_id": division_id,
            "description": ""
        }
    })
    headers = {
        'Content-Type': 'application/json',
        'Authorization': "Bearer " + procore_token
    }
    url = settings.PROCORE_BASE_URL + '/rest/v1.0/specification_sections?project_id=' + str(project_id)
    response = requests.post(url, headers=headers, data=payload)
    return response

def get_submittal_types(procore_company_id, procore_token):
    url = settings.PROCORE_BASE_URL + '/rest/v1.0/companies/' + str(procore_company_id) + '/submittal_types'
    headers = {'Authorization': "Bearer " + procore_token}
    response = requests.get(url, headers=headers)
    return response

def create_submittal(
    submittal_content,
    paragraph_number,
    procore_spec_section_id,
    procore_status_id,
    procore_submittal_manager_id,
    submittal_title,
    submittal_type,
    project_id,
    procore_token
):
    payload = json.dumps({
        "submittal": {
            "description": submittal_content,
            "number": paragraph_number,
            "specification_section_id": procore_spec_section_id,
            "status_id": procore_status_id,
            "submittal_manager_id": procore_submittal_manager_id,
            "title": submittal_title,
            "type": submittal_type
        }
    })
    headers = {
        'Content-Type': 'application/json',
        'Authorization': "Bearer " + procore_token
    }
    url = settings.PROCORE_BASE_URL + '/rest/v1.0/projects/' + str(project_id) + "/submittals"
    response = requests.post(url, headers=headers, data=payload)
    return response