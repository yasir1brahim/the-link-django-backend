from django.db import migrations


def convert_email_to_lowercase(apps, schema_editor):
    CustomUser = apps.get_model('users', 'CustomUser')
    for user in CustomUser.objects.all():
        if user.email:
            user.email = user.email.lower()
            user.save()


def reverse_convert_email(apps, schema_editor):
    # No reverse operation needed since we can't determine original case
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_customuser_legacy_role_id'),
    ]

    operations = [
        migrations.RunPython(convert_email_to_lowercase, reverse_convert_email),
    ]