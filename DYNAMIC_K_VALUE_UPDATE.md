# Dynamic k-Value Implementation

## Issue
The adaptive RAG was still using a fixed k value (max_documents) for all retrieval calls, missing the opportunity to let the agent dynamically adjust retrieval based on query complexity.

## Solution
Made the retrieval tool accept a `num_documents` parameter that the LLM agent can control, allowing it to retrieve different amounts of documents based on the query.

### Changes Made

#### 1. Updated `retrieve_documents` Tool Signature

**Before:**
```python
@tool
def retrieve_documents(query: str) -> str:
    """Retrieve relevant documents from project specifications."""
    documents = vectorstore.similarity_search(query, k=max_documents, ...)
```

**After:**
```python
@tool
def retrieve_documents(query: str, num_documents: int = 5) -> str:
    """Retrieve relevant documents from project specifications.
    
    YOU control how many documents to retrieve based on the query complexity:
    - Simple, specific queries: Use 3-5 documents
    - Broader queries needing more context: Use 5-8 documents  
    - Complex queries requiring comprehensive coverage: Use up to 10 documents
    
    Args:
        query: Search query for finding relevant specification sections
        num_documents: Number of documents to retrieve (default: 5, max: 10).
                      Adjust based on query complexity.
    """
    # Validate and cap num_documents
    num_documents = min(max(num_documents, 1), max_documents)
    documents = vectorstore.similarity_search(query, k=num_documents, ...)
```

#### 2. Updated Agent System Prompts

Added guidance in both HTTP and WebSocket system messages:

```
DYNAMIC DOCUMENT RETRIEVAL:
- For simple, specific questions: Request 3-5 documents
- For broader questions: Request 5-8 documents
- For complex questions needing comprehensive coverage: Request up to 10 documents
- You control the num_documents parameter - adjust it based on query complexity
```

### How It Works

1. **Agent decides retrieval amount**: When the agent determines it needs to retrieve documents, it now chooses how many based on the query complexity

2. **Validation**: The tool validates the num_documents parameter:
   - Minimum: 1 document
   - Maximum: 10 documents (or whatever max_documents is set to)
   - Default: 5 documents if not specified

3. **Examples**:
   ```python
   # Simple question about a specific requirement
   retrieve_documents("concrete strength requirements", num_documents=3)
   
   # Broader question needing more context
   retrieve_documents("safety requirements for excavation", num_documents=7)
   
   # Complex question requiring comprehensive coverage
   retrieve_documents("complete waterproofing procedures", num_documents=10)
   ```

### Benefits

- **Efficiency**: Simple queries don't waste tokens on unnecessary documents
- **Completeness**: Complex queries can retrieve more documents when needed
- **Cost optimization**: Fewer tokens used overall by retrieving only what's needed
- **Better relevance**: Agent can do multiple smaller retrievals with different amounts rather than one large retrieval
- **True adaptive RAG**: The "adaptive" part now includes both WHEN to retrieve and HOW MUCH to retrieve

### Impact on k=21 Legacy Value

The old system always retrieved up to k=21 documents regardless of query complexity. The new system:
- **Defaults to 5** instead of 21 (60% reduction for typical queries)
- **Can go as low as 1-3** for very specific questions (85-95% reduction)
- **Can go up to 10** for complex queries (still 50% less than 21)
- **Agent makes intelligent decisions** based on query analysis

This means most queries will retrieve significantly fewer documents, making the system more efficient while maintaining or improving answer quality.

### Testing

The agent will now make decisions like:
- "Hello" → 0 documents (doesn't use tool at all)
- "What is the concrete strength requirement?" → 3-5 documents
- "Tell me about all safety requirements" → 8-10 documents
- "What are the waterproofing, concrete, and steel requirements?" → Multiple calls with 5-7 documents each

Monitor PromptLayer logs to see how the agent adjusts num_documents based on different query types.

