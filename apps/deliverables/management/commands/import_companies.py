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
    help = "Import companies from legacy database"

    