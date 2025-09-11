import logging
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
from django.conf import settings


logger = logging.getLogger(__name__)


def send_team_added_notification(user, team, role, *, source: str = "unknown") -> None:
    """
    Send notification email that an existing user has been added to a team.

    This uses text and HTML templates:
      - templates/teams/email/team_added_notification.txt
      - templates/teams/email/team_added_notification.html
    """
    subject = _("You've been added to {}" ).format(team.name)

    context = {
        'user': user,
        'team': team,
        'role': role,
        'project_name': settings.PROJECT_METADATA.get("NAME", "The Link"),
    }

    message_text = render_to_string("teams/email/team_added_notification.txt", context)
    message_html = render_to_string("teams/email/team_added_notification.html", context)

    send_mail(
        subject=subject,
        message=message_text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
        html_message=message_html,
    ) 