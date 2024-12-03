import datetime

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.conf import settings
from djstripe.models import APIKey, Product
from djstripe.settings import djstripe_settings
from stripe.error import AuthenticationError

from apps.deliverables.models import ProjectMembership, Project, ROLE_PROJECT_ADMIN
from apps.teams.models import Team, Membership
from apps.users.models import CustomUser
from apps.teams.roles import ROLE_ADMIN, ROLE_MEMBER
from .base_import_command import BaseImportCommand

import mysql.connector


class Command(BaseImportCommand):
    help = "Import projects from legacy database"

    legacy_customer_id_to_team_id = {}

    def get_legacy_projects(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM project_view ORDER BY project_id DESC")
        columns = [col[0] for col in cursor.description]
        # Fetch all results
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        return results
    
    def get_team_from_legacy_customer_id(self, legacy_customer_id):
        new_team = Team.objects.filter(legacy_id=legacy_customer_id).first()
        if not new_team:
            raise Exception(f"Team for customer_id {legacy_customer_id} not found")
        return new_team
    
    def get_additional_project_data(self, legacy_id):
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM projects WHERE project_id = %s", (legacy_id,))
        columns = [col[0] for col in cursor.description]
        # Fetch all results
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        return results[0]
    
    def get_or_create_project(self, legacy_id, legacy_project_from_view_import):
        project = Project.objects.filter(legacy_id=legacy_id).first()
        team_id = self.legacy_customer_id_to_team_id.get(legacy_project_from_view_import['customer_id'])
        if not team_id:
            team_id = self.get_team_from_legacy_customer_id(legacy_project_from_view_import['customer_id']).id
            self.legacy_customer_id_to_team_id[legacy_project_from_view_import['customer_id']] = team_id
        if not project:
            legacy_project = legacy_project_from_view_import
            additional_project_data = self.get_additional_project_data(legacy_id)
            project = Project(
                legacy_id=legacy_project['project_id'],
                name=legacy_project['project_name'],
                project_number=legacy_project['project_number'] or '',
                project_type=legacy_project['project_type'],
                description="",
                team_id=team_id,
                is_archived=legacy_project['status'] == 'Archived',
                start_date=legacy_project['start_date'],
                end_date=legacy_project['end_date'],
                procore_id=additional_project_data['procore_id'],
                procore_name=additional_project_data['procore_name'],
                procore_submittal_manager_id=additional_project_data['procore_submittal_manager_id'],
                procore_submittal_manager_name=additional_project_data['procore_submittal_manager_name'],
            )
            project.save()
        return project
        
    def handle(self, **options):
        print("Importing projects from legacy database...")
        legacy_projects = self.get_legacy_projects()
        print(legacy_projects)

        for legacy_project in legacy_projects:
            self.get_or_create_project(legacy_project['project_id'], legacy_project)
            user_count = legacy_project['users']

            # create users for the project