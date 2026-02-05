from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from unittest.mock import patch

from apps.deliverables.models import (
    Project,
    ProjectMembership,
    SpecComparison,
    SpecComparisonStatus,
    SpecConflict,
    SkippedNote,
    SkipReason,
)
from apps.teams.models import Team

User = get_user_model()


class TestSpecConflictsEndpoint(APITestCase):
    """Test GET /projects/{id}/spec-conflicts/ endpoint"""

    def setUp(self):
        self.user = User.objects.create_user(
            'test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role='project_member'
        )

        # Create a successful comparison with conflicts
        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event-1',
            completed_at='2026-02-02T10:00:00Z',
        )
        self.conflict1 = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='1',
            note_text='Note 1',
            spec_text='Spec 1',
            spec_file_s3_key='specs/plumbing.pdf',
            spec_page_number=15,
            spec_masterformat_number='220500',
            confidence=0.85,
            reason='Conflict 1',
        )
        self.conflict2 = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='2',
            note_text='Note 2',
            spec_text='Spec 2',
            spec_file_s3_key='specs/mechanical.pdf',
            spec_page_number=20,
            spec_masterformat_number='230500',
            confidence=0.75,
            reason='Conflict 2',
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse(
            'deliverables:spec-conflicts',
            kwargs={'project_id': self.project.id}
        )

    def test_missing_project_version_id_returns_400(self):
        """Test 400 when project_version_id is not provided"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('project_version_id', response.data['error'])

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_returns_conflicts_from_latest_successful(self, mock_presigned):
        """Test returns conflicts from latest successful comparison"""
        mock_presigned.return_value = 'https://presigned-url.com/file.pdf'

        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['comparison']['id'], self.comparison.id)
        self.assertEqual(len(response.data['results']), 2)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_excludes_failed_comparisons_from_latest(self, mock_presigned):
        """Test 'latest' excludes FAILED comparisons"""
        mock_presigned.return_value = 'https://presigned-url.com/file.pdf'

        # Create a newer FAILED comparison
        SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.FAILED,
            event_id='test-event-2',
            completed_at='2026-02-02T11:00:00Z',  # Newer
        )

        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        # Should still return the successful comparison
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['comparison']['id'], self.comparison.id)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_by_comparison_id(self, mock_presigned):
        """Test filtering by comparison_id"""
        mock_presigned.return_value = 'https://presigned-url.com/file.pdf'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'comparison_id': self.comparison.id
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['comparison']['id'], self.comparison.id)

    def test_comparison_id_wrong_project_returns_404(self):
        """Test comparison_id from different project returns 404"""
        other_project = Project.objects.create(
            name='Other Project',
            project_number='P-OTHER',
            team=self.team,
            created_by=self.user
        )
        other_comparison = SpecComparison.objects.create(
            project=other_project,
            project_version=other_project.versions.first(),
            status=SpecComparisonStatus.SUCCESS,
            event_id='other-event',
        )

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'comparison_id': other_comparison.id
        })

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_returns_403(self):
        """Test 403 for unauthenticated requests"""
        self.client.force_authenticate(user=None)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_member_returns_403(self):
        """Test 403 for non-project members"""
        other_user = User.objects.create_user(
            'other@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=other_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_empty_results_when_no_comparisons(self):
        """Test empty results when no comparisons exist"""
        SpecComparison.objects.all().delete()

        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)
        self.assertIsNone(response.data['comparison'])

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_pagination(self, mock_presigned):
        """Test pagination works correctly"""
        mock_presigned.return_value = 'https://presigned-url.com/file.pdf'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'limit': 1
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertIsNotNone(response.data['next'])

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_deterministic_ordering(self, mock_presigned):
        """Test results are ordered by id for deterministic pagination"""
        mock_presigned.return_value = 'https://presigned-url.com/file.pdf'

        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        results = response.data['results']
        self.assertEqual(results[0]['id'], self.conflict1.id)
        self.assertEqual(results[1]['id'], self.conflict2.id)


class TestSkippedNotesEndpoint(APITestCase):
    """Test GET /projects/{id}/skipped-notes/ endpoint"""

    def setUp(self):
        self.user = User.objects.create_user(
            'test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role='project_member'
        )

        # Create a successful comparison with skipped notes
        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event-1',
            completed_at='2026-02-02T10:00:00Z',
        )
        self.skipped1 = SkippedNote.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='1',
            disciplines=['plumbing'],
            sheet_discipline='mechanical',
            reason=SkipReason.NO_MATCHING_SPECS,
            detail='Division 22 has no specs',
        )
        self.skipped2 = SkippedNote.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='2',
            reason=SkipReason.UNKNOWN_DISCIPLINE,
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse(
            'deliverables:skipped-notes',
            kwargs={'project_id': self.project.id}
        )

    def test_missing_project_version_id_returns_400(self):
        """Test 400 when project_version_id is not provided"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('project_version_id', response.data['error'])

    def test_returns_skipped_notes(self):
        """Test returns skipped notes from latest successful comparison"""
        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)

    def test_filter_by_reason(self):
        """Test filtering by reason"""
        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'reason': 'no_matching_specs'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['reason'], 'no_matching_specs')


class TestSpecComparisonsListEndpoint(APITestCase):
    """Test GET /projects/{id}/spec-comparisons/ endpoint"""

    def setUp(self):
        self.user = User.objects.create_user(
            'test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role='project_member'
        )

        self.comparison1 = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            triggered_by=self.user,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event-1',
            notes_processed=100,
        )
        self.comparison2 = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.FAILED,
            event_id='test-event-2',
            error_message='Lambda timeout',
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse(
            'deliverables:spec-comparisons-list',
            kwargs={'project_id': self.project.id}
        )

    def test_lists_all_comparisons(self):
        """Test lists all comparisons for project"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)

    def test_includes_triggered_by(self):
        """Test includes triggered_by info"""
        response = self.client.get(self.url)

        results = response.data['results']
        # Find the comparison with triggered_by
        comparison_with_user = next(
            (r for r in results if r['id'] == self.comparison1.id),
            None
        )
        self.assertIsNotNone(comparison_with_user)
        self.assertIsNotNone(comparison_with_user['triggered_by'])


class TestSpecConflictsSorting(APITestCase):
    """Test sorting on spec conflicts endpoint"""

    def setUp(self):
        self.user = User.objects.create_user(
            'test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role='project_member'
        )

        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event',
        )

        # Create conflicts with different values for sorting
        self.conflict_a = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='1',
            note_text='Alpha note',
            spec_text='Spec A',
            spec_file_s3_key='specs/a.pdf',
            spec_page_number=1,
            spec_masterformat_number='220500',
            confidence=0.9,
            reason='Reason A',
        )
        self.conflict_b = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='2',
            note_text='Beta note',
            spec_text='Spec B',
            spec_file_s3_key='specs/b.pdf',
            spec_page_number=2,
            spec_masterformat_number='230500',
            confidence=0.8,
            reason='Reason B',
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse('deliverables:spec-conflicts', kwargs={'project_id': self.project.id})

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_sort_by_note_text_asc(self, mock_presigned):
        """Test sorting by note_text ascending"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'sort_column': 'note_text',
            'sort_direction': 'asc'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(results[0]['note_text'], 'Alpha note')
        self.assertEqual(results[1]['note_text'], 'Beta note')

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_sort_by_note_text_desc(self, mock_presigned):
        """Test sorting by note_text descending"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'sort_column': 'note_text',
            'sort_direction': 'desc'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(results[0]['note_text'], 'Beta note')
        self.assertEqual(results[1]['note_text'], 'Alpha note')

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_sort_by_spec_masterformat_number(self, mock_presigned):
        """Test sorting by spec_masterformat_number"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'sort_column': 'spec_masterformat_number',
            'sort_direction': 'asc'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(results[0]['spec_masterformat_number'], '220500')
        self.assertEqual(results[1]['spec_masterformat_number'], '230500')

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_invalid_sort_column_ignored(self, mock_presigned):
        """Test invalid sort column is ignored (falls back to default)"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'sort_column': 'invalid_column',
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestSpecConflictsFiltering(APITestCase):
    """Test filtering on spec conflicts endpoint"""

    def setUp(self):
        from apps.deliverables.models import (
            DrawingFile,
            DrawingExtraction,
            DrawingExtractionStatus,
            DrawingPage,
            DrawingNoteSection,
            DrawingNote,
        )

        self.user = User.objects.create_user(
            'test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role='project_member'
        )

        # Create drawing structures for sheet_number filtering
        self.drawing_file = DrawingFile.objects.create(
            project=self.project,
            project_version=self.project_version,
            file_name='test.pdf',
            file_s3_key='drawings/test.pdf',
            md5='abc123',
        )
        self.extraction = DrawingExtraction.objects.create(
            drawing_file=self.drawing_file,
            status=DrawingExtractionStatus.SUCCESS,
        )
        self.page1 = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=1,
            page_type='drawing',
            extraction_status='success',
            sheet_number='P-201',
        )
        self.page2 = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=2,
            page_type='drawing',
            extraction_status='success',
            sheet_number='M-101',
        )
        self.section1 = DrawingNoteSection.objects.create(page=self.page1, header='NOTES')
        self.section2 = DrawingNoteSection.objects.create(page=self.page2, header='NOTES')
        self.note1 = DrawingNote.objects.create(
            section=self.section1, note_number=1, category='general', text='Valve note'
        )
        self.note2 = DrawingNote.objects.create(
            section=self.section2, note_number=1, category='general', text='Duct note'
        )

        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event',
        )

        self.conflict1 = SpecConflict.objects.create(
            comparison=self.comparison,
            note=self.note1,
            note_id_from_lambda='1',
            note_text='Ball valve required',
            spec_text='Gate valve specified',
            spec_file_s3_key='specs/plumbing.pdf',
            spec_page_number=1,
            spec_masterformat_number='220500',
            confidence=0.9,
            reason='Valve type mismatch',
        )
        self.conflict2 = SpecConflict.objects.create(
            comparison=self.comparison,
            note=self.note2,
            note_id_from_lambda='2',
            note_text='Duct size 12 inch',
            spec_text='Duct size 10 inch',
            spec_file_s3_key='specs/mechanical.pdf',
            spec_page_number=2,
            spec_masterformat_number='230500',
            confidence=0.8,
            reason='Dimension mismatch',
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse('deliverables:spec-conflicts', kwargs={'project_id': self.project.id})

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_by_search_in_note_text(self, mock_presigned):
        """Test search filter matches note_text"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'search': 'valve'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['note_text'], 'Ball valve required')

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_by_search_in_spec_text(self, mock_presigned):
        """Test search filter matches spec_text"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'search': 'Gate'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_by_search_in_reason(self, mock_presigned):
        """Test search filter matches reason"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'search': 'Dimension'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertIn('Dimension', response.data['results'][0]['reason'])

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_by_sheet_number(self, mock_presigned):
        """Test filtering by exact sheet_number"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'sheet_number': 'P-201'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['sheet_number'], 'P-201')

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_by_spec_masterformat_number(self, mock_presigned):
        """Test filtering by exact spec_masterformat_number"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'spec_masterformat_number': '220500'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_by_reason(self, mock_presigned):
        """Test filtering by exact reason"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'reason': 'Valve type mismatch'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_combined_filters(self, mock_presigned):
        """Test combining multiple filters"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {
            'project_version_id': self.project_version.id,
            'sheet_number': 'P-201',
            'search': 'valve'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)


class TestSpecConflictsFilterOptions(APITestCase):
    """Test filter_options in spec conflicts response"""

    def setUp(self):
        from apps.deliverables.models import (
            DrawingFile,
            DrawingExtraction,
            DrawingExtractionStatus,
            DrawingPage,
            DrawingNoteSection,
            DrawingNote,
        )

        self.user = User.objects.create_user('test@example.com', password='testpass123')
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role='project_member'
        )

        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event',
        )

        # Create drawing structures
        self.drawing_file = DrawingFile.objects.create(
            project=self.project,
            project_version=self.project_version,
            file_name='test.pdf',
            file_s3_key='drawings/test.pdf',
            md5='abc123',
        )
        self.extraction = DrawingExtraction.objects.create(
            drawing_file=self.drawing_file,
            status=DrawingExtractionStatus.SUCCESS,
        )
        page1 = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=1,
            page_type='drawing',
            extraction_status='success',
            sheet_number='P-201',
        )
        page2 = DrawingPage.objects.create(
            drawing_file=self.drawing_file,
            extraction=self.extraction,
            page_number=2,
            page_type='drawing',
            extraction_status='success',
            sheet_number='M-101',
        )
        section1 = DrawingNoteSection.objects.create(page=page1, header='NOTES')
        section2 = DrawingNoteSection.objects.create(page=page2, header='NOTES')
        note1 = DrawingNote.objects.create(section=section1, note_number=1, category='general', text='Note 1')
        note2 = DrawingNote.objects.create(section=section2, note_number=1, category='general', text='Note 2')

        SpecConflict.objects.create(
            comparison=self.comparison,
            note=note1,
            note_id_from_lambda='1',
            note_text='Note 1',
            spec_text='Spec 1',
            spec_file_s3_key='specs/a.pdf',
            spec_page_number=1,
            spec_masterformat_number='220500',
            confidence=0.9,
            reason='Reason A',
        )
        SpecConflict.objects.create(
            comparison=self.comparison,
            note=note2,
            note_id_from_lambda='2',
            note_text='Note 2',
            spec_text='Spec 2',
            spec_file_s3_key='specs/b.pdf',
            spec_page_number=2,
            spec_masterformat_number='230500',
            confidence=0.8,
            reason='Reason B',
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse('deliverables:spec-conflicts', kwargs={'project_id': self.project.id})

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_includes_filter_options(self, mock_presigned):
        """Test response includes filter_options"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('filter_options', response.data)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_options_contains_sheet_numbers(self, mock_presigned):
        """Test filter_options includes unique sheet numbers"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        sheet_numbers = response.data['filter_options']['sheet_numbers']
        self.assertIn('P-201', sheet_numbers)
        self.assertIn('M-101', sheet_numbers)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_options_contains_spec_masterformat_numbers(self, mock_presigned):
        """Test filter_options includes unique spec masterformat numbers"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        spec_numbers = response.data['filter_options']['spec_masterformat_numbers']
        self.assertIn('220500', spec_numbers)
        self.assertIn('230500', spec_numbers)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3.generate_presigned_url')
    def test_filter_options_contains_reasons(self, mock_presigned):
        """Test filter_options includes unique reasons"""
        mock_presigned.return_value = 'https://presigned-url.com'

        response = self.client.get(self.url, {'project_version_id': self.project_version.id})

        reasons = response.data['filter_options']['reasons']
        self.assertIn('Reason A', reasons)
        self.assertIn('Reason B', reasons)
