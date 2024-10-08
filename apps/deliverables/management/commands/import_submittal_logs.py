import datetime
import json

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
from .base_import_command import BaseImportCommand

import mysql.connector


class Command(BaseImportCommand):
    help = "Import submittal items from legacy database"


    def get_legacy_logs(self, cursor):
        cursor.execute("SELECT * FROM all_logs ORDER BY id DESC")
         # Get the column names from cursor description
        columns = [col[0] for col in cursor.description]
        
        # Fetch all results
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        return results


    def get_or_create_document(self, legacy_id, project):
        document = UploadedFile.objects.filter(legacy_id=legacy_id).first()
        if not document:
            legacy_document = self.get_legacy_document(legacy_id)
            print(legacy_document)
            document = UploadedFile(
                legacy_id=legacy_id,
                project=project,
                document_path=legacy_document['document_path'],
                parsed_document_path=legacy_document['parsed_doc_path'],
                name=legacy_document['document_name'],
                md5=legacy_document['md5'],
                processing_status=legacy_document['processing_status'] or "PROCESSED",
            )
            document.save()
        return document
    
    def get_or_create_spec_section(self, masterformat_number, document):
        masterformat_number_record = MasterFormatSection.objects.filter(masterformat_number=masterformat_number).first()
        if not masterformat_number_record:
            print("Creating masterformat number record:", masterformat_number)
            masterformat_number_record = MasterFormatSection(
                masterformat_number=masterformat_number,
            )
            masterformat_number_record.save()
        spec_section = SpecSection.objects.filter(masterformat_section=masterformat_number_record, document=document).first()
        if not spec_section:
            print("Creating spec section record:", masterformat_number_record)
            spec_section = SpecSection(
                masterformat_section=masterformat_number_record,
                document=document,
                processing_status = "PROCESSED",
            )
            spec_section.save()
        return spec_section
    

    def convert_to_valid_json(self, text):
        text = text.replace("'", '"')
        return json.loads(text)

    def map_legacy_log_to_submittal_item(self, log, project, document):
        print("LOG", log)
        submittal_item = SubmittalItem()
        submittal_item.legacy_id = log['id']
        submittal_item.legacy_updated_at = log['updated_date'].astimezone(datetime.timezone.utc)

        submittal_item.project = project
        submittal_item.document = document
        submittal_item.spec_section = self.get_or_create_spec_section(log['spec_section'], document)

        submittal_item.paragraph_number = log['para_no'] or ""
        submittal_item.submittal_type = log['type']
        submittal_item.submittal_description = log['item_desc']
        submittal_item.submittal_content = log['para_context']
        submittal_item.submittal_number = log['submittal_number']
        submittal_item.text_location = self.convert_to_valid_json(log['text_loc'])
        submittal_item.additional_text_locations = self.convert_to_valid_json(log['additional_text_locations'])
        submittal_item.updated_by = self.get_or_create_user(log['updated_by'])
        return submittal_item

    def handle(self, **options):
        print("Importing submittal items from legacy database...")
        self.connect_to_legacy_db()
        cursor = self.connection.cursor()
        legacy_logs = self.get_legacy_logs(cursor)

        for log in legacy_logs:
            if SubmittalItem.objects.filter(legacy_id=log['id']).exists():
                print(f"Submittal item with legacy_id {log['id']} already exists")
                continue
            project = self.get_or_create_project(log['project_id'])
            document = self.get_or_create_document(log['doc_id'], project)

            submittal_item = self.map_legacy_log_to_submittal_item(log, project, document)
            submittal_item.save()
            print("-"*100)
