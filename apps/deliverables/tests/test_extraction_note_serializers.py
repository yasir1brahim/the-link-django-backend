# apps/deliverables/tests/test_extraction_note_serializers.py
from django.test import TestCase
from apps.deliverables.models import ExtractedData, ExtractionNote, Project, ProjectVersion, ExtractionSource, CustomItemType
from apps.deliverables.serializers.extraction_note import ExtractionNoteSerializer, ExtractionNoteCreateUpdateSerializer
from apps.teams.models import Team
from django.contrib.auth import get_user_model

User = get_user_model()


class TestExtractionNoteSerializer(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('test@example.com', first_name='Test', last_name='User')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(name="Test Project", team=self.team, created_by=self.user)
        self.version = self.project.versions.first()
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
        self.note = ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="Test note content",
            created_by=self.user
        )

    def test_serializer_includes_all_fields(self):
        """Test that serializer includes required fields"""
        serializer = ExtractionNoteSerializer(self.note)
        data = serializer.data

        self.assertIn('id', data)
        self.assertIn('text', data)
        self.assertIn('created_by_id', data)
        self.assertIn('created_by_name', data)
        self.assertIn('created_at', data)
        self.assertIn('updated_at', data)

        self.assertEqual(data['text'], "Test note content")
        self.assertEqual(data['created_by_id'], self.user.id)
        self.assertEqual(data['created_by_name'], "Test User")

    def test_serializer_with_null_user(self):
        """Test serializer handles deleted user (null created_by)"""
        self.note.created_by = None
        self.note.save()

        serializer = ExtractionNoteSerializer(self.note)
        data = serializer.data

        self.assertIsNone(data['created_by_id'])
        self.assertIsNone(data['created_by_name'])

    def test_create_update_serializer_validation(self):
        """Test that create/update serializer validates text"""
        # Valid data
        serializer = ExtractionNoteCreateUpdateSerializer(data={'text': 'Valid note'})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['text'], 'Valid note')

        # Empty text
        serializer = ExtractionNoteCreateUpdateSerializer(data={'text': ''})
        self.assertFalse(serializer.is_valid())
        self.assertIn('text', serializer.errors)

        # Whitespace only
        serializer = ExtractionNoteCreateUpdateSerializer(data={'text': '   '})
        self.assertFalse(serializer.is_valid())
        self.assertIn('text', serializer.errors)

    def test_create_update_serializer_strips_whitespace(self):
        """Test that serializer strips leading/trailing whitespace"""
        serializer = ExtractionNoteCreateUpdateSerializer(data={'text': '  Note with spaces  '})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['text'], 'Note with spaces')


class TestExtractedDataWithNotes(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('test@example.com', first_name='Test', last_name='User')
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.project = Project.objects.create(name="Test Project", team=self.team, created_by=self.user)
        self.version = self.project.versions.first()
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

    def test_extracted_data_includes_notes(self):
        """Test that ExtractedData serializer includes notes"""
        from apps.deliverables.serializers.extracted_data import ExtractedDataSerializer

        # Create notes
        ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="First note",
            created_by=self.user
        )
        ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="Second note",
            created_by=self.user
        )

        serializer = ExtractedDataSerializer(self.extracted_data)
        data = serializer.data

        self.assertIn('notes', data)
        self.assertEqual(len(data['notes']), 2)
        self.assertEqual(data['notes'][0]['text'], 'First note')
        self.assertEqual(data['notes'][1]['text'], 'Second note')

    def test_extracted_data_with_no_notes(self):
        """Test ExtractedData with no notes returns empty array"""
        from apps.deliverables.serializers.extracted_data import ExtractedDataSerializer

        serializer = ExtractedDataSerializer(self.extracted_data)
        data = serializer.data

        self.assertIn('notes', data)
        self.assertEqual(len(data['notes']), 0)
        self.assertEqual(data['notes'], [])

    def test_extracted_data_list_serializer_includes_notes(self):
        """Test that list serializer also includes notes"""
        from apps.deliverables.serializers.extracted_data import ExtractedDataListSerializer

        ExtractionNote.objects.create(
            extracted_data=self.extracted_data,
            text="Note in list",
            created_by=self.user
        )

        serializer = ExtractedDataListSerializer(self.extracted_data)
        data = serializer.data

        self.assertIn('notes', data)
        self.assertEqual(len(data['notes']), 1)
        self.assertEqual(data['notes'][0]['text'], 'Note in list')
