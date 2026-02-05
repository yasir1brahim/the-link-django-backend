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

def is_specgpt_websockets_feature_flag_active(user, team, project):
    """
    Check if the specgpt_websockets feature flag is active for the given user/team/project.
    
    Args:
        user: User object
        team: Team object
        project: Optional Project object
        
    Returns:
        bool: True if flag is active, False otherwise
    """
    return (settings.SPECGPT_WEBSOCKETS_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or 
            settings.SPECGPT_WEBSOCKETS_FEATURE_FLAG_NAME in get_active_flags_for_team(team) or 
            (project and settings.SPECGPT_WEBSOCKETS_FEATURE_FLAG_NAME in get_active_flags_for_project(project)))

def is_inspection_log_use_data_tables_feature_flag_active(user, team, project):
    return (settings.INSPECTION_LOG_USE_DATA_TABLES_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or 
            settings.INSPECTION_LOG_USE_DATA_TABLES_FEATURE_FLAG_NAME in get_active_flags_for_team(team) or 
            settings.INSPECTION_LOG_USE_DATA_TABLES_FEATURE_FLAG_NAME in get_active_flags_for_project(project))

def is_qa_planner_feature_flag_active(user, team, project=None):
    """
    Check if the qa_planner feature flag is active for the given user/team/project.
    
    Args:
        user: User object
        team: Team object
        project: Optional Project object
        
    Returns:
        bool: True if flag is active, False otherwise
    """
    return (settings.QA_PLANNER_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or 
            settings.QA_PLANNER_FEATURE_FLAG_NAME in get_active_flags_for_team(team) or 
            (project and settings.QA_PLANNER_FEATURE_FLAG_NAME in get_active_flags_for_project(project)))

def is_spec_centered_view_feature_flag_active(user, team, project=None):
    """
    Check if the spec_centered_view feature flag is active for the given user/team/project.
    
    Args:
        user: User object
        team: Team object
        project: Optional Project object
        
    Returns:
        bool: True if flag is active, False otherwise
    """
    return (settings.SPEC_CENTERED_VIEW_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or 
            settings.SPEC_CENTERED_VIEW_FEATURE_FLAG_NAME in get_active_flags_for_team(team) or 
            (project and settings.SPEC_CENTERED_VIEW_FEATURE_FLAG_NAME in get_active_flags_for_project(project)))

def is_versioning_pdf_comparison_feature_flag_active(user, team, project=None):
    """
    Check if the versioning_pdf_comparison feature flag is active for the given user/team/project.
    
    Args:
        user: User object
        team: Team object
        project: Optional Project object
        
    Returns:
        bool: True if flag is active, False otherwise
    """
    return (settings.VERSIONING_PDF_COMPARISON_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or 
            settings.VERSIONING_PDF_COMPARISON_FEATURE_FLAG_NAME in get_active_flags_for_team(team) or 
            (project and settings.VERSIONING_PDF_COMPARISON_FEATURE_FLAG_NAME in get_active_flags_for_project(project)))

def is_langchain_update_feature_flag_active(user, team, project=None):
    """
    Check if the langchain_update feature flag is active for the given user/team/project.
    This flag enables the adaptive RAG implementation using LangGraph agents.

    Args:
        user: User object
        team: Team object
        project: Optional Project object

    Returns:
        bool: True if flag is active, False otherwise
    """
    return (settings.LANGCHAIN_UPDATE_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or
            settings.LANGCHAIN_UPDATE_FEATURE_FLAG_NAME in get_active_flags_for_team(team) or
            (project and settings.LANGCHAIN_UPDATE_FEATURE_FLAG_NAME in get_active_flags_for_project(project)))


def is_drawings_feature_flag_active(user, team, project=None):
    """
    Check if the drawings feature flag is active for the given user/team/project.
    This flag enables the drawing parser webhook and notes display features.

    Args:
        user: User object
        team: Team object
        project: Optional Project object

    Returns:
        bool: True if flag is active, False otherwise
    """
    return (settings.DRAWINGS_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or
            settings.DRAWINGS_FEATURE_FLAG_NAME in get_active_flags_for_team(team) or
            (project and settings.DRAWINGS_FEATURE_FLAG_NAME in get_active_flags_for_project(project)))


def is_drawing_spec_comparison_active(user, team, project=None):
    """
    Check if the drawing spec comparison feature flag is active.

    Args:
        user: User object
        team: Team object
        project: Optional Project object

    Returns:
        bool: True if flag is active, False otherwise
    """
    return (
        settings.DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME in get_active_flags_for_user(user) or
        settings.DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME in get_active_flags_for_team(team) or
        (project and settings.DRAWING_SPEC_COMPARISON_FEATURE_FLAG_NAME in get_active_flags_for_project(project))
    )
