"""
Test cases for get_next_submittal_number utility function.

This module contains comprehensive tests for the submittal number calculation
utility, ensuring proper scoping by project version and handling of edge cases.
"""
from django.test import TestCase
from apps.deliverables.utils import get_next_submittal_number
from apps.deliverables.models import (
    Project,
    ProjectVersion,
    SubmittalItem,
    MasterFormatSection,
    UploadedFile,
)
from apps.teams.models import Team


class TestGetNextSubmittalNumber(TestCase):
    """Test cases for get_next_submittal_number utility function."""
    
    def setUp(self):
        """Set up test data for submittal number tests."""
        self.team = Team.objects.create(name="Test Team")
        self.project = Project.objects.create(
            name="Test Project",
            team=self.team,
            project_number="PRJ-001"
        )
        # Project automatically creates version 1
        self.project_version_1 = ProjectVersion.objects.get(project=self.project)
        
        # Create a second project version
        self.project_version_2 = ProjectVersion.objects.create(
            project=self.project,
            version_number=2,
            version_name="Version 2"
        )
        
        # Create a second project for cross-project testing
        self.project_2 = Project.objects.create(
            name="Test Project 2",
            team=self.team,
            project_number="PRJ-002"
        )
        self.project_2_version_1 = ProjectVersion.objects.get(project=self.project_2)
        
        # Create master format sections
        self.mf_section = MasterFormatSection.objects.create(
            masterformat_number="01 33 00",
            masterformat_description="Submittal Procedures"
        )
        
        # Create documents
        self.document_v1 = UploadedFile.objects.create(
            name="Test Document V1",
            project=self.project,
            project_version=self.project_version_1,
            document_path="test/path/v1",
            md5="test_v1.pdf"
        )
        
        self.document_v2 = UploadedFile.objects.create(
            name="Test Document V2",
            project=self.project,
            project_version=self.project_version_2,
            document_path="test/path/v2",
            md5="test_v2.pdf"
        )
    
    def test_first_submittal_returns_none(self):
        """Test that the first submittal for a project version returns None."""
        result = get_next_submittal_number(
            project_id=self.project.id,
            project_version_id=self.project_version_1.id
        )
        self.assertIsNone(result)
    
    def test_subsequent_submittals_return_incremented_number(self):
        """Test that subsequent submittals return incremented numbers."""
        # Create first submittal
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version_1,
            masterformat_section=self.mf_section,
            document=self.document_v1,
            submittal_number=1
        )
        
        result = get_next_submittal_number(
            project_id=self.project.id,
            project_version_id=self.project_version_1.id
        )
        self.assertEqual(result, 2)
        
        # Create second submittal
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version_1,
            masterformat_section=self.mf_section,
            document=self.document_v1,
            submittal_number=2
        )
        
        result = get_next_submittal_number(
            project_id=self.project.id,
            project_version_id=self.project_version_1.id
        )
        self.assertEqual(result, 3)
    
    def test_correct_scoping_by_project_version_id(self):
        """Test that submittal numbers are correctly scoped by project_version_id."""
        # Create submittals in version 1
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version_1,
            masterformat_section=self.mf_section,
            document=self.document_v1,
            submittal_number=1
        )
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version_1,
            masterformat_section=self.mf_section,
            document=self.document_v1,
            submittal_number=2
        )
        
        # Create submittals in version 2 (independent numbering)
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version_2,
            masterformat_section=self.mf_section,
            document=self.document_v2,
            submittal_number=1
        )
        
        # Version 1 should get number 3
        result_v1 = get_next_submittal_number(
            project_id=self.project.id,
            project_version_id=self.project_version_1.id
        )
        self.assertEqual(result_v1, 3)
        
        # Version 2 should get number 2 (independent from version 1)
        result_v2 = get_next_submittal_number(
            project_id=self.project.id,
            project_version_id=self.project_version_2.id
        )
        self.assertEqual(result_v2, 2)
    
    def test_decimal_submittal_numbers_are_rounded(self):
        """Test that decimal submittal numbers are properly rounded up."""
        # Create submittal with decimal number
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version_1,
            masterformat_section=self.mf_section,
            document=self.document_v1,
            submittal_number=5.7
        )
        
        result = get_next_submittal_number(
            project_id=self.project.id,
            project_version_id=self.project_version_1.id
        )
        # Should round 5.7 to 6, then add 1 to get 7
        self.assertEqual(result, 7)
    
    def test_non_sequential_numbers_return_max_plus_one(self):
        """Test that non-sequential submittal numbers still return max + 1."""
        # Create submittals with gaps in numbering
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version_1,
            masterformat_section=self.mf_section,
            document=self.document_v1,
            submittal_number=1
        )
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version_1,
            masterformat_section=self.mf_section,
            document=self.document_v1,
            submittal_number=5
        )
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version_1,
            masterformat_section=self.mf_section,
            document=self.document_v1,
            submittal_number=3
        )
        
        result = get_next_submittal_number(
            project_id=self.project.id,
            project_version_id=self.project_version_1.id
        )
        # Should return max (5) + 1 = 6
        self.assertEqual(result, 6)
    
    def test_different_projects_have_independent_numbering(self):
        """Test that different projects have independent submittal numbering."""
        # Create submittals in project 1
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version_1,
            masterformat_section=self.mf_section,
            document=self.document_v1,
            submittal_number=10
        )
        
        # Create submittals in project 2
        document_p2 = UploadedFile.objects.create(
            name="Test Document P2",
            project=self.project_2,
            project_version=self.project_2_version_1,
            document_path="test/path/p2",
            md5="test_p2.pdf"
        )
        SubmittalItem.objects.create(
            project=self.project_2,
            project_version=self.project_2_version_1,
            masterformat_section=self.mf_section,
            document=document_p2,
            submittal_number=1
        )
        
        # Project 1 should get 11
        result_p1 = get_next_submittal_number(
            project_id=self.project.id,
            project_version_id=self.project_version_1.id
        )
        self.assertEqual(result_p1, 11)
        
        # Project 2 should get 2 (independent from project 1)
        result_p2 = get_next_submittal_number(
            project_id=self.project_2.id,
            project_version_id=self.project_2_version_1.id
        )
        self.assertEqual(result_p2, 2)
    
    def test_null_submittal_numbers_are_ignored(self):
        """Test that submittal items with null numbers don't affect the calculation."""
        # Create submittals with and without numbers
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version_1,
            masterformat_section=self.mf_section,
            document=self.document_v1,
            submittal_number=None  # Null number
        )
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version_1,
            masterformat_section=self.mf_section,
            document=self.document_v1,
            submittal_number=3
        )
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version_1,
            masterformat_section=self.mf_section,
            document=self.document_v1,
            submittal_number=None  # Another null number
        )
        
        result = get_next_submittal_number(
            project_id=self.project.id,
            project_version_id=self.project_version_1.id
        )
        # Should return max non-null (3) + 1 = 4
        self.assertEqual(result, 4)
    
    def test_only_null_submittal_numbers_returns_none(self):
        """Test that if all submittal numbers are null, function returns None."""
        # Create submittals with only null numbers
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version_1,
            masterformat_section=self.mf_section,
            document=self.document_v1,
            submittal_number=None
        )
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version_1,
            masterformat_section=self.mf_section,
            document=self.document_v1,
            submittal_number=None
        )
        
        result = get_next_submittal_number(
            project_id=self.project.id,
            project_version_id=self.project_version_1.id
        )
        self.assertIsNone(result)
