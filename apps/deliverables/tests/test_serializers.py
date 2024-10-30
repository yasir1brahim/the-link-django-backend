from django.test import TestCase

from django.utils import timezone
from ..models import Project, UploadedFile, DocProcessingStatus
from ..serializers import ProjectReadSerializer
from apps.users.models import CustomUser
from apps.teams.models import Team

class ProjectReadSerializerTest(TestCase):
    def setUp(self):
        team = Team.objects.create(
            name="Test Team"
        )
        owner = CustomUser.objects.create(
            email="test@test.com",
            first_name="Test",
            last_name="User"
        )
        self.project = Project.objects.create(
            name="Test Project",
            description="Test Description",
            owner=owner,
            team=team
        )

        # Create test documents with different statuses and timestamps
        self.doc1 = UploadedFile.objects.create(
            project=self.project,
            name="Doc 1",
            processing_status=DocProcessingStatus.PROCESSED,  # status_order = 6
            created_at=timezone.now(),
        )
        
        self.doc2 = UploadedFile.objects.create(
            project=self.project,
            name="Doc 2", 
            processing_status=DocProcessingStatus.PENDING_PROCESSING,  # status_order = 1
            created_at=timezone.now()
        )
        
        self.doc3 = UploadedFile.objects.create(
            project=self.project,
            name="Doc 3",
            processing_status=DocProcessingStatus.PROCESSING,  # status_order = 2
            created_at=timezone.now()
        )

    def test_document_ordering(self):
        serializer = ProjectReadSerializer(self.project)
        documents = serializer.data['document_details']
        
        # Check the order matches our status_order Case/When logic
        self.assertEqual(documents[0]['document_name'], "Doc 2")  # PENDING_PROCESSING (1)
        self.assertEqual(documents[1]['document_name'], "Doc 3")  # PROCESSING (2) 
        self.assertEqual(documents[2]['document_name'], "Doc 1")  # PROCESSED (6)


    def test_document_ordering_same_status(self):
        # Create two documents with same status but different timestamps
        older_time = timezone.now() - timezone.timedelta(hours=1)
        newer_time = timezone.now()
        
        doc4 = UploadedFile.objects.create(
            project=self.project,
            name="Doc 4",
            processing_status=DocProcessingStatus.PENDING_PROCESSING,
            created_at=older_time
        )
        
        doc5 = UploadedFile.objects.create(
            project=self.project,
            name="Doc 5",
            processing_status=DocProcessingStatus.PENDING_PROCESSING,
            created_at=newer_time
        )
        
        serializer = ProjectReadSerializer(self.project)
        documents = serializer.data['document_details']
        
        # Find documents with PENDING_PROCESSING status
        pending_docs = [doc for doc in documents 
                       if doc['document_status'] == DocProcessingStatus.PENDING_PROCESSING]
        
        # Verify that within same status, docs are ordered by -created_at
        self.assertEqual(pending_docs[0]['document_name'], "Doc 5")
        self.assertEqual(pending_docs[1]['document_name'], "Doc 4")
