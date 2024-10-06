import datetime

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.conf import settings
from djstripe.models import APIKey, Product
from djstripe.settings import djstripe_settings
from stripe.error import AuthenticationError

from apps.deliverables.models import SubmittalItem, UploadedFile, Project, SpecSection, MasterFormatSection
from apps.teams.models import Team
from apps.users.models import CustomUser
from apps.teams.roles import ROLE_ADMIN, ROLE_MEMBER

import mysql.connector



class BaseImportCommand(BaseCommand):
    help = "Abstract base class for importing data from legacy database"

    def connect_to_legacy_db(self):
        connection = mysql.connector.connect(
            host=settings.LEGACY_DB_HOST,
            port=3306,
            user=settings.LEGACY_DB_USER,
            password=settings.LEGACY_DB_PASSWORD,
            database=settings.LEGACY_DB_NAME
        )
        self.connection = connection
    

    def get_legacy_logs(self, cursor):
        cursor.execute("SELECT * FROM all_logs ORDER BY id DESC LIMIT 50")
         # Get the column names from cursor description
        columns = [col[0] for col in cursor.description]
        
        # Fetch all results
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        return results


    def get_legacy_document(self, legacy_id):
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM documents WHERE id = %s", (legacy_id,))
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        return dict(zip(columns, row))
    

    def get_legacy_project(self, legacy_id):
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM projects WHERE project_id = %s", (legacy_id,))
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        return dict(zip(columns, row))
    

    def get_legacy_team(self, legacy_customer_id):
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM customers_view WHERE customer_id = %s", (legacy_customer_id,))
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        return dict(zip(columns, row))
    

    def get_legacy_user(self, legacy_id):
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE id = %s", (legacy_id,))
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        return dict(zip(columns, row))
    

    def get_or_create_team(self, legacy_customer_id):
        team = Team.objects.filter(legacy_customer_id=legacy_customer_id).first()
        if not team:
            legacy_team = self.get_legacy_team(legacy_customer_id)
            team = Team(
                legacy_account_id=legacy_team['account_id'],
                legacy_customer_id=legacy_team['customer_id'],
                name=legacy_team['customer_name'],
                legacy_status=legacy_team['status'],
                is_enterprise=True,
                legacy_admin_id=legacy_team['admin_id'],
            )
            team.save()
        return team
    
    def map_legacy_role_to_user_role(self, legacy_role):
        legacy_role_map = {
            0: ROLE_ADMIN,
            1: ROLE_ADMIN,
            2: ROLE_MEMBER,
            3: ROLE_MEMBER,
            4: ROLE_MEMBER,
            5: ROLE_MEMBER,
            6: ROLE_MEMBER,
        }
        return legacy_role_map.get(legacy_role, ROLE_MEMBER)
    
    def get_or_create_user(self, legacy_id):
        user = CustomUser.objects.filter(legacy_id=legacy_id).first()
        if not user:
            legacy_user = self.get_legacy_user(legacy_id)
            print("legacy_user", legacy_user)
            try:
                first_name = legacy_user['full_name'].split(' ')[0]
                last_name = legacy_user['full_name'].split(' ')[1]
            except IndexError:
                first_name = legacy_user['full_name']
                last_name = ""
            user = CustomUser(
                legacy_id=legacy_user['id'],
                first_name=first_name,
                last_name=last_name,
                email=legacy_user['email_address'],
                username=legacy_user['username'],
                # role=self.map_legacy_role_to_user_role(legacy_user['role_id']),
                is_superuser=legacy_user['role_id'] == 0,
            )
            user.save()
        return user
    
    def get_or_create_project(self, legacy_id):
        project = Project.objects.filter(legacy_id=legacy_id).first()
        if not project:
            legacy_project = self.get_legacy_project(legacy_id)
            project = Project(
                legacy_id=legacy_project['project_id'],
                name=legacy_project['project_name'],
                status=legacy_project['status'],
                start_date=legacy_project['start_date'],
                end_date=legacy_project['end_date'],
                team=self.get_or_create_team(legacy_project['customer_id']),
                owner=self.get_or_create_user(legacy_project['lead_id']),
                created_by = self.get_or_create_user(legacy_project['created_by']),
                procore_id=legacy_project['procore_id'],
                procore_name=legacy_project['procore_name'],
                procore_submittal_manager_id=legacy_project['procore_submittal_manager_id'],
                procore_submittal_manager_name=legacy_project['procore_submittal_manager_name'],
            )
            project.save()
        return project