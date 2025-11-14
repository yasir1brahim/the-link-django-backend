# Async/Sync Context Fix

## Problem
WebSocket connections were failing with the error:
```
You cannot call this from an async context - use a thread or sync_to_async.
```

## Root Cause
In the `_run_adaptive_streaming_chain` method, synchronous PromptLayer API calls were being made directly from an async context:

```python
# ❌ BAD - Synchronous calls in async method
viewset = ChatViewSet()
promptlayer_template = viewset.get_promptlayer_template(settings.SPEC_GPT_PROMPTLAYER_PROMPT_NAME)
```

Django's async safety checks prevent this because synchronous I/O operations (like HTTP requests) block the event loop and prevent other async operations from running.

## Solution
Wrapped the synchronous PromptLayer calls in `run_in_executor` to run them in a thread pool:

```python
# ✅ GOOD - Run synchronous calls in thread pool
viewset = ChatViewSet()
promptlayer_template = await asyncio.get_event_loop().run_in_executor(
    None, viewset.get_promptlayer_template, settings.SPEC_GPT_PROMPTLAYER_PROMPT_NAME
)
```

## Technical Details

### Why This Happens
Django has three contexts:
1. **Sync context**: Traditional Django views, ORM operations
2. **Async context**: Async views, WebSocket consumers
3. **Mixed context**: Can be either

When running in an async context (like a WebSocket consumer), Django prevents synchronous ORM or I/O operations because they would block the entire async event loop.

### The Right Approach

#### For Database Operations
Use `@database_sync_to_async`:
```python
@database_sync_to_async
def get_user_data(user_id):
    return User.objects.get(id=user_id)

# In async method:
user = await get_user_data(123)
```

#### For Other Synchronous Operations
Use `run_in_executor`:
```python
# For blocking I/O (HTTP requests, file operations, etc.)
result = await asyncio.get_event_loop().run_in_executor(
    None,  # Use default executor (ThreadPoolExecutor)
    blocking_function,
    arg1,
    arg2
)
```

## Changes Made

### File: `apps/deliverables/consumers.py`

**Method**: `_run_adaptive_streaming_chain` (lines 363-386)

**Before**:
```python
viewset = ChatViewSet()
promptlayer_template = viewset.get_promptlayer_template(settings.SPEC_GPT_PROMPTLAYER_PROMPT_NAME)
model_meta = viewset.get_promptlayer_model_metadata(promptlayer_template)

try:
    adaptive_rag_template = viewset.get_promptlayer_template(settings.SPEC_GPT_V2_PROMPTLAYER_PROMPT_NAME)
    agent_system_message = viewset.get_promptlayer_system_prompt(adaptive_rag_template)
```

**After**:
```python
viewset = ChatViewSet()
promptlayer_template = await asyncio.get_event_loop().run_in_executor(
    None, viewset.get_promptlayer_template, settings.SPEC_GPT_PROMPTLAYER_PROMPT_NAME
)
model_meta = viewset.get_promptlayer_model_metadata(promptlayer_template)

try:
    adaptive_rag_template = await asyncio.get_event_loop().run_in_executor(
        None, viewset.get_promptlayer_template, settings.SPEC_GPT_V2_PROMPTLAYER_PROMPT_NAME
    )
    agent_system_message = viewset.get_promptlayer_system_prompt(adaptive_rag_template)
```

## Why These Specific Calls Needed Fixing

- `get_promptlayer_template()` makes HTTP requests to PromptLayer API
- HTTP requests are blocking I/O operations
- Must run in a thread pool to avoid blocking the async event loop

## Other Methods Already Correct

✅ `_prepare_chain_dependencies` - Already decorated with `@database_sync_to_async`
✅ `_run_streaming_chain` - Already uses `run_in_executor` for blocking operations
✅ `get_user_from_token` - Already decorated with `@database_sync_to_async`
✅ `check_feature_flag` - Already decorated with `@database_sync_to_async`

## Testing

After applying this fix:

1. ✅ WebSocket connections should establish successfully
2. ✅ Messages should stream properly
3. ✅ No "async context" errors in logs
4. ✅ Adaptive RAG should work when feature flag is enabled

### Test Case
1. Enable `specgpt_websockets` feature flag
2. Enable `langchain_update` feature flag (for adaptive RAG)
3. Navigate to Compass chat
4. Send a message
5. Verify streaming response appears
6. Check logs for errors

## Performance Considerations

### Thread Pool Execution
- `run_in_executor(None, ...)` uses the default `ThreadPoolExecutor`
- Default pool size: `min(32, os.cpu_count() + 4)`
- Sufficient for PromptLayer API calls
- Doesn't block the async event loop

### Alternative Approaches

If you need more control:
```python
# Create custom executor
import concurrent.futures
executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

# Use custom executor
result = await loop.run_in_executor(executor, blocking_func)
```

## Related Errors

If you see similar errors, check for:
- ❌ Database queries in async methods (use `@database_sync_to_async`)
- ❌ HTTP requests in async methods (use `run_in_executor`)
- ❌ File I/O in async methods (use `run_in_executor`)
- ❌ Any blocking operation in async context

## Resources

- [Django Async Documentation](https://docs.djangoproject.com/en/4.2/topics/async/)
- [Channels Documentation](https://channels.readthedocs.io/)
- [Python asyncio Documentation](https://docs.python.org/3/library/asyncio.html)

## Status
✅ **Fixed** - Server restarted with changes applied









