# apps/deliverables/tests/test_extraction_note_viewset.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.deliverables.models import ExtractedData, ExtractionNote, Project, ProjectVersion, ExtractionSource, CustomItemType
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class TestExtractionNoteViewSet(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('test@example.com', password='testpass123')
        self.other_user = User.objects.create_user('other@example.com', password='testpass123')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(name="Test Project", team=self.team, created_by=self.user)
        self.version = self.project.versions.first()

        # Add user to project
        from apps.deliverables.models import ProjectMembership, ROLE_PROJECT_MEMBER
        ProjectMembership.objects.create(project=self.project, user=self.user, role=ROLE_PROJECT_MEMBER)

        self.custom_item_type = CustomItemType.objects.create(
            project=self.project,
            name="Test Highlight Type",
            color="#FF0000"
        )
        self.extracted_data = ExtractedData.objects.create(
            project=self.project,
            project_version=self.version,
            spec_section_number="01 1000",
            spec_section_name="General Requirements",
            extraction_type="custom_highlights",
            custom_item_type=self.custom_item_type,
            requirement_text="Test requirement",
            source=ExtractionSource.HUMAN,
            created_by=self.user
        )

        self.client.force_authenticate(user=self.user)

    def test_create_note(self):
        """Test creating a note on an ExtractedData"""
        url = reverse('deliverables:extractionnote-list', kwargs={
            'project_pk': self.project.id,
            'extracteddata_pk': self.extracted_data.id
        })
        data = {'text': 'This is a new note'}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ExtractionNote.objects.count(), 1)
        note = ExtractionNote.objects.first()
        self.assertEqual(note.text, 'This is a new note')
        self.assertEqual(note.created_by, self.user)
        self.assertEqual(note.extracted_data, self.extracted_data)
