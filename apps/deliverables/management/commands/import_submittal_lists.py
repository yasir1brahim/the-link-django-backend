from .base_import_command import BaseImportCommand
from apps.deliverables.models import SubmittalItemList, SubmittalItem
from django.conf import settings
class Command(BaseImportCommand):
    help = "Import submittal lists from legacy database"

    def get_legacy_lists(self, cursor):
        cursor.execute("SELECT * FROM saved_logs ORDER BY id DESC")
         # Get the column names from cursor description
        columns = [col[0] for col in cursor.description]
        
        # Fetch all results
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        return results

    def handle(self, *args, **kwargs):
        print("Importing data from legacy database...")
        print("Database host:", settings.LEGACY_DB_HOST)
        input("Press Enter to continue...")
        self.connect_to_legacy_db()
        cursor = self.connection.cursor()
        legacy_lists = self.get_legacy_lists(cursor)
        submittal_items = SubmittalItem.objects.all()
        legacy_ids_to_django_ids = {submittal_item.legacy_id: submittal_item.id for submittal_item in submittal_items}
        print(legacy_lists)

        for legacy_list in legacy_lists:
            print(legacy_list)
            try:
                project = self.get_or_create_project(legacy_list['project_id'])
            except Exception as e:
                print(f"Error getting or creating project for legacy list {legacy_list['view_name']}: {e}")
                continue
            new_list = SubmittalItemList(
                project=project,
                name=legacy_list['view_name'],
            )
            new_list.save()

            submittal_item_ids = legacy_list['records'][1:-1].split(', ')
            django_submittal_item_ids = []
            for submittal_item_id in submittal_item_ids:
                django_id = legacy_ids_to_django_ids.get(int(submittal_item_id))
                if django_id:
                    django_submittal_item_ids.append(django_id)
            new_list.submittals.add(*django_submittal_item_ids)
            new_list.save()
            print(new_list)
