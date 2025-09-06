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
from rest_framework.pagination import PageNumberPagination
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
from apps.utils.feature_flags import is_inspection_log_use_data_tables_feature_flag_active


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
    table: str | Optional[List[dict]] # markdown table or structured data from Lambda


def _process_log_data(log_data, log_type, markdown_table):
    """
    Helper function to process log data and convert structured data to markdown.
    
    Args:
        log_data: Structured data list or None
        log_type: Type of log ('inspection_log' or 'owner_deliverables_log')
        markdown_table: Fallback markdown string
    
    Returns:
        tuple: (processed_log_data, processed_markdown_table)
    """
    if log_data is not None:
        # Structured data received
        print(f"Processing structured data: {len(log_data)} items")
        
        # Convert structured data to markdown for fallback
        try:
            if log_data and len(log_data) > 0:
                # Determine the appropriate model class based on log_type
                if log_type == 'inspection_log':
                    # Access InspectionLogRow from ChatViewSet
                    viewset = ChatViewSet()
                    model_class = viewset.InspectionLogRow
                elif log_type == 'owner_deliverables_log':
                    # Access OwnerDeliverablesRow from ChatViewSet
                    viewset = ChatViewSet()
                    model_class = viewset.OwnerDeliverablesRow
                else:
                    model_class = None
                
                if model_class:
                    markdown_from_data = convert_to_markdown_table(log_data, model_class)
                    print(f"Converted structured data to markdown")
                    return log_data, markdown_from_data
                else:
                    # Fallback to empty string if model class not found
                    print(f"Model class not found for log_type: {log_type}")
                    return log_data, ''
            else:
                # Empty structured data
                print("Empty structured data received")
                return log_data, ''
        except Exception as e:
            print(f"Error converting structured data to markdown: {str(e)}")
            # Fallback to empty string
            return log_data, ''
    else:
        # Markdown data received
        print(f"Processing markdown data: {len(markdown_table)} characters")
        return None, markdown_table


def _handle_qa_planner_webhook(log_obj, qa_option, new_status, log_data, markdown_table):
    """Handle webhook response for QA planner logs with merging logic."""
    
    # Update completion status for this QA option
    if log_obj.completion_status is None:
        log_obj.completion_status = {}
    
    log_obj.completion_status[qa_option] = new_status
    
    # Add item_type to each data entry if we have structured data
    if log_data and isinstance(log_data, list):
        # Tag each item with the QA option type
        for item in log_data:
            if isinstance(item, dict):
                item['item_type'] = qa_option
        
        # Merge with existing log_data
        if log_obj.log_data is None:
            log_obj.log_data = []
        
        log_obj.log_data.extend(log_data)
        
        # Sort all log_data by spec_section_number (simple string sort works due to leading zeros)
        log_obj.log_data.sort(key=lambda item: item.get('spec_section_number', ''))
        print(f"Merged and sorted {len(log_data)} items for QA option '{qa_option}' into log {log_obj.id}")
    
    # Merge markdown table data
    if markdown_table:
        if log_obj.log_table:
            log_obj.log_table += f"\n\n## {qa_option.replace('_', ' ').title()}\n\n{markdown_table}"
        else:
            log_obj.log_table = f"## {qa_option.replace('_', ' ').title()}\n\n{markdown_table}"
    
    # Check if all QA options are complete
    selected_options = log_obj.qa_options_selected or []
    completed_options = list(log_obj.completion_status.keys())
    all_complete = all(option in completed_options for option in selected_options)
    
    if all_complete:
        # Determine overall status
        all_statuses = list(log_obj.completion_status.values())
        success_count = all_statuses.count('SUCCESS')
        failure_count = all_statuses.count('FAILURE')
        
        if failure_count == 0:
            log_obj.log_status = 'SUCCESS'
        elif success_count == 0:
            log_obj.log_status = 'FAILURE'
        else:
            log_obj.log_status = 'PARTIAL_SUCCESS'
        
        print(f"QA planner log {log_obj.id} completed with status: {log_obj.log_status}")
        print(f"Individual statuses: {log_obj.completion_status}")
    
    log_obj.save()


@api_view(['POST'])
@permission_classes([AllowAny])
def ai_log_generation_webhook(request):
    request_payload = request.data
    print(f"AI LOG GENERATION WEBHOOK received request: {request_payload}")

    request_data = AiLogGenerationRequest(**request_payload)

    new_status = request_data['new_status']
    ai_generated_log_id = request_payload.get('ai_generated_log_id') or request_data.get('ai_generated_log_id')
    # Extract QA option from log_type if it's a QA planner log
    qa_option = None
    log_type = request_data['log_type']
    if log_type.startswith('qa_planner__'):
        qa_option = log_type.split('qa_planner__')[1]

    if new_status in ['SUCCESS', 'FAILURE']:
        # Prefer updating by explicit log id if provided
        log_obj = None
        
        # Handle data from Lambda (could be markdown string or structured data)
        table_data = request_data.get('table', '')
        
        # Determine if we have structured data or markdown
        log_data = None
        markdown_table = ''
        
        if isinstance(table_data, list):
            # Structured data received
            log_data = table_data
            print(f"Received structured data: {len(log_data)} items")
        else:
            # Markdown string received
            markdown_table = table_data.decode("utf-8", errors="replace").replace("\x00", "\uFFFD") if isinstance(table_data, bytes) else str(table_data)
            print(f"Received markdown data: {len(markdown_table)} characters")
        
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
            # Handle QA planner logs differently (they need merging)
            if log_obj.log_type == 'qa_planner' and qa_option:
                _handle_qa_planner_webhook(log_obj, qa_option, new_status, log_data, markdown_table)
            else:
                # Handle regular logs (inspection, owner_deliverables)
                log_obj.log_status = new_status
                
                # Process log data using helper function
                processed_log_data, processed_markdown = _process_log_data(log_data, request_data['log_type'], markdown_table)
                
                # Store processed data
                if processed_log_data is not None:
                    log_obj.log_data = processed_log_data
                    print(f"Stored structured data for log {log_obj.id}: {len(processed_log_data)} items")
                log_obj.log_table = processed_markdown
                
                log_obj.save()
        else:
            # Create new log entry
            log_entry_data = {
                'project_id': request_data['project_id'],
                'project_version_id': request_data['project_version_id'],
                'log_type': request_data['log_type'],
                'log_status': new_status,
            }
            
            # Process log data using helper function
            processed_log_data, processed_markdown = _process_log_data(log_data, request_data['log_type'], markdown_table)
            
            # Add processed data to log entry
            if processed_log_data is not None:
                log_entry_data['log_data'] = processed_log_data
                print(f"Created new log with structured data: {len(processed_log_data)} items")
            log_entry_data['log_table'] = processed_markdown
            
            AiGeneratedLog.objects.create(**log_entry_data)
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
    pagination_class = PageNumberPagination
    page_size = 50  # Default page size for structured data

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
        
        # Set team context from project for feature flag evaluation
        try:
            project = Project.objects.get(id=project_id)
            self.request.team = project.team
        except Project.DoesNotExist:
            pass
        
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
        
        # Apply sorting
        queryset = self.apply_sorting(queryset)
        
        return queryset
    
    def apply_sorting(self, queryset):
        """
        Apply sorting to the queryset based on query parameters.
        For structured data, sorting is done in Python after retrieval.
        """
        # Get sorting parameters
        order_by = self.request.query_params.get('order_by', 'created_at')
        order_direction = self.request.query_params.get('order', 'desc')
        
        # Validate sorting parameters
        valid_sort_fields = self.get_valid_sort_fields()
        if order_by not in valid_sort_fields:
            order_by = 'created_at'  # Default
        
        # Apply database sorting for non-structured fields
        if order_by == 'created_at':
            if order_direction == 'desc':
                return queryset.order_by('-created_at')
            else:
                return queryset.order_by('created_at')
        
        # For structured data fields, we'll sort in Python after retrieval
        # Store sorting info in request for use in serializer
        self.request.sort_field = order_by
        self.request.sort_direction = order_direction
        
        # Default to created_at desc for database query
        return queryset.order_by('-created_at')
    
    @action(detail=True, methods=['get'])
    def filter_values(self, request, pk=None, project_id=None):
        """
        Get all available filter values for filterable columns in the log data.
        """
        try:
            # Get the log object directly without going through get_queryset 
            # to avoid project_id validation for this specific action
            log_obj = AiGeneratedLog.objects.get(id=pk)
            
            if not log_obj.log_data:
                return Response({'filter_values': {}})
            
            # Get filterable columns based on log type
            filterable_columns = self.get_filterable_columns(log_obj.log_type)
            
            filter_values = {}
            
            for column_key in filterable_columns:
                # Extract unique values for this column
                values = set()
                for item in log_obj.log_data:
                    value = item.get(column_key)
                    if value is not None and value != '':
                        values.add(str(value))
                
                # Sort the values
                filter_values[column_key] = sorted(list(values))
            
            return Response({'filter_values': filter_values})
            
        except AiGeneratedLog.DoesNotExist:
            return Response(
                {'error': 'Log not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Error fetching filter values: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def get_filterable_columns(self, log_type):
        """
        Get filterable column names based on log type.
        """
        if log_type == 'qa_planner':
            return ['Spec Section #', 'item_type', 'Responsible Party']
        elif log_type == 'inspection_log':
            return ['Spec Section #', 'Responsible Party']
        elif log_type == 'owner_deliverables_log':
            return ['Spec Section #', 'Responsible Party', 'Deliverable Type']
        else:
            return []

    def get_valid_sort_fields(self):
        """
        Get valid sort fields based on log type.
        """
        # Get log_type from the URL path (log_id)
        log_id = self.kwargs.get('pk')
        log_type = None
        
        if log_id:
            try:
                log_obj = AiGeneratedLog.objects.get(id=log_id)
                log_type = log_obj.log_type
            except AiGeneratedLog.DoesNotExist:
                pass
        
        if log_type == 'inspection_log':
            return [
                'created_at', 'spec_section_number', 'spec_section_name',
                'inspection_type_and_requirements', 'inspection_frequency', 'responsible_party'
            ]
        elif log_type == 'owner_deliverables_log':
            return [
                'created_at', 'spec_section_number', 'spec_section_name',
                'deliverable_type', 'when_due', 'responsible_party', 'exact_requirement_text'
            ]
        elif log_type == 'qa_planner':
            return [
                'created_at', 'spec_section_number', 'spec_section_name',
                'paragraph_number', 'item_type', 'requirement_text', 'responsible_party', 'when_due'
            ]
        else:
            return ['created_at']  # Default

    @action(detail=True, methods=['get'])
    def export(self, request, pk=None, project_id=None):
        """
        Export AI generated log data to Excel with optional filters, search, and sorting.
        """
        try:
            # Get the log object
            log_obj = AiGeneratedLog.objects.get(id=pk)
            
            if not log_obj.log_data:
                return Response(
                    {'error': 'No data available for export'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get filter, search, and sort parameters
            filter_params = {}
            for param_name, values in request.query_params.items():
                if param_name.startswith('filter_'):
                    # Extract column name from parameter
                    raw_key = param_name.replace('filter_', '')
                    column_key = ' '.join(part for part in raw_key.split('_') if part).title()
                    
                    # Map to actual column names
                    if column_key == 'Spec Section':
                        column_key = 'Spec Section #'
                    elif column_key == 'Item Type':
                        column_key = 'item_type'
                    elif column_key == 'Responsible Party':
                        column_key = 'Responsible Party'
                    
                    filter_params[column_key] = values.split(',')
            
            search_term = request.query_params.get('search', '')
            order_by = request.query_params.get('order_by', 'created_at')
            order_direction = request.query_params.get('order', 'desc')
            
            # Use the serializer to process the data with filters, search, and sorting
            serializer = AiGeneratedLogSerializer(log_obj, context={'request': request})
            
            # Apply filters, search, and sorting
            filtered_data = log_obj.log_data
            
            if filter_params:
                filtered_data = serializer.filter_structured_data(filtered_data, filter_params)
            
            if search_term:
                filtered_data = serializer.search_structured_data(filtered_data, search_term)
            
            if order_by != 'created_at':
                filtered_data = serializer.sort_structured_data(filtered_data, order_by, order_direction)
            
            if not filtered_data:
                return Response(
                    {'error': 'No data matches the specified filters'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create Excel workbook
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.title = f"{log_obj.log_type.replace('_', ' ').title()} Export"
            
            # Define styles
            header_font = Font(bold=True, color='FFFFFF')
            header_fill = PatternFill(start_color='202a44', end_color='202a44', fill_type='solid')
            header_alignment = Alignment(wrap_text=True, vertical='center')
            text_alignment = Alignment(wrap_text=True, vertical='center')
            
            # Get headers from first row
            headers = list(filtered_data[0].keys()) if filtered_data else []
            
            # Write headers
            for col_idx, header in enumerate(headers, 1):
                cell = worksheet.cell(row=1, column=col_idx, value=header)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_alignment
            
            # Write data rows
            for row_idx, item in enumerate(filtered_data, 2):
                for col_idx, header in enumerate(headers, 1):
                    value = item.get(header, '')
                    cell = worksheet.cell(row=row_idx, column=col_idx, value=value)
                    cell.alignment = text_alignment
            
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
            
            # Create response
            response = HttpResponse(
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            log_type_display = log_obj.log_type.replace('_', ' ').title()
            response['Content-Disposition'] = f'attachment; filename={log_type_display}_Export.xlsx'
            
            # Save workbook to response
            workbook.save(response)
            return response
            
        except AiGeneratedLog.DoesNotExist:
            return Response(
                {'error': 'Log not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Error exporting data: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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
        results: List['ChatViewSet.InspectionLogRow'] = Field(description="List of inspection log rows")

    class OwnerDeliverablesRow(BaseModel):
        spec_section_number: str = Field(alias="Spec Section #", description="The section this item was found in")
        spec_section_name: str = Field(alias="Spec Section Name", description="The name of the section")
        deliverable_type: str = Field(alias="Deliverable Type", description="The type of deliverable")
        when_due: str = Field(alias="When Due", description="The date the deliverable is due")
        responsible_party: str = Field(alias="Responsible Party", description="The responsible party for the deliverable")
        exact_requirement_text: str = Field(alias="Exact Requirement Text", description="The exact requirement text")

    class OwnerDeliverablesLog(BaseModel):
        results: List['ChatViewSet.OwnerDeliverablesRow'] = Field(description="List of owner deliverables rows")

    def generate_general_log(self, project_id, project_version_id, promptlayer_template_name, full_log_model, log_row_model, request=None):
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

        # Check if the inspection_log_use_data_tables feature flag is active
        use_data_tables = False
        if request and hasattr(request, 'user'):
            try:
                project = Project.objects.get(id=project_id)
                team = project.team
                user = request.user
                use_data_tables = is_inspection_log_use_data_tables_feature_flag_active(user, team, project)
                print(f"Feature flag check - use_data_tables: {use_data_tables}")
            except Exception as e:
                print(f"Error checking feature flag: {str(e)}")
                use_data_tables = False

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
                'use_data_tables': use_data_tables,
            }
        )
        return processing_log


    def generate_inspection_log(self, project_id, project_version_id, request=None):
        processing_log = self.generate_general_log(
            project_id, 
            project_version_id, 
            settings.INSPECTION_LOG_PROMPTLAYER_PROMPT_NAME, 
            ChatViewSet.InspectionLog,
            ChatViewSet.InspectionLogRow,
            request
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
    
    def generate_owner_deliverables_log(self, project_id, project_version_id, request=None):
        processing_log = self.generate_general_log(
            project_id, 
            project_version_id, 
            settings.OWNER_DELIVERABLES_PROMPTLAYER_PROMPT_NAME, 
            ChatViewSet.OwnerDeliverablesLog,
            ChatViewSet.OwnerDeliverablesRow,
            request
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

    def generate_qa_planner_log(self, project_id, project_version_id, selected_options, request=None):
        """Generate QA planner log by processing multiple QA options."""
        
        # QA option to PromptLayer template mapping
        QA_OPTION_PROMPTS = {
            'inspections': 'qa_planner__inspections',
            'mock_ups_sample_construction': 'qa_planner__mock_ups_sample_construction', 
            'pre_installation_meetings': 'qa_planner__pre_installation_meetings',
            'warranties': 'qa_planner__warranties',
            'certificates': 'qa_planner__certificates',
            'closeout_submittals': 'qa_planner__closeout_submittals',
            'test_reports': 'qa_planner__test_reports',
            'commissioning': 'qa_planner__commissioning',
            'delegated_design': 'qa_planner__delegated_design'
        }
        
        # Generate log types for lambda calls
        def get_qa_log_type(qa_option):
            return f"qa_planner__{qa_option}"
        
        # Validate selected options
        invalid_options = [opt for opt in selected_options if opt not in QA_OPTION_PROMPTS]
        if invalid_options:
            raise ValueError(f"Invalid QA options: {invalid_options}")
        
        # Create initial processing log
        processing_log = None
        try:
            processing_log = AiGeneratedLog.objects.create(
                project_id=project_id,
                project_version_id=project_version_id,
                log_type='qa_planner',
                log_status='PROCESSING',
                log_table='',
                qa_options_selected=selected_options,
                completion_status={option: 'PENDING' for option in selected_options}
            )
        except Exception as e:
            print(f"Failed to create PROCESSING AiGeneratedLog for QA planner: {str(e)}")
            raise e
        
        # Get common data for all lambda calls
        project_version_files = UploadedFile.objects.filter(project_version_id=project_version_id).order_by('id')
        project_version_specs = SpecSection.objects.filter(document__in=project_version_files).order_by('id')
        spec_sections = [{
            'master_format_section_number': spec_section.masterformat_section.masterformat_number,
            'file_s3_key': spec_section.file_s3_key
        } for spec_section in project_version_specs if spec_section.file_s3_key]
        s3_bucket = settings.S3_BUCKET
        
        # Check feature flag for data tables
        use_data_tables = False
        if request and hasattr(request, 'user'):
            try:
                project = Project.objects.get(id=project_id)
                team = project.team
                user = request.user
                use_data_tables = is_inspection_log_use_data_tables_feature_flag_active(user, team, project)
            except Exception as e:
                print(f"Error checking feature flag: {str(e)}")
                use_data_tables = False
        
        # Invoke lambda for each selected QA option
        for qa_option in selected_options:
            try:
                promptlayer_template_name = QA_OPTION_PROMPTS[qa_option]
                
                # Get prompt data for this QA option
                try:
                    promptlayer_template = self.get_promptlayer_template(promptlayer_template_name)
                except Exception as e:
                    print(f"Failed to retrieve PromptLayer template for {qa_option}: {str(e)}")
                    # Update completion status for this option to failed
                    processing_log.completion_status[qa_option] = 'FAILURE'
                    processing_log.save()
                    continue
                
                system_prompt = self.get_promptlayer_system_prompt(promptlayer_template)
                user_prompt = self.get_promptlayer_user_prompt(promptlayer_template)
                promptlayer_model_metadata = self.get_promptlayer_model_metadata(promptlayer_template)
                temperature = promptlayer_model_metadata['parameters'].get('temperature', 0.1)
                top_p = promptlayer_model_metadata['parameters'].get('top_p', 1)
                
                # Call lambda with QA-specific log type
                qa_log_type = get_qa_log_type(qa_option)
                requests.post(
                    settings.GENERATE_LOG_LAMBDA_FUNCTION_URL,
                    json={
                        'project_id': project_id,
                        'project_version_id': project_version_id,
                        'log_type': qa_log_type,  # Use qa_planner__[option] format
                        'bucket': s3_bucket,
                        'spec_sections': spec_sections,
                        'callback_url': settings.BACKEND_AI_LOG_CALLBACK_URL,
                        'ai_generated_log_id': str(processing_log.id),
                        'promptlayer_system_prompt': system_prompt,
                        'promptlayer_user_prompt': user_prompt,
                        'promptlayer_model_metadata': promptlayer_model_metadata,
                        'temperature': temperature,
                        'top_p': top_p,
                        'chunk_size': settings.OPENAI_MODEL_MAX_CONTEXT_SIZE,
                        'use_data_tables': use_data_tables,
                    }
                )
                print(f"Lambda invoked for QA option: {qa_option}")
                
            except Exception as e:
                print(f"Error invoking lambda for QA option {qa_option}: {str(e)}")
                # Update completion status for this option to failed
                processing_log.completion_status[qa_option] = 'FAILURE'
                processing_log.save()
        
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
            processing_log_object = self.generate_inspection_log(project_id, project_version_id, request)
        elif log_type == 'owner_deliverables_log':
            processing_log_object = self.generate_owner_deliverables_log(project_id, project_version_id, request)
        elif log_type == 'qa_planner':
            selected_options = request.data.get('selected_options', [])
            if not selected_options:
                return Response(status=status.HTTP_400_BAD_REQUEST, data={
                    'error': 'Selected options are required for QA planner'
                })
            processing_log_object = self.generate_qa_planner_log(project_id, project_version_id, selected_options, request)
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'error': 'Invalid log type'
            })
        serializer = AiGeneratedLogSerializer(processing_log_object)
        return Response(status=status.HTTP_200_OK, data=serializer.data)

    @action(detail=False, methods=['post'], url_path='generate-qa-planner-log')
    def generate_qa_planner_log_endpoint(self, request, project_id=None):
        """API endpoint specifically for QA planner log generation."""
        print("Generate QA Planner log")
        print(request.data)
        
        project_id = request.data.get('project_id', None)
        project_version_id = request.data.get('project_version_id', None)
        selected_options = request.data.get('selected_options', [])
        
        # Validation
        if not project_id:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'error': 'Project ID is required'
            })
        if not project_version_id:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'error': 'Project version ID is required'
            })
        if not selected_options or not isinstance(selected_options, list):
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'error': 'Selected options are required and must be a list'
            })
        
        try:
            processing_log_object = self.generate_qa_planner_log(
                project_id, project_version_id, selected_options, request
            )
            serializer = AiGeneratedLogSerializer(processing_log_object)
            return Response(status=status.HTTP_200_OK, data=serializer.data)
        except ValueError as e:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'error': str(e)
            })
        except Exception as e:
            print(f"Error generating QA planner log: {str(e)}")
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={
                'error': 'Internal server error while generating QA planner log'
            })

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
        
        