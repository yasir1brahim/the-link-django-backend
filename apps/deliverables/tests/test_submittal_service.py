from django.test import TestCase
from apps.teams.models import Team
from ..models import Project, ProjectVersion, SubmittalItem, SpecSection, MasterFormatSection, UploadedFile
from ..services import SubmittalService


class TestSubmittalNumberAssignment(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(name="Test Project", team=self.team)
        self.project_version = ProjectVersion.objects.get(project=self.project)
        self.project_version_2 = ProjectVersion.objects.create(
            project=self.project,
            version_name="Test Version 2"
        )
        self.masterformat1 = MasterFormatSection.objects.create(
            masterformat_number="033000"
        )
        self.masterformat2 = MasterFormatSection.objects.create(
            masterformat_number="033001"
        )
        self.masterformat3 = MasterFormatSection.objects.create(
            masterformat_number="033002"
        )
        self.document = UploadedFile.objects.create(
            project=self.project,
            project_version=self.project_version,
            document_path="test.pdf",
            name="test.pdf",
            md5="test.pdf",
            processing_status='PROCESSED'
        )
        self.spec_section1 = SpecSection.objects.create(
            document=self.document,
            masterformat_section=self.masterformat1,
            processing_method=SpecSection.ProcessingMethod.REGEX_SUCCESS
        )
        self.spec_section2 = SpecSection.objects.create(
            document=self.document,
            masterformat_section=self.masterformat2,
            processing_method=SpecSection.ProcessingMethod.REGEX_SUCCESS
        )
        self.spec_section3 = SpecSection.objects.create(
            document=self.document,
            masterformat_section=self.masterformat3,
            processing_method=SpecSection.ProcessingMethod.REGEX_SUCCESS
        )
        self.document_2 = UploadedFile.objects.create(
            project=self.project,
            project_version=self.project_version_2,
            document_path="test.pdf",
            name="test.pdf",
            md5="test.pdf",
            processing_status='PROCESSED'
        )
        self.document_2_spec_section1 = SpecSection.objects.create(
            document=self.document_2,
            masterformat_section=self.masterformat1,
            processing_method=SpecSection.ProcessingMethod.REGEX_SUCCESS
        )
        self.document_2_spec_section2 = SpecSection.objects.create(
            document=self.document_2,
            masterformat_section=self.masterformat2,
            processing_method=SpecSection.ProcessingMethod.REGEX_SUCCESS
        )
        self.document_2_spec_section3 = SpecSection.objects.create(
            document=self.document_2,
            masterformat_section=self.masterformat3,
            processing_method=SpecSection.ProcessingMethod.REGEX_SUCCESS
        )
        
    def test_initial_assignment(self):
        """Test initial assignment of submittal numbers"""
        # Create test items without submittal numbers
        sections = [self.spec_section1, self.spec_section2, self.spec_section3] * 3
        items = [
            SubmittalItem.objects.create(
                project=self.project,
                project_version=self.project_version,
                spec_section=section,
                masterformat_section=section.masterformat_section,
                submittal_number=None,
                paragraph_number=f"{9-i}"
            ) for i, section in enumerate(sections)
        ]

        SubmittalService._actually_assign_submittal_numbers(
            project=self.project.id,
            project_version_id=self.project_version.id,
            reassign=False
        )

        # Refresh from db and verify numbers were assigned sequentially
        items = SubmittalItem.objects.all().order_by('submittal_number')
        self.assertEqual(items[0].masterformat_section.masterformat_number, "033000")
        self.assertEqual(items[1].masterformat_section.masterformat_number, "033000")
        self.assertEqual(items[2].masterformat_section.masterformat_number, "033000")
        self.assertEqual(items[3].masterformat_section.masterformat_number, "033001")
        self.assertEqual(items[4].masterformat_section.masterformat_number, "033001")
        self.assertEqual(items[5].masterformat_section.masterformat_number, "033001")
        self.assertEqual(items[6].masterformat_section.masterformat_number, "033002")
        self.assertEqual(items[7].masterformat_section.masterformat_number, "033002")
        self.assertEqual(items[8].masterformat_section.masterformat_number, "033002")

        self.assertEqual(items[0].paragraph_number, "3")
        self.assertEqual(items[1].paragraph_number, "6")
        self.assertEqual(items[2].paragraph_number, "9")
        self.assertEqual(items[3].paragraph_number, "2")
        self.assertEqual(items[4].paragraph_number, "5")
        self.assertEqual(items[5].paragraph_number, "8")
        self.assertEqual(items[6].paragraph_number, "1")
        self.assertEqual(items[7].paragraph_number, "4")
        self.assertEqual(items[8].paragraph_number, "7")


    def test_submittal_numbers_are_assigned_with_new_set_in_new_version(self):
        """Test submittal numbers are assigned with new set in new version"""
        # Create test items without submittal numbers
        sections = [self.spec_section1, self.spec_section2, self.spec_section3] * 3
        items = [
            SubmittalItem.objects.create(
                project=self.project,
                project_version=self.project_version,
                spec_section=section,
                masterformat_section=section.masterformat_section,
                submittal_number=None,
                paragraph_number=f"{9-i}"
            ) for i, section in enumerate(sections)
        ]

        SubmittalService._actually_assign_submittal_numbers(
            project=self.project.id,
            project_version_id=self.project_version.id,
            reassign=False
        )

        # Create test items without submittal numbers in new version
        sections_2 = [self.document_2_spec_section1, self.document_2_spec_section2, self.document_2_spec_section3] * 3
        items_2 = [
            SubmittalItem.objects.create(
                project=self.project,
                project_version=self.project_version_2,
                spec_section=section,
                masterformat_section=section.masterformat_section,
                submittal_number=None,
                paragraph_number=f"{9-i}"
            ) for i, section in enumerate(sections_2)
        ]

        SubmittalService._actually_assign_submittal_numbers(
            project=self.project.id,
            project_version_id=self.project_version_2.id,
            reassign=False
        )

        # Refresh from db and verify numbers were assigned sequentially
        items = SubmittalItem.objects.filter(project_version=self.project_version_2).order_by('submittal_number')
        self.assertEqual(items[0].masterformat_section.masterformat_number, "033000")
        self.assertEqual(items[1].masterformat_section.masterformat_number, "033000")
        self.assertEqual(items[2].masterformat_section.masterformat_number, "033000")
        self.assertEqual(items[3].masterformat_section.masterformat_number, "033001")
        self.assertEqual(items[4].masterformat_section.masterformat_number, "033001")
        self.assertEqual(items[5].masterformat_section.masterformat_number, "033001")
        self.assertEqual(items[6].masterformat_section.masterformat_number, "033002")
        self.assertEqual(items[7].masterformat_section.masterformat_number, "033002")
        self.assertEqual(items[8].masterformat_section.masterformat_number, "033002")

        self.assertEqual(items[0].paragraph_number, "3")
        self.assertEqual(items[1].paragraph_number, "6")
        self.assertEqual(items[2].paragraph_number, "9")
        self.assertEqual(items[3].paragraph_number, "2")
        self.assertEqual(items[4].paragraph_number, "5")
        self.assertEqual(items[5].paragraph_number, "8")
        self.assertEqual(items[6].paragraph_number, "1")
        self.assertEqual(items[7].paragraph_number, "4")
        self.assertEqual(items[8].paragraph_number, "7")


    def test_excluded_items_not_assigned(self):
        """Test items with REGEX_UNABLE_TO_DETECT are excluded"""
        excluded_section = SpecSection.objects.create(
            document=self.document,
            masterformat_section=self.masterformat1,
            processing_method=SpecSection.ProcessingMethod.REGEX_UNABLE_TO_DETECT
        )

        # Create one excluded item
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version,
            spec_section=excluded_section,
            masterformat_section=excluded_section.masterformat_section,
            submittal_number=None
        )

        # Create one normal item
        SubmittalItem.objects.create(
            project=self.project,
            project_version=self.project_version,
            spec_section=self.spec_section1,
            masterformat_section=self.spec_section1.masterformat_section,
            submittal_number=None
        )

        SubmittalService._actually_assign_submittal_numbers(
            project=self.project.id,
            project_version_id=self.project_version.id,
            reassign=False
        )

        # Verify only non-excluded item got a number
        excluded = SubmittalItem.objects.filter(
            spec_section__processing_method=SpecSection.ProcessingMethod.REGEX_UNABLE_TO_DETECT
        ).first()
        self.assertIsNone(excluded.submittal_number)

        normal = SubmittalItem.objects.filter(
            spec_section__processing_method=SpecSection.ProcessingMethod.REGEX_SUCCESS
        ).first()
        self.assertEqual(normal.submittal_number, 1)