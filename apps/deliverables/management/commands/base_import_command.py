import datetime

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.conf import settings
from djstripe.models import APIKey, Product
from djstripe.settings import djstripe_settings
from stripe.error import AuthenticationError

from apps.deliverables.models import Project, ROLE_PROJECT_ADMIN, ROLE_PROJECT_MEMBER
from apps.teams.models import Team
from apps.users.models import CustomUser
from apps.teams.roles import ROLE_ADMIN, ROLE_MEMBER
from apps.teams.helpers import get_next_unique_team_slug
import mysql.connector
from apps.users.helpers import get_next_unique_username


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
        try:
            return dict(zip(columns, row))
        except Exception as e:
            print("Error getting legacy user:", legacy_id)
            print("Row:", row)
            print("Columns:", columns)
            return None
    

    def get_or_create_team(self, legacy_customer_id, legacy_team_from_import = None):
        team = Team.objects.filter(legacy_customer_id=legacy_customer_id).first()
        if not team:
            legacy_team = legacy_team_from_import or self.get_legacy_team(legacy_customer_id)
            team = Team(
                legacy_account_id=legacy_team['account_id'],
                legacy_customer_id=legacy_team['customer_id'],
                name=legacy_team['customer_name'],
                legacy_status=legacy_team['status'],
                is_enterprise=True,
                slug=get_next_unique_team_slug(legacy_team['customer_name']),
                legacy_admin_id=legacy_team['admin_id'],
            )
            team.save()
        return team
    
    def map_legacy_role_to_team_role(self, legacy_role):
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
    
    def map_legacy_role_to_project_role(self, legacy_role):
        legacy_role_map = {
            0: ROLE_PROJECT_ADMIN,
            1: ROLE_PROJECT_ADMIN,
            2: ROLE_PROJECT_MEMBER,
            3: ROLE_PROJECT_MEMBER,
            4: ROLE_PROJECT_MEMBER,
            5: ROLE_PROJECT_MEMBER,
            6: ROLE_PROJECT_MEMBER,
        }
        return legacy_role_map.get(legacy_role, ROLE_MEMBER)
    

    def get_sentinel_user(self):
        return CustomUser.objects.get_or_create(username='deleted', defaults={'is_superuser': False})[0]
    
    def get_or_create_user(self, legacy_id, legacy_user_from_import = None):
        user = CustomUser.objects.filter(legacy_id=legacy_id).first()
        if not user:
            legacy_user = legacy_user_from_import or self.get_legacy_user(legacy_id)
            if legacy_user is None:
                print("legacy_user not found for legacy_id:", legacy_id)
                return self.get_sentinel_user()
            print("creating user:", legacy_user)
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
                username=get_next_unique_username(CustomUser, legacy_user['username']),
                legacy_role_id=legacy_user['role_id'],
                is_superuser=legacy_user['role_id'] == 0,
            )
            user.save()
        return user
    
    def get_or_create_project(self, legacy_id, legacy_project_from_import = None):
        project = Project.objects.filter(legacy_id=legacy_id).first()
        if not project:
            legacy_project = legacy_project_from_import or self.get_legacy_project(legacy_id)
            print("creating project:", legacy_project)
            project = Project(
                legacy_id=legacy_project['project_id'],
                name=legacy_project['project_name'],
                start_date=legacy_project['start_date'],
                end_date=legacy_project['end_date'],
                team=self.get_or_create_team(legacy_project['customer_id']),
                created_by = self.get_or_create_user(legacy_project['created_by']),
                procore_id=legacy_project['procore_id'],
                procore_name=legacy_project['procore_name'],
                procore_submittal_manager_id=legacy_project['procore_submittal_manager_id'],
                procore_submittal_manager_name=legacy_project['procore_submittal_manager_name'],
            )
            project.save()
        return project