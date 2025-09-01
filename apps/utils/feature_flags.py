from django.conf import settings
from apps.teams.models import Flag

def get_active_flags_for_project(project):
    project_flags = Flag.objects.filter(projects=project)
    return [flag.name for flag in project_flags]

def get_active_flags_for_team(team):
    team_flags = Flag.objects.filter(teams=team)
    return [flag.name for flag in team_flags]

def get_active_flags_for_user(user):
    all_flags = Flag.objects.all()
    return [flag.name for flag in all_flags if flag.is_active_for_user(user)]

def is_notices_feature_flag_active(user, team):
    return settings.NOTICES_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or settings.NOTICES_FEATURE_FLAG_NAME in get_active_flags_for_team(team)

def is_versioning_feature_flag_active(user, team):
    return settings.VERSIONING_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or settings.VERSIONING_FEATURE_FLAG_NAME in get_active_flags_for_team(team)

def is_v2_process_deliverables_feature_flag_active(user, team, project):
    return True

def is_versioning_submittal_comparison_feature_flag_active(user, team, project):
    return (settings.VERSIONING_SUBMITTAL_COMPARISON_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or 
            settings.VERSIONING_SUBMITTAL_COMPARISON_FEATURE_FLAG_NAME in get_active_flags_for_team(team) or 
            settings.VERSIONING_SUBMITTAL_COMPARISON_FEATURE_FLAG_NAME in get_active_flags_for_project(project))

def is_full_spec_processing_feature_flag_active(user, team, project):
    return (settings.FULL_SPEC_PROCESSING_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or 
            settings.FULL_SPEC_PROCESSING_FEATURE_FLAG_NAME in get_active_flags_for_team(team) or 
            settings.FULL_SPEC_PROCESSING_FEATURE_FLAG_NAME in get_active_flags_for_project(project))

def is_specgpt_feature_flag_active(user, team, project):
    return (settings.SPECGPT_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or 
            settings.SPECGPT_FEATURE_FLAG_NAME in get_active_flags_for_team(team) or 
            settings.SPECGPT_FEATURE_FLAG_NAME in get_active_flags_for_project(project))

def is_inspection_log_use_data_tables_feature_flag_active(user, team, project):
    return (settings.INSPECTION_LOG_USE_DATA_TABLES_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or 
            settings.INSPECTION_LOG_USE_DATA_TABLES_FEATURE_FLAG_NAME in get_active_flags_for_team(team) or 
            settings.INSPECTION_LOG_USE_DATA_TABLES_FEATURE_FLAG_NAME in get_active_flags_for_project(project))
