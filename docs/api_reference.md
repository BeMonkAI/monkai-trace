# API Reference

Complete reference for MonkAI Trace Python SDK.

## MonkAIClient

Synchronous client for MonkAI API.

### Constructor

```python
MonkAIClient(
    tracer_token: str,
    base_url: str = "https://monkai.ai/api",
    timeout: int = 30,
    max_retries: int = 3
)
```

**Parameters:**
- `tracer_token` (str, required): Your MonkAI tracer token (starts with `tk_`)
- `base_url` (str): API endpoint URL
- `timeout` (int): Request timeout in seconds
- `max_retries` (int): Maximum retry attempts on failure

### Methods

#### upload_record()

Upload a single conversation record.

```python
client.upload_record(
    namespace: str,
    agent: str,
    messages: Union[Dict, List[Dict]],
    session_id: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    process_tokens: Optional[int] = None,
    memory_tokens: Optional[int] = None,
    **kwargs
) -> Dict[str, Any]
```

**Example:**
```python
client.upload_record(
    namespace="support",
    agent="bot-v1",
    messages={"role": "assistant", "content": "Hello!"},
    input_tokens=5,
    output_tokens=10
)
```

#### upload_records_batch()

Upload multiple records efficiently.

```python
client.upload_records_batch(
    records: List[ConversationRecord],
    chunk_size: int = 100
) -> Dict[str, Any]
```

**Returns:**
```python
{
    "total_inserted": 150,
    "total_records": 150,
    "failures": []
}
```

#### upload_records_from_json()

Upload records from JSON file.

```python
client.upload_records_from_json(
    file_path: Union[str, Path],
    chunk_size: int = 100
) -> Dict[str, Any]
```

**Example:**
```python
result = client.upload_records_from_json("conversations.json")
print(f"Uploaded {result['total_inserted']} records")
```

#### upload_log()

Upload a single log entry.

```python
client.upload_log(
    namespace: str,
    level: str,
    message: str,
    agent: Optional[str] = None,
    session_id: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]
```

**Log Levels:**
- `"info"`: Informational messages
- `"warn"`: Warning messages
- `"error"`: Error messages

#### test_connection()

Test API connectivity.

```python
client.test_connection() -> bool
```

---

## AsyncMonkAIClient

Asynchronous client for high-performance applications.

### Constructor

```python
AsyncMonkAIClient(
    tracer_token: str,
    base_url: str = "https://monkai.ai/api",
    timeout: int = 30,
    max_retries: int = 3
)
```

### Usage

```python
async with AsyncMonkAIClient(tracer_token="tk_xxx") as client:
    await client.upload_record(
        namespace="test",
        agent="bot",
        messages={"role": "user", "content": "Hi"}
    )
```

### Methods

All methods are async versions of `MonkAIClient` with additional `parallel` parameter for batch uploads:

```python
await client.upload_records_batch(
    records,
    chunk_size=100,
    parallel=True  # Upload chunks in parallel
)
```

---

## MonkAIRunHooks

OpenAI Agents integration hooks.

### Constructor

```python
MonkAIRunHooks(
    tracer_token: str,
    namespace: str,
    auto_upload: bool = True,
    estimate_system_tokens: bool = True,
    batch_size: int = 10
)
```

**Parameters:**
- `tracer_token` (str): Your MonkAI tracer token
- `namespace` (str): Namespace for all conversations
- `auto_upload` (bool): Auto-upload after agent ends
- `estimate_system_tokens` (bool): Estimate process tokens from instructions
- `batch_size` (int): Records to batch before upload

### Usage

```python
from monkai_trace.integrations.openai_agents import MonkAIRunHooks

hooks = MonkAIRunHooks(
    tracer_token="tk_xxx",
    namespace="customer-support"
)

# ✅ Recommended: Use run_with_tracking() for full internal tools capture
result = await MonkAIRunHooks.run_with_tracking(agent, "Hello", hooks)
```

### run_with_tracking() (v0.2.4+, enhanced in v0.2.6)

Static async method to run agent with full internal tool capture.

```python
result = await MonkAIRunHooks.run_with_tracking(
    agent,
    user_input,
    hooks,
    **kwargs  # Additional Runner.run() parameters
)
```

**v0.2.6+ Auto-Include Parameters:**

The method automatically injects these parameters to ensure internal tool details are captured:

- `web_search_call.action.sources` - Full URLs and titles for web searches
- `file_search_call.results` - Complete file search results

**No configuration needed** - sources are captured automatically when using `run_with_tracking()`.

### Lifecycle Hooks

The following hooks are automatically called:

- `on_agent_start(context, agent)`: Agent starts processing
- `on_agent_end(context, agent, output)`: Agent completes (uploads data)
- `on_handoff(context, from_agent, to_agent)`: Agent hands off to another
- `on_tool_start(context, agent, tool)`: Tool execution starts
- `on_tool_end(context, agent, tool, result)`: Tool execution ends

---

## Data Models

### ConversationRecord

```python
ConversationRecord(
    namespace: str,
    agent: str,
    msg: Union[Message, List[Message], Dict],
    session_id: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    process_tokens: Optional[int] = None,
    memory_tokens: Optional[int] = None,
    transfers: Optional[List[Transfer]] = None
)
```

### Message

```python
Message(
    role: str,  # "user", "assistant", "tool", "system"
    content: Union[str, Dict],
    sender: Optional[str] = None,
    tool_name: Optional[str] = None
)
```

### Transfer

```python
Transfer(
    from_agent: str,
    to_agent: str,
    reason: Optional[str] = None,
    timestamp: Optional[str] = None
)
```

### TokenUsage

```python
TokenUsage(
    input_tokens: int = 0,
    output_tokens: int = 0,
    process_tokens: int = 0,
    memory_tokens: int = 0,
    total_tokens: Optional[int] = None,  # Auto-calculated
    requests: Optional[int] = None
)
```

**Factory Method:**
```python
TokenUsage.from_openai_agents_usage(
    usage: agents.Usage,
    system_prompt_tokens: int = 0,
    context_tokens: int = 0
) -> TokenUsage
```

### LogEntry

```python
LogEntry(
    namespace: str,
    level: str,  # "info", "warn", "error"
    message: str,
    agent: Optional[str] = None,
    session_id: Optional[str] = None
)
```

---

## Exceptions

### MonkAIAPIError

Raised when API request fails.

```python
from monkai_trace.exceptions import MonkAIAPIError

try:
    client.upload_record(...)
except MonkAIAPIError as e:
    print(f"API error: {e}")
```

### MonkAIAuthError

Raised for authentication issues.

```python
from monkai_trace.exceptions import MonkAIAuthError

try:
    client = MonkAIClient(tracer_token="invalid")
    client.upload_record(...)
except MonkAIAuthError:
    print("Invalid tracer token")
```

### MonkAIValidationError

Raised for validation errors.

```python
from monkai_trace.exceptions import MonkAIValidationError

try:
    record = ConversationRecord(namespace="", agent="bot")
except MonkAIValidationError as e:
    print(f"Validation error: {e}")
```

---

## Environment Variables

Set environment variables for configuration:

```bash
export MONKAI_TRACER_TOKEN="tk_your_token"
export MONKAI_BASE_URL="https://custom.api.com"
```

```python
import os

client = MonkAIClient(
    tracer_token=os.getenv("MONKAI_TRACER_TOKEN"),
    base_url=os.getenv("MONKAI_BASE_URL", "https://monkai.ai/api")
)
```

---

## Best Practices

1. **Use async client for high throughput:**
   ```python
   async with AsyncMonkAIClient(...) as client:
       await client.upload_records_batch(records, parallel=True)
   ```

2. **Batch uploads for efficiency:**
   ```python
   client.upload_records_batch(records, chunk_size=100)
   ```

3. **Enable system token estimation:**
   ```python
   hooks = MonkAIRunHooks(..., estimate_system_tokens=True)
   ```

4. **Handle exceptions gracefully:**
   ```python
   try:
       client.upload_record(...)
   except MonkAIAPIError:
       # Log and retry
       pass
   ```

5. **Use meaningful namespaces:**
   ```python
   # Good
   namespace="customer-support-tier1"
   
   # Avoid
   namespace="prod"
   ```
