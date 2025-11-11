# apps/deliverables/tests/test_ai_generated_log_serializer_extracted_data.py
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.db.models import Prefetch
from apps.deliverables.models import (
    Project,
    ProjectVersion,
    AiGeneratedLog,
    ExtractedData,
    ExtractionSource,
    MasterFormatSection,
    SpecSection,
    UploadedFile,
)
from apps.teams.models import Team
from rest_framework.test import APIRequestFactory, force_authenticate
from apps.deliverables.serializers.specgpt import AiGeneratedLogSerializer
from apps.deliverables.views.specgpt_views import AiGeneratedLogViewSet

User = get_user_model()


class TestAiGeneratedLogSerializerWithExtractedData(TestCase):
    """Test that AiGeneratedLogSerializer properly uses ExtractedData when available"""

    def setUp(self):
        self.user = User.objects.create_user('test@example.com')
        self.user.is_superuser = True
        self.user.save()
        self.team = Team.objects.create(name='Test Team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='TP-001',
            team=self.team
        )
        self.version = self.project.versions.first()
        self.request_factory = RequestFactory()

    def _get_log_with_prefetch(self, log: AiGeneratedLog):
        return AiGeneratedLog.objects.prefetch_related(
            Prefetch(
                'extracted_items',
                queryset=ExtractedData.objects.select_related(
                    'spec_section__masterformat_section',
                    'created_by'
                )
            )
        ).get(id=log.id)

    def _create_spec_section(self, number='05 1000', description='Metals', title='Division 05 - Metals'):
        masterformat_section = MasterFormatSection.objects.create(
            masterformat_number=number,
            masterformat_description=description
        )
        uploaded_file = UploadedFile.objects.create(
            project=self.project,
            project_version=self.version,
            document_path=f'{number.replace(" ", "_")}.pdf',
            name=f'{number} Spec',
            md5=f'{number.replace(" ", "")}-md5',
            processing_status='PROCESSED'
        )
        spec_section = SpecSection.objects.create(
            masterformat_section=masterformat_section,
            custom_section_title=title,
            document=uploaded_file
        )
        return spec_section, masterformat_section

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
        ai_log_with_prefetch = self._get_log_with_prefetch(ai_log)

        request = self.request_factory.get('/')
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
        self.assertEqual(row['Spec Section Name'], 'General')

    def test_spec_section_relationship_overrides_legacy_fields(self):
        """SpecSection masterformat data should override legacy fields"""
        spec_section, masterformat = self._create_spec_section(
            number='05 1000',
            description='Metals',
            title='Division 05 – Metals'
        )

        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='inspection_log',
            log_status='SUCCESS',
            created_by=self.user
        )

        ExtractedData.objects.create(
            ai_generated_log=ai_log,
            project=self.project,
            project_version=self.version,
            spec_section=spec_section,
            spec_section_number='Legacy Number',
            spec_section_name='Legacy Name',
            extraction_type='inspection_log',
            requirement_text='Inspect welds',
            responsible_party='Inspector',
            source=ExtractionSource.AI,
            created_by=self.user,
            metadata={
                'raw_item': {
                    'Spec Section #': 'Legacy Number',
                    'Spec Section Name': 'Legacy Name'
                }
            }
        )

        ai_log_with_prefetch = self._get_log_with_prefetch(ai_log)

        request = self.request_factory.get('/')
        request.user = self.user
        request.team = self.team

        serializer = AiGeneratedLogSerializer(
            ai_log_with_prefetch,
            context={'request': request}
        )
        data = serializer.data

        row = data['log_data'][0]
        self.assertEqual(row['Spec Section #'], masterformat.masterformat_number)
        self.assertEqual(row['Spec Section Name'], 'Division 05 – Metals')

    def test_spec_section_description_used_when_no_custom_title(self):
        """Fallback to masterformat description when custom title missing"""
        spec_section, masterformat = self._create_spec_section(
            number='03 3000',
            description='Cast-in-Place Concrete',
            title=None
        )

        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='inspection_log',
            log_status='SUCCESS',
            created_by=self.user
        )

        ExtractedData.objects.create(
            ai_generated_log=ai_log,
            project=self.project,
            project_version=self.version,
            spec_section=spec_section,
            spec_section_number='Legacy Number',
            spec_section_name='Legacy Name',
            extraction_type='inspection_log',
            requirement_text='Verify concrete mix design',
            responsible_party='Engineer',
            source=ExtractionSource.AI,
            created_by=self.user,
            metadata={
                'raw_item': {
                    'Spec Section #': 'Legacy Number',
                    'Spec Section Name': 'Legacy Name'
                }
            }
        )

        ai_log_with_prefetch = self._get_log_with_prefetch(ai_log)

        request = self.request_factory.get('/')
        request.user = self.user
        request.team = self.team

        serializer = AiGeneratedLogSerializer(
            ai_log_with_prefetch,
            context={'request': request}
        )
        data = serializer.data

        row = data['log_data'][0]
        self.assertEqual(row['Spec Section #'], masterformat.masterformat_number)
        self.assertEqual(row['Spec Section Name'], masterformat.masterformat_description)

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

        request = self.request_factory.get('/')
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
        ai_log_with_prefetch = self._get_log_with_prefetch(ai_log)

        request = self.request_factory.get('/')
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

        ai_log_with_prefetch = self._get_log_with_prefetch(ai_log)

        request = self.request_factory.get('/')
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

        ai_log_with_prefetch = self._get_log_with_prefetch(ai_log)

        request = self.request_factory.get('/')
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

    def test_serializer_includes_human_created_highlights(self):
        """Human-created highlights should appear alongside AI extracted rows"""
        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='inspection_log',
            log_status='SUCCESS',
            created_by=self.user
        )

        # Baseline AI-generated item
        ExtractedData.objects.create(
            ai_generated_log=ai_log,
            project=self.project,
            project_version=self.version,
            spec_section_number='01 3000',
            spec_section_name='Concrete Forms',
            extraction_type='inspection_log',
            requirement_text='Verify formwork alignment',
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

        # Human-created highlight with no ai_generated_log reference
        ExtractedData.objects.create(
            ai_generated_log=None,
            project=self.project,
            project_version=self.version,
            spec_section_number='02 4000',
            spec_section_name='Existing Conditions',
            extraction_type='inspection_log',
            requirement_text='Document existing site utilities before demolition',
            responsible_party='Owner',
            source=ExtractionSource.HUMAN,
            created_by=self.user,
            metadata={
                'raw_item': {
                    'Inspection Type And Requirements': 'Document existing site utilities before demolition',
                    'Responsible Party': 'Owner'
                }
            }
        )

        ai_log_with_prefetch = self._get_log_with_prefetch(ai_log)

        request = self.request_factory.get('/')
        request.user = self.user
        request.team = self.team

        serializer = AiGeneratedLogSerializer(
            ai_log_with_prefetch,
            context={'request': request}
        )
        data = serializer.data

        self.assertEqual(len(data['log_data']), 2)

        human_rows = [
            row for row in data['log_data']
            if row.get('Spec Section #') == '02 4000'
        ]
        self.assertEqual(len(human_rows), 1)
        self.assertEqual(
            human_rows[0]['Inspection Type And Requirements'],
            'Document existing site utilities before demolition'
        )

    def test_filter_values_includes_human_created_highlights(self):
        """Filter values endpoint should surface human-created metadata"""
        ai_log = AiGeneratedLog.objects.create(
            project=self.project,
            project_version=self.version,
            log_type='inspection_log',
            log_status='SUCCESS',
            created_by=self.user
        )

        ExtractedData.objects.create(
            ai_generated_log=ai_log,
            project=self.project,
            project_version=self.version,
            spec_section_number='03 3000',
            spec_section_name='Concrete',
            extraction_type='inspection_log',
            requirement_text='Verify reinforcement placement',
            responsible_party='Contractor',
            source=ExtractionSource.AI,
            created_by=self.user,
            metadata={'raw_item': {}}
        )

        ExtractedData.objects.create(
            project=self.project,
            project_version=self.version,
            spec_section_number='04 4000',
            spec_section_name='Masonry',
            extraction_type='inspection_log',
            requirement_text='Document masonry control samples',
            responsible_party='Owner',
            source=ExtractionSource.HUMAN,
            created_by=self.user,
            metadata={'raw_item': {}}
        )

        factory = APIRequestFactory()
        request = factory.get(f'/api/deliverables/{self.project.id}/ai-generated-logs/{ai_log.id}/filter_values/')
        force_authenticate(request, user=self.user)

        view = AiGeneratedLogViewSet.as_view({'get': 'filter_values'})
        response = view(request, project_id=self.project.id, pk=ai_log.id)

        self.assertEqual(response.status_code, 200)
        responsible_parties = response.data['filter_values']['Responsible Party']
        self.assertIn('Owner', responsible_parties)
