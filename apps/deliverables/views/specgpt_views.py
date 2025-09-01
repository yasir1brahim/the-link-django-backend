from __future__ import annotations
import datetime
import json
import csv
import re
import requests
from uuid import UUID
from typing import Any, List, Optional
from enum import Enum
import boto3
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.decorators import action
import pymupdf
from openai import OpenAI
from django.conf import settings
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from promptlayer.templates import TemplateManager
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain
from langchain_community.callbacks.promptlayer_callback import PromptLayerCallbackHandler
from langchain.schema.messages import BaseMessage, AIMessage, _message_to_dict, messages_from_dict
from langchain_core.outputs import (
    ChatGeneration,
    LLMResult,
)
from langchain.prompts.chat import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
import tiktoken
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter
import io

from apps.deliverables.serializers.specgpt import ChatDetailSerializer, AiGeneratedLogSerializer
from apps.deliverables.permissions import ChatAccessPermissions, AiGeneratedLogAccessPermissions
from apps.deliverables.models import Project, ProjectVersion
from typing import TypedDict, List

from apps.deliverables.models import (
    UploadedFile, MasterFormatSection, 
    SpecSection, DocProcessingStatus, 
    Chat, ChatMessage, 
    CustomPostgresChatMessageHistory,
    AiGeneratedLog
)

from langchain.memory import ConversationBufferMemory
from apps.deliverables.utils import extract_and_convert_tables_to_csv, extract_first_table_to_csv, merge_tables_from_text, convert_to_markdown_table


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count the number of tokens in a text string."""
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except KeyError:
        # Fallback to cl100k_base encoding for unknown models
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))


def split_file_content_into_chunks(
        file_content: str,
        max_tokens_per_chunk: int = settings.OPENAI_MODEL_MAX_CONTEXT_SIZE, 
        model: str = "gpt-4o",
        preferred_separator: str = f'\n\n{"-"*100}\n',
        split_by_regex: bool = False,
        regex_pattern: str = r"^\s*END OF SECTION\b.*$"
    ) -> List[str]:
    """
    Split large content into chunks that fit within the model's context limit.
    
    Args:
        system_prompt: The system prompt
        user_prompt_template: The user prompt template with {file_content} placeholder
        file_content: The file contents to split over multiple LLM calls
        max_tokens_per_chunk: Maximum tokens per chunk
        model: The model name for token counting
        preferred_separator: The separator to use between chunks (defaults to "\n\n")
    Returns:
        List of content chunks
    """
    
    # Split content into chunks using regex
    chunks = []
    current_chunk = ""
    current_tokens = 0
    
    # Handle empty content
    if not file_content.strip():
        return []
    
    # Split by separator to maintain some structure
    if split_by_regex:
        pieces = re.split(regex_pattern, file_content, flags=re.MULTILINE | re.IGNORECASE)
    else:
        pieces = file_content.split(preferred_separator)
    
    for i, piece in enumerate(pieces):
        piece_tokens = count_tokens(piece, model)
        
        # If adding this piece would exceed the limit, save current chunk and start new one
        if current_tokens + piece_tokens > max_tokens_per_chunk:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = piece
            current_tokens = piece_tokens
        else:
            # Always add separator to maintain consistency with original behavior
            if current_chunk:
                current_chunk += preferred_separator + piece
                current_tokens += piece_tokens
            else:
                # For the first piece, add the separator to match expected behavior
                current_chunk = preferred_separator + piece
                current_tokens = piece_tokens
    
    # Add the last chunk if it has content
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks


class SpecGptEmbeddingRequest(TypedDict):
    new_status: str
    doc_db_record_id: str
    db_document_chunks: List[str]
    master_format_section_number: str
    file_s3_key: str


@api_view(['POST'])
@permission_classes([AllowAny])
def specgpt_embedding_webhook(request):
    # TODO: Complete this
    request_payload = request.data
    print(f"SPEC GPT EMBEDDING WEBHOOK received request: {request_payload}")

    request_data = SpecGptEmbeddingRequest(**request_payload)

    uploaded_file = UploadedFile.objects.get(id=int(request_data['doc_db_record_id']))
    masterformat_section, created = MasterFormatSection.objects.get_or_create(masterformat_number=request_data['master_format_section_number'])
    section, created = SpecSection.objects.get_or_create(
        document_id=request_data['doc_db_record_id'],
        masterformat_section=masterformat_section,
        file_s3_key=request_data['file_s3_key']
    )

    if request_data['new_status'] == 'PROCESSING':
        print(f"SPEC GPT EMBEDDING WEBHOOK: setting document {request_data['doc_db_record_id']} section {request_data['master_format_section_number']} with file_s3_key {request_data['file_s3_key']} processing status to PROCESSING")
        section.specgpt_embedding_status = UploadedFile.SpecgptProcessingStatusChoices.PROCESSING
        section.save()
    elif request_data['new_status'] == 'PROCESSED':
        print(f"SPEC GPT EMBEDDING WEBHOOK: setting document {request_data['doc_db_record_id']} section {request_data['master_format_section_number']} with file_s3_key {request_data['file_s3_key']} processing status to PROCESSED")
        section.specgpt_embedding_status = UploadedFile.SpecgptProcessingStatusChoices.PROCESSED
        section.save()
    elif request_data['new_status'] == 'FAILED':
        print(f"SPEC GPT EMBEDDING WEBHOOK: setting document {request_data['doc_db_record_id']} section {request_data['master_format_section_number']} with file_s3_key {request_data['file_s3_key']} processing status to FAILED")
        uploaded_file.specgpt_processing_status = UploadedFile.SpecgptProcessingStatusChoices.FAILED
        uploaded_file.save()
        section.specgpt_embedding_status = UploadedFile.SpecgptProcessingStatusChoices.FAILED
        section.save()

    """IF document.processing_status == SUBSECTIONS_EXTRACTED or SECTION_PROCESSING_FAILED then we have records of all extracted subsections.
    If so, then update document.specgpt_processing_status to PROCESSED if all subsections have been processed"""
    print(f"SPEC GPT EMBEDDING WEBHOOK: checking if all subsections have been processed for document {request_data['doc_db_record_id']}")
    document = uploaded_file
    if document.specgpt_processing_status in [UploadedFile.SpecgptProcessingStatusChoices.SUBSECTIONS_EXTRACTED, UploadedFile.SpecgptProcessingStatusChoices.SECTION_PROCESSING_FAILED]:
        print(f"SPEC GPT EMBEDDING WEBHOOK: getting unprocessed section count for document {request_data['doc_db_record_id']}")
        unprocessed_spec_section_count = SpecSection.objects.filter(document_id=request_data['doc_db_record_id']).exclude(
            specgpt_embedding_status=UploadedFile.SpecgptProcessingStatusChoices.PROCESSED
        ).count()
        print(f"SPEC GPT EMBEDDING WEBHOOK: unprocessed_spec_section_count: {unprocessed_spec_section_count}")
        if unprocessed_spec_section_count == 0:
            print(f"SPEC GPT EMBEDDING WEBHOOK: all subsections have been processed for document {request_data['doc_db_record_id']}")
            document.specgpt_processing_status = UploadedFile.SpecgptProcessingStatusChoices.PROCESSED
            document.save()

    return Response(status=status.HTTP_200_OK)


class AiLogGenerationRequest(TypedDict):
    log_type: str
    project_id: str
    project_version_id: str
    new_status: str
    table: str


@api_view(['POST'])
@permission_classes([AllowAny])
def ai_log_generation_webhook(request):
    request_payload = request.data
    print(f"AI LOG GENERATION WEBHOOK received request: {request_payload}")

    request_data = AiLogGenerationRequest(**request_payload)

    new_status = request_data['new_status']
    ai_generated_log_id = request_payload.get('ai_generated_log_id') or request_data.get('ai_generated_log_id')

    if new_status in ['SUCCESS', 'FAILURE']:
        # Prefer updating by explicit log id if provided
        log_obj = None
        if ai_generated_log_id:
            try:
                log_obj = AiGeneratedLog.objects.get(id=int(ai_generated_log_id))
            except Exception:
                log_obj = None
        if not log_obj:
            # Fallback: try to update the latest PROCESSING record for this context
            log_obj = AiGeneratedLog.objects.filter(
                project_id=request_data['project_id'],
                project_version_id=request_data['project_version_id'],
                log_type=request_data['log_type'],
                log_status='PROCESSING',
            ).order_by('-created_at').first()

        if log_obj:
            log_obj.log_status = new_status
            if request_data.get('table') is not None:
                log_obj.log_table = request_data['table']
            log_obj.save()
        else:
            AiGeneratedLog.objects.create(
                project_id=request_data['project_id'],
                project_version_id=request_data['project_version_id'],
                log_type=request_data['log_type'],
                log_table=request_data.get('table'),
                log_status=new_status,
            )
        if new_status == 'FAILURE':
            print(f"AI LOG GENERATION WEBHOOK: Failure for {request_data.get('log_type', 'unknown')} log for project {request_data.get('project_id', 'unknown')} project version {request_data.get('project_version_id', 'unknown')}")
    elif new_status == 'PROCESSING':
        # Ensure there is a PROCESSING record referencing this id if provided
        if ai_generated_log_id:
            try:
                log_obj = AiGeneratedLog.objects.get(id=int(ai_generated_log_id))
                if log_obj.log_status != 'PROCESSING':
                    log_obj.log_status = 'PROCESSING'
                    log_obj.save()
            except AiGeneratedLog.DoesNotExist:
                AiGeneratedLog.objects.create(
                    id=int(ai_generated_log_id),
                    project_id=request_data['project_id'],
                    project_version_id=request_data['project_version_id'],
                    log_type=request_data['log_type'],
                    log_status='PROCESSING',
                )
        else:
            exists = AiGeneratedLog.objects.filter(
                project_id=request_data['project_id'],
                project_version_id=request_data['project_version_id'],
                log_type=request_data['log_type'],
                log_status='PROCESSING',
            ).exists()
            if not exists:
                AiGeneratedLog.objects.create(
                    project_id=request_data['project_id'],
                    project_version_id=request_data['project_version_id'],
                    log_type=request_data['log_type'],
                    log_status='PROCESSING',
                )

    return Response(status=status.HTTP_200_OK)


class AiGeneratedLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for AiGeneratedLog objects providing list and detail views.
    
    Required query parameters:
    - project_id: ID of the project
    - project_version_id: ID of the project version  
    - log_type: Type of log to filter by
    
    The view filters logs by project, project version, and log type,
    and ensures users have access to the project.
    """
    queryset = AiGeneratedLog.objects.all()
    permission_classes = [IsAuthenticated, AiGeneratedLogAccessPermissions]
    serializer_class = AiGeneratedLogSerializer

    def get_queryset(self):
        """
        Filter queryset by project_id from URL parameters and project_version_id, log_type from query parameters.
        For detail views, only filter by project_id.
        """
        queryset = super().get_queryset()
        
        # Get project_id from URL parameters
        project_id = self.kwargs.get('project_id')
        
        # Validate required project_id
        if not project_id:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'error': 'project_id is required'})
        
        # For list views, also filter by project_version_id and log_type
        if self.action == 'list':
            project_version_id = self.request.query_params.get('project_version_id')
            log_type = self.request.query_params.get('log_type')
            
            if not project_version_id:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({'error': 'project_version_id is required'})
            if not log_type:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({'error': 'log_type is required'})
            
            # Filter by all required parameters
            queryset = queryset.filter(
                project_id=project_id,
                project_version_id=project_version_id,
                log_type=log_type
            )
        else:
            # For detail views, only filter by project_id
            queryset = queryset.filter(project_id=project_id)
        
        # Order by creation date (newest first)
        return queryset.order_by('-created_at')


class CustomPromptLayerCallbackHandler(PromptLayerCallbackHandler):
    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        from promptlayer.utils import get_api_key, promptlayer_api_request

        run_info = self.runs.get(run_id, {})
        if not run_info:
            return
        run_info["request_end_time"] = datetime.datetime.now().timestamp()
        for i in range(len(response.generations)):
            generation = response.generations[i][0]

            resp = {
                "text": generation.text,
                "llm_output": response.llm_output,
            }
            model_params = run_info.get("invocation_params", {})
            is_chat_model = run_info.get("messages", None) is not None
            model_input = (
                run_info.get("messages", [])[i]
                if is_chat_model
                else [run_info.get("prompts", [])[i]]
            )
            model_response = (
                [self._convert_message_to_dict(generation.message)]
                if is_chat_model and isinstance(generation, ChatGeneration)
                else resp
            )

            pl_request_id = promptlayer_api_request(
                function_name=run_info.get("name"),
                provider_type="langchain",
                args=model_input,
                kwargs=model_params,
                tags=self.pl_tags,
                response=model_response,
                request_start_time=run_info.get("request_start_time"),
                request_end_time=run_info.get("request_end_time"),
                api_key=get_api_key(),
                return_pl_id=bool(self.pl_id_callback is not None),
                metadata={
                    "_langchain_run_id": str(run_id),
                    "_langchain_parent_run_id": str(parent_run_id),
                    "_langchain_tags": str(run_info.get("tags", [])),
                },
            )

            if self.pl_id_callback:
                self.pl_id_callback(pl_request_id)


class ChatViewSet(viewsets.ModelViewSet):
    embedding_model = "text-embedding-3-large"
    vector_dimensionality = 3072
    embedding_provider = OpenAIEmbeddings
    queryset = Chat.objects.all()
    permission_classes = [IsAuthenticated, ChatAccessPermissions]
    serializer_class = ChatDetailSerializer

    class RESPONSE_TYPES(str, Enum):
        STANDARD = "standard"
        INSPECTION_LOG = "inspection_log"
        OWNER_DELIVERABLES_LOG = "owner_deliverables_log"
        

    def list(self, request, project_id=None):
        """
        Return a list of chats for the project with custom pagination and metadata.
        """
        project_version_id = request.query_params.get('project_version_id', None)
        history_today = []
        history_yesterday = []
        history_prev_7_days = []
        history_prev_30_days = []
        history_next_30_days = []
        _now = datetime.datetime.utcnow()
        start_of_today = _now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_yesterday = start_of_today - datetime.timedelta(days=1)
        end_of_prev_7_days = start_of_today - datetime.timedelta(days=6, microseconds=1)
        end_of_prev_30_days = start_of_today - datetime.timedelta(days=29, microseconds=1)
        if not project_version_id:
            project_version = ProjectVersion.objects.filter(project_id=project_id).order_by('-created_at').first()
            if not project_version:
                return Response(status=status.HTTP_404_NOT_FOUND, data={
                    'error': 'No project version found'
                })
            project_version_id = project_version.id
        
        # Get queryset and apply pagination
        queryset = self.get_queryset().filter(project_id=project_id, project_version_id=project_version_id)
        
        for chat in queryset:
            first_human_message = chat.messages.filter(type__in=[ChatMessage.ChatMessageType.HUMAN, ChatMessage.ChatMessageType.SYSTEM]).order_by('created_at').first()
            _history = {
                'session_id': chat.id,
                'question': first_human_message.message if first_human_message else '',
            }
            if chat.created_at.astimezone(datetime.UTC) > start_of_today.astimezone(datetime.UTC):
                history_today.append(_history)
            elif chat.created_at.astimezone(datetime.UTC) > start_of_yesterday.astimezone(datetime.UTC):
                history_yesterday.append(_history)
            elif chat.created_at.astimezone(datetime.UTC) > end_of_prev_7_days.astimezone(datetime.UTC):
                history_prev_7_days.append(_history)
            elif chat.created_at.astimezone(datetime.UTC) > end_of_prev_30_days.astimezone(datetime.UTC):
                history_prev_30_days.append(_history)
            else:
                history_next_30_days.append(_history)

        session_id_history_list = [
            {
                'day': "Today",
                'chats': history_today
            },
            {
                'day': "Yesterday",
                'chats': history_yesterday
            },
            {
                'day': "Previous 7 Days",
                'chats': history_prev_7_days
            },
            {
                'day': "Previous 30 Days",
                'chats': history_prev_30_days
            },
            {
                'day': "30 Days After",
                'chats': history_next_30_days
            }
        ]
        
        return Response(status=status.HTTP_200_OK, data={
            'results': session_id_history_list
        })
    


    def get_promptlayer_template(self, promptlayer_prompt_name):
        template_manager = TemplateManager(api_key=settings.PROMPTLAYER_API_KEY)
        return template_manager.get(promptlayer_prompt_name, {'label': settings.ENVIRONMENT})

    def get_promptlayer_model_metadata(self, promptlayer_template):
        return promptlayer_template['metadata']['model']
    
    def get_promptlayer_system_prompt(self, promptlayer_template):
        prompts = promptlayer_template['prompt_template']['messages']
        system_prompt = [prompt for prompt in prompts if prompt['role'] == 'system']
        return system_prompt[0]['content'][0]['text']
    
    def get_promptlayer_user_prompt(self, promptlayer_template):
        prompts = promptlayer_template['prompt_template']['messages']
        user_prompt = [prompt for prompt in prompts if prompt['role'] == 'user']
        return user_prompt[0]['content'][0]['text']
    
    def get_promptlayer_developer_prompt(self, promptlayer_template):
        prompts = promptlayer_template['prompt_template']['messages']
        developer_prompt = [prompt for prompt in prompts if prompt['role'] == 'developer']
        return developer_prompt[0]['content'][0]['text']
    
    def get_prompt(self, promptlayer_template):
        print("PROMPTLAYER TEMPLATE")
        print(promptlayer_template)

        promptlayer_template_string = promptlayer_template['prompt_template']['messages'][0]['content'][0]['text']
        messages = [
            SystemMessagePromptTemplate.from_template(promptlayer_template_string),
            HumanMessagePromptTemplate.from_template("{question}"),
        ]
        return ChatPromptTemplate.from_messages(messages)
    
    def _build_message_sources(self, source_documents):
        message_sources = []
        for source_document in source_documents:
            metadata = source_document.metadata
            message_sources.append({
                'user_id': metadata['userid'],
                'master_format_section_number': metadata['master_format_section_number'],
                's3_bucket': metadata['s3_bucket'],
                's3_key': metadata['s3_key'],
                'source_file_name': metadata['source'],
                'text': source_document.page_content
            })
        return message_sources
    
    def create_raw_message(self, message, role):
        return {
            'data': {
                'id': None,
                'name': None,
                'type': role,
                'content': message,
                'example': False,
                'tool_calls': [],
                'usage_metadata': None,
                'additional_kwargs': {},
                'response_metadata': {},
                'invalid_tool_calls': []
            },
            'type': role
        }
    
    def generate_standard_chat_response(self, chat, project_id, project_version_id, user_email, user_input, num_documents_to_return):
        try:
            promptlayer_template = self.get_promptlayer_template(settings.SPEC_GPT_PROMPTLAYER_PROMPT_NAME)
        except Exception as e:
            print(f"Failed to retrieve PromptLayer template: {str(e)}")
            raise e

        vectorstore = PineconeVectorStore(
            pinecone_api_key=settings.PINECONE_API_KEY,
            index_name=settings.PINECONE_INDEX_NAME,
            embedding=self.embedding_provider(model=self.embedding_model)
        )

        chat_memory = CustomPostgresChatMessageHistory(chat)
        memory = ConversationBufferMemory(
            memory_key="chat_history",
            chat_memory=chat_memory,
            input_key='question', 
            output_key='answer',
            return_messages=True,
        )

        promptlayer_model_metadata = self.get_promptlayer_model_metadata(promptlayer_template)

        vectorstore_filter = {
            'project_id': {"$eq": str(project_id)},
            'project_version_id': {"$eq": str(project_version_id)},
        }

        specgpt_qa = ConversationalRetrievalChain.from_llm(
            llm=ChatOpenAI(
                temperature=promptlayer_model_metadata['parameters']['temperature'],
                model_name=promptlayer_model_metadata['name'],
                callbacks=[
                    CustomPromptLayerCallbackHandler(
                        pl_tags=[
                            f"environment: {settings.ENVIRONMENT}",
                            f"application: deliverables",
                            f"user: {user_email}",
                            f"prompt_name: {promptlayer_template['prompt_name']}",
                            f"prompt_commit_message: {promptlayer_template['commit_message']}",
                            f"llm_model_name: {promptlayer_model_metadata['name']}",
                            f"llm_temperature: {promptlayer_model_metadata['parameters']['temperature']}"
                        ]
                    )
                ]
            ),
            retriever=vectorstore.as_retriever(
                search_kwargs={
                    "k": num_documents_to_return, 
                    "filter": vectorstore_filter
                }
            ),
            memory=memory,
            return_source_documents=True,
            combine_docs_chain_kwargs={"prompt": self.get_prompt(promptlayer_template)},
            verbose=False,
        )    

        results = specgpt_qa({'question': user_input})

        source_documents = results['source_documents']
        chat_message = chat_memory.message_db_object
        message_sources = [
            {'metadata': x.metadata, 'page_content': x.page_content}
            for x in source_documents
        ]
        chat_message.sources = message_sources
        chat_message.save()
        return results['answer'], message_sources
    

    class InspectionLogRow(BaseModel):
        spec_section_number: str = Field(alias="Spec Section #", description="The section this item was found in")
        spec_section_name: str = Field(alias="Spec Section Name", description="The name of the section")
        inspection_type_and_requirements: str = Field(alias="Inspection Type And Requirements", description="The type and requirements of the inspection")
        inspection_frequency: str = Field(alias="Inspection Frequency", description="The frequency of the inspection")
        responsible_party: str = Field(alias="Responsible Party", description="The responsible party for the inspection")

    class InspectionLog(BaseModel):
        results: List['InspectionLogRow'] = Field(description="List of inspection log rows")

    class OwnerDeliverablesRow(BaseModel):
        spec_section_number: str = Field(alias="Spec Section #", description="The section this item was found in")
        spec_section_name: str = Field(alias="Spec Section Name", description="The name of the section")
        deliverable_type: str = Field(alias="Deliverable Type", description="The type of deliverable")
        when_due: str = Field(alias="When Due", description="The date the deliverable is due")
        responsible_party: str = Field(alias="Responsible Party", description="The responsible party for the deliverable")
        exact_requirement_text: str = Field(alias="Exact Requirement Text", description="The exact requirement text")

    class OwnerDeliverablesLog(BaseModel):
        results: List['OwnerDeliverablesRow'] = Field(description="List of owner deliverables rows")

    def generate_general_log(self, project_id, project_version_id, promptlayer_template_name, full_log_model, log_row_model):
        try:
            promptlayer_template = self.get_promptlayer_template(promptlayer_template_name)
        except Exception as e:
            print(f"Failed to retrieve PromptLayer template: {str(e)}")
            raise e
        
        system_prompt = self.get_promptlayer_system_prompt(promptlayer_template)
        user_prompt = self.get_promptlayer_user_prompt(promptlayer_template)
        promptlayer_model_metadata = self.get_promptlayer_model_metadata(promptlayer_template)
        temperature = promptlayer_model_metadata['parameters'].get('temperature', 0.1)
        top_p = promptlayer_model_metadata['parameters'].get('top_p', 1)
        print("GENERATE GENERAL LOG: top_p: ", top_p)

        project_version_files = UploadedFile.objects.filter(project_version_id=project_version_id).order_by('id')
        project_version_specs = SpecSection.objects.filter(document__in=project_version_files).order_by('id')
        spec_sections = [{
            'master_format_section_number': spec_section.masterformat_section.masterformat_number,
            'file_s3_key': spec_section.file_s3_key
        } for spec_section in project_version_specs if spec_section.file_s3_key]
        s3_bucket = settings.S3_BUCKET

        # Create a processing record so the UI can reflect loading state immediately
        processing_log = None
        try:
            processing_log = AiGeneratedLog.objects.create(
                project_id=project_id,
                project_version_id=project_version_id,
                log_type=promptlayer_template_name,
                log_status='PROCESSING',
                log_table='',
            )
        except Exception as e:
            # Non-fatal; logging only
            print(f"Failed to create PROCESSING AiGeneratedLog: {str(e)}")

        requests.post(
            settings.GENERATE_LOG_LAMBDA_FUNCTION_URL,
            json={
                'project_id': project_id,
                'project_version_id': project_version_id,
                'log_type': promptlayer_template_name,
                'bucket': s3_bucket,
                'spec_sections': spec_sections,
                'callback_url': settings.BACKEND_AI_LOG_CALLBACK_URL,
                'ai_generated_log_id': str(processing_log.id) if processing_log else None,
                'promptlayer_system_prompt': system_prompt,
                'promptlayer_user_prompt': user_prompt,
                'promptlayer_model_metadata': promptlayer_model_metadata,
                'temperature': temperature,
                'top_p': top_p,
                'chunk_size': settings.OPENAI_MODEL_MAX_CONTEXT_SIZE,
            }
        )
        return processing_log


    def generate_inspection_log(self, project_id, project_version_id):
        processing_log = self.generate_general_log(
            project_id, 
            project_version_id, 
            settings.INSPECTION_LOG_PROMPTLAYER_PROMPT_NAME, 
            self.InspectionLog,
            self.InspectionLogRow
        )

        # save chat messages
        # Note: this has been removed now that we're doing this async and storing the logs in a separate model
        # human_chat_message = ChatMessage.objects.create(
        #     chat=chat,
        #     message="Generate inspection log",
        #     type=ChatMessage.ChatMessageType.SYSTEM,
        #     raw_message=self.create_raw_message("Generate inspection log", "human")
        # )
        # ai_chat_message = ChatMessage.objects.create(
        #     chat=chat,
        #     message=final_answer,
        #     type=ChatMessage.ChatMessageType.AI_INSPECTION_LOG,
        #     raw_message=self.create_raw_message(final_answer, "ai")
        # )

        return processing_log
    
    def generate_owner_deliverables_log(self, project_id, project_version_id):
        processing_log = self.generate_general_log(
            project_id, 
            project_version_id, 
            settings.OWNER_DELIVERABLES_PROMPTLAYER_PROMPT_NAME, 
            self.OwnerDeliverablesLog,
            self.OwnerDeliverablesRow
        )

        # # save chat messages
        # Note: this has been removed now that we're doing this async and storing the logs in a separate model
        # human_chat_message = ChatMessage.objects.create(
        #     chat=chat,
        #     message="Generate owner deliverables log",
        #     type=ChatMessage.ChatMessageType.SYSTEM,
        #     raw_message=self.create_raw_message("Generate owner deliverables log", "human")
        # )
        # ai_chat_message = ChatMessage.objects.create(
        #     chat=chat,
        #     message=final_answer,
        #     type=ChatMessage.ChatMessageType.AI_OWNER_DELIVERABLES_LOG,
        #     raw_message=self.create_raw_message(final_answer, "ai")
        # )

        return processing_log

    @action(detail=False, methods=['post'], url_path='generate-ai-log')
    def generate_ai_log(self, request, project_id=None):
        print("Generate AI log")
        print(request.data)
        project_id = request.data.get('project_id', None)
        project_version_id = request.data.get('project_version_id', None)
        log_type = request.data.get('log_type', None)
        if not project_id:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'error': 'Project ID is required'
            })
        if not project_version_id:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'error': 'Project version ID is required'
            })
        if not log_type:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'error': 'Log type is required'
            })
        
        processing_log_object = None
        if log_type == 'inspection_log':
            processing_log_object = self.generate_inspection_log(project_id, project_version_id)
        elif log_type == 'owner_deliverables_log':
            processing_log_object = self.generate_owner_deliverables_log(project_id, project_version_id)
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'error': 'Invalid log type'
            })
        serializer = AiGeneratedLogSerializer(processing_log_object)
        return Response(status=status.HTTP_200_OK, data=serializer.data)


    @action(detail=False, methods=['post'], url_path='generate-response')
    def generate_response(self, request, project_id=None):
        print("Generate response")
        print(request.data)
        chat_id = request.data.get('chat_id', None)
        project_version_id = request.data.get('project_version_id', None)
        if not project_version_id:
            project_version = ProjectVersion.objects.filter(project_id=project_id).order_by('-created_at').first()
            if not project_version:
                return Response(status=status.HTTP_404_NOT_FOUND, data={
                    'error': 'No project version found'
                })
            project_version_id = project_version.id
        else:
            project_version = ProjectVersion.objects.get(id=project_version_id)
            if project_version.project.id != project_id:
                return Response(status=status.HTTP_400_BAD_REQUEST, data={
                    'error': 'Project version does not match project'
                })

        if not chat_id:
            chat = Chat.objects.create(
                user=request.user,
                project=Project.objects.get(id=project_id),
                project_version=project_version
            )
        else:
            chat = Chat.objects.get(id=chat_id)
            if not chat:
                return Response(status=status.HTTP_404_NOT_FOUND, data={
                    'error': 'No chat found'
                })
            if chat.project_version.id != project_version_id:
                return Response(status=status.HTTP_400_BAD_REQUEST, data={
                    'error': 'Chat project version does not match project version'
                })
            if chat.project.id != project_id:
                return Response(status=status.HTTP_400_BAD_REQUEST, data={
                    'error': 'Chat project does not match project'
                })
            if chat.user != request.user:
                return Response(status=status.HTTP_403_FORBIDDEN, data={
                    'error': 'Unauthorized'
                })
            print(f"AI messages count: {chat.messages.filter(type=ChatMessage.ChatMessageType.AI).count()}")
            if chat.messages.filter(type=ChatMessage.ChatMessageType.AI).count() >= settings.MAX_CHAT_MESSAGES:
                return Response(status=status.HTTP_200_OK, data={
                    'error': 'Chat has reached the maximum number of messages',
                    'max_chat_messages': settings.MAX_CHAT_MESSAGES
                })

        user_input = request.data.get('user_input', '')
        response_type = request.data.get('response_type', self.RESPONSE_TYPES.STANDARD)
        try:
            num_documents_to_return = int(request.data.get('k', 10))
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'error': 'Invalid value for k'
            })

        if response_type == self.RESPONSE_TYPES.STANDARD:
            answer, message_sources = self.generate_standard_chat_response(chat, project_id, project_version_id, request.user.email, user_input, num_documents_to_return)
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'error': 'Invalid response type'
            })

        return Response(status=status.HTTP_200_OK, data={
            'chat_id': chat.id,
            'answer': answer,
            'question': user_input,
            'sources': message_sources,
            'max_chat_messages': settings.MAX_CHAT_MESSAGES
        })
    

        
    @action(detail=False, methods=['get'], url_path='generate-presigned-url')
    def generate_presigned_url(self, request, project_id=None):
        print("Generate presigned url")
        print(request.query_params)
        s3_key = request.query_params.get('s3_key', None)
        s3_bucket = request.query_params.get('s3_bucket', None)
        if not s3_key:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'error': 'S3 key is required'
            })
        if not s3_bucket:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'error': 'S3 bucket is required'
            })
        s3 = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        presigned_url = s3.generate_presigned_url(
            'get_object', 
            Params={'Bucket': s3_bucket, 'Key': s3_key}, 
            ExpiresIn=3600
        )
        return Response(status=status.HTTP_200_OK, data={
            'url': presigned_url
        })
        
    @action(detail=False, methods=['post'], url_path='extract-tables-to-csv')
    def extract_tables_to_csv(self, request, project_id=None):
        """
        Extract markdown tables from AI response text and convert to Excel format.
        
        Expected payload:
        {
            "text": "AI response containing markdown tables...",
            "extract_all": true  // if false, only extract first table
        }
        """
        text = request.data.get('text', '')
        extract_all = request.data.get('extract_all', True)
        
        if not text:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'error': 'Text content is required'
            })
        
        try:
            if extract_all:
                csv_tables = extract_and_convert_tables_to_csv(text)
                print("CSV TABLES")
                print(csv_tables)
                if not csv_tables:
                    return Response(status=status.HTTP_422_UNPROCESSABLE_ENTITY, data={
                        'error': 'No tables found'
                    })
                
                # Create Excel workbook with single worksheet
                workbook = Workbook()
                worksheet = workbook.active
                worksheet.title = "Table"
                
                # Combine all tables into one large table
                all_rows = []
                headers = None
                
                for csv_content in csv_tables:
                    csv_lines = csv_content.strip().split('\n')
                    if not csv_lines:
                        continue
                    
                    # Parse CSV content
                    parsed_rows = []
                    for line in csv_lines:
                        csv_reader = csv.reader([line])
                        parsed_rows.append(next(csv_reader))
                    
                    if not parsed_rows:
                        continue
                    
                    # Set headers from first table
                    if headers is None:
                        headers = parsed_rows[0]
                        all_rows.append(headers)  # Add header row
                    
                    # Verify headers match (they should be the same)
                    if parsed_rows[0] == headers:
                        # Add data rows (skip header row)
                        all_rows.extend(parsed_rows[1:])
                    else:
                        # If headers don't match, still add but log warning
                        print(f"Warning: Table headers don't match. Expected: {headers}, Got: {parsed_rows[0]}")
                        if headers is None:
                            headers = parsed_rows[0]
                            all_rows.append(headers)
                        all_rows.extend(parsed_rows[1:])
                
                # Write all rows to worksheet
                for row_idx, row_data in enumerate(all_rows, 1):
                    for col_idx, cell_value in enumerate(row_data, 1):
                        worksheet.cell(row=row_idx, column=col_idx, value=cell_value)
                
                # Style the header row
                if all_rows:
                    header_font = Font(bold=True, color='FFFFFF')
                    header_fill = PatternFill(start_color='202a44', end_color='202a44', fill_type='solid')
                    header_alignment = Alignment(wrap_text=True, vertical='center')
                    
                    # Style the first row (headers)
                    for col in range(1, len(headers) + 1):
                        cell = worksheet.cell(row=1, column=col)
                        cell.font = header_font
                        cell.fill = header_fill
                        cell.alignment = header_alignment
                
                # Auto-adjust column widths
                for col_num, col in enumerate(worksheet.columns, 1):
                    max_length = 0
                    column = get_column_letter(col_num)
                    for cell in col:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)  # Cap at 50 characters
                    worksheet.column_dimensions[column].width = adjusted_width
                
                # Create response with Excel content type
                response = HttpResponse(
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                response['Content-Disposition'] = 'attachment; filename=inspection_log.xlsx'
                
                # Save workbook to response
                workbook.save(response)
                return response
                
            else:
                csv_content = extract_first_table_to_csv(text)
                if csv_content is None:
                    return Response(status=status.HTTP_422_UNPROCESSABLE_ENTITY, data={
                        'error': 'No markdown tables found in the text'
                    })
                
                # Create Excel workbook for single table
                workbook = Workbook()
                worksheet = workbook.active
                worksheet.title = "Inspection Log"
                
                # Parse CSV content and add to worksheet
                csv_lines = csv_content.strip().split('\n')
                for row_idx, line in enumerate(csv_lines, 1):
                    # Use proper CSV parsing to handle quoted values
                    csv_reader = csv.reader([line])
                    cells = next(csv_reader)
                    for col_idx, cell_value in enumerate(cells, 1):
                        worksheet.cell(row=row_idx, column=col_idx, value=cell_value)
                
                # Style the header row
                if csv_lines:
                    header_font = Font(bold=True, color='FFFFFF')
                    header_fill = PatternFill(start_color='202a44', end_color='202a44', fill_type='solid')
                    header_alignment = Alignment(wrap_text=True, vertical='center')
                    
                    # Parse first line to get column count
                    csv_reader = csv.reader([csv_lines[0]])
                    header_cells = next(csv_reader)
                    
                    for col in range(1, len(header_cells) + 1):
                        cell = worksheet.cell(row=1, column=col)
                        cell.font = header_font
                        cell.fill = header_fill
                        cell.alignment = header_alignment
                
                # Auto-adjust column widths
                for col_num, col in enumerate(worksheet.columns, 1):
                    max_length = 0
                    column = get_column_letter(col_num)
                    for cell in col:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)  # Cap at 50 characters
                    worksheet.column_dimensions[column].width = adjusted_width
                
                # Create response with Excel content type
                response = HttpResponse(
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                response['Content-Disposition'] = 'attachment; filename=inspection_log.xlsx'
                
                # Save workbook to response
                workbook.save(response)
                return response
                
        except Exception as e:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={
                'error': f'Failed to extract tables: {str(e)}'
            })
        
        