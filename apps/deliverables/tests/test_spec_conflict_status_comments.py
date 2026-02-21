from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from rest_framework.test import APITestCase
from rest_framework import status
from unittest.mock import patch, MagicMock
from apps.deliverables.models import (
    SpecComparison,
    SpecComparisonStatus,
    SpecConflict,
    SpecConflictStatus,
    SpecConflictComment,
    Project,
    DrawingNote,
    DrawingNoteSection,
    DrawingPage,
    DrawingFile,
    DrawingExtraction,
    DrawingExtractionStatus,
)
from apps.deliverables.serializers.spec_comparison_serializers import (
    SpecConflictReadSerializer,
    SpecConflictCommentSerializer,
)
from apps.teams.models import Team

User = get_user_model()


class TestSpecConflictStatusEnum(TestCase):
    """Test SpecConflictStatus enum values"""

    def test_all_status_values_exist(self):
        self.assertEqual(SpecConflictStatus.UNREVIEWED, "UNREVIEWED")
        self.assertEqual(SpecConflictStatus.RFI, "RFI")
        self.assertEqual(SpecConflictStatus.ACCEPT, "ACCEPT")
        self.assertEqual(SpecConflictStatus.NEEDS_REVIEW, "NEEDS_REVIEW")
        self.assertEqual(SpecConflictStatus.REVISION_INCOMING, "REVISION_INCOMING")

    def test_status_labels(self):
        self.assertEqual(SpecConflictStatus.UNREVIEWED.label, "Unreviewed")
        self.assertEqual(SpecConflictStatus.RFI.label, "RFI")
        self.assertEqual(SpecConflictStatus.ACCEPT.label, "Accept")
        self.assertEqual(SpecConflictStatus.NEEDS_REVIEW.label, "Needs Review")
        self.assertEqual(SpecConflictStatus.REVISION_INCOMING.label, "Revision Incoming")


class TestSpecConflictWithStatus(TestCase):
    """Test SpecConflict model with status field"""

    def setUp(self):
        self.user = User.objects.create_user('test@example.com', password='testpass123')
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event-status',
        )

    def test_default_status_is_unreviewed(self):
        conflict = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='123',
            note_text='Test note text',
            spec_text='Conflicting spec text',
            spec_file_s3_key='specs/test.pdf',
            spec_page_number=1,
            spec_masterformat_number='220500',
            confidence=0.85,
            reason='Test reason',
        )
        self.assertEqual(conflict.status, SpecConflictStatus.UNREVIEWED)

    def test_can_set_status_to_valid_choice(self):
        conflict = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='123',
            note_text='Test note text',
            spec_text='Conflicting spec text',
            spec_file_s3_key='specs/test.pdf',
            spec_page_number=1,
            spec_masterformat_number='220500',
            confidence=0.85,
            reason='Test reason',
            status=SpecConflictStatus.RFI,
        )
        self.assertEqual(conflict.status, SpecConflictStatus.RFI)

    def test_get_status_display(self):
        conflict = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='123',
            note_text='Test note text',
            spec_text='Conflicting spec text',
            spec_file_s3_key='specs/test.pdf',
            spec_page_number=1,
            spec_masterformat_number='220500',
            confidence=0.85,
            reason='Test reason',
            status=SpecConflictStatus.NEEDS_REVIEW,
        )
        self.assertEqual(conflict.get_status_display(), "Needs Review")


class TestSpecConflictCommentModel(TestCase):
    """Test SpecConflictComment model"""

    def setUp(self):
        self.user = User.objects.create_user('test@example.com', password='testpass123')
        self.user2 = User.objects.create_user('test2@example.com', password='testpass123')
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event-comments',
        )
        self.conflict = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='123',
            note_text='Test note text',
            spec_text='Conflicting spec text',
            spec_file_s3_key='specs/test.pdf',
            spec_page_number=1,
            spec_masterformat_number='220500',
            confidence=0.85,
            reason='Test reason',
        )

    def test_create_comment(self):
        comment = SpecConflictComment.objects.create(
            conflict=self.conflict,
            user=self.user,
            text='This is a test comment',
        )
        self.assertEqual(comment.text, 'This is a test comment')
        self.assertEqual(comment.user, self.user)
        self.assertEqual(comment.conflict, self.conflict)
        self.assertIsNotNone(comment.created_at)

    def test_comment_str_representation(self):
        comment = SpecConflictComment.objects.create(
            conflict=self.conflict,
            user=self.user,
            text='This is a long comment that should be truncated when displayed in string representation',
        )
        str_repr = str(comment)
        self.assertIn(self.user.email, str_repr)
        self.assertIn('This is a long comment that should be truncated', str_repr)
        self.assertIn('...', str_repr)

    def test_comment_ordering(self):
        """Test comments are ordered by created_at"""
        comment1 = SpecConflictComment.objects.create(
            conflict=self.conflict,
            user=self.user,
            text='First comment',
        )
        comment2 = SpecConflictComment.objects.create(
            conflict=self.conflict,
            user=self.user2,
            text='Second comment',
        )
        comments = list(self.conflict.comments.all())
        self.assertEqual(comments[0].id, comment1.id)
        self.assertEqual(comments[1].id, comment2.id)

    def test_user_set_null_on_delete(self):
        comment = SpecConflictComment.objects.create(
            conflict=self.conflict,
            user=self.user2,
            text='Test comment by user2',
        )
        self.user2.delete()
        comment.refresh_from_db()
        self.assertIsNone(comment.user)
        self.assertEqual(comment.text, 'Test comment by user2')

    def test_comment_cascade_delete_with_conflict(self):
        comment = SpecConflictComment.objects.create(
            conflict=self.conflict,
            user=self.user,
            text='Test comment',
        )
        comment_id = comment.id
        self.conflict.delete()
        with self.assertRaises(SpecConflictComment.DoesNotExist):
            SpecConflictComment.objects.get(id=comment_id)


class TestSpecConflictReadSerializerWithStatus(TestCase):
    """Test SpecConflictReadSerializer with status and comment_count fields"""

    def setUp(self):
        self.user = User.objects.create_user('test@example.com', password='testpass123')
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event-serializer',
        )
        self.conflict = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='123',
            note_text='Test note text',
            spec_text='Conflicting spec text',
            spec_file_s3_key='specs/test.pdf',
            spec_page_number=1,
            spec_masterformat_number='220500',
            confidence=0.85,
            reason='Test reason',
            status=SpecConflictStatus.RFI,
        )

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3')
    def test_serializer_includes_status_field(self, mock_s3):
        mock_s3.generate_presigned_url.return_value = 'https://test-url.com/test.pdf'

        serializer = SpecConflictReadSerializer(self.conflict, context={'request': MagicMock()})
        data = serializer.data

        self.assertIn('status', data)
        self.assertEqual(data['status'], SpecConflictStatus.RFI)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3')
    def test_serializer_includes_comment_count_field(self, mock_s3):
        mock_s3.generate_presigned_url.return_value = 'https://test-url.com/test.pdf'

        # Create some comments
        SpecConflictComment.objects.create(
            conflict=self.conflict,
            user=self.user,
            text='Comment 1',
        )
        SpecConflictComment.objects.create(
            conflict=self.conflict,
            user=self.user,
            text='Comment 2',
        )

        serializer = SpecConflictReadSerializer(self.conflict, context={'request': MagicMock()})
        data = serializer.data

        self.assertIn('comment_count', data)
        self.assertEqual(data['comment_count'], 2)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3')
    def test_serializer_uses_annotated_comment_count(self, mock_s3):
        mock_s3.generate_presigned_url.return_value = 'https://test-url.com/test.pdf'

        # Simulate annotated count
        self.conflict.comment_count_annotated = 5

        serializer = SpecConflictReadSerializer(self.conflict, context={'request': MagicMock()})
        data = serializer.data

        self.assertEqual(data['comment_count'], 5)


class TestSpecConflictCommentSerializer(TestCase):
    """Test SpecConflictCommentSerializer"""

    def setUp(self):
        self.user = User.objects.create_user('test@example.com', password='testpass123')
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        self.project_version = self.project.versions.first()
        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event-comment-serializer',
        )
        self.conflict = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='123',
            note_text='Test note text',
            spec_text='Conflicting spec text',
            spec_file_s3_key='specs/test.pdf',
            spec_page_number=1,
            spec_masterformat_number='220500',
            confidence=0.85,
            reason='Test reason',
        )

    def test_serializer_fields(self):
        comment = SpecConflictComment.objects.create(
            conflict=self.conflict,
            user=self.user,
            text='Test comment',
        )

        serializer = SpecConflictCommentSerializer(comment)
        data = serializer.data

        self.assertIn('id', data)
        self.assertIn('text', data)
        self.assertIn('user_id', data)
        self.assertIn('user_full_name', data)
        self.assertIn('created_at', data)
        self.assertIn('updated_at', data)

        self.assertEqual(data['text'], 'Test comment')
        self.assertEqual(data['user_id'], self.user.id)

    def test_serializer_user_full_name(self):
        # Set user's first and last name
        self.user.first_name = 'John'
        self.user.last_name = 'Doe'
        self.user.save()

        comment = SpecConflictComment.objects.create(
            conflict=self.conflict,
            user=self.user,
            text='Test comment',
        )

        serializer = SpecConflictCommentSerializer(comment)
        data = serializer.data

        self.assertEqual(data['user_full_name'], 'John Doe')

    def test_serializer_validation(self):
        data = {'text': 'Valid comment text'}
        serializer = SpecConflictCommentSerializer(data=data)

        self.assertTrue(serializer.is_valid())

    def test_serializer_empty_text_invalid(self):
        data = {'text': ''}
        serializer = SpecConflictCommentSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn('text', serializer.errors)


class TestSpecConflictStatusAndCommentsAPI(APITestCase):
    """Test API endpoints for status updates and comments"""

    def setUp(self):
        self.user = User.objects.create_user('test@example.com', password='testpass123')
        self.user2 = User.objects.create_user('test2@example.com', password='testpass123')
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        self.project = Project.objects.create(
            name='Test Project',
            project_number='P-001',
            team=self.team,
            created_by=self.user
        )
        # Add both users to project
        self.project.members.add(self.user, self.user2)

        self.project_version = self.project.versions.first()
        self.comparison = SpecComparison.objects.create(
            project=self.project,
            project_version=self.project_version,
            status=SpecComparisonStatus.SUCCESS,
            event_id='test-event-api',
        )
        self.conflict = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='123',
            note_text='Test note text',
            spec_text='Conflicting spec text',
            spec_file_s3_key='specs/test.pdf',
            spec_page_number=1,
            spec_masterformat_number='220500',
            confidence=0.85,
            reason='Test reason',
        )

        # Mock the project membership check
        patcher = patch('apps.users.models.CustomUser.is_member_of_project')
        self.mock_is_member = patcher.start()
        self.mock_is_member.return_value = True
        self.addCleanup(patcher.stop)

    @patch('apps.deliverables.serializers.spec_comparison_serializers.s3')
    def test_update_conflict_status(self, mock_s3):
        mock_s3.generate_presigned_url.return_value = 'https://test-url.com/test.pdf'

        self.client.force_authenticate(user=self.user)

        url = f'/api/deliverables/projects/{self.project.id}/spec-conflicts/{self.conflict.id}/status/'
        data = {'status': SpecConflictStatus.RFI}

        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.conflict.refresh_from_db()
        self.assertEqual(self.conflict.status, SpecConflictStatus.RFI)

    def test_update_conflict_status_invalid_status(self):
        self.client.force_authenticate(user=self.user)

        url = f'/api/deliverables/projects/{self.project.id}/spec-conflicts/{self.conflict.id}/status/'
        data = {'status': 'INVALID_STATUS'}

        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Invalid status', response.data['error'])

    def test_update_conflict_status_not_found(self):
        self.client.force_authenticate(user=self.user)

        url = f'/api/deliverables/projects/{self.project.id}/spec-conflicts/999999/status/'
        data = {'status': SpecConflictStatus.RFI}

        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_comments(self):
        # Create some comments
        comment1 = SpecConflictComment.objects.create(
            conflict=self.conflict,
            user=self.user,
            text='First comment',
        )
        comment2 = SpecConflictComment.objects.create(
            conflict=self.conflict,
            user=self.user2,
            text='Second comment',
        )

        self.client.force_authenticate(user=self.user)

        url = f'/api/deliverables/projects/{self.project.id}/spec-conflicts/{self.conflict.id}/comments/'

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]['text'], 'First comment')
        self.assertEqual(response.data[1]['text'], 'Second comment')

    def test_create_comment(self):
        self.client.force_authenticate(user=self.user)

        url = f'/api/deliverables/projects/{self.project.id}/spec-conflicts/{self.conflict.id}/comments/'
        data = {'text': 'New test comment'}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['text'], 'New test comment')
        self.assertEqual(response.data['user_id'], self.user.id)

        # Verify comment was created in database
        comment = SpecConflictComment.objects.get(id=response.data['id'])
        self.assertEqual(comment.text, 'New test comment')
        self.assertEqual(comment.user, self.user)
        self.assertEqual(comment.conflict, self.conflict)

    def test_delete_own_comment(self):
        comment = SpecConflictComment.objects.create(
            conflict=self.conflict,
            user=self.user,
            text='Comment to delete',
        )

        self.client.force_authenticate(user=self.user)

        url = f'/api/deliverables/projects/{self.project.id}/spec-conflicts/{self.conflict.id}/comments/{comment.id}/'

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify comment was deleted
        with self.assertRaises(SpecConflictComment.DoesNotExist):
            SpecConflictComment.objects.get(id=comment.id)

    def test_cannot_delete_other_users_comment(self):
        comment = SpecConflictComment.objects.create(
            conflict=self.conflict,
            user=self.user2,
            text='Other user comment',
        )

        self.client.force_authenticate(user=self.user)

        url = f'/api/deliverables/projects/{self.project.id}/spec-conflicts/{self.conflict.id}/comments/{comment.id}/'

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('You can only delete your own comments', response.data['error'])

        # Verify comment still exists
        self.assertTrue(SpecConflictComment.objects.filter(id=comment.id).exists())

    def test_comment_endpoints_require_authentication(self):
        # Test all comment endpoints without authentication
        comment = SpecConflictComment.objects.create(
            conflict=self.conflict,
            user=self.user,
            text='Test comment',
        )

        # List comments
        url = f'/api/deliverables/projects/{self.project.id}/spec-conflicts/{self.conflict.id}/comments/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Create comment
        response = self.client.post(url, {'text': 'New comment'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Delete comment
        url = f'/api/deliverables/projects/{self.project.id}/spec-conflicts/{self.conflict.id}/comments/{comment.id}/'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.deliverables.views.spec_comparison_views.s3')
    def test_get_spec_conflicts_with_status_filter(self, mock_s3):
        mock_s3.generate_presigned_url.return_value = 'https://test-url.com/test.pdf'

        # Create conflicts with different statuses
        conflict1 = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='456',
            note_text='Note 1',
            spec_text='Spec 1',
            spec_file_s3_key='specs/test1.pdf',
            spec_page_number=1,
            spec_masterformat_number='220500',
            confidence=0.9,
            reason='Reason 1',
            status=SpecConflictStatus.RFI,
        )
        conflict2 = SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='789',
            note_text='Note 2',
            spec_text='Spec 2',
            spec_file_s3_key='specs/test2.pdf',
            spec_page_number=2,
            spec_masterformat_number='220500',
            confidence=0.8,
            reason='Reason 2',
            status=SpecConflictStatus.ACCEPT,
        )

        self.client.force_authenticate(user=self.user)

        # Test filtering by status
        url = f'/api/deliverables/projects/{self.project.id}/spec-conflicts/?project_version_id={self.project_version.id}&status={SpecConflictStatus.RFI}'

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['status'], SpecConflictStatus.RFI)

    @patch('apps.deliverables.views.spec_comparison_views.s3')
    def test_get_spec_conflicts_includes_status_in_filter_options(self, mock_s3):
        mock_s3.generate_presigned_url.return_value = 'https://test-url.com/test.pdf'

        # Create conflicts with different statuses
        SpecConflict.objects.create(
            comparison=self.comparison,
            note_id_from_lambda='456',
            note_text='Note 1',
            spec_text='Spec 1',
            spec_file_s3_key='specs/test1.pdf',
            spec_page_number=1,
            spec_masterformat_number='220500',
            confidence=0.9,
            reason='Reason 1',
            status=SpecConflictStatus.RFI,
        )

        self.client.force_authenticate(user=self.user)

        url = f'/api/deliverables/projects/{self.project.id}/spec-conflicts/?project_version_id={self.project_version.id}'

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('filter_options', response.data)
        self.assertIn('statuses', response.data['filter_options'])
        self.assertIn(SpecConflictStatus.UNREVIEWED, response.data['filter_options']['statuses'])
        self.assertIn(SpecConflictStatus.RFI, response.data['filter_options']['statuses'])
