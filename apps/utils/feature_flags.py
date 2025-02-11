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
    return (settings.V2_PROCESS_DELIVERABLES_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or 
            settings.V2_PROCESS_DELIVERABLES_FEATURE_FLAG_NAME in get_active_flags_for_team(team) or 
            settings.V2_PROCESS_DELIVERABLES_FEATURE_FLAG_NAME in get_active_flags_for_project(project))