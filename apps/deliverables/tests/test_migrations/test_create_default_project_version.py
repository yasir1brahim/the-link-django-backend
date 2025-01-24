from django.test import TestCase
from django.db import connections, migrations
from django.core.management import call_command
from django.db.migrations.executor import MigrationExecutor
from django.db import connection

from apps.teams.models import Team
from apps.deliverables.models import (
    Project,
    ProjectVersion,
    UploadedFile,
    SubmittalItem,
    SubmittalItemList,
    NoticeMatch,
    MasterFormatSection,
    SpecSection,
    NoticeExcerpt,
)

class TestCreateDefaultProjectVersion(TestCase):
    def setUp(self):
        # Get executor
        self.executor = MigrationExecutor(connection)
        
        # Get the app and migration you want to test
        self.app = 'deliverables'
        # This should be the migration immediately BEFORE your data migration
        self.migrate_from = [(self.app, '0032_projectversion_noticematch_project_version_and_more')]
        # This should be your data migration
        self.migrate_to = [(self.app, '0033_create_default_project_version')]

        # Reverse to the original migration
        self.executor.migrate(self.migrate_from)

        # Create the old schema editor to set up the old state
        self.old_apps = self.executor.loader.project_state(self.migrate_from).apps

        

    def tearDown(self):
        pass
        # Clean up by running all migrations
        # call_command('migrate')

    def test_data_migration(self):
        """Test the data migration"""
        # Create data in the old state
        OldTeam = self.old_apps.get_model('teams', 'Team')
        OldProject = self.old_apps.get_model(self.app, 'Project')
        OldUploadedFile = self.old_apps.get_model(self.app, 'UploadedFile')
        OldSubmittalItem = self.old_apps.get_model(self.app, 'SubmittalItem')
        OldSubmittalItemList = self.old_apps.get_model(self.app, 'SubmittalItemList')
        OldNoticeMatch = self.old_apps.get_model(self.app, 'NoticeMatch')
        OldNoticeExcerpt = self.old_apps.get_model(self.app, 'NoticeExcerpt')
        OldMasterFormatSection = self.old_apps.get_model(self.app, 'MasterFormatSection')
        OldProjectVersion = self.old_apps.get_model(self.app, 'ProjectVersion')
        # Create some documents, submittal items, submittal item lists, and notices
        self.masterformat_section_1 = OldMasterFormatSection.objects.create(masterformat_number="123456")
        self.team_1 = OldTeam.objects.create(name="Test Team 1", slug="test-team-1")
        self.team_2 = OldTeam.objects.create(name="Test Team 2", slug="test-team-2")
        self.project_1 = OldProject.objects.create(name="Test Project 1", project_number="123456", team=self.team_1)
        self.project_2 = OldProject.objects.create(name="Test Project 2", project_number="123457", team=self.team_2)
        self.document_1 = OldUploadedFile.objects.create(
            name="Test Document 1",
            project=self.project_1,
            document_path="test_document_1.pdf",
            md5="1234567890",
            processing_status="PROCESSED"
        )
        self.document_2 = OldUploadedFile.objects.create(
            name="Test Document 2",
            project=self.project_2,
            document_path="test_document_2.pdf",
            md5="1234567890",
            processing_status="PROCESSED"
        )
        self.notice_excerpt_1 = OldNoticeExcerpt.objects.create(
            document=self.document_1,
            anchor="Test Notice Excerpt 1",
            lines=[1, 2, 3, 4, 5]
        )
        self.notice_excerpt_2 = OldNoticeExcerpt.objects.create(
            document=self.document_2,
            anchor="Test Notice Excerpt 2",
            lines=[1, 2, 3, 4, 5]
        )
        self.submittal_item_1 = OldSubmittalItem.objects.create(
            document=self.document_1,
            project=self.project_1,
            masterformat_section=self.masterformat_section_1,
            paragraph_number="1.1",
            submittal_type="Test Submittal Type 1",
            submittal_description="Test Submittal Item 1",
            submittal_content="Test Submittal Content 1"
        )
        self.submittal_item_2 = OldSubmittalItem.objects.create(
            document=self.document_2,
            project=self.project_2,
            masterformat_section=self.masterformat_section_1,
            paragraph_number="1.1",
            submittal_type="Test Submittal Type 2",
            submittal_description="Test Submittal Item 2",
            submittal_content="Test Submittal Content 2"
        )
        self.submittal_item_list_1 = OldSubmittalItemList.objects.create(
            name="Test Submittal Item List 1", 
            project=self.project_1,
        )
        self.submittal_item_list_1.submittals.add(self.submittal_item_1)
        self.submittal_item_list_2 = OldSubmittalItemList.objects.create(
            name="Test Submittal Item List 2",
            project=self.project_2,
        )
        self.submittal_item_list_2.submittals.add(self.submittal_item_2)
        self.notice_1 = OldNoticeMatch.objects.create(
            document=self.document_1,
            project=self.project_1,
            highlight_discriminators={"test": "test"},
            leading_anchor="Test Notice 1",
        )
        self.notice_1.excerpt_anchors.add(self.notice_excerpt_1)
        self.notice_2 = OldNoticeMatch.objects.create(
            document=self.document_2,
            project=self.project_2,
            highlight_discriminators={"test": "test"},
            leading_anchor="Test Notice 2",
        )
        self.notice_2.excerpt_anchors.add(self.notice_excerpt_2)

        # Assert some preconditions
        self.assertEqual(OldProjectVersion.objects.count(), 0)

        print(f"OldProjectVersion.objects.count(): {OldProjectVersion.objects.count()}")
        print("running migration")
        # Run the migration we want to test
        self.executor.loader.build_graph()  # reload.
        self.executor.migrate(self.migrate_to)
        print(f"OldProjectVersion.objects.count(): {OldProjectVersion.objects.count()}")
        # Get the new state
        new_apps = self.executor.loader.project_state(self.migrate_to).apps
        NewProject = new_apps.get_model(self.app, 'Project')
        self.project_1 = NewProject.objects.get(id=self.project_1.id)
        self.project_2 = NewProject.objects.get(id=self.project_2.id)
        NewProjectVersion = new_apps.get_model(self.app, 'ProjectVersion')
        NewUploadedFile = new_apps.get_model(self.app, 'UploadedFile')
        NewSubmittalItem = new_apps.get_model(self.app, 'SubmittalItem')
        NewSubmittalItemList = new_apps.get_model(self.app, 'SubmittalItemList')
        NewNoticeMatch = new_apps.get_model(self.app, 'NoticeMatch')
        print(f"ProjectVersion.objects.count(): {ProjectVersion.objects.count()}")
        print(f"NewProjectVersion.objects.count(): {NewProjectVersion.objects.count()}")

        # Assert a project version was created for each project
        self.assertEqual(NewProjectVersion.objects.count(), 2)
        project_version_1 = NewProjectVersion.objects.get(project=self.project_1)
        project_version_2 = NewProjectVersion.objects.get(project=self.project_2)
        self.assertEqual(project_version_1.project, self.project_1)
        self.assertEqual(project_version_1.version_number, 1)
        self.assertEqual(project_version_1.version_name, "Version 1")
        self.assertEqual(project_version_1.created_by, None)
        self.assertEqual(project_version_2.project, self.project_2)
        self.assertEqual(project_version_2.version_number, 1)
        self.assertEqual(project_version_2.version_name, "Version 1")
        self.assertEqual(project_version_2.created_by, None)


        # Assert that the documents are associated with the project versions
        self.assertEqual(NewUploadedFile.objects.count(), 2)
        self.assertEqual(NewUploadedFile.objects.get(project=self.project_1).project_version, project_version_1)
        self.assertEqual(NewUploadedFile.objects.get(project=self.project_1).project, self.project_1)
        self.assertEqual(NewUploadedFile.objects.get(project=self.project_2).project_version, project_version_2)
        self.assertEqual(NewUploadedFile.objects.get(project=self.project_2).project, self.project_2)

        # Assert that the submittal items are associated with the project versions
        self.assertEqual(NewSubmittalItem.objects.count(), 2)
        self.assertEqual(NewSubmittalItem.objects.get(project=self.project_1).project_version, project_version_1)
        self.assertEqual(NewSubmittalItem.objects.get(project=self.project_2).project_version, project_version_2)
        self.assertEqual(NewSubmittalItemList.objects.get(project=self.project_1).project_version, project_version_1)
        self.assertEqual(NewSubmittalItemList.objects.get(project=self.project_2).project_version, project_version_2)

        # Assert that the notice matches are associated with the project versions
        self.assertEqual(NewNoticeMatch.objects.count(), 2)
        notice_match_1 = NewNoticeMatch.objects.get(project=self.project_1)
        notice_match_2 = NewNoticeMatch.objects.get(project=self.project_2)
        self.assertEqual(notice_match_1.project_version, project_version_1)
        self.assertEqual(notice_match_2.project_version, project_version_2)

