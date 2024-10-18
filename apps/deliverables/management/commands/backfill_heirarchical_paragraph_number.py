from django.core.management.base import BaseCommand
from django.apps import apps

class Command(BaseCommand):
    help = 'Backfill the heirarchical_paragraph_number field for all SubmittalItems'

    def handle(self, *args, **kwargs):
        SubmittalItem = apps.get_model('deliverables', 'SubmittalItem')
        for item in SubmittalItem.objects.all():
            item.heirarchical_paragraph_number = item.convert_paragraph_number_to_heirarchical_number()
            item.save()
