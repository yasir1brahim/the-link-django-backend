from .base_import_command import BaseImportCommand
from apps.deliverables.models import SubmittalItemList, SubmittalItem

class Command(BaseImportCommand):
    help = "Import submittal lists from legacy database"

    def get_legacy_lists(self, cursor):
        cursor.execute("SELECT * FROM saved_logs ORDER BY id DESC LIMIT 10")
         # Get the column names from cursor description
        columns = [col[0] for col in cursor.description]
        
        # Fetch all results
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        return results

    def handle(self, *args, **kwargs):
        self.connect_to_legacy_db()
        cursor = self.connection.cursor()
        legacy_lists = self.get_legacy_lists(cursor)
        print(legacy_lists)

        for legacy_list in legacy_lists:
            print(legacy_list)
            project = self.get_or_create_project(legacy_list['project_id'])
            new_list = SubmittalItemList(
                project=project,
                name=legacy_list['view_name'],
            )
            new_list.save()

            submittal_item_ids = legacy_list['records'][1:-1].split(', ')
            new_list.submittals.add(*submittal_item_ids)
            print(new_list)
