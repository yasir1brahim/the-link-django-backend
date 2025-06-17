import datetime
from uuid import UUID
from typing import Any, List, Optional
import boto3
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.decorators import action
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
        uploaded_file.specgpt_processing_status = UploadedFile.SpecgptProcessingStatusChoices.PROCESSING
        uploaded_file.save()
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
    if document.processing_status in [DocProcessingStatus.SUBSECTIONS_EXTRACTED, DocProcessingStatus.SECTION_PROCESSING_FAILED]:
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

    def get_promptlayer_template(self):
        template_manager = TemplateManager(api_key=settings.PROMPTLAYER_API_KEY)
        return template_manager.get(settings.PROMPTLAYER_PROMPT_NAME, {'label': settings.ENVIRONMENT})

    def get_promptlayer_model_metadata(self, promptlayer_template):
        return promptlayer_template['metadata']['model']
    
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
            promptlayer_template = self.get_promptlayer_template()
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
            'userid': {"$eq": str(request.user.id)},
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
        
        