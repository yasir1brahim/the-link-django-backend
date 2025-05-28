import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from apps.teams.models import Team, Membership as TeamMembership
from apps.deliverables.models import (
    Project, ProjectMembership, Chat, ChatMessage, ProjectVersion,
    ROLE_PROJECT_ADMIN, ROLE_PROJECT_MEMBER
)
from langchain_core.documents import Document

class SpecGptViewSetTests(APITestCase):
    def setUp(self):
        self.User = get_user_model()
        
        # Create test user
        self.user = self.User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        
        # Create team
        self.team = Team.objects.create(name='Test Team', slug='test-team')
        
        # Add user to team
        TeamMembership.objects.create(
            user=self.user,
            team=self.team,
            role='member'
        )
        
        # Create project
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team
        )
        self.project_version = ProjectVersion.objects.get(project=self.project)
        
        # Add user to project
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ROLE_PROJECT_MEMBER
        )
        
        # Create chat
        self.chat = Chat.objects.create(
            project=self.project,
            project_version=self.project_version,
            user=self.user
        )
        
        # URL for generate-response endpoint
        self.url = reverse(
            'specgpt-chat-generate-response', 
            kwargs={'project_id': self.project.id, 'pk': self.chat.id}
        )

        # Mock PromptLayer template
        self.mock_promptlayer_template = {
            'prompt_name': 'test-prompt',
            'commit_message': 'test-commit',
            'prompt_template': {
                'messages': [{
                    'content': [{
                        'text': 'You are a helpful assistant.'
                    }]
                }]
            },
            'metadata': {
                'model': {
                    'name': 'gpt-4',
                    'parameters': {
                        'temperature': 0.7
                    }
                }
            }
        }

    def test_unauthenticated_user_cannot_generate_response(self):
        """Test that unauthenticated users cannot generate responses"""
        response = self.client.post(self.url, {'user_input': 'test question'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.deliverables.views.specgpt_views.PineconeVectorStore')
    @patch('apps.deliverables.views.specgpt_views.ChatOpenAI')
    @patch('apps.deliverables.views.specgpt_views.ConversationalRetrievalChain')
    @patch('apps.deliverables.views.specgpt_views.TemplateManager')
    def test_authenticated_user_can_generate_response(self, mock_template_manager, mock_chain, mock_chat_openai, mock_pinecone):
        """Test that authenticated users can generate responses"""
        # Mock PromptLayer template manager
        mock_template_manager_instance = MagicMock()
        mock_template_manager.return_value = mock_template_manager_instance
        mock_template_manager_instance.get.return_value = self.mock_promptlayer_template
        
        # Mock the vector store and its retriever
        mock_vectorstore = MagicMock()
        mock_retriever = MagicMock()
        mock_vectorstore.as_retriever.return_value = mock_retriever
        mock_pinecone.return_value = mock_vectorstore
        
        # Mock the LLM
        mock_llm = MagicMock()
        mock_chat_openai.return_value = mock_llm
        
        # Mock the chain
        mock_chain.from_llm.return_value = MagicMock()
        mock_chain.from_llm.return_value.return_value = {
            'answer': 'Test answer',
            'source_documents': [
                Document(
                    page_content='Test content',
                    metadata={
                        'userid': str(self.user.id),
                        'master_format_section_number': '01 00 00',
                        's3_bucket': 'test-bucket',
                        's3_key': 'test-key',
                        'source': 'test.pdf'
                    }
                )
            ]
        }
        
        # Authenticate user
        self.client.force_authenticate(user=self.user)
        
        # Make request
        response = self.client.post(self.url, {
            'user_input': 'test question',
            'k': 5
        })
        
        # Assert response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['answer'], 'Test answer')
        self.assertEqual(response.data['question'], 'test question')
        self.assertEqual(len(response.data['sources']), 1)
        self.assertEqual(response.data['sources'][0]['text'], 'Test content')
        self.assertEqual(response.data['sources'][0]['master_format_section_number'], '01 00 00')

        # Verify PromptLayer template was retrieved
        mock_template_manager_instance.get.assert_called_once()

    @patch('apps.deliverables.views.specgpt_views.PineconeVectorStore')
    @patch('apps.deliverables.views.specgpt_views.ChatOpenAI')
    @patch('apps.deliverables.views.specgpt_views.ConversationalRetrievalChain')
    @patch('apps.deliverables.views.specgpt_views.TemplateManager')
    def test_generate_response_with_default_k(self, mock_template_manager, mock_chain, mock_chat_openai, mock_pinecone):
        """Test that generate response uses default k value when not provided"""
        # Mock PromptLayer template manager
        mock_template_manager_instance = MagicMock()
        mock_template_manager.return_value = mock_template_manager_instance
        mock_template_manager_instance.get.return_value = self.mock_promptlayer_template
        
        # Mock the vector store and its retriever
        mock_vectorstore = MagicMock()
        mock_retriever = MagicMock()
        mock_vectorstore.as_retriever.return_value = mock_retriever
        mock_pinecone.return_value = mock_vectorstore
        
        # Mock the LLM
        mock_llm = MagicMock()
        mock_chat_openai.return_value = mock_llm
        
        # Mock the chain
        mock_chain.from_llm.return_value = MagicMock()
        mock_chain.from_llm.return_value.return_value = {
            'answer': 'Test answer',
            'source_documents': []
        }
        
        # Authenticate user
        self.client.force_authenticate(user=self.user)
        
        # Make request without k parameter
        response = self.client.post(self.url, {
            'user_input': 'test question'
        })
        
        # Assert response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_vectorstore.as_retriever.assert_called_once()
        search_kwargs = mock_vectorstore.as_retriever.call_args[1]['search_kwargs']
        self.assertEqual(search_kwargs['k'], 10)  # Default value

        # Verify PromptLayer template was retrieved
        mock_template_manager_instance.get.assert_called_once()

    def test_non_member_cannot_generate_response(self):
        """Test that non-project members cannot generate responses"""
        # Create another user who is a project member but not part of this chat
        other_user = self.User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='password123'
        )
        other_user_project_membership = ProjectMembership.objects.create(
            project=self.project,
            user=other_user,
            role=ROLE_PROJECT_MEMBER
        )
        # Authenticate other user
        self.client.force_authenticate(user=other_user)
        
        # Make request
        response = self.client.post(self.url, {'user_input': 'test question'})
        
        # Assert response
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_project_member_but_not_chat_member_cannot_generate_response(self):
        """Test that project members but not chat members cannot generate responses"""
        # Create another user who is a project member but not part of this chat
        other_user = self.User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='password123'
        )
        other_user_project_membership = ProjectMembership.objects.create(
            project=self.project,
            user=other_user,
            role=ROLE_PROJECT_MEMBER
        )
        # Authenticate other user
        self.client.force_authenticate(user=other_user)
        
        # Make request
        response = self.client.post(self.url, {'user_input': 'test question'})

        # Assert response
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    

    @patch('apps.deliverables.views.specgpt_views.PineconeVectorStore')
    @patch('apps.deliverables.views.specgpt_views.ChatOpenAI')
    @patch('apps.deliverables.views.specgpt_views.ConversationalRetrievalChain')
    @patch('apps.deliverables.views.specgpt_views.TemplateManager')
    def test_generate_response_with_invalid_k(self, mock_template_manager, mock_chain, mock_chat_openai, mock_pinecone):
        """Test that generate response handles invalid k values"""
        # Mock PromptLayer template manager
        mock_template_manager_instance = MagicMock()
        mock_template_manager.return_value = mock_template_manager_instance
        mock_template_manager_instance.get.return_value = self.mock_promptlayer_template
        
        # Authenticate user
        self.client.force_authenticate(user=self.user)
        
        # Make request with invalid k value
        response = self.client.post(self.url, {
            'user_input': 'test question',
            'k': 'invalid'
        })
        
        # Assert response
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('apps.deliverables.views.specgpt_views.PineconeVectorStore')
    @patch('apps.deliverables.views.specgpt_views.ChatOpenAI')
    @patch('apps.deliverables.views.specgpt_views.ConversationalRetrievalChain')
    @patch('apps.deliverables.views.specgpt_views.TemplateManager')
    def test_promptlayer_template_error_handling(self, mock_template_manager, mock_chain, mock_chat_openai, mock_pinecone):
        """Test handling of PromptLayer template retrieval errors"""
        # Mock PromptLayer template manager to raise an exception
        mock_template_manager_instance = MagicMock()
        mock_template_manager.return_value = mock_template_manager_instance
        mock_template_manager_instance.get.side_effect = Exception("Template not found")
        
        # Authenticate user
        self.client.force_authenticate(user=self.user)
        
        # Make request
        response = self.client.post(self.url, {
            'user_input': 'test question'
        })
        
        # Assert response
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn('error', response.data)
        self.assertIn('Failed to retrieve PromptLayer template', response.data['error'])
        self.assertIn('Template not found', response.data['error']) 