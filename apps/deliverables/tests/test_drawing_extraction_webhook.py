# apps/deliverables/tests/test_drawing_extraction_webhook.py
import json
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.deliverables.models import (
    Project, DrawingFile, DrawingExtraction, DrawingExtractionStatus,
)
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class TestDrawingExtractionWebhookBasic(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('test@example.com')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(
            name="Test Project",
            project_number="P-001",
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        self.drawing_file = DrawingFile.objects.create(
            project=self.project,
            project_version=self.project_version,
            file_name="Mechanical.pdf",
            file_s3_key="drawings/test.pdf",
            md5="abc123",
        )
        self.extraction = DrawingExtraction.objects.create(
            drawing_file=self.drawing_file,
            status=DrawingExtractionStatus.PENDING,
        )
        self.webhook_url = reverse('deliverables:drawing-extraction-webhook')

    def test_webhook_accepts_post_without_auth(self):
        """Test webhook endpoint exists and allows unauthenticated POST"""
        payload = {
            "event_id": "evt_001",
            "extraction_id": self.extraction.id,
            "new_status": "PROCESSING",
        }

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
