# apps/deliverables/tests/test_ai_generated_log_serializer_extracted_data.py
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from apps.deliverables.models import (
    Project, ProjectVersion, AiGeneratedLog, ExtractedData,
    ExtractionSource
)
from apps.teams.models import Team
from apps.deliverables.serializers.specgpt import AiGeneratedLogSerializer

User = get_user_model()


class TestAiGeneratedLogSerializerWithExtractedData(TestCase):
    """Test that AiGeneratedLogSerializer properly uses ExtractedData when available"""

    def setUp(self):
        self.user = User.objects.create_user('test@example.com')
        self.team = Team.objects.create(name='Test Team')
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team
        )
        self.version = ProjectVersion.objects.create(
            project=self.project,
            version_number='1.0'
        )

    def test_serializer_uses_extracted_data_when_available(self):
        """Test that serializer uses ExtractedData instead of log_data when available"""
        # Create AI log with log_data
        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='inspection_log',
            log_status='SUCCESS',
            created_by=self.user,
            log_data=[
                {
                    'Spec Section #': '01 1000',
                    'Spec Section Name': 'General',
                    'Inspection Type And Requirements': 'Old data from JSON',
                    'Inspection Frequency': 'Daily',
                    'Responsible Party': 'Contractor',
                }
            ]
        )

        # Create ExtractedData that should override log_data
        ExtractedData.objects.create(
            ai_generated_log=ai_log,
            project=self.project,
            project_version=self.version,
            spec_section_number='01 1000',
            spec_section_name='General',
            extraction_type='inspection_log',
            requirement_text='New data from ExtractedData model',
            responsible_party='Contractor',
            source=ExtractionSource.AI,
            created_by=self.user,
            metadata={
                'inspection_frequency': 'Daily',
                'raw_item': {
                    'Inspection Frequency': 'Daily',
                }
            }
        )

        # Serialize with ExtractedData prefetched
        ai_log_with_prefetch = AiGeneratedLog.objects.prefetch_related(
            'extracted_items'
        ).get(id=ai_log.id)

        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user
        request.team = self.team

        serializer = AiGeneratedLogSerializer(
            ai_log_with_prefetch,
            context={'request': request}
        )
        data = serializer.data

        # Verify that data comes from ExtractedData, not log_data
        self.assertEqual(len(data['log_data']), 1)
        row = data['log_data'][0]
        self.assertEqual(
            row['Inspection Type And Requirements'],
            'New data from ExtractedData model'
        )
        self.assertEqual(row['Spec Section #'], '01 1000')
        self.assertEqual(row['Inspection Frequency'], 'Daily')

    def test_serializer_falls_back_to_log_data_when_no_extracted_data(self):
        """Test that serializer falls back to log_data when ExtractedData is not available"""
        # Create AI log with only log_data (no ExtractedData)
        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='inspection_log',
            log_status='SUCCESS',
            created_by=self.user,
            log_data=[
                {
                    'Spec Section #': '01 1000',
                    'Spec Section Name': 'General',
                    'Inspection Type And Requirements': 'From JSON fallback',
                    'Inspection Frequency': 'Weekly',
                }
            ]
        )

        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user
        request.team = self.team

        serializer = AiGeneratedLogSerializer(
            ai_log,
            context={'request': request}
        )
        data = serializer.data

        # Verify data comes from log_data JSON field
        self.assertEqual(len(data['log_data']), 1)
        row = data['log_data'][0]
        self.assertEqual(
            row['Inspection Type And Requirements'],
            'From JSON fallback'
        )

    def test_extracted_data_format_matches_legacy_format(self):
        """Test that ExtractedData is formatted exactly like legacy log_data"""
        legacy_row = {
            'Spec Section #': '01 1000',
            'Spec Section Name': 'General Requirements',
            'Inspection Type And Requirements': 'Verify installation',
            'Inspection Frequency': 'Daily',
            'Responsible Party': 'Contractor',
            'pdf_locations': [{'page': 5, 'bbox': [100, 200, 300, 250]}]
        }

        # Create AI log with legacy format
        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='inspection_log',
            log_status='SUCCESS',
            created_by=self.user,
            log_data=[legacy_row]
        )

        # Create matching ExtractedData
        ExtractedData.objects.create(
            ai_generated_log=ai_log,
            project=self.project,
            project_version=self.version,
            spec_section_number='01 1000',
            spec_section_name='General Requirements',
            extraction_type='inspection_log',
            requirement_text='Verify installation',
            responsible_party='Contractor',
            pdf_locations=[{'page': 5, 'bbox': [100, 200, 300, 250]}],
            source=ExtractionSource.AI,
            created_by=self.user,
            metadata={
                'inspection_frequency': 'Daily',
                'raw_item': legacy_row
            }
        )

        # Get with prefetch
        ai_log_with_prefetch = AiGeneratedLog.objects.prefetch_related(
            'extracted_items'
        ).get(id=ai_log.id)

        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user
        request.team = self.team

        serializer = AiGeneratedLogSerializer(
            ai_log_with_prefetch,
            context={'request': request}
        )
        data = serializer.data

        # Verify format matches exactly
        row = data['log_data'][0]
        self.assertEqual(row['Spec Section #'], legacy_row['Spec Section #'])
        self.assertEqual(row['Spec Section Name'], legacy_row['Spec Section Name'])
        self.assertEqual(
            row['Inspection Type And Requirements'],
            legacy_row['Inspection Type And Requirements']
        )
        self.assertEqual(row['Inspection Frequency'], legacy_row['Inspection Frequency'])
        self.assertEqual(row['Responsible Party'], legacy_row['Responsible Party'])
        self.assertEqual(row['pdf_locations'], legacy_row['pdf_locations'])

    def test_qa_planner_extracted_data_format(self):
        """Test QA Planner extraction type formatting"""
        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='qa_planner',
            log_status='SUCCESS',
            created_by=self.user
        )

        ExtractedData.objects.create(
            ai_generated_log=ai_log,
            project=self.project,
            project_version=self.version,
            spec_section_number='03 3000',
            spec_section_name='Concrete',
            extraction_type='qa_planner',
            item_type='product',
            paragraph_number='3.1.A',
            requirement_text='Use Type II cement',
            responsible_party='Contractor',
            source=ExtractionSource.AI,
            created_by=self.user,
            metadata={
                'when_due': 'Prior to placement',
                'raw_item': {
                    'Paragraph Number': '3.1.A',
                    'item_type': 'product',
                    'When Due': 'Prior to placement'
                }
            }
        )

        ai_log_with_prefetch = AiGeneratedLog.objects.prefetch_related(
            'extracted_items'
        ).get(id=ai_log.id)

        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user
        request.team = self.team

        serializer = AiGeneratedLogSerializer(
            ai_log_with_prefetch,
            context={'request': request}
        )
        data = serializer.data

        row = data['log_data'][0]
        self.assertEqual(row['Requirement Text'], 'Use Type II cement')
        self.assertEqual(row['item_type'], 'product')
        self.assertEqual(row['Paragraph Number'], '3.1.A')
        self.assertEqual(row['When Due'], 'Prior to placement')

    def test_owner_deliverables_extracted_data_format(self):
        """Test Owner Deliverables extraction type formatting"""
        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='owner_deliverables_log',
            log_status='SUCCESS',
            created_by=self.user
        )

        ExtractedData.objects.create(
            ai_generated_log=ai_log,
            project=self.project,
            project_version=self.version,
            spec_section_number='01 7800',
            spec_section_name='Closeout Submittals',
            extraction_type='owner_deliverables_log',
            requirement_text='Provide as-built drawings',
            responsible_party='Contractor',
            source=ExtractionSource.AI,
            created_by=self.user,
            metadata={
                'deliverable_type': 'Drawing',
                'when_due': 'Prior to final payment',
                'raw_item': {
                    'Deliverable Type': 'Drawing',
                    'When Due': 'Prior to final payment'
                }
            }
        )

        ai_log_with_prefetch = AiGeneratedLog.objects.prefetch_related(
            'extracted_items'
        ).get(id=ai_log.id)

        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user
        request.team = self.team

        serializer = AiGeneratedLogSerializer(
            ai_log_with_prefetch,
            context={'request': request}
        )
        data = serializer.data

        row = data['log_data'][0]
        self.assertEqual(row['Exact Requirement Text'], 'Provide as-built drawings')
        self.assertEqual(row['Deliverable Type'], 'Drawing')
        self.assertEqual(row['When Due'], 'Prior to final payment')
