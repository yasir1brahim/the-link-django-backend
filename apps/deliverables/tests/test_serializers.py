import unittest
from unittest.mock import patch
from django.test import TestCase

from django.utils import timezone
from django.db.models import QuerySet
from ..models import Project, ProjectVersion, UploadedFile, DocProcessingStatus, Entitlement, SubmittalItem, MasterFormatSection, SpecSection, ROLE_PROJECT_ADMIN
from ..serializers import (ProjectDetailsSerializer, ProjectMembership, ProjectWriteSerializer,
                            SubmittalItemReadSerializer, SubmittalItemWriteSerializer)
from apps.teams.models import Membership
from rest_framework.exceptions import ValidationError
from apps.users.models import CustomUser
from apps.teams.models import Team
from rest_framework.test import APIRequestFactory
class ProjectReadSerializerTest(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            first_name="Test",
            last_name="User"
        )
        self.team = Team.objects.create(
            name="Test Team"
        )
        self.project = Project.objects.create(
            name="Test Project",
            description="Test Description",
            team=self.team
        )
        self.project_version_1 = ProjectVersion.objects.get(project=self.project)

        self.project_entitlement = Entitlement.objects.create(
            code_name="project_level_entitlement"
        )
        self.team_entitlement = Entitlement.objects.create(
            code_name="team_level_entitlement"
        )

        # Create test documents with different statuses and timestamps
        self.doc1 = UploadedFile.objects.create(
            project=self.project,
            name="Doc 1",
            processing_status=DocProcessingStatus.PROCESSED,  # status_order = 6
            created_at=timezone.now(),
            project_version=self.project_version_1
        )
        
        self.doc2 = UploadedFile.objects.create(
            project=self.project,
            name="Doc 2", 
            processing_status=DocProcessingStatus.PENDING_PROCESSING,  # status_order = 1
            created_at=timezone.now(),
            project_version=self.project_version_1
        )
        
        self.doc3 = UploadedFile.objects.create(
            project=self.project,
            name="Doc 3",
            processing_status=DocProcessingStatus.PROCESSING,  # status_order = 2
            created_at=timezone.now(),
            project_version=self.project_version_1
        )

    @patch('apps.deliverables.serializers.s3.generate_presigned_url')
    def test_serializer_contains_expected_fields(self, mock_generate_presigned_url):
        """Test that serializer contains all expected fields"""
        mock_generate_presigned_url.return_value = "https://test.com"
        serializer = ProjectDetailsSerializer(instance=self.project)
        expected_fields = {
            'id', 'name', 'description', 'team', 
            'members', 'user_limit',
            'start_date', 'end_date', 'is_archived',
            'doc_parsed', 'document_details', 'project_number',
            'project_type', 'project_versions'
        }
        self.assertEqual(set(serializer.data.keys()), expected_fields)

    @patch('apps.deliverables.serializers.s3.generate_presigned_url')
    def test_team_field_returns_id(self, mock_generate_presigned_url):
        """Test that team field returns only the ID"""
        mock_generate_presigned_url.return_value = "https://test.com"
        serializer = ProjectDetailsSerializer(instance=self.project)
        self.assertEqual(serializer.data['team'], self.team.id)

    @patch('apps.deliverables.serializers.s3.generate_presigned_url')
    def test_members_field_serialization(self, mock_generate_presigned_url):
        """Test that members field properly serializes project memberships"""
        mock_generate_presigned_url.return_value = "https://test.com"
        membership = ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role="MEMBER"
        )
        
        serializer = ProjectDetailsSerializer(instance=self.project)
        self.assertEqual(len(serializer.data['members']), 1)
        self.assertEqual(serializer.data['members'][0]['user_id'], self.user.id)
        self.assertEqual(serializer.data['members'][0]['role'], "MEMBER")

    @patch('apps.deliverables.serializers.s3.generate_presigned_url')
    def test_project_versions(self, mock_generate_presigned_url):
        """Test that members field properly serializes project memberships"""
        mock_generate_presigned_url.return_value = "https://test.com"
        project_version_2 = ProjectVersion.objects.create(
            project = self.project,
            version_name = "Version 2"
        )
        project_version_3 = ProjectVersion.objects.create(
            project = self.project,
            version_name = "Version 3"
        )
        
        serializer = ProjectDetailsSerializer(instance=self.project)
        self.assertEqual(len(serializer.data['project_versions']), 3)
        self.assertEqual(serializer.data['project_versions'][0]['version_name'], self.project_version_1.version_name)
        self.assertEqual(serializer.data['project_versions'][1]['version_name'], project_version_2.version_name)
        self.assertEqual(serializer.data['project_versions'][2]['version_name'], project_version_3.version_name)

    @patch('apps.deliverables.serializers.s3.generate_presigned_url')
    def test_project_versions_only_returns_unarchived_versions(self, mock_generate_presigned_url):
        """Test that project versions only returns unarchived versions"""
        mock_generate_presigned_url.return_value = "https://test.com"
        project_version_2 = ProjectVersion.objects.create(
            project = self.project,
            version_name = "Version 2"
        )
        project_version_3 = ProjectVersion.objects.create(
            project = self.project,
            version_name = "Version 3"
        )
        project_version_2.is_archived = True
        project_version_2.save()
        serializer = ProjectDetailsSerializer(instance=self.project)
        self.assertEqual(len(serializer.data['project_versions']), 2)
        self.assertEqual(serializer.data['project_versions'][0]['version_name'], self.project_version_1.version_name)
        self.assertEqual(serializer.data['project_versions'][1]['version_name'], project_version_3.version_name)

    @unittest.skip("Entitlements aren't used yet, so not calculated to improve performance")
    def test_get_entitlements_project_level(self):
        """Test entitlements method returns project-level entitlements when they exist"""
        self.project.entitlements.add(self.project_entitlement)
        
        serializer = ProjectDetailsSerializer(instance=self.project)
        self.assertEqual(
            list(serializer.data['entitlements']),
            ['project_level_entitlement']
        )

    @unittest.skip("Entitlements aren't used yet, so not calculated to improve performance")
    def test_get_entitlements_team_level_fallback(self):
        """Test entitlements method falls back to team-level entitlements"""
        self.team.entitlements.add(self.team_entitlement)
        
        serializer = ProjectDetailsSerializer(instance=self.project)
        self.assertEqual(
            list(serializer.data['entitlements']),
            ['team_level_entitlement']
        )

    @patch('apps.deliverables.serializers.s3.generate_presigned_url')
    def test_document_ordering(self, mock_generate_presigned_url):
        mock_generate_presigned_url.return_value = "https://test.com"
        serializer = ProjectDetailsSerializer(self.project)
        documents = serializer.data['document_details']
        
        # Check the order matches our status_order Case/When logic
        self.assertEqual(documents[0]['document_name'], "Doc 2")  # PENDING_PROCESSING (1)
        self.assertEqual(documents[1]['document_name'], "Doc 3")  # PROCESSING (2) 
        self.assertEqual(documents[2]['document_name'], "Doc 1")  # PROCESSED (6)


    @patch('apps.deliverables.serializers.s3.generate_presigned_url')
    def test_document_ordering_same_status(self, mock_generate_presigned_url):
        # Create two documents with same status but different timestamps
        mock_generate_presigned_url.return_value = "https://test.com"
        older_time = timezone.now() - timezone.timedelta(hours=1)
        newer_time = timezone.now()
        
        doc4 = UploadedFile.objects.create(
            project=self.project,
            name="Doc 4",
            processing_status=DocProcessingStatus.PENDING_PROCESSING,
            created_at=older_time,
            project_version=self.project_version_1
        )
        
        doc5 = UploadedFile.objects.create(
            project=self.project,
            name="Doc 5",
            processing_status=DocProcessingStatus.PENDING_PROCESSING,
            created_at=newer_time,
            project_version=self.project_version_1
        )
        
        serializer = ProjectDetailsSerializer(self.project)
        documents = serializer.data['document_details']
        
        # Find documents with PENDING_PROCESSING status
        pending_docs = [doc for doc in documents 
                       if doc['document_status'] == DocProcessingStatus.PENDING_PROCESSING]
        
        # Verify that within same status, docs are ordered by -created_at
        self.assertEqual(pending_docs[0]['document_name'], "Doc 5")
        self.assertEqual(pending_docs[1]['document_name'], "Doc 4")

    @patch('apps.deliverables.serializers.s3.generate_presigned_url')
    def test_get_doc_parsed_returns_correct_count(self, mock_generate_presigned_url):
        # Arrange
        mock_generate_presigned_url.return_value = "https://test.com"
        UploadedFile.objects.create(
            project=self.project,
            name="test1.pdf",
            processing_status=DocProcessingStatus.PROCESSED,
            project_version=self.project_version_1
        )
        UploadedFile.objects.create(
            project=self.project,
            name="test2.pdf",
            processing_status=DocProcessingStatus.PROCESSING,
            project_version=self.project_version_1
        )

        # Act
        result = ProjectDetailsSerializer(self.project).data['doc_parsed']

        # Assert
        self.assertEqual(result, 5)
    
    def test_empty_project_returns_empty_document_details(self):
        # Act
        new_project = Project.objects.create(
            name="New Project",
            description="New Description",
            team=self.team
        )
        result = ProjectDetailsSerializer(new_project).data['document_details']

        # Assert
        self.assertEqual(result, [])
        
    def test_empty_project_returns_zero_doc_parsed(self):
        # Act
        new_project = Project.objects.create(
            name="New Project",
            description="New Description",
            team=self.team
        )
        result = ProjectDetailsSerializer(new_project).data['doc_parsed']

        # Assert
        self.assertEqual(result, 0)


class TestProjectWriteSerializer(TestCase):
    def setUp(self):
        # Create test data
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.other_team = Team.objects.create(name="Other Team", slug="other-team")
        
        self.user1 = CustomUser.objects.create(
            username="user1",
            first_name="Test",
            last_name="User1"
        )
        self.user2 = CustomUser.objects.create(
            username="user2",
            first_name="Test",
            last_name="User2"
        )

        Membership.objects.create(
            team=self.team,
            user=self.user1,
            role="MEMBER"
        )

        
        self.project_data = {
            'name': 'Test Project',
            'project_number': '123456',
            'description': 'Test Description',
            'team': self.team.id,
            'members': [
                {
                    'user_id': self.user1.id,
                    'role': 'project_member'
                }
            ]
        }

        self.factory = APIRequestFactory()
        self.request = self.factory.get('/')
        self.request.user = self.user1

    def test_create_project_with_valid_data(self):
        """Test creating a project with valid data"""
        serializer = ProjectWriteSerializer(data=self.project_data)
        self.assertTrue(serializer.is_valid(raise_exception=True))
        
        project = serializer.save()
        self.assertEqual(project.name, 'Test Project')
        self.assertEqual(project.team, self.team)
        self.assertEqual(project.project_memberships.count(), 1)
        self.assertEqual(project.project_memberships.first().user, self.user1)

    def test_create_project_without_members(self):
        """Test creating a project without members"""
        self.project_data['members'] = []
        serializer = ProjectWriteSerializer(data=self.project_data)
        self.assertTrue(serializer.is_valid())
        project = serializer.save()
        self.assertEqual(project.name, 'Test Project')
        self.assertEqual(project.team, self.team)
        self.assertEqual(project.project_memberships.count(), 0)

    def test_validate_members_must_be_in_team(self):
        """Test validation that members must belong to the project's team"""
        # Add user2 who is not in the team
        self.project_data['members'].append({
            'user_id': self.user2.id,
            'role': 'project_member'
        })

        print("team", self.team.members.all())
        print("user2 team membership", self.user2.is_member_of_team(self.team))
        
        serializer = ProjectWriteSerializer(
            data=self.project_data,
        )
        print("serializer.initial_data", serializer.initial_data)
        serializer.is_valid()
        print("serializer.data", serializer.data)

        with self.assertRaises(ValidationError) as context:
            serializer.is_valid(raise_exception=True)
        
        self.assertIn('All members must be a member of the team', str(context.exception))

    def test_update_project_members(self):
        """Test updating project members"""
        # Create initial project with user1
        project = Project.objects.create(
            name='Test Project',
            team=self.team
        )
        ProjectMembership.objects.create(
            project=project,
            user=self.user1,
            role=ROLE_PROJECT_ADMIN
        )

        # Add user2 to team and update project members
        Membership.objects.create(
            team=self.team,
            user=self.user2,
            role="MEMBER"
        )
        update_data = {
            'members': [
                {
                    'user_id': self.user2.id,
                    'role': 'project_member'
                }
            ]
        }

        serializer = ProjectWriteSerializer(
            instance=project,
            data=update_data,
            partial=True,
            context={'request': self.request}
        )
        self.assertTrue(serializer.is_valid())
        updated_project = serializer.save()

        # Check that user1 was removed and user2 was added
        self.assertEqual(updated_project.project_memberships.count(), 1)
        self.assertEqual(
            updated_project.project_memberships.first().user,
            self.user2
        )

    def test_partial_update_preserves_other_fields(self):
        """Test that partial update only modifies specified fields"""
        project = Project.objects.create(
            name='Original Name',
            description='Original Description',
            team=self.team
        )

        update_data = {
            'name': 'New Name'
        }

        serializer = ProjectWriteSerializer(
            instance=project,
            data=update_data,
            partial=True,
            context={'request': self.request}
        )
        self.assertTrue(serializer.is_valid())
        updated_project = serializer.save()

        self.assertEqual(updated_project.name, 'New Name')
        self.assertEqual(updated_project.description, 'Original Description')
        self.assertEqual(updated_project.team, self.team)

    def test_bulk_create_members(self):
        """Test creating multiple project members at once"""
        # Add both users to team
        Membership.objects.create(
            team=self.team,
            user=self.user2,
            role="MEMBER"
        )
        
        self.project_data['members'] = [
            {'user_id': self.user1.id, 'role': 'project_member'},
            {'user_id': self.user2.id, 'role': 'project_admin'}
        ]

        serializer = ProjectWriteSerializer(data=self.project_data)
        self.assertTrue(serializer.is_valid())
        project = serializer.save()

        self.assertEqual(project.project_memberships.count(), 2)
        roles = set(project.project_memberships.values_list('role', flat=True))
        self.assertEqual(roles, {'project_member', 'project_admin'})


class TestSubmittalItemReadSerializer(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Test Team")
        self.project = Project.objects.create(name="Test Project", team=self.team)
        self.project_version = ProjectVersion.objects.get(project=self.project)

        self.submittal_item = SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version,
            masterformat_section=MasterFormatSection.objects.create(masterformat_number="01000"),
            document=UploadedFile.objects.create(name="Test Document", project=self.project, project_version=self.project_version, document_path="test/path"),
        )

    def test_serializer_contains_expected_fields(self):
        """Test that serializer contains all expected fields"""
        serializer = SubmittalItemReadSerializer(instance=self.submittal_item)
        expected_fields = {
            'additional_text_locations',
            'doc_id',
            'doc_link',
            'id',
            'item_desc',
            'para_context',
            'para_no',
            'project_id',
            'section_title',
            'spec_section',
            'submittal_number',
            'text_loc',
            'type',
            'parsing_method',
        }
        self.assertEqual(set(serializer.data.keys()), expected_fields)


class TestSubmittalItemWriteSerializer(TestCase):
    def setUp(self):
        # Create necessary related objects
        self.team = Team.objects.create(name="Test Team")
        self.user = CustomUser.objects.create(
            email="test@example.com",
            first_name="Test",
            last_name="User"
        )
        self.project = Project.objects.create(
            name="Test Project",
            team=self.team
        )
        self.project_version = ProjectVersion.objects.get(project=self.project)
        self.document = UploadedFile.objects.create(
            name="Test Document",
            project=self.project,
            document_path="test/path",
            md5="test.pdf",
            project_version=self.project_version
        )
        self.mf_section = MasterFormatSection.objects.create(
            masterformat_number="01 33 00",
            masterformat_description="Submittal Procedures"
        )
        
    def test_create_basic_submittal_item(self):
        # Test creating a submittal item without added_under_submittal_id
        data = {
            "updated_by": self.user.id,
            "spec_section": "01 33 00",
            "item_desc": "Test Description",
            "para_context": "Test Context",
            "para_no": "1.2.3",
            "type": "Product Data",
            "project_version": str(self.project_version.id)
        }
        
        serializer = SubmittalItemWriteSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        submittal_item = serializer.save(project_id=self.project.id)
        
        self.assertEqual(submittal_item.submittal_description, "Test Description")
        self.assertEqual(submittal_item.masterformat_section, self.mf_section)
        self.assertTrue(submittal_item.manually_added)
        self.assertIsNone(submittal_item.added_under_submittal)
        self.assertIsNone(submittal_item.document)
        self.assertIsNone(submittal_item.spec_section)

    def test_create_submittal_item_assigns_next_submittal_number(self):
        # Create a submittal item
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version,
            masterformat_section=self.mf_section,
            document=self.document,
            manually_added=False,
            submittal_number=1
        )
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version,
            masterformat_section=self.mf_section,
            document=self.document,
            manually_added=False,
            submittal_number=2
        )
        data = {
            "updated_by": self.user.id,
            "spec_section": "01 33 00",
            "item_desc": "Test Description",
            "para_context": "Test Context",
            "para_no": "1.2.3",
            "type": "Product Data",
            "project_version": str(self.project_version.id)
        }
        serializer = SubmittalItemWriteSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        submittal_item = serializer.save(project_id=self.project.id)
        self.assertEqual(submittal_item.submittal_number, 3.0)

    def test_create_submittal_item_with_parent(self):
        # Create a parent submittal item first
        spec_section = SpecSection.objects.create(
            masterformat_section=self.mf_section,
            document=self.document,
            processing_method=SpecSection.ProcessingMethod.REGEX_SUCCESS
        )
        parent_submittal = SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version,
            masterformat_section=self.mf_section,
            submittal_description="Parent Submittal",
            document=None,
            spec_section=spec_section,
            manually_added=False
        )

        data = {
            "updated_by": self.user.id,
            "spec_section": "01 33 00",
            "item_desc": "Child Description",
            "para_context": "Child Context",
            "para_no": "1.2.3",
            "type": "Product Data",
            "added_under_submittal_id": parent_submittal.id,
            "project_version": str(self.project_version.id)
        }
        
        serializer = SubmittalItemWriteSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        print("serializer.validated_data", serializer.validated_data)
        submittal_item = serializer.save(project_id=self.project.id)
        
        self.assertEqual(submittal_item.submittal_description, "Child Description")
        self.assertEqual(submittal_item.added_under_submittal, parent_submittal)
        self.assertEqual(submittal_item.spec_section, spec_section)
        self.assertEqual(submittal_item.document, parent_submittal.document)
        self.assertTrue(submittal_item.manually_added)

    def test_create_with_invalid_parent_id(self):
        # Test creating with non-existent parent submittal ID
        data = {
            "updated_by": self.user.id,
            "spec_section": "01 33 00",
            "item_desc": "Test Description",
            "para_context": "Test Context",
            "para_no": "1.2.3",
            "type": "Product Data",
            "added_under_submittal_id": 99999,  # Non-existent ID
            "project_version": str(self.project_version.id)
        }
        
        serializer = SubmittalItemWriteSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        submittal_item = serializer.save(project_id=self.project.id)
        
        self.assertIsNone(submittal_item.added_under_submittal)
        self.assertIsNone(submittal_item.document)
        self.assertIsNone(submittal_item.spec_section)

    def test_create_with_parent_in_different_project(self):
        other_project = Project.objects.create(
            name="Other Project",
            team=self.team
        )
        other_submittal = SubmittalItem.objects.create(
            project=other_project,
            project_version=self.project_version,
            masterformat_section=self.mf_section,
            document=self.document,
            manually_added=False
        )
        data = {
            "updated_by": self.user.id,
            "spec_section": "01 33 00",
            "item_desc": "Test Description",
            "para_context": "Test Context",
            "para_no": "1.2.3",
            "type": "Product Data",
            "added_under_submittal_id": other_submittal.id,
            "project_version": str(self.project_version.id)
        }
        
        serializer = SubmittalItemWriteSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        submittal_item = serializer.save(project_id=self.project.id)
        
        self.assertIsNone(submittal_item.added_under_submittal)
        self.assertIsNone(submittal_item.document)
        self.assertIsNone(submittal_item.spec_section)
