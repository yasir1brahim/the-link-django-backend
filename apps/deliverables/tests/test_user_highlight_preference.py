import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.deliverables.models import (
    CustomItemType,
    Project,
    ProjectMembership,
    UserHighlightPreference,
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


class UserHighlightPreferenceModelTests(TestCase):
    """Tests for the UserHighlightPreference model."""

    def setUp(self):
        self.team = create_team()
        self.user = create_user("model_test")
        Membership.objects.create(team=self.team, user=self.user, role=team_roles.ROLE_ADMIN)

        self.project = Project.objects.create(
            name="Test Project",
            project_number="TP-001",
            team=self.team,
            created_by=self.user,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ROLE_PROJECT_ADMIN,
        )

        self.custom_type = CustomItemType.objects.create(
            name="Safety Requirements",
            color="#FF5733",
            project=self.project,
            created_by=self.user,
        )

    def test_create_preference_with_standard_type(self):
        """Test creating a preference with a standard type."""
        preference = UserHighlightPreference.objects.create(
            user=self.user,
            project=self.project,
            is_custom_type=False,
            standard_item_type="inspections",
            extraction_type="qa_planner",
            type_display_name="Inspections",
            type_color="#FF0000",
        )

        self.assertEqual(preference.user, self.user)
        self.assertEqual(preference.project, self.project)
        self.assertFalse(preference.is_custom_type)
        self.assertEqual(preference.standard_item_type, "inspections")

    def test_create_preference_with_custom_type(self):
        """Test creating a preference with a custom type."""
        preference = UserHighlightPreference.objects.create(
            user=self.user,
            project=self.project,
            is_custom_type=True,
            custom_item_type=self.custom_type,
            extraction_type="custom_highlights",
            type_display_name="Safety Requirements",
            type_color="#FF5733",
        )

        self.assertTrue(preference.is_custom_type)
        self.assertEqual(preference.custom_item_type, self.custom_type)

    def test_unique_constraint_per_user_project(self):
        """Test that only one preference per user per project is allowed."""
        UserHighlightPreference.objects.create(
            user=self.user,
            project=self.project,
            is_custom_type=False,
            standard_item_type="inspections",
            type_display_name="Inspections",
            type_color="#FF0000",
        )

        with self.assertRaises(IntegrityError):
            UserHighlightPreference.objects.create(
                user=self.user,
                project=self.project,
                is_custom_type=False,
                standard_item_type="warranties",
                type_display_name="Warranties",
                type_color="#00FF00",
            )

    def test_set_null_when_custom_type_deleted(self):
        """Test that custom_item_type is set to NULL when the custom type is deleted."""
        preference = UserHighlightPreference.objects.create(
            user=self.user,
            project=self.project,
            is_custom_type=True,
            custom_item_type=self.custom_type,
            extraction_type="custom_highlights",
            type_display_name="Safety Requirements",
            type_color="#FF5733",
        )

        # Hard delete the custom type
        self.custom_type.delete()

        preference.refresh_from_db()
        self.assertIsNone(preference.custom_item_type)


class UserHighlightPreferenceAPITests(APITestCase):
    """Tests for the UserHighlightPreference API endpoints."""

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

        self.custom_type = CustomItemType.objects.create(
            name="Custom Highlights",
            color="#3B82F6",
            project=self.project,
            created_by=self.user,
        )

        self.client.force_authenticate(user=self.user)
        self.base_url = f"/api/deliverables/projects/{self.project.id}/highlight-preference/"

    def test_get_preference_returns_404_when_not_exists(self):
        """Test that GET returns 404 when no preference exists."""
        response = self.client.get(self.base_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("No highlight preference found", response.data["detail"])

    def test_create_preference_with_standard_type(self):
        """Test creating a preference with a standard type."""
        payload = {
            "is_custom_type": False,
            "standard_item_type": "inspections",
            "extraction_type": "qa_planner",
            "type_display_name": "Inspections",
            "type_color": "#FF0000",
        }

        response = self.client.post(self.base_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_custom_type"])
        self.assertEqual(response.data["standard_item_type"], "inspections")

    def test_create_preference_with_custom_type(self):
        """Test creating a preference with a custom type."""
        payload = {
            "is_custom_type": True,
            "custom_item_type": self.custom_type.id,
            "extraction_type": "custom_highlights",
            "type_display_name": "Custom Highlights",
            "type_color": "#3B82F6",
        }

        response = self.client.post(self.base_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_custom_type"])
        self.assertEqual(response.data["custom_item_type"], self.custom_type.id)

    def test_get_preference_after_create(self):
        """Test that GET returns the preference after creation."""
        payload = {
            "is_custom_type": False,
            "standard_item_type": "inspections",
            "type_display_name": "Inspections",
            "type_color": "#FF0000",
        }
        self.client.post(self.base_url, payload, format="json")

        response = self.client.get(self.base_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["standard_item_type"], "inspections")

    def test_upsert_behavior_updates_existing(self):
        """Test that creating twice updates the existing record."""
        payload1 = {
            "is_custom_type": False,
            "standard_item_type": "inspections",
            "type_display_name": "Inspections",
            "type_color": "#FF0000",
        }
        self.client.post(self.base_url, payload1, format="json")

        payload2 = {
            "is_custom_type": False,
            "standard_item_type": "warranties",
            "type_display_name": "Warranties",
            "type_color": "#00FF00",
        }
        response = self.client.post(self.base_url, payload2, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["standard_item_type"], "warranties")

        # Verify only one preference exists
        count = UserHighlightPreference.objects.filter(
            user=self.user, project=self.project
        ).count()
        self.assertEqual(count, 1)

    def test_validation_requires_standard_type_when_not_custom(self):
        """Test that standard_item_type is required when is_custom_type is False."""
        payload = {
            "is_custom_type": False,
            "type_display_name": "Test",
            "type_color": "#FF0000",
        }

        response = self.client.post(self.base_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_validation_requires_custom_type_when_custom(self):
        """Test that custom_item_type is required when is_custom_type is True."""
        payload = {
            "is_custom_type": True,
            "type_display_name": "Test",
            "type_color": "#FF0000",
        }

        response = self.client.post(self.base_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_validation_custom_type_must_belong_to_project(self):
        """Test that custom_item_type must belong to the same project."""
        other_team = create_team("Other Team")
        other_user = create_user("other")
        Membership.objects.create(team=other_team, user=other_user, role=team_roles.ROLE_ADMIN)
        other_project = Project.objects.create(
            name="Other Project",
            project_number="OP-001",
            team=other_team,
            created_by=other_user,
        )
        other_custom_type = CustomItemType.objects.create(
            name="Other Type",
            color="#999999",
            project=other_project,
            created_by=other_user,
        )

        payload = {
            "is_custom_type": True,
            "custom_item_type": other_custom_type.id,
            "type_display_name": "Test",
            "type_color": "#FF0000",
        }

        response = self.client.post(self.base_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("must belong to the same project", str(response.data))

    def test_validation_custom_type_must_be_active(self):
        """Test that custom_item_type must be active."""
        inactive_type = CustomItemType.objects.create(
            name="Inactive Type",
            color="#888888",
            project=self.project,
            created_by=self.user,
            is_active=False,
        )

        payload = {
            "is_custom_type": True,
            "custom_item_type": inactive_type.id,
            "type_display_name": "Test",
            "type_color": "#FF0000",
        }

        response = self.client.post(self.base_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("must be active", str(response.data))

    def test_validation_type_color_hex_format(self):
        """Test that type_color must be in HEX format."""
        payload = {
            "is_custom_type": False,
            "standard_item_type": "inspections",
            "type_display_name": "Inspections",
            "type_color": "invalid",
        }

        response = self.client.post(self.base_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("HEX format", str(response.data))

    def test_type_color_normalized_to_uppercase(self):
        """Test that type_color is normalized to uppercase."""
        payload = {
            "is_custom_type": False,
            "standard_item_type": "inspections",
            "type_display_name": "Inspections",
            "type_color": "#ff0000",
        }

        response = self.client.post(self.base_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type_color"], "#FF0000")


class UserHighlightPreferencePermissionTests(APITestCase):
    """Tests for permission enforcement on UserHighlightPreference API."""

    def setUp(self):
        self.team = create_team("Permission Team")
        self.owner = create_user("owner")
        self.non_member = create_user("nonmember")

        Membership.objects.create(team=self.team, user=self.owner, role=team_roles.ROLE_ADMIN)

        self.project = Project.objects.create(
            name="Permission Project",
            project_number="PP-001",
            team=self.team,
            created_by=self.owner,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.owner,
            role=ROLE_PROJECT_ADMIN,
        )

        self.base_url = f"/api/deliverables/projects/{self.project.id}/highlight-preference/"

    def test_non_project_member_denied_access(self):
        """Test that non-project members are denied access."""
        self.client.force_authenticate(user=self.non_member)

        response = self.client.get(self.base_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_project_member_denied_create(self):
        """Test that non-project members cannot create preferences."""
        self.client.force_authenticate(user=self.non_member)

        payload = {
            "is_custom_type": False,
            "standard_item_type": "inspections",
            "type_display_name": "Inspections",
            "type_color": "#FF0000",
        }

        response = self.client.post(self.base_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_denied(self):
        """Test that unauthenticated users are denied access."""
        response = self.client.get(self.base_url)

        # DRF returns 403 for unauthenticated requests with session authentication
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_user_can_only_see_own_preference(self):
        """Test that users can only see their own preferences."""
        other_member = create_user("othermember")
        Membership.objects.create(team=self.team, user=other_member, role=team_roles.ROLE_MEMBER)
        ProjectMembership.objects.create(
            project=self.project,
            user=other_member,
            role=ROLE_PROJECT_MEMBER,
        )

        # Owner creates a preference
        self.client.force_authenticate(user=self.owner)
        payload = {
            "is_custom_type": False,
            "standard_item_type": "inspections",
            "type_display_name": "Inspections",
            "type_color": "#FF0000",
        }
        self.client.post(self.base_url, payload, format="json")

        # Other member tries to get preferences - should get 404 (not owner's preference)
        self.client.force_authenticate(user=other_member)
        response = self.client.get(self.base_url)

        # Should get 404 because other_member has no preference, not owner's preference
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
