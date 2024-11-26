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
    help = "Import companies, users, and projects from legacy database"

    def get_legacy_companies(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM customers_view ORDER BY customer_id ASC")
        columns = [col[0] for col in cursor.description]
        # Fetch all results
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        return results
    def get_legacy_users(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM users ORDER BY id ASC")
        columns = [col[0] for col in cursor.description]
        # Fetch all results
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        return results
    def get_legacy_projects(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM projects ORDER BY project_id ASC")
        columns = [col[0] for col in cursor.description]
        # Fetch all results
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        return results
    def get_legacy_user_to_team_mappings(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM employees ORDER BY user_id ASC")
        columns = [col[0] for col in cursor.description]
        # Fetch all results
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        return results
    
    def get_legacy_user_to_project_mappings(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM employee_project_map ORDER BY user_id ASC")
        columns = [col[0] for col in cursor.description]
        # Fetch all results
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        return results

    def handle(self, *args, **kwargs):
        print("Importing companies from legacy database...")
        self.connect_to_legacy_db()
        companies = self.get_legacy_companies()

        for company in companies:
            print(company)
            if Team.objects.filter(legacy_customer_id=company['customer_id']).exists():
                print(f"Team with legacy_customer_id {company['customer_id']} already exists")
                continue
            self.get_or_create_team(company['customer_id'])
        
        print("Importing users from legacy database...")
        users = self.get_legacy_users()
        for user in users:
            if 'pjdick' in user['email_address']:   
                print(user)
                print("--------------------------------")
            if CustomUser.objects.filter(legacy_id=user['id']).exists():
                print(f"User with legacy_id {user['id']} already exists")
                continue
            self.get_or_create_user(user['id'])

        import_projects = False
        if import_projects:
            projects = self.get_legacy_projects()        
            print(f"Importing {len(projects)} projects from legacy database...")
            for project in projects:
                if Project.objects.filter(legacy_id=project['project_id']).exists():
                    print(f"Project with legacy_id {project['project_id']} already exists")
                    continue
                self.get_or_create_project(project['project_id'])
        
        print("Mapping users to teams...")
        user_to_team_mappings = self.get_legacy_user_to_team_mappings()
        for user_mapping in user_to_team_mappings:
            user = self.get_or_create_user(user_mapping['user_id'])
            team = self.get_or_create_team(user_mapping['customer_id'])
            Membership.objects.get_or_create(
                user=user, 
                team=team, 
                role=self.map_legacy_role_to_team_role(user.legacy_role_id)
            )
        if import_projects:
            print("Mapping users to projects...")
            user_to_project_mappings = self.get_legacy_user_to_project_mappings()
            for user_mapping in user_to_project_mappings:
                user = self.get_or_create_user(user_mapping['user_id'])
                project = self.get_or_create_project(user_mapping['project_id'])
                ProjectMembership.objects.get_or_create(
                    user=user, 
                    project=project, 
                    role=self.map_legacy_role_to_project_role(user.legacy_role_id)
                )

        print("Import complete!")