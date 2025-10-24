"""Tests for adaptive RAG implementation using LangGraph agents."""

from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.teams.models import Team, TeamMember, Flag
from apps.deliverables.models import Project, ProjectVersion, Chat, ChatMessage
from apps.deliverables.views.specgpt_views import ChatViewSet
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.documents import Document

User = get_user_model()


class AdaptiveRAGFeatureFlagTests(TestCase):
    """Test feature flag routing for adaptive RAG."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team')
        TeamMember.objects.create(team=self.team, user=self.user, role='owner')
        
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team
        )
        self.project_version = ProjectVersion.objects.create(
            project=self.project,
            version_number=1
        )
        
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
    
    def test_feature_flag_off_uses_standard_method(self):
        """Test that with flag OFF, standard RAG is used."""
        # Ensure flag is not active
        Flag.objects.filter(name='langchain_update').delete()
        
        with patch.object(ChatViewSet, 'generate_standard_chat_response') as mock_standard:
            with patch.object(ChatViewSet, 'generate_adaptive_chat_response') as mock_adaptive:
                mock_standard.return_value = ("Standard response", [])
                
                response = self.client.post(
                    f'/api/projects/{self.project.id}/chats/generate-response',
                    {
                        'user_input': 'Hello',
                        'project_version_id': str(self.project_version.id),
                        'k': 10
                    },
                    format='json'
                )
                
                # Standard method should be called
                mock_standard.assert_called_once()
                # Adaptive method should NOT be called
                mock_adaptive.assert_not_called()
    
    def test_feature_flag_on_uses_adaptive_method(self):
        """Test that with flag ON, adaptive RAG is used."""
        # Enable the flag for this project
        flag = Flag.objects.create(name='langchain_update')
        flag.projects.add(self.project)
        
        with patch.object(ChatViewSet, 'generate_standard_chat_response') as mock_standard:
            with patch.object(ChatViewSet, 'generate_adaptive_chat_response') as mock_adaptive:
                mock_adaptive.return_value = ("Adaptive response", [])
                
                response = self.client.post(
                    f'/api/projects/{self.project.id}/chats/generate-response',
                    {
                        'user_input': 'Hello',
                        'project_version_id': str(self.project_version.id),
                        'k': 10
                    },
                    format='json'
                )
                
                # Adaptive method should be called
                mock_adaptive.assert_called_once()
                # Standard method should NOT be called
                mock_standard.assert_not_called()


class AdaptiveRAGSimpleQueriesTests(TestCase):
    """Test adaptive RAG with simple queries that shouldn't retrieve documents."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team')
        TeamMember.objects.create(team=self.team, user=self.user, role='owner')
        
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team
        )
        self.project_version = ProjectVersion.objects.create(
            project=self.project,
            version_number=1
        )
        
        self.chat = Chat.objects.create(
            user=self.user,
            project=self.project,
            project_version=self.project_version
        )
        
        self.viewset = ChatViewSet()
    
    @patch('apps.deliverables.views.specgpt_views.create_react_agent')
    @patch('apps.deliverables.views.specgpt_views.PineconeVectorStore')
    @patch('apps.deliverables.views.specgpt_views.ChatViewSet.get_promptlayer_template')
    def test_simple_greeting_no_retrieval(self, mock_template, mock_vectorstore, mock_agent):
        """Test that simple greetings don't trigger retrieval."""
        # Mock PromptLayer template
        mock_template.return_value = {
            'prompt_name': 'test_prompt',
            'commit_message': 'test',
            'metadata': {
                'model': {
                    'name': 'gpt-4o',
                    'parameters': {'temperature': 0.1}
                }
            },
            'prompt_template': {
                'messages': [
                    {'role': 'system', 'content': [{'text': 'You are a helpful assistant.'}]}
                ]
            }
        }
        
        # Mock agent executor that returns without using tools
        mock_executor = MagicMock()
        mock_agent.return_value = mock_executor
        
        # Simulate agent response without tool calls
        mock_executor.invoke.return_value = {
            'messages': [
                HumanMessage(content="Hello"),
                AIMessage(content="Hi! How can I help you today?")
            ]
        }
        
        # Call the adaptive method
        answer, sources = self.viewset.generate_adaptive_chat_response(
            chat=self.chat,
            project_id=str(self.project.id),
            project_version_id=str(self.project_version.id),
            user_email=self.user.email,
            user_input="Hello",
            num_documents_to_return=10
        )
        
        # Verify response
        self.assertIn("Hi", answer)
        # No sources should be returned for simple greeting
        self.assertEqual(len(sources), 0)
    
    @patch('apps.deliverables.views.specgpt_views.create_react_agent')
    @patch('apps.deliverables.views.specgpt_views.PineconeVectorStore')
    @patch('apps.deliverables.views.specgpt_views.ChatViewSet.get_promptlayer_template')
    def test_capability_question_no_retrieval(self, mock_template, mock_vectorstore, mock_agent):
        """Test that questions about capabilities don't trigger retrieval."""
        # Mock PromptLayer template
        mock_template.return_value = {
            'prompt_name': 'test_prompt',
            'commit_message': 'test',
            'metadata': {
                'model': {
                    'name': 'gpt-4o',
                    'parameters': {'temperature': 0.1}
                }
            },
            'prompt_template': {
                'messages': [
                    {'role': 'system', 'content': [{'text': 'You are a helpful assistant.'}]}
                ]
            }
        }
        
        # Mock agent executor
        mock_executor = MagicMock()
        mock_agent.return_value = mock_executor
        
        # Simulate agent response without tool calls
        mock_executor.invoke.return_value = {
            'messages': [
                HumanMessage(content="What can you do?"),
                AIMessage(content="I can help you with project specifications and requirements.")
            ]
        }
        
        # Call the adaptive method
        answer, sources = self.viewset.generate_adaptive_chat_response(
            chat=self.chat,
            project_id=str(self.project.id),
            project_version_id=str(self.project_version.id),
            user_email=self.user.email,
            user_input="What can you do?",
            num_documents_to_return=10
        )
        
        # Verify response format
        self.assertIsInstance(answer, str)
        self.assertIsInstance(sources, list)
        # No sources for capability questions
        self.assertEqual(len(sources), 0)


class AdaptiveRAGComplexQueriesTests(TestCase):
    """Test adaptive RAG with complex queries that should retrieve documents."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team')
        TeamMember.objects.create(team=self.team, user=self.user, role='owner')
        
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team
        )
        self.project_version = ProjectVersion.objects.create(
            project=self.project,
            version_number=1
        )
        
        self.chat = Chat.objects.create(
            user=self.user,
            project=self.project,
            project_version=self.project_version
        )
        
        self.viewset = ChatViewSet()
    
    @patch('apps.deliverables.views.specgpt_views.create_retrieval_tool')
    @patch('apps.deliverables.views.specgpt_views.create_react_agent')
    @patch('apps.deliverables.views.specgpt_views.PineconeVectorStore')
    @patch('apps.deliverables.views.specgpt_views.ChatViewSet.get_promptlayer_template')
    def test_technical_question_with_retrieval(self, mock_template, mock_vectorstore, mock_agent, mock_create_tool):
        """Test that technical questions trigger document retrieval."""
        # Mock PromptLayer template
        mock_template.return_value = {
            'prompt_name': 'test_prompt',
            'commit_message': 'test',
            'metadata': {
                'model': {
                    'name': 'gpt-4o',
                    'parameters': {'temperature': 0.1}
                }
            },
            'prompt_template': {
                'messages': [
                    {'role': 'system', 'content': [{'text': 'You are a helpful assistant.'}]}
                ]
            }
        }
        
        # Mock retrieved documents
        mock_doc = Document(
            page_content="The concrete mix shall have a minimum compressive strength of 4000 psi at 28 days.",
            metadata={
                'master_format_section_number': '03 30 00',
                'source': 'concrete_spec.pdf'
            }
        )
        retrieved_docs = [mock_doc]
        
        # Mock the create_retrieval_tool to return tool and document store
        mock_tool = MagicMock()
        mock_tool.name = "retrieve_documents"
        mock_tool.description = "Retrieve relevant documents from project specifications"
        mock_create_tool.return_value = (mock_tool, retrieved_docs)
        
        # Mock agent executor
        mock_executor = MagicMock()
        mock_agent.return_value = mock_executor
        
        mock_executor.invoke.return_value = {
            'messages': [
                HumanMessage(content="What are the concrete requirements?"),
                AIMessage(content="According to Section 03 30 00, the concrete mix shall have a minimum compressive strength of 4000 psi at 28 days.")
            ]
        }
        
        # Call the adaptive method
        answer, sources = self.viewset.generate_adaptive_chat_response(
            chat=self.chat,
            project_id=str(self.project.id),
            project_version_id=str(self.project_version.id),
            user_email=self.user.email,
            user_input="What are the concrete requirements?",
            num_documents_to_return=10
        )
        
        # Verify response
        self.assertIn("4000 psi", answer)
        # Sources should be present
        self.assertGreater(len(sources), 0)
        # Verify source structure matches standard implementation
        self.assertIn('metadata', sources[0])
        self.assertIn('page_content', sources[0])
        self.assertEqual(sources[0]['metadata']['source'], 'concrete_spec.pdf')
        self.assertIn('4000 psi', sources[0]['page_content'])
    
    @patch('apps.deliverables.views.specgpt_views.create_react_agent')
    @patch('apps.deliverables.views.specgpt_views.PineconeVectorStore')
    @patch('apps.deliverables.views.specgpt_views.ChatViewSet.get_promptlayer_template')
    def test_response_format_matches_standard(self, mock_template, mock_vectorstore, mock_agent):
        """Test that adaptive response format matches standard response format."""
        # Mock PromptLayer template
        mock_template.return_value = {
            'prompt_name': 'test_prompt',
            'commit_message': 'test',
            'metadata': {
                'model': {
                    'name': 'gpt-4o',
                    'parameters': {'temperature': 0.1}
                }
            },
            'prompt_template': {
                'messages': [
                    {'role': 'system', 'content': [{'text': 'You are a helpful assistant.'}]}
                ]
            }
        }
        
        # Mock agent executor
        mock_executor = MagicMock()
        mock_agent.return_value = mock_executor
        
        mock_executor.invoke.return_value = {
            'messages': [
                HumanMessage(content="Test question"),
                AIMessage(content="Test answer")
            ]
        }
        
        # Call the adaptive method
        answer, sources = self.viewset.generate_adaptive_chat_response(
            chat=self.chat,
            project_id=str(self.project.id),
            project_version_id=str(self.project_version.id),
            user_email=self.user.email,
            user_input="Test question",
            num_documents_to_return=10
        )
        
        # Verify return format matches standard method
        self.assertIsInstance(answer, str)
        self.assertIsInstance(sources, list)
        # Each source should have metadata and page_content
        for source in sources:
            self.assertIsInstance(source, dict)
            self.assertIn('metadata', source)
            self.assertIn('page_content', source)


class AdaptiveRAGIterationLimitTests(TestCase):
    """Test that iteration limits are enforced in adaptive RAG."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team')
        TeamMember.objects.create(team=self.team, user=self.user, role='owner')
        
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team
        )
        self.project_version = ProjectVersion.objects.create(
            project=self.project,
            version_number=1
        )
        
        self.chat = Chat.objects.create(
            user=self.user,
            project=self.project,
            project_version=self.project_version
        )
        
        self.viewset = ChatViewSet()
    
    @patch('apps.deliverables.views.specgpt_views.create_react_agent')
    @patch('apps.deliverables.views.specgpt_views.PineconeVectorStore')
    @patch('apps.deliverables.views.specgpt_views.ChatViewSet.get_promptlayer_template')
    def test_recursion_limit_enforced(self, mock_template, mock_vectorstore, mock_agent):
        """Test that recursion limit of 4 is enforced."""
        # Mock PromptLayer template
        mock_template.return_value = {
            'prompt_name': 'test_prompt',
            'commit_message': 'test',
            'metadata': {
                'model': {
                    'name': 'gpt-4o',
                    'parameters': {'temperature': 0.1}
                }
            },
            'prompt_template': {
                'messages': [
                    {'role': 'system', 'content': [{'text': 'You are a helpful assistant.'}]}
                ]
            }
        }
        
        # Mock agent executor
        mock_executor = MagicMock()
        mock_agent.return_value = mock_executor
        
        # Simulate successful completion within limit
        mock_executor.invoke.return_value = {
            'messages': [
                HumanMessage(content="Complex question"),
                AIMessage(content="Answer after multiple iterations")
            ]
        }
        
        # Call the adaptive method
        answer, sources = self.viewset.generate_adaptive_chat_response(
            chat=self.chat,
            project_id=str(self.project.id),
            project_version_id=str(self.project_version.id),
            user_email=self.user.email,
            user_input="Complex question",
            num_documents_to_return=10
        )
        
        # Verify config was passed with recursion limit
        call_args = mock_executor.invoke.call_args
        self.assertIn('config', call_args[1] if len(call_args) > 1 else call_args[0])
        config = call_args[1].get('config') if len(call_args) > 1 else call_args[0].get('config')
        self.assertEqual(config.get('recursion_limit'), 4)


class AdaptiveRAGChatHistoryTests(TestCase):
    """Test chat history integration with adaptive RAG."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.team = Team.objects.create(name='Test Team')
        TeamMember.objects.create(team=self.team, user=self.user, role='owner')
        
        self.project = Project.objects.create(
            name='Test Project',
            team=self.team
        )
        self.project_version = ProjectVersion.objects.create(
            project=self.project,
            version_number=1
        )
        
        self.chat = Chat.objects.create(
            user=self.user,
            project=self.project,
            project_version=self.project_version
        )
        
        self.viewset = ChatViewSet()
    
    @patch('apps.deliverables.views.specgpt_views.create_react_agent')
    @patch('apps.deliverables.views.specgpt_views.PineconeVectorStore')
    @patch('apps.deliverables.views.specgpt_views.ChatViewSet.get_promptlayer_template')
    def test_multi_turn_conversation(self, mock_template, mock_vectorstore, mock_agent):
        """Test that adaptive RAG works with multi-turn conversations."""
        # Mock PromptLayer template
        mock_template.return_value = {
            'prompt_name': 'test_prompt',
            'commit_message': 'test',
            'metadata': {
                'model': {
                    'name': 'gpt-4o',
                    'parameters': {'temperature': 0.1}
                }
            },
            'prompt_template': {
                'messages': [
                    {'role': 'system', 'content': [{'text': 'You are a helpful assistant.'}]}
                ]
            }
        }
        
        # Add existing messages to chat
        ChatMessage.objects.create(
            chat=self.chat,
            message="What sections cover concrete?",
            type=ChatMessage.ChatMessageType.HUMAN
        )
        ChatMessage.objects.create(
            chat=self.chat,
            message="Section 03 30 00 covers concrete specifications.",
            type=ChatMessage.ChatMessageType.AI
        )
        
        # Mock agent executor
        mock_executor = MagicMock()
        mock_agent.return_value = mock_executor
        
        mock_executor.invoke.return_value = {
            'messages': [
                HumanMessage(content="What are the strength requirements?"),
                AIMessage(content="The concrete shall have a minimum compressive strength of 4000 psi.")
            ]
        }
        
        # Call the adaptive method with follow-up question
        answer, sources = self.viewset.generate_adaptive_chat_response(
            chat=self.chat,
            project_id=str(self.project.id),
            project_version_id=str(self.project_version.id),
            user_email=self.user.email,
            user_input="What are the strength requirements?",
            num_documents_to_return=10
        )
        
        # Verify response
        self.assertIsInstance(answer, str)
        self.assertIsInstance(sources, list)
        
        # Verify messages were saved to chat history
        messages = ChatMessage.objects.filter(chat=self.chat).order_by('created_at')
        # Should have original 2 + new 2 (user + AI)
        self.assertGreaterEqual(messages.count(), 4)

