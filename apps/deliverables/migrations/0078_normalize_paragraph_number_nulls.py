from django.db import migrations


def normalize_empty_paragraph_numbers(apps, schema_editor):
    SubmittalItem = apps.get_model('deliverables', 'SubmittalItem')
    SemanticallyProcessedSpecItem = apps.get_model('deliverables', 'SemanticallyProcessedSpecItem')

    SubmittalItem.objects.filter(paragraph_number="").update(paragraph_number=None)
    SemanticallyProcessedSpecItem.objects.filter(paragraph_number="").update(paragraph_number=None)


class Migration(migrations.Migration):

    dependencies = [
        ('deliverables', '0077_merge_20260129_1224'),
    ]

    operations = [
        migrations.RunPython(
            normalize_empty_paragraph_numbers,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
