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


class ProcoreCompanyMappingSerializer(serializers.Serializer):
    procore_company_id = serializers.IntegerField(required=False, allow_null=True)
    procore_company_name = serializers.CharField(required=False, allow_null=True)


class ProcoreCompanySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()
    logo_url = serializers.URLField()
    pcn_business_experience = serializers.BooleanField()
    my_company = serializers.BooleanField()


class ProcoreMeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    login = serializers.CharField()
    name = serializers.CharField()


class ProcoreProjectMappingSerializer(serializers.Serializer):
    procore_project_id = serializers.IntegerField()
    procore_project_name = serializers.CharField()
    submittal_manager_id = serializers.CharField()
    procore_submittal_manager_name = serializers.CharField()
    procore_company_id = serializers.IntegerField(required=False, allow_null=True)
    procore_company_name = serializers.CharField(required=False, allow_null=True)


class CreateProcoreProjectMappingSerializer(serializers.Serializer):
    project_id = serializers.IntegerField()
    procore_project_id = serializers.IntegerField()
    procore_project_name = serializers.CharField()
    procore_submittal_manager_id = serializers.CharField()
    procore_submittal_manager_name = serializers.CharField()
    procore_company_id = serializers.IntegerField(required=False, allow_null=True)
    procore_company_name = serializers.CharField(required=False, allow_null=True)

class ProcoreSubmittalSerializer(serializers.Serializer):
    project_id = serializers.IntegerField()
    records = serializers.ListField(child=serializers.IntegerField())
    export_all = serializers.BooleanField(required=False)

class ProcoreSubmittalCreationResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    divs = serializers.DictField()
    specs = serializers.DictField()
    nums = serializers.DictField()
    submittals = serializers.DictField()
    submittals_not_created = serializers.ListField(child=serializers.DictField())

class CreateProcoreCompanyMappingSerializer(serializers.Serializer):
    link_company_id = serializers.IntegerField()
    procore_company_id = serializers.IntegerField()
    procore_company_name = serializers.CharField()