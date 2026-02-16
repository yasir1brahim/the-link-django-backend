from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.deliverables.models import (
    Project, ProjectVersion, ProjectMembership, UploadedFile,
    MasterFormatSection, SpecSection, SubmittalItem,
    ROLE_PROJECT_MEMBER, DocProcessingStatus,
)
from apps.users.models import CustomUser
from apps.teams.models import Team


class CreateFromHighlightTests(APITestCase):
    """Integration tests for the submittal-items/from-highlight endpoint."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser", password="testpass",
            first_name="Test", last_name="User",
        )
        self.team = Team.objects.create(name="Test Team")

        # Project A (the one we'll POST to)
        self.project_a = Project.objects.create(
            name="Project A", project_number="PA-001", team=self.team,
        )
        self.version_a = ProjectVersion.objects.get(project=self.project_a)
        ProjectMembership.objects.create(
            project=self.project_a, user=self.user, role=ROLE_PROJECT_MEMBER,
        )

        # Project B (cross-project)
        self.project_b = Project.objects.create(
            name="Project B", project_number="PB-001", team=self.team,
        )
        self.version_b = ProjectVersion.objects.get(project=self.project_b)

        # Masterformat section (shared)
        self.mf_section = MasterFormatSection.objects.create(
            masterformat_number="01 00 00",
            masterformat_description="General Requirements",
        )

        # Document + SpecSection for project A
        self.doc_a = UploadedFile.objects.create(
            project=self.project_a, project_version=self.version_a,
            name="Doc A", document_path="doc_a.pdf", md5="aaa",
            processing_status=DocProcessingStatus.PROCESSED,
        )
        self.spec_section_a = SpecSection.objects.create(
            masterformat_section=self.mf_section, document=self.doc_a,
        )

        # Document + SpecSection for project B
        self.doc_b = UploadedFile.objects.create(
            project=self.project_b, project_version=self.version_b,
            name="Doc B", document_path="doc_b.pdf", md5="bbb",
            processing_status=DocProcessingStatus.PROCESSED,
        )
        self.spec_section_b = SpecSection.objects.create(
            masterformat_section=self.mf_section, document=self.doc_b,
        )

        # SubmittalItem in project A (for added_under_submittal tests)
        self.submittal_a = SubmittalItem.objects.create(
            project=self.project_a, project_version=self.version_a,
            document=self.doc_a, masterformat_section=self.mf_section,
            spec_section=self.spec_section_a,
            submittal_type="Shop Drawings", submittal_description="Test",
            submittal_content="Content", parsing_method="UNKNOWN",
            parsing_version="1",
        )

        # SubmittalItem in project B
        self.submittal_b = SubmittalItem.objects.create(
            project=self.project_b, project_version=self.version_b,
            document=self.doc_b, masterformat_section=self.mf_section,
            spec_section=self.spec_section_b,
            submittal_type="Shop Drawings", submittal_description="Test B",
            submittal_content="Content B", parsing_method="UNKNOWN",
            parsing_version="1",
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = f"/api/deliverables/projects/{self.project_a.id}/submittal-items/from-highlight/"

    def _payload(self, **overrides):
        data = {
            "spec_section_id": self.spec_section_a.id,
            "item_desc": "Test submittal from highlight",
            "para_context": "Some paragraph context",
            "type": "Shop Drawings",
            "para_no": "1.1",
            "project_version": self.version_a.id,
        }
        data.update(overrides)
        return data

    def test_successful_creation(self):
        response = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        item = SubmittalItem.objects.get(id=response.data["id"])
        self.assertEqual(item.project_id, self.project_a.id)
        self.assertEqual(item.spec_section_id, self.spec_section_a.id)
        self.assertTrue(item.manually_added)

    def test_cross_project_spec_section_rejected(self):
        response = self.client.post(
            self.url,
            self._payload(spec_section_id=self.spec_section_b.id),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("SpecSection does not belong to this project", str(response.data))

    def test_cross_project_added_under_submittal_rejected(self):
        response = self.client.post(
            self.url,
            self._payload(added_under_submittal_id=self.submittal_b.id),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("added_under_submittal does not belong to this project", str(response.data))

    def test_valid_added_under_submittal_accepted(self):
        response = self.client.post(
            self.url,
            self._payload(added_under_submittal_id=self.submittal_a.id),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        item = SubmittalItem.objects.get(id=response.data["id"])
        self.assertEqual(item.added_under_submittal_id, self.submittal_a.id)

    # ── Missing required fields ──────────────────────────────────────

    def test_missing_item_desc_returns_400(self):
        payload = self._payload()
        del payload["item_desc"]
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_para_context_returns_400(self):
        payload = self._payload()
        del payload["para_context"]
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_type_returns_400(self):
        payload = self._payload()
        del payload["type"]
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_spec_section_id_returns_400(self):
        payload = self._payload()
        del payload["spec_section_id"]
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Invalid / non-existent spec_section_id ───────────────────────

    def test_nonexistent_spec_section_id_returns_400(self):
        response = self.client.post(
            self.url,
            self._payload(spec_section_id=999999),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("does not exist", str(response.data))

    # ── text_location and additional_text_locations edge cases ────────

    def test_text_location_null_accepted(self):
        response = self.client.post(
            self.url,
            self._payload(text_location=None),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        item = SubmittalItem.objects.get(id=response.data["id"])
        self.assertIsNone(item.text_location)

    def test_text_location_with_valid_json_object(self):
        loc = {"pageIndex": 0, "left": 10.0, "top": 20.0, "width": 100.0, "height": 50.0}
        response = self.client.post(
            self.url,
            self._payload(text_location=loc),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        item = SubmittalItem.objects.get(id=response.data["id"])
        self.assertEqual(item.text_location, loc)

    def test_additional_text_locations_empty_list(self):
        response = self.client.post(
            self.url,
            self._payload(additional_text_locations=[]),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        item = SubmittalItem.objects.get(id=response.data["id"])
        self.assertEqual(item.additional_text_locations, [])

    def test_additional_text_locations_with_multiple_entries(self):
        locs = [
            {"pageIndex": 0, "left": 10.0, "top": 20.0, "width": 100.0, "height": 50.0},
            {"pageIndex": 1, "left": 15.0, "top": 25.0, "width": 120.0, "height": 60.0},
        ]
        response = self.client.post(
            self.url,
            self._payload(additional_text_locations=locs),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        item = SubmittalItem.objects.get(id=response.data["id"])
        self.assertEqual(item.additional_text_locations, locs)

    def test_additional_text_locations_null_accepted(self):
        response = self.client.post(
            self.url,
            self._payload(additional_text_locations=None),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
