import datetime
import json

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.conf import settings
from djstripe.models import APIKey, Product
from djstripe.settings import djstripe_settings
from stripe.error import AuthenticationError

from apps.deliverables.models import ProjectMembership, Project, ROLE_PROJECT_ADMIN, ROLE_PROJECT_MEMBER
from apps.deliverables.models import UploadedFile, SubmittalItem, MasterFormatSection
from apps.teams.models import Team, Membership
from apps.users.models import CustomUser
from apps.teams.roles import ROLE_ADMIN, ROLE_MEMBER
from .base_import_command import BaseImportCommand
from apps.users.helpers import get_next_unique_username
from django.db import IntegrityError


class Command(BaseImportCommand):
    help = "Import data from legacy database"

    legacy_customer_id_to_team_id = {}
    legacy_customer_user_counts = {}
    legacy_user_id_to_user_id = {}
    legacy_project_id_to_project_id = {}
    legacy_project_user_counts = {}
    django_project_id_to_team_id_map = {}
    legacy_document_id_to_document_id = {}
    masterformat_number_to_masterformat_section_id = {}


    def get_legacy_companies(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM customers_view ORDER BY customer_id ASC")
        columns = [col[0] for col in cursor.description]
        # Fetch all results
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        return results
        
    def import_companies(self):
        print("Importing companies from legacy database...")
        legacy_companies = self.get_legacy_companies()
        print(legacy_companies)

        for legacy_company in legacy_companies:
            team = self.get_or_create_team(legacy_company['customer_id'], legacy_company)
            self.legacy_customer_id_to_team_id[legacy_company['customer_id']] = team.id
            self.legacy_customer_user_counts[legacy_company['customer_id']] = legacy_company['users']
            # Create admin user for the company
            # the customer_id in the legacy database corresponds to the id of the admin user
            legacy_admin_id = legacy_company['customer_id']
            user = self.get_or_create_user(legacy_admin_id)
            Membership.objects.create(user_id=user, team_id=team.id, role=ROLE_ADMIN)


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
    
    def transform_date(self, mm_dd_yyyy_date_string):
        if not mm_dd_yyyy_date_string:
            return None
        month, day, year = mm_dd_yyyy_date_string.split('-')
        return f"{year}-{month}-{day}"
    
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
                start_date=self.transform_date(legacy_project['start_date']),
                end_date=self.transform_date(legacy_project['end_date']),
                procore_id=additional_project_data['procore_id'],
                procore_name=additional_project_data['procore_name'],
                procore_submittal_manager_id=additional_project_data['procore_submittal_manager_id'],
                procore_submittal_manager_name=additional_project_data['procore_submittal_manager_name'],
            )
            project.save()
        
        return project
    
    def get_legacy_user_to_project_mappings(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM employee_project_map ORDER BY user_id ASC")
        columns = [col[0] for col in cursor.description]
        # Fetch all results
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        return results
    
    def import_projects(self):
        print("Importing projects from legacy database...")
        legacy_projects = self.get_legacy_projects()
        print(legacy_projects)

        for legacy_project in legacy_projects:
            project = self.get_or_create_project(legacy_project['project_id'], legacy_project)
            self.legacy_project_id_to_project_id[legacy_project['project_id']] = project.id
            self.django_project_id_to_team_id_map[project.id] = project.team_id
            user_count = legacy_project['users']
            self.legacy_project_user_counts[legacy_project['project_id']] = user_count

    def get_or_create_user(self, legacy_id, legacy_user_from_import = None):
        legacy_user = legacy_user_from_import
        if self.legacy_user_id_to_user_id.get(legacy_id):
            return self.legacy_user_id_to_user_id[legacy_id]
        if not legacy_user:
            legacy_user = self.get_legacy_user(legacy_id)
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
        self.legacy_user_id_to_user_id[legacy_user['id']] = user.id
        return user.id

    def import_users(self):
        print("Importing users from legacy database...")
        users = self.get_legacy_users()
        for user in users:
            user_id = self.get_or_create_user(user['id'], user)
            self.legacy_user_id_to_user_id[user['id']] = user_id

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

    def map_users_to_companies(self):
        print("Mapping users to companies...")
        user_to_team_mappings = self.get_legacy_user_to_team_mappings()
        for user_mapping in user_to_team_mappings:
            user_id = self.legacy_user_id_to_user_id[user_mapping['user_id']]
            team_id = self.legacy_customer_id_to_team_id[user_mapping['customer_id']]
            Membership.objects.create(
                user_id=user_id, 
                team_id=team_id, 
                role=ROLE_MEMBER
            )
    
    def map_users_to_projects(self):
        print("Mapping users to projects...")
        user_to_project_mappings = self.get_legacy_user_to_project_mappings()
        for user_mapping in user_to_project_mappings:
            user_id = self.legacy_user_id_to_user_id.get(user_mapping['user_id'])
            if not user_id:
                continue
            project_id = self.legacy_project_id_to_project_id[user_mapping['project_id']]
            try:
                ProjectMembership.objects.create(
                    user_id=user_id,
                    project_id=project_id,
                    role=ROLE_PROJECT_MEMBER
                )
            except IntegrityError:
                print(f"Project membership for user {user_id} and project {project_id} already exists")
                continue


    def get_legacy_logs(self):
        self.cursor.execute("SELECT * FROM all_logs ORDER BY id DESC")
         # Get the column names from cursor description
        columns = [col[0] for col in self.cursor.description]
        
        # Fetch all results
        rows = self.cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        return results

    def get_legacy_users(self):
        self.cursor.execute("SELECT * FROM users ORDER BY id ASC")
        columns = [col[0] for col in self.cursor.description]
        # Fetch all results
        rows = self.cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        return results

    def get_or_create_document(self, legacy_id, project_id):
        if self.legacy_document_id_to_document_id.get(legacy_id):
            return self.legacy_document_id_to_document_id[legacy_id]
        document = UploadedFile.objects.filter(legacy_id=legacy_id).first()
        legacy_document = self.get_legacy_document(legacy_id)
        document = UploadedFile(
            legacy_id=legacy_id,
            project_id=project_id,
            document_path=legacy_document['document_path'],
            parsed_document_path=legacy_document['parsed_doc_path'],
            name=legacy_document['document_name'],
            md5=legacy_document['md5'],
            processing_status=legacy_document['processing_status'] or "PROCESSED",
        )
        document.save()
        self.legacy_document_id_to_document_id[legacy_id] = document.id
        return document.id
    
    def get_or_create_masterformat_section(self, masterformat_number, document):
        if self.masterformat_number_to_masterformat_section_id.get(masterformat_number):
            return self.masterformat_number_to_masterformat_section_id[masterformat_number]
        print("Creating masterformat number record:", masterformat_number)
        
        masterformat_number_record, created = MasterFormatSection.objects.get_or_create(
            masterformat_number=masterformat_number,
        )
        self.masterformat_number_to_masterformat_section_id[masterformat_number] = masterformat_number_record.id
        return masterformat_number_record.id
    

    def convert_to_valid_json(self, text):
        if text is None:
            return []
        text = text.replace("'", '"')
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            print(f"Error decoding JSON: {text}")
            return []

    def map_legacy_log_to_submittal_item(self, log, project_id, document_id):
        submittal_item = SubmittalItem()
        submittal_item.legacy_id = log['id']
        submittal_item.legacy_updated_at = log['updated_date'].astimezone(datetime.timezone.utc)

        submittal_item.project_id = project_id
        submittal_item.document_id = document_id
        submittal_item.masterformat_section_id = self.get_or_create_masterformat_section(log['spec_section'], document_id)

        submittal_item.paragraph_number = log['para_no'] or ""
        submittal_item.submittal_type = log['type']
        submittal_item.submittal_description = log['item_desc']
        submittal_item.submittal_content = log['para_context']
        submittal_item.submittal_number = log['submittal_number']
        submittal_item.text_location = self.convert_to_valid_json(log['text_loc'])
        submittal_item.additional_text_locations = self.convert_to_valid_json(log['additional_text_locations'])
        submittal_item.updated_by_id = self.get_or_create_user(log['updated_by'])
        return submittal_item


    def import_submittal_items(self):
        print("Importing submittal items from legacy database...")
        submittal_items = self.get_legacy_logs()

        chunk_size = 1000
        for i in range(0, len(submittal_items), chunk_size):
            chunk = submittal_items[i:i + chunk_size]
            submittal_objects = []
            for log in chunk:
                project_id = self.legacy_project_id_to_project_id.get(log['project_id'])
                if not project_id:
                    print(f"Project with legacy_id {log['project_id']} not found")
                    continue
                document_id = self.get_or_create_document(log['doc_id'], project_id)
                submittal_item = self.map_legacy_log_to_submittal_item(log, project_id, document_id)
                submittal_objects.append(submittal_item)
            SubmittalItem.objects.bulk_create(submittal_objects, batch_size=chunk_size)
            print(f"Inserted {i + len(chunk)} / {len(submittal_items)} submittal items.")

    def set_idempotency_maps(self):
        documents = UploadedFile.objects.all()
        for document in documents:
            self.legacy_document_id_to_document_id[document.legacy_id] = document.id
        masterformat_sections = MasterFormatSection.objects.all()
        for masterformat_section in masterformat_sections:
            self.masterformat_number_to_masterformat_section_id[masterformat_section.masterformat_number] = masterformat_section.id
        teams = Team.objects.all()
        for team in teams:
            self.legacy_customer_id_to_team_id[team.legacy_id] = team.id
        users = CustomUser.objects.all()
        for user in users:
            self.legacy_user_id_to_user_id[user.legacy_id] = user.id
        projects = Project.objects.all()
        for project in projects:
            self.legacy_project_id_to_project_id[project.legacy_id] = project.id
            self.django_project_id_to_team_id_map[project.id] = project.team_id
            self.legacy_project_user_counts[project.legacy_id] = project.users

    def get_legacy_lists(self, cursor):
        self.cursor.execute("SELECT * FROM saved_logs ORDER BY id DESC LIMIT 10")
         # Get the column names from cursor description
        columns = [col[0] for col in self.cursor.description]
        
        # Fetch all results
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        return results
    

    def import_submittal_lists(self):
        print("Importing submittal lists from legacy database...")
        print("Run separate import command for this")
        
    def handle(self, *args, **kwargs):
        self.connect_to_legacy_db()
        self.cursor = self.connection.cursor()
        # self.set_idempotency_maps()
        self.import_companies()
        self.import_projects()
        self.import_users()
        self.map_users_to_companies()
        self.map_users_to_projects()
        self.import_submittal_items()
        self.import_submittal_lists()

