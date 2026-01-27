import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.deliverables.models import (
    ExtractedData,
    ExtractionSource,
    Project,
    ProjectMembership,
    ROLE_PROJECT_ADMIN,
    ROLE_PROJECT_MEMBER,
)
from apps.teams.models import Membership, Team
from apps.teams import roles as team_roles

User = get_user_model()


def create_team(name: str = "Test Team") -> Team:
    return Team.objects.create(name=name, slug=f"{uuid.uuid4()}-team")


def create_user(username: str) -> User:
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="testpass123",
        first_name=username.title(),
        last_name="User",
    )


class CustomItemTypeModelTests(TestCase):
    def setUp(self):
        self.team = create_team()
        self.user = create_user("model")
        Membership.objects.create(team=self.team, user=self.user, role=team_roles.ROLE_ADMIN)

        self.project = Project.objects.create(
            name="Project Alpha",
            project_number="PA-001",
            team=self.team,
            created_by=self.user,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ROLE_PROJECT_ADMIN,
        )

    def test_create_custom_item_type(self):
        from apps.deliverables.models import CustomItemType

        custom_type = CustomItemType.objects.create(
            name="Safety Requirements",
            color="#FF5733",
            description="Safety-related requirements",
            project=self.project,
            created_by=self.user,
        )

        self.assertEqual(custom_type.name, "Safety Requirements")
        self.assertEqual(custom_type.color, "#FF5733")
        self.assertTrue(custom_type.is_active)

    def test_unique_name_per_project(self):
        from apps.deliverables.models import CustomItemType

        CustomItemType.objects.create(
            name="Type A",
            project=self.project,
            created_by=self.user,
        )

        with self.assertRaises(IntegrityError):
            CustomItemType.objects.create(
                name="Type A",
                project=self.project,
                created_by=self.user,
            )

    def test_color_validation(self):
        from apps.deliverables.models import CustomItemType

        custom_type = CustomItemType(
            name="Valid Color",
            color="#00FF00",
            project=self.project,
            created_by=self.user,
        )
        custom_type.full_clean()  # Should not raise

        custom_type.color = "invalid"
        with self.assertRaises(ValidationError):
            custom_type.full_clean()

    def test_soft_delete_marks_inactive(self):
        from apps.deliverables.models import CustomItemType

        custom_type = CustomItemType.objects.create(
            name="To Delete",
            project=self.project,
            created_by=self.user,
        )

        custom_type.is_active = False
        custom_type.save(update_fields=["is_active"])

        custom_type.refresh_from_db()
        self.assertFalse(custom_type.is_active)


class ExtractedDataCustomTypeTests(TestCase):
    def setUp(self):
        self.team = create_team("Highlights Team")
        self.user = create_user("highlights")
        Membership.objects.create(team=self.team, user=self.user, role=team_roles.ROLE_ADMIN)

        self.project = Project.objects.create(
            name="Highlights Project",
            project_number="HP-001",
            team=self.team,
            created_by=self.user,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ROLE_PROJECT_MEMBER,
        )
        self.project_version = self.project.versions.first()

        from apps.deliverables.models import CustomItemType

        self.custom_type = CustomItemType.objects.create(
            name="Custom Type",
            color="#3B82F6",
            project=self.project,
            created_by=self.user,
        )

    def create_extracted_kwargs(self, **overrides):
        data = {
            "project": self.project,
            "project_version": self.project_version,
            "spec_section_number": "01 11 00",
            "spec_section_name": "Summary of Work",
            "extraction_type": "inspection_log",
            "requirement_text": "Provide detailed description of work.",
            "source": ExtractionSource.HUMAN,
            "created_by": self.user,
        }
        data.update(overrides)
        return data

    def test_auto_sets_extraction_type(self):
        from apps.deliverables.models import CustomItemType

        extracted = ExtractedData.objects.create(
            custom_item_type=self.custom_type,
            **self.create_extracted_kwargs(),
        )
        self.assertEqual(extracted.extraction_type, "custom_highlights")
        self.assertEqual(extracted.custom_item_type_id, self.custom_type.id)

    def test_requires_custom_type_when_extraction_type_custom_highlights(self):
        extracted = ExtractedData(
            **self.create_extracted_kwargs(extraction_type="custom_highlights", custom_item_type=None)
        )
        with self.assertRaises(ValidationError):
            extracted.full_clean()

    def test_custom_type_must_belong_to_project(self):
        other_team = create_team("Other Team")
        other_user = create_user("other")
        Membership.objects.create(team=other_team, user=other_user, role=team_roles.ROLE_ADMIN)
        other_project = Project.objects.create(
            name="Other Project",
            project_number="OP-001",
            team=other_team,
            created_by=other_user,
        )
        ProjectMembership.objects.create(
            project=other_project,
            user=other_user,
            role=ROLE_PROJECT_MEMBER,
        )
        other_version = other_project.versions.first()

        extracted = ExtractedData(
            custom_item_type=self.custom_type,
            project=other_project,
            project_version=other_version,
            spec_section_number="02 00 00",
            spec_section_name="Existing Conditions",
            extraction_type="inspection_log",
            requirement_text="Existing condition requirement.",
            source=ExtractionSource.HUMAN,
            created_by=other_user,
        )

        with self.assertRaises(ValidationError):
            extracted.save()


class CustomItemTypeAPITests(APITestCase):
    def setUp(self):
        self.team = create_team("API Team")
        self.user = create_user("apiuser")
        Membership.objects.create(team=self.team, user=self.user, role=team_roles.ROLE_ADMIN)

        self.project = Project.objects.create(
            name="API Project",
            project_number="API-001",
            team=self.team,
            created_by=self.user,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ROLE_PROJECT_ADMIN,
        )
        self.project_version = self.project.versions.first()
        self.client.force_authenticate(user=self.user)

        self.base_url = f"/api/deliverables/projects/{self.project.id}/custom-item-types/"

    def create_custom_type(self, **kwargs):
        from apps.deliverables.models import CustomItemType

        defaults = {
            "name": "Sample Type",
            "color": "#FF0000",
            "project": self.project,
            "created_by": self.user,
        }
        defaults.update(kwargs)
        return CustomItemType.objects.create(**defaults)

    def create_extracted(self, **kwargs):
        defaults = {
            "project": self.project,
            "project_version": self.project_version,
            "spec_section_number": "03 30 00",
            "spec_section_name": "Cast-in-Place Concrete",
            "extraction_type": "inspection_log",
            "requirement_text": "Provide concrete submittals prior to pours.",
            "source": ExtractionSource.HUMAN,
            "created_by": self.user,
        }
        defaults.update(kwargs)
        return ExtractedData.objects.create(**defaults)

    def test_list_custom_types(self):
        self.create_custom_type(name="Type 1", color="#FF1111")
        self.create_custom_type(name="Type 2", color="#00FF00")

        response = self.client.get(self.base_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertEqual(response.data["count"], 2)

    def test_create_custom_type_via_api(self):
        payload = {
            "name": "Inspection Highlights",
            "color": "#123ABC",
            "description": "Items captured during inspections.",
        }

        response = self.client.post(self.base_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], payload["name"])
        self.assertEqual(response.data["color"], payload["color"])

    def test_update_custom_type(self):
        custom_type = self.create_custom_type(name="Original", color="#111111")

        response = self.client.patch(
            f"{self.base_url}{custom_type.id}/",
            {"name": "Updated", "color": "#222222"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        custom_type.refresh_from_db()
        self.assertEqual(custom_type.name, "Updated")
        self.assertEqual(custom_type.color, "#222222")

    def test_delete_soft_deletes(self):
        custom_type = self.create_custom_type(name="Delete Me")

        response = self.client.delete(f"{self.base_url}{custom_type.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        from apps.deliverables.models import CustomItemType

        custom_type.refresh_from_db()
        self.assertFalse(custom_type.is_active)
        self.assertTrue(CustomItemType.objects.filter(id=custom_type.id).exists())

    def test_assign_custom_type_to_extracted_data(self):
        custom_type = self.create_custom_type(name="Assign Me")
        ed1 = self.create_extracted()
        ed2 = self.create_extracted(requirement_text="Second requirement")

        response = self.client.post(
            f"{self.base_url}{custom_type.id}/assign-to-extracted-data/",
            {"extracted_data_ids": [ed1.id, ed2.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["updated_count"], 2)

        ed1.refresh_from_db()
        ed2.refresh_from_db()
        self.assertEqual(ed1.custom_item_type_id, custom_type.id)
        self.assertEqual(ed1.extraction_type, "custom_highlights")
        self.assertEqual(ed2.custom_item_type_id, custom_type.id)
        self.assertEqual(ed2.extraction_type, "custom_highlights")

    def test_color_palette_endpoint(self):
        self.create_custom_type(name="Used Color", color="#EF4444")

        response = self.client.get(f"{self.base_url}color-palette/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("#EF4444", response.data["used_colors"])
        self.assertNotIn("#EF4444", response.data["available_colors"])






