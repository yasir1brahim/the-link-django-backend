import datetime
import json
import csv
from uuid import UUID
from typing import Any, List, Optional
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
from langchain_openai import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain
from langchain_community.callbacks.promptlayer_callback import PromptLayerCallbackHandler
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

from apps.deliverables.serializers.specgpt import ChatDetailSerializer
from apps.deliverables.permissions import ChatAccessPermissions
from apps.deliverables.models import Project, ProjectVersion
from typing import TypedDict, List

from apps.deliverables.models import (
    UploadedFile, MasterFormatSection, 
    SpecSection, DocProcessingStatus, 
    Chat, ChatMessage, 
    CustomPostgresChatMessageHistory
)

from langchain.memory import ConversationBufferMemory
from apps.deliverables.utils import extract_and_convert_tables_to_csv, extract_first_table_to_csv


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
        preferred_separator: str = f'\n\n{"-"*100}\n'
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
    
    # Split by separator to maintain some structure
    pieces = file_content.split(preferred_separator)
    
    for piece in pieces:
        piece_tokens = count_tokens(piece, model)
        
        if current_tokens + piece_tokens > max_tokens_per_chunk:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = piece
                current_tokens = piece_tokens
            else:
                # Single line is too long, split it further
                lines = piece.split("\n")
                for line in lines:
                    line_tokens = count_tokens(line + '\n', model)
                    if current_tokens + line_tokens > max_tokens_per_chunk:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                            current_chunk = line + '\n'
                            current_tokens = line_tokens
                        else:
                            # Single line is too long, truncate
                            chunks.append(line[:max_tokens_per_chunk//4] + "...")
                            current_chunk = ""
                            current_tokens = 0
                    else:
                        current_chunk += line + '\n'
                        current_tokens += line_tokens
        else:
            current_chunk += preferred_separator + piece
            current_tokens += piece_tokens
    
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
            first_human_message = chat.messages.filter(type=ChatMessage.ChatMessageType.HUMAN).order_by('created_at').first()
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

        user_input = request.data.get('user_input', '')
        try:
            num_documents_to_return = int(request.data.get('k', 10))
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'error': 'Invalid value for k'
            })

        try:
            promptlayer_template = self.get_promptlayer_template(settings.SPEC_GPT_PROMPTLAYER_PROMPT_NAME)
        except Exception as e:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={
                'error': f'Failed to retrieve PromptLayer template: {str(e)}'
            })

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
                            f"user: {request.user.email}",
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
        chat_message.sources = [
            {'metadata': x.metadata, 'page_content': x.page_content}
            for x in source_documents
        ]
        chat_message.save()
        message_sources = self._build_message_sources(source_documents)

        return Response(status=status.HTTP_200_OK, data={
            'chat_id': chat.id,
            'answer': results['answer'],
            'question': user_input,
            'sources': message_sources
        })
    
    @action(detail=False, methods=['post'], url_path='generate-inspection-log')
    def generate_inspection_log(self, request, project_id=None):
        print("Generate inspection log")
        print(request.data)
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
        
        
        try:
            promptlayer_template = self.get_promptlayer_template(settings.INSPECTION_LOG_PROMPTLAYER_PROMPT_NAME)
        except Exception as e:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={
                'error': f'Failed to retrieve PromptLayer template: {str(e)}'
            })

        system_prompt = self.get_promptlayer_system_prompt(promptlayer_template)
        user_prompt = self.get_promptlayer_user_prompt(promptlayer_template)
        developer_prompt_to_rejoin_separate_logs = self.get_promptlayer_developer_prompt(promptlayer_template)
        promptlayer_model_metadata = self.get_promptlayer_model_metadata(promptlayer_template)

        project_version_files = UploadedFile.objects.filter(project_version=project_version)
        file_content = ""
        for file in project_version_files:
            try:
                # Get the file content from S3
                s3_client = boto3.client('s3')
                response = s3_client.get_object(
                    Bucket=settings.S3_BUCKET,
                    Key=file.document_path
                )
                
                # Read the PDF content
                pdf_bytes = response['Body'].read()
                
                # Extract text from PDF using PyMuPDF
                pdf_document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
                pdf_text = ""
                for page_num in range(pdf_document.page_count):
                    page = pdf_document[page_num]
                    pdf_text += page.get_text() + "\n"
                pdf_document.close()
                
                file_content += f"\n\n{'-'*100}\n"
                file_content += pdf_text
                
            except Exception as e:
                print(f"Error reading file {file.name}: {str(e)}")
                file_content += f"\n\n{'-'*100}\n"

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Check if content is too large for a single request
        model_name = promptlayer_model_metadata['name']
        full_user_prompt = user_prompt.format(file_content=file_content)
        total_tokens = count_tokens(system_prompt + full_user_prompt, model_name)
        
        if total_tokens > settings.OPENAI_MODEL_MAX_CONTEXT_SIZE:
            # Split content into chunks
            print(f"Content too large ({total_tokens} tokens), splitting into chunks...")
            chunks = split_file_content_into_chunks(
                file_content, 
                settings.OPENAI_MODEL_MAX_CONTEXT_SIZE,
                model_name,
                preferred_separator="\n\n"
            )
            
            chunk_results = []
            for i, chunk in enumerate(chunks):
                chunk_user_prompt = user_prompt.format(file_content=chunk)
                chunk_completion = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": system_prompt
                        },
                        {
                            "role": "user",
                            "content": chunk_user_prompt
                        }
                    ]
                )
                chunk_results.append(chunk_completion.choices[0].message.content)
            
            # Stitch results together
            print("Separate agent responses")
            print(chunk_results)
            print("Rejoin prompt")
            print(developer_prompt_to_rejoin_separate_logs)
            rejoin_prompt = developer_prompt_to_rejoin_separate_logs.format(separate_agent_responses="\n\n".join(chunk_results))
            rejoin_completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": rejoin_prompt
                    }
                ]
            )
            final_answer = rejoin_completion.choices[0].message.content
        else:
            # Process normally with single request
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": full_user_prompt
                    }
                ]
            )
            final_answer = completion.choices[0].message.content

        return Response(status=status.HTTP_200_OK, data={
            'answer': final_answer,
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
                if not csv_tables:
                    return Response(status=status.HTTP_404_NOT_FOUND, data={
                        'error': 'No markdown tables found in the text'
                    })
                
                # Create Excel workbook
                workbook = Workbook()
                
                # Remove default sheet
                workbook.remove(workbook.active)
                
                # Add each table as a separate worksheet
                for i, csv_content in enumerate(csv_tables, 1):
                    worksheet = workbook.create_sheet(title=f"Table_{i}")
                    
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
                
            else:
                csv_content = extract_first_table_to_csv(text)
                if csv_content is None:
                    return Response(status=status.HTTP_404_NOT_FOUND, data={
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
        
        