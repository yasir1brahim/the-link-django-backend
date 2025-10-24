import json
import asyncio
import re
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.conf import settings
from apps.deliverables.models import Project
from apps.utils.feature_flags import is_specgpt_websockets_feature_flag_active, is_langchain_update_feature_flag_active

# LangChain / LLM imports for streaming
from langchain_openai import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain.callbacks.base import AsyncCallbackHandler

# LangGraph imports for adaptive RAG
from langgraph.prebuilt import create_react_agent
from apps.deliverables.tools.adaptive_retrieval import create_retrieval_tool

# Models used for memory/history
from apps.deliverables.models import (
    Chat,
    CustomPostgresChatMessageHistory,
    ProjectVersion,
)

# Prompt templating helpers (reuse from view where possible)
from apps.deliverables.views.specgpt_views import ChatViewSet, CustomPromptLayerCallbackHandler


class SpecGptWebSocketConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Extract project_id from URL
        self.project_id = self.scope['url_route']['kwargs']['project_id']
        
        # Authenticate user via JWT token from query parameters
        self.user = await self.get_user_from_token()
        if not self.user or self.user.is_anonymous:
            await self.close()
            return
        
        # Check if the WebSocket feature flag is active for this user/team/project
        is_active = await self.check_feature_flag()
        if not is_active:
            await self.close()
            return
        
        # Join project-specific group
        self.room_group_name = f"specgpt_project_{self.project_id}"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'chat_message':
                await self.handle_chat_message(data)
            elif message_type == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
            else:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'data': {'error': 'Unknown message type'}
                }))
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'data': {'error': 'Invalid JSON format'}
            }))

    async def handle_chat_message(self, data):
        # Extract message data
        user_input = data.get('user_input', '')
        chat_id = data.get('chat_id')
        project_version_id = data.get('project_version_id')
        num_documents = data.get('k', 10)
        
        if not user_input:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'data': {'error': 'User input is required'}
            }))
            return
        
        # Start streaming response
        await self.stream_chat_response(user_input, chat_id, project_version_id, num_documents)

    async def stream_chat_response(self, user_input, chat_id, project_version_id, num_documents):
        # Send initial response
        await self.send(text_data=json.dumps({
            'type': 'response_start',
            'data': {'status': 'processing'}
        }))

        try:
            # Check if adaptive RAG is enabled
            use_adaptive_rag = await self.check_adaptive_rag_flag()
            
            if use_adaptive_rag:
                # Use adaptive RAG with LangGraph agent
                results = await self._run_adaptive_streaming_chain(user_input, chat_id, project_version_id, num_documents)
            else:
                # Use standard RAG with ConversationalRetrievalChain
                results = await self._run_streaming_chain(user_input, chat_id, project_version_id, num_documents)

            # Send completion signal
            await self.send(text_data=json.dumps({
                'type': 'response_complete',
                'data': {
                    'status': 'complete',
                    'sources': results.get('sources', []),
                    'chat_id': str(results.get('chat_id')) if results.get('chat_id') else None,
                }
            }))

        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'response_error',
                'data': {'error': str(e)}
            }))

    @database_sync_to_async
    def get_user_from_token(self):
        """Extract and validate JWT token from query parameters."""
        try:
            # Get token from query parameters
            query_string = self.scope.get('query_string', b'').decode()
            query_params = dict(item.split('=') for item in query_string.split('&') if '=' in item)
            token = query_params.get('token', '')
            
            if not token:
                return None
            
            # Validate JWT token
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            
            # Get user from database
            UserModel = get_user_model()
            return UserModel.objects.get(id=user_id)
            
        except (InvalidToken, TokenError, KeyError, ObjectDoesNotExist) as e:
            return None

    @database_sync_to_async
    def check_feature_flag(self):
        """Check if the WebSocket feature flag is active."""
        try:
            project = Project.objects.get(id=self.project_id)
            team = project.team
            return is_specgpt_websockets_feature_flag_active(self.user, team, project)
        except Project.DoesNotExist:
            return False
    
    @database_sync_to_async
    def check_adaptive_rag_flag(self):
        """Check if the adaptive RAG feature flag is active."""
        try:
            project = Project.objects.get(id=self.project_id)
            team = project.team
            return is_langchain_update_feature_flag_active(self.user, team, project)
        except Project.DoesNotExist:
            return False

    class _StreamingTokenHandler(AsyncCallbackHandler):
        def __init__(self, send_coroutine):
            self.send_coroutine = send_coroutine
            self._buffer = ""
            self._last_sent_len = 0
            self._tail_window = 800
        
        def _clean_tail(self, text: str) -> str:
            # Apply light-weight de-duplication on the tail of the buffer
            tail = text[-self._tail_window:]
            # Collapse immediate repeated words (case-insensitive)
            tail = re.sub(r"\b(\w{1,60})(\s+\1)+\b", r"\1", tail, flags=re.IGNORECASE)
            # Collapse subword stutter like "alal", "tt", limited to tail
            tail = re.sub(r"(\w{2,3})\1", r"\1", tail)
            # Collapse duplicate punctuation like ", ," or ".."
            tail = re.sub(r"([,.;:!?])\s*\1+", r"\1", tail)
            return text[:-min(len(text), self._tail_window)] + tail if len(text) > self._tail_window else tail
        
        async def on_llm_new_token(self, token: str, *args, **kwargs) -> None:
            if not token:
                return
            
            # Append token to buffer
            self._buffer += token
            
            # No need to clean the buffer - we'll let the frontend handle the display
            # Just send the new token directly
            await self.send_coroutine(json.dumps({
                'type': 'response_chunk',
                'data': {'content': token}
            }))
            
            # Update the last sent position
            self._last_sent_len = len(self._buffer)

        async def on_chat_model_start(self, *args, **kwargs):
            return None

    @database_sync_to_async
    def _prepare_chain_dependencies(self, user_input, chat_id, project_version_id, num_documents):
        """
        Prepare everything needed for the chain synchronously (DB access etc.).
        Returns a dict used by the async streaming runner.
        """
        # Validate or derive project_version
        if project_version_id:
            project_version = ProjectVersion.objects.get(id=project_version_id)
            if str(project_version.project.id) != str(self.project_id):
                raise ValueError('Project version does not match project')
        else:
            project_version = ProjectVersion.objects.filter(project_id=self.project_id).order_by('-created_at').first()
            if not project_version:
                raise ValueError('No project version found')
            project_version_id = project_version.id

        # Get or create chat
        if chat_id:
            chat = Chat.objects.get(id=chat_id)
        else:
            chat = Chat.objects.create(user=self.user, project_id=self.project_id, project_version_id=project_version_id)

        # Vector store and retriever
        vectorstore = PineconeVectorStore(
            index_name=settings.PINECONE_INDEX_NAME,
            embedding=OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY),
            namespace=str(self.project_id),
        )
        retriever = vectorstore.as_retriever(
            search_kwargs={
                'k': int(num_documents),
                'filter': {
                    'userid': {'$eq': str(self.user.id)},
                    'project_id': {'$eq': str(self.project_id)},
                    'project_version_id': {'$eq': str(project_version_id)},
                }
            }
        )

        # Chat memory backed by Postgres
        chat_history = CustomPostgresChatMessageHistory(chat)
        memory = ConversationBufferMemory(
            chat_memory=chat_history,
            memory_key='chat_history',
            input_key='question',
            output_key='answer',
            return_messages=True,
        )

        # PromptLayer template and prompt
        viewset = ChatViewSet()
        promptlayer_template = viewset.get_promptlayer_template(settings.SPEC_GPT_PROMPTLAYER_PROMPT_NAME)
        prompt = viewset.get_prompt(promptlayer_template)
        model_meta = viewset.get_promptlayer_model_metadata(promptlayer_template)

        # Return all
        return {
            'chat': chat,
            'project_version_id': project_version_id,
            'retriever': retriever,
            'memory': memory,
            'prompt': prompt,
            'model_meta': model_meta,
        }

    async def _run_streaming_chain(self, user_input, chat_id, project_version_id, num_documents):
        deps = await self._prepare_chain_dependencies(user_input, chat_id, project_version_id, num_documents)

        # Build a real context string up-front to satisfy PromptLayer and stabilize the model
        def _prefetch_context():
            docs = deps['retriever'].get_relevant_documents(user_input)
            parts = []
            for d in docs[: int(num_documents)]:
                text = d.page_content or ""
                meta = d.metadata or {}
                sn = meta.get('master_format_section_number') or meta.get('spec_section_number') or ''
                parts.append(f"[Section: {sn}]\n{text}")
            context_text = "\n\n".join(parts)
            return context_text

        context_text = await asyncio.get_event_loop().run_in_executor(None, _prefetch_context)

        # Streaming token handler that sends tokens incrementally
        token_handler = self._StreamingTokenHandler(self.send)

        # LLM with streaming and PromptLayer callback (use project-specific handler)
        callbacks = [
            CustomPromptLayerCallbackHandler(
                pl_tags=[
                    f"environment: {settings.ENVIRONMENT}",
                    "application: deliverables",
                    f"user: {self.user.email}",
                    f"prompt_name: {settings.SPEC_GPT_PROMPTLAYER_PROMPT_NAME}",
                    f"llm_model_name: {deps['model_meta']['name']}",
                    f"llm_temperature: {deps['model_meta']['parameters'].get('temperature', 0.1)}",
                ]
            ),
            token_handler,
        ]

        llm = ChatOpenAI(
            temperature=min(deps['model_meta']['parameters'].get('temperature', 0.1), 0.3),
            model_name=deps['model_meta']['name'],
            streaming=True,
            callbacks=callbacks,
        )

        # Build chain with explicit prompt that expects 'context' and 'question'
        chain = ConversationalRetrievalChain.from_llm(
            llm=llm,
            retriever=deps['retriever'],
            memory=deps['memory'],
            return_source_documents=True,
            combine_docs_chain_kwargs={"prompt": deps['prompt']},
            verbose=False,
        )

        # Ensure the input contains both 'question' and a resolved 'context'
        inputs = {'question': user_input, 'context': context_text}

        # Invoke chain (tokens stream via callback)
        results = await asyncio.get_event_loop().run_in_executor(None, lambda: chain(inputs))

        # Persist sources onto the last AI message for this chat
        source_documents = results.get('source_documents', [])
        message_sources = [
            {'metadata': x.metadata, 'page_content': x.page_content}
            for x in source_documents
        ]

        # Save sources to DB (attach to last AI message)
        await self._save_sources_to_last_ai_message(deps['memory'].chat_memory, message_sources)

        return {
            'answer': results.get('answer', ''),
            'sources': message_sources,
            'chat_id': deps['chat'].id,
        }

    @database_sync_to_async
    def _save_sources_to_last_ai_message(self, chat_memory, sources):
        try:
            chat_message = chat_memory.message_db_object
            chat_message.sources = sources
            chat_message.save()
        except Exception:
            pass
    
    async def _run_adaptive_streaming_chain(self, user_input, chat_id, project_version_id, num_documents):
        """Run adaptive RAG agent with streaming support.
        
        Uses LangGraph ReAct agent that decides dynamically whether to retrieve documents.
        Streams tokens in the same format as the standard chain for frontend compatibility.
        """
        deps = await self._prepare_chain_dependencies(user_input, chat_id, project_version_id, num_documents)
        
        # Get model metadata and prompt from PromptLayer
        viewset = ChatViewSet()
        promptlayer_template = viewset.get_promptlayer_template(settings.SPEC_GPT_PROMPTLAYER_PROMPT_NAME)
        model_meta = viewset.get_promptlayer_model_metadata(promptlayer_template)
        
        # Fetch the adaptive RAG system prompt from PromptLayer
        try:
            adaptive_rag_template = viewset.get_promptlayer_template(settings.SPEC_GPT_V2_PROMPTLAYER_PROMPT_NAME)
            agent_system_message = viewset.get_promptlayer_system_prompt(adaptive_rag_template)
        except Exception as e:
            print(f"Failed to retrieve PromptLayer template for adaptive RAG: {str(e)}")
            raise e
        
        # Create retrieval tool with project context
        # The tool returns both the tool itself and a list that will store retrieved documents
        retrieved_documents_store = []
        retrieval_tool, _ = create_retrieval_tool(
            vectorstore=deps['retriever'].vectorstore,  # Access vectorstore from retriever
            project_id=self.project_id,
            project_version_id=project_version_id,
            max_documents=int(num_documents),
            retrieved_documents_store=retrieved_documents_store
        )
        
        # Create streaming token handler
        token_handler = self._StreamingTokenHandler(self.send)
        
        # Initialize LLM with streaming
        llm = ChatOpenAI(
            temperature=min(model_meta['parameters'].get('temperature', 0.1), 0.3),
            model_name=model_meta['name'],
            streaming=True,
            callbacks=[
                CustomPromptLayerCallbackHandler(
                    pl_tags=[
                        f"environment: {settings.ENVIRONMENT}",
                        "application: deliverables",
                        f"user: {self.user.email}",
                        f"prompt_name: {adaptive_rag_template['prompt_name']}",
                        f"prompt_commit_message: {adaptive_rag_template['commit_message']}",
                        f"llm_model_name: {model_meta['name']}",
                        f"llm_temperature: {model_meta['parameters'].get('temperature', 0.1)}",
                        "rag_type: adaptive_streaming"
                    ]
                ),
                token_handler,
            ]
        )
        
        # Create the ReAct agent
        agent_executor = create_react_agent(
            llm,
            tools=[retrieval_tool],
            state_modifier=agent_system_message
        )
        
        # Get conversation history
        history_messages = deps['memory'].chat_memory.messages if hasattr(deps['memory'].chat_memory, 'messages') else []
        
        # Stream agent execution
        # LangGraph's astream_events allows us to capture streaming tokens and tool calls
        config = {"recursion_limit": 4}
        
        print(f"\n{'='*80}")
        print(f"🤖 ADAPTIVE RAG AGENT START (WebSocket)")
        print(f"{'='*80}")
        print(f"User query: '{user_input}'")
        print(f"Chat ID: {chat_id or 'NEW'}")
        print(f"Max iterations: 4")
        print(f"{'='*80}\n")
        
        try:
            # Stream agent execution events
            async for event in agent_executor.astream_events(
                {"messages": history_messages + [("user", user_input)]},
                config=config,
                version="v2"
            ):
                # The events include:
                # - on_chat_model_stream: streaming tokens from LLM
                # - on_tool_start: tool is being called
                # - on_tool_end: tool finished execution
                
                # Streaming tokens are handled by the callback handler
                # Tool calls automatically populate retrieved_documents_store
                pass
            
            # Get the final state to extract the answer
            final_state = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: agent_executor.invoke(
                    {"messages": history_messages + [("user", user_input)]},
                    config=config
                )
            )
            
            # Extract final answer
            final_message = final_state['messages'][-1]
            answer = final_message.content if hasattr(final_message, 'content') else str(final_message)
            
            # Extract sources from retrieved documents (same format as standard implementation)
            message_sources = [
                {'metadata': doc.metadata, 'page_content': doc.page_content}
                for doc in retrieved_documents_store
            ]
            
            # Extract and log the queries used
            tool_call_messages = [msg for msg in final_state['messages'] if hasattr(msg, 'tool_calls') and msg.tool_calls]
            queries_used = []
            for msg in tool_call_messages:
                for tool_call in msg.tool_calls:
                    if 'query' in tool_call.get('args', {}):
                        queries_used.append(tool_call['args']['query'])
            
            # Log completion
            print(f"\n{'='*80}")
            print(f"✅ ADAPTIVE RAG AGENT COMPLETE (WebSocket)")
            print(f"{'='*80}")
            print(f"Tool calls made: {len(tool_call_messages)}")
            print(f"Total sources retrieved: {len(retrieved_documents_store)}")
            if queries_used:
                print(f"Queries used by agent:")
                for i, query in enumerate(queries_used, 1):
                    print(f"  {i}. \"{query}\"")
            if len(retrieved_documents_store) == 0:
                print(f"ℹ️  Agent decided NOT to retrieve documents (query didn't require project specs)")
            print(f"Answer length: {len(answer)} characters")
            print(f"{'='*80}\n")
            
            # Save to chat history
            await self._save_chat_messages_adaptive(deps['memory'].chat_memory, user_input, answer, message_sources)
            
            return {
                'answer': answer,
                'sources': message_sources,
                'chat_id': deps['chat'].id,
            }
            
        except Exception as e:
            print(f"Error in adaptive streaming agent: {str(e)}")
            # Fallback to standard streaming if adaptive fails
            return await self._run_streaming_chain(user_input, chat_id, project_version_id, num_documents)
    
    @database_sync_to_async
    def _save_chat_messages_adaptive(self, chat_memory, user_input, answer, sources):
        """Save chat messages and sources for adaptive agent."""
        try:
            # Add user message
            chat_memory.add_user_message(user_input)
            # Add AI response
            chat_memory.add_ai_message(answer)
            # Attach sources
            chat_message = chat_memory.message_db_object
            chat_message.sources = sources
            chat_message.save()
        except Exception as e:
            print(f"Error saving adaptive chat messages: {str(e)}") 