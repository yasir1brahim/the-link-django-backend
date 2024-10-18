import json

from django.core.management.base import BaseCommand
from django.apps import apps


class Command(BaseCommand):
    help = 'Backfill the json fields with valid json for all SubmittalItems'
    def convert_to_valid_json(self, text, default_value):
        try:
            text = text.replace("'", '"')
            return json.loads(text)
        except:
            return default_value
    
    def handle(self, *args, **kwargs):
        SubmittalItem = apps.get_model('deliverables', 'SubmittalItem')
        for item in SubmittalItem.objects.all():
            item.text_location = self.convert_to_valid_json(item.text_location, {})
            item.additional_text_locations = self.convert_to_valid_json(item.additional_text_locations, [])
            item.save()
