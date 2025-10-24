"""Adaptive retrieval tool for LangGraph agents.

This module provides a retrieval tool that allows LangGraph agents to dynamically
query the Pinecone vector store for project-specific documents based on user queries.
"""

from typing import List, Dict, Any
from langchain.tools import tool
from langchain_core.documents import Document
from langchain_pinecone import PineconeVectorStore
from django.conf import settings
import tiktoken


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count the number of tokens in a text string."""
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except KeyError:
        # Fallback to cl100k_base encoding for unknown models
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))


def format_documents_for_context(documents: List[Document], max_tokens: int = 8000) -> str:
    """Format retrieved documents into a context string with token limit.
    
    Args:
        documents: List of Document objects from vector store
        max_tokens: Maximum number of tokens to include in context
        
    Returns:
        Formatted string containing document content with metadata
    """
    if not documents:
        return "No relevant documents found."
    
    formatted_parts = []
    total_tokens = 0
    
    for doc in documents:
        metadata = doc.metadata
        section_number = (
            metadata.get('master_format_section_number') or 
            metadata.get('spec_section_number') or 
            'Unknown Section'
        )
        source_file = metadata.get('source', 'Unknown Source')
        
        doc_text = doc.page_content.strip()
        
        # Format the document with metadata
        formatted_doc = f"""
[Section: {section_number} | Source: {source_file}]
{doc_text}
---
"""
        
        doc_tokens = count_tokens(formatted_doc)
        
        # Check if adding this document would exceed token limit
        if total_tokens + doc_tokens > max_tokens:
            # If we haven't added any documents yet, include at least one (truncated)
            if not formatted_parts:
                # Truncate to fit within token limit
                available_tokens = max_tokens - count_tokens(f"[Section: {section_number} | Source: {source_file}]\n...(truncated)...")
                words = doc_text.split()
                truncated_text = ""
                for word in words:
                    test_text = truncated_text + " " + word if truncated_text else word
                    if count_tokens(test_text) > available_tokens:
                        break
                    truncated_text = test_text
                
                formatted_doc = f"""
[Section: {section_number} | Source: {source_file}]
{truncated_text}
...(truncated for length)
---
"""
                formatted_parts.append(formatted_doc)
            break
        
        formatted_parts.append(formatted_doc)
        total_tokens += doc_tokens
    
    return "\n".join(formatted_parts)


def create_retrieval_tool(
    vectorstore: PineconeVectorStore,
    project_id: str,
    project_version_id: str,
    user_id: str = None,
    max_documents: int = 100,
    retrieved_documents_store: List[Document] = None
):
    """Factory function to create a retrieval tool with bound project context.
    
    Args:
        vectorstore: Initialized PineconeVectorStore instance
        project_id: ID of the project to retrieve documents from
        project_version_id: ID of the project version
        user_id: Optional user ID for filtering (not used currently)
        max_documents: Maximum number of documents to retrieve per query
        retrieved_documents_store: Optional list to store retrieved documents for source tracking
        
    Returns:
        A tuple of (tool, retrieved_documents_store) where the tool can be used by LangGraph agents
        and retrieved_documents_store accumulates all retrieved documents
    """
    # Create a store for retrieved documents if not provided
    if retrieved_documents_store is None:
        retrieved_documents_store = []
    
    @tool
    def retrieve_documents(query: str, num_documents: int = 5) -> str:
        """Retrieve relevant documents from project specifications.
        
        Use this tool when you need specific information from project documents
        to answer the user's question. Generate focused, specific search queries.
        
        YOU control how many documents to retrieve based on the query complexity:
        - Simple, specific queries: Use 3-5 documents
        - Broader queries needing more context: Use 5-8 documents  
        - Complex queries requiring comprehensive coverage: Use up to 10 documents
        
        Args:
            query: A focused search query for finding relevant specification sections.
                   Examples: "concrete mix design requirements", "fire protection systems",
                   "waterproofing installation procedures"
            num_documents: Number of documents to retrieve (default: 5, max: 100).
                          Adjust based on query complexity.
        
        Returns:
            Formatted document excerpts with section numbers and source files.
            Returns "No relevant documents found" if no matches.
        """
        # Validate and cap num_documents
        requested_num = num_documents
        num_documents = min(max(num_documents, 1), max_documents)
        
        # Log the tool call
        print(f"\n{'='*80}")
        print(f"🔍 ADAPTIVE RAG TOOL CALL")
        print(f"{'='*80}")
        print(f"Query: '{query}'")
        print(f"Documents requested: {requested_num} (capped at: {num_documents})")
        print(f"Project: {project_id}, Version: {project_version_id}")
        
        # Build the filter for Pinecone query
        vectorstore_filter = {
            'project_id': {"$eq": str(project_id)},
            'project_version_id': {"$eq": str(project_version_id)},
        }
        
        # Perform similarity search
        try:
            documents = vectorstore.similarity_search(
                query,
                k=num_documents,
                filter=vectorstore_filter
            )
            
            # Log retrieval results
            print(f"Documents retrieved: {len(documents)}")
            if documents:
                print(f"Top sections retrieved:")
                for i, doc in enumerate(documents[:3], 1):  # Show first 3
                    section = doc.metadata.get('master_format_section_number', 'Unknown')
                    source = doc.metadata.get('source', 'Unknown')
                    content_preview = doc.page_content[:100].replace('\n', ' ')
                    print(f"  {i}. Section {section} ({source})")
                    print(f"     Preview: {content_preview}...")
            else:
                print(f"⚠️  No documents found matching query")
            print(f"{'='*80}\n")
            
            # Store the retrieved documents for source tracking
            retrieved_documents_store.extend(documents)
            
            # Format documents for context
            formatted_context = format_documents_for_context(documents, max_tokens=8000)
            
            return formatted_context
            
        except Exception as e:
            error_msg = f"Error retrieving documents: {str(e)}"
            print(f"❌ {error_msg}")
            print(f"{'='*80}\n")
            return error_msg
    
    return retrieve_documents, retrieved_documents_store


def extract_sources_from_documents(documents: List[Document]) -> List[Dict[str, Any]]:
    """Extract source information from documents in the format expected by the frontend.
    
    Args:
        documents: List of Document objects
        
    Returns:
        List of dictionaries containing source metadata
    """
    sources = []
    for doc in documents:
        metadata = doc.metadata
        sources.append({
            'metadata': metadata,
            'page_content': doc.page_content
        })
    return sources

