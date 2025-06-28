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
from openpyxl import load_workbook
from io import BytesIO

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
            kwargs={'project_id': self.project.id}
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
            'chat_id': self.chat.id,
            'user_input': 'test question',
            'k': 5
        })
        
        # Assert response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['chat_id'], self.chat.id)
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
    def test_calling_endpoint_without_chat_id_creates_new_chat(self, mock_template_manager, mock_chain, mock_chat_openai, mock_pinecone):
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

        # Verify new chat was created
        self.assertEqual(Chat.objects.count(), 2)
        new_chat = Chat.objects.exclude(id=self.chat.id).last()
        self.assertEqual(new_chat.user, self.user)
        self.assertEqual(new_chat.project, self.project)
        self.assertEqual(new_chat.project_version, self.project_version)
        
        # Assert response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(response.data['chat_id'], self.chat.id)
        self.assertEqual(response.data['chat_id'], new_chat.id)
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
    def test_calling_endpoint_without_chat_id_and_specifying_project_version_creates_new_chat(self, mock_template_manager, mock_chain, mock_chat_openai, mock_pinecone):
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
        new_project_version = ProjectVersion.objects.create(
            project=self.project,
            version_number=2,
            version_name='2.0.0'
        )
        
        # Make request
        response = self.client.post(self.url, {
            'project_version_id': new_project_version.id,
            'user_input': 'test question',
            'k': 5
        })

        # Verify new chat was created
        self.assertEqual(Chat.objects.count(), 2)
        new_chat = Chat.objects.exclude(id=self.chat.id).last()
        self.assertEqual(new_chat.user, self.user)
        self.assertEqual(new_chat.project, self.project)
        self.assertEqual(new_chat.project_version, new_project_version)
        
        # Assert response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['chat_id'], new_chat.id)
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
            'chat_id': self.chat.id,
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
        response = self.client.post(self.url, {
            'chat_id': self.chat.id,
            'user_input': 'test question'
        })
        
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
        response = self.client.post(self.url, {
            'chat_id': self.chat.id,
            'user_input': 'test question'
        })

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

    def test_extract_tables_to_csv_unauthenticated_user(self):
        """Test that unauthenticated users cannot extract tables"""
        url = reverse('specgpt-chat-extract-tables-to-csv', kwargs={'project_id': self.project.id})
        response = self.client.post(url, {'text': 'test text'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_extract_tables_to_csv_missing_text(self):
        """Test that missing text returns 400 error"""
        self.client.force_authenticate(user=self.user)
        url = reverse('specgpt-chat-extract-tables-to-csv', kwargs={'project_id': self.project.id})
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('Text content is required', response.data['error'])

    def test_extract_tables_to_csv_empty_text(self):
        """Test that empty text returns 400 error"""
        self.client.force_authenticate(user=self.user)
        url = reverse('specgpt-chat-extract-tables-to-csv', kwargs={'project_id': self.project.id})
        response = self.client.post(url, {'text': ''})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('Text content is required', response.data['error'])

    def test_extract_tables_to_csv_no_tables_found_single_mode(self):
        """Test that no tables found in single mode returns 404"""
        self.client.force_authenticate(user=self.user)
        url = reverse('specgpt-chat-extract-tables-to-csv', kwargs={'project_id': self.project.id})
        response = self.client.post(url, {
            'text': 'This is just regular text with no tables.',
            'extract_all': False
        })
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('error', response.data)
        self.assertIn('No markdown tables found in the text', response.data['error'])

    def test_extract_tables_to_csv_no_tables_found_multiple_mode(self):
        """Test that no tables found in multiple mode returns 404"""
        self.client.force_authenticate(user=self.user)
        url = reverse('specgpt-chat-extract-tables-to-csv', kwargs={'project_id': self.project.id})
        response = self.client.post(url, {
            'text': 'This is just regular text with no tables.',
            'extract_all': True
        })
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('error', response.data)
        self.assertIn('No markdown tables found in the text', response.data['error'])

    def test_extract_tables_to_csv_single_table_success(self):
        """Test successful extraction of single table"""
        self.client.force_authenticate(user=self.user)
        url = reverse('specgpt-chat-extract-tables-to-csv', kwargs={'project_id': self.project.id})
        
        text_with_table = """
        Here's the project status:
        
        | Task | Status | Priority |
        |------|--------|----------|
        | Frontend | Done | High |
        | Backend | In Progress | Medium |
        | Testing | Pending | Low |
        
        The project is progressing well.
        """
        
        response = self.client.post(url, {
            'text': text_with_table,
            'extract_all': False
        })
        
        # Assert response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('inspection_log.xlsx', response['Content-Disposition'])
        
        # Verify Excel content
        workbook = load_workbook(BytesIO(response.content))
        worksheet = workbook.active
        self.assertEqual(worksheet.title, "Table_1")
        
        # Check headers
        self.assertEqual(worksheet['A1'].value, 'Task')
        self.assertEqual(worksheet['B1'].value, 'Status')
        self.assertEqual(worksheet['C1'].value, 'Priority')
        
        # Check data
        self.assertEqual(worksheet['A2'].value, 'Frontend')
        self.assertEqual(worksheet['B2'].value, 'Done')
        self.assertEqual(worksheet['C2'].value, 'High')
        
        self.assertEqual(worksheet['A3'].value, 'Backend')
        self.assertEqual(worksheet['B3'].value, 'In Progress')
        self.assertEqual(worksheet['C3'].value, 'Medium')
        
        self.assertEqual(worksheet['A4'].value, 'Testing')
        self.assertEqual(worksheet['B4'].value, 'Pending')
        self.assertEqual(worksheet['C4'].value, 'Low')

    def test_extract_tables_to_csv_multiple_tables_success(self):
        """Test successful extraction of multiple tables"""
        self.client.force_authenticate(user=self.user)
        url = reverse('specgpt-chat-extract-tables-to-csv', kwargs={'project_id': self.project.id})
        
        text_with_tables = """
        ## Task Summary
        | Task | Hours | Status |
        |------|-------|--------|
        | Planning | 8 | Complete |
        | Development | 40 | In Progress |
        
        ## Resource Allocation
        | Resource | Role | Availability |
        |----------|------|--------------|
        | John | Developer | 100% |
        | Jane | Designer | 80% |
        | Bob | Tester | 60% |
        
        ## Budget Breakdown
        | Category | Budget | Spent |
        |----------|--------|-------|
        | Labor | $50,000 | $35,000 |
        | Tools | $5,000 | $4,200 |
        """
        
        response = self.client.post(url, {
            'text': text_with_tables,
            'extract_all': True
        })
        
        # Assert response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('inspection_log.xlsx', response['Content-Disposition'])
        
        # Verify Excel content
        workbook = load_workbook(BytesIO(response.content))
        
        # Check that we have 3 worksheets
        self.assertEqual(len(workbook.sheetnames), 3)
        self.assertIn('Table_1', workbook.sheetnames)
        self.assertIn('Table_2', workbook.sheetnames)
        self.assertIn('Table_3', workbook.sheetnames)
        
        # Check first table (Task Summary)
        worksheet1 = workbook['Table_1']
        self.assertEqual(worksheet1['A1'].value, 'Task')
        self.assertEqual(worksheet1['B1'].value, 'Hours')
        self.assertEqual(worksheet1['C1'].value, 'Status')
        self.assertEqual(worksheet1['A2'].value, 'Planning')
        self.assertEqual(worksheet1['B2'].value, '8')
        self.assertEqual(worksheet1['C2'].value, 'Complete')
        
        # Check second table (Resource Allocation)
        worksheet2 = workbook['Table_2']
        self.assertEqual(worksheet2['A1'].value, 'Resource')
        self.assertEqual(worksheet2['B1'].value, 'Role')
        self.assertEqual(worksheet2['C1'].value, 'Availability')
        self.assertEqual(worksheet2['A2'].value, 'John')
        self.assertEqual(worksheet2['B2'].value, 'Developer')
        self.assertEqual(worksheet2['C2'].value, '100%')
        
        # Check third table (Budget Breakdown)
        worksheet3 = workbook['Table_3']
        self.assertEqual(worksheet3['A1'].value, 'Category')
        self.assertEqual(worksheet3['B1'].value, 'Budget')
        self.assertEqual(worksheet3['C1'].value, 'Spent')
        self.assertEqual(worksheet3['A2'].value, 'Labor')
        self.assertEqual(worksheet3['B2'].value, '$50,000')
        self.assertEqual(worksheet3['C2'].value, '$35,000')

    def test_extract_tables_to_csv_with_quoted_values(self):
        """Test extraction of tables with quoted values and commas"""
        self.client.force_authenticate(user=self.user)
        url = reverse('specgpt-chat-extract-tables-to-csv', kwargs={'project_id': self.project.id})
        
        text_with_quoted_table = """
        | Name | Description | Location |
        |------|-------------|----------|
        | John | "Hello, world" | NYC, NY |
        | Jane | No quotes here | LA, CA |
        """
        
        response = self.client.post(url, {
            'text': text_with_quoted_table,
            'extract_all': False
        })
        
        # Assert response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify Excel content
        workbook = load_workbook(BytesIO(response.content))
        worksheet = workbook.active
        
        # Check that quoted values are properly handled
        self.assertEqual(worksheet['B2'].value, '"Hello, world"')  
        self.assertEqual(worksheet['C2'].value, 'NYC, NY')  # Should handle commas

    def test_extract_tables_to_csv_with_empty_cells(self):
        """Test extraction of tables with empty cells"""
        self.client.force_authenticate(user=self.user)
        url = reverse('specgpt-chat-extract-tables-to-csv', kwargs={'project_id': self.project.id})
        
        text_with_empty_cells = """
        | Name | Age | City |
        |------|-----|------|
        | John |     | NYC  |
        |      | 30  |      |
        | Jane | 25  | LA   |
        """
        
        response = self.client.post(url, {
            'text': text_with_empty_cells,
            'extract_all': False
        })
        
        # Assert response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify Excel content
        workbook = load_workbook(BytesIO(response.content))
        worksheet = workbook.active
        
        # Check that empty cells are handled properly
        self.assertEqual(worksheet['B2'].value, None)  # Empty age for John
        self.assertEqual(worksheet['A3'].value, None)  # Empty name
        self.assertEqual(worksheet['C3'].value, None)  # Empty city

    def test_extract_tables_to_csv_default_extract_all_true(self):
        """Test that extract_all defaults to True when not specified"""
        self.client.force_authenticate(user=self.user)
        url = reverse('specgpt-chat-extract-tables-to-csv', kwargs={'project_id': self.project.id})
        
        text_with_tables = """
        | A | B |
        |---|---|
        | 1 | 2 |
        
        | X | Y |
        |---|---|
        | 3 | 4 |
        """
        
        response = self.client.post(url, {
            'text': text_with_tables
            # extract_all not specified, should default to True
        })
        
        # Assert response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('inspection_log.xlsx', response['Content-Disposition'])
        
        # Verify Excel content has multiple worksheets
        workbook = load_workbook(BytesIO(response.content))
        self.assertEqual(len(workbook.sheetnames), 2)

    def test_extract_tables_to_csv_exception_handling(self):
        """Test handling of exceptions during table extraction"""
        self.client.force_authenticate(user=self.user)
        url = reverse('specgpt-chat-extract-tables-to-csv', kwargs={'project_id': self.project.id})
        
        # Mock the extract function to raise an exception
        with patch('apps.deliverables.views.specgpt_views.extract_and_convert_tables_to_csv') as mock_extract:
            mock_extract.side_effect = Exception("Test exception")
            
            response = self.client.post(url, {
                'text': 'test text',
                'extract_all': True
            })
            
            # Assert response
            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
            self.assertIn('error', response.data)
            self.assertIn('Failed to extract tables', response.data['error'])
            self.assertIn('Test exception', response.data['error'])

    def test_extract_tables_to_csv_non_project_member_access_denied(self):
        """Test that non-project members cannot access the endpoint"""
        # Create another user who is not a project member
        other_user = self.User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='password123'
        )
        
        # Add other user to team but not to project
        TeamMembership.objects.create(
            user=other_user,
            team=self.team,
            role='member'
        )
        
        self.client.force_authenticate(user=other_user)
        url = reverse('specgpt-chat-extract-tables-to-csv', kwargs={'project_id': self.project.id})
        
        response = self.client.post(url, {
            'text': 'test text'
        })
        
        # Assert access denied
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_extract_tables_to_csv_header_styling(self):
        """Test that Excel headers are properly styled"""
        self.client.force_authenticate(user=self.user)
        url = reverse('specgpt-chat-extract-tables-to-csv', kwargs={'project_id': self.project.id})
        
        text_with_table = """
        | Name | Age | City |
        |------|-----|------|
        | John | 25  | NYC  |
        """
        
        response = self.client.post(url, {
            'text': text_with_table,
            'extract_all': False
        })
        
        # Assert response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify Excel content and styling
        workbook = load_workbook(BytesIO(response.content))
        worksheet = workbook.active
        
        # Check header cell styling
        header_cell = worksheet['A1']
        self.assertTrue(header_cell.font.bold)
        self.assertEqual(header_cell.font.color.rgb, '00FFFFFF')  # White text
        self.assertEqual(header_cell.fill.start_color.rgb, '00202a44')  # Dark blue background 