# JSON Upload Guide

Upload bulk conversation records and logs from JSON files.

## Overview

MonkAI supports uploading data from JSON files, perfect for:
- Migrating historical conversation data
- Bulk importing from other systems
- Testing with sample datasets
- Batch processing offline logs

## JSON File Formats

### Conversation Records Format

`conversations.json`:
```json
[
  {
    "namespace": "customer-support",
    "agent": "support-bot-v1",
    "session_id": "session-123",
    "msg": {
      "role": "assistant",
      "content": "How can I help you today?"
    },
    "input_tokens": 10,
    "output_tokens": 15,
    "process_tokens": 5,
    "memory_tokens": 0
  },
  {
    "namespace": "customer-support",
    "agent": "support-bot-v1",
    "session_id": "session-123",
    "msg": [
      {
        "role": "user",
        "content": "I need help with my order"
      },
      {
        "role": "assistant",
        "content": "I'd be happy to help! What's your order number?"
      }
    ],
    "input_tokens": 20,
    "output_tokens": 25,
    "process_tokens": 5,
    "memory_tokens": 30,
    "transfers": [
      {
        "from": "triage-agent",
        "to": "support-bot-v1",
        "reason": "Customer needs order assistance"
      }
    ]
  }
]
```

### Logs Format

`logs.json`:
```json
[
  {
    "level": "info",
    "message": "Agent initialized successfully",
    "agent": "support-bot-v1",
    "session_id": "session-123"
  },
  {
    "level": "warn",
    "message": "High token usage detected",
    "agent": "support-bot-v1",
    "metadata": {
      "tokens_used": 1500,
      "threshold": 1000
    }
  },
  {
    "level": "error",
    "message": "API call failed",
    "agent": "support-bot-v1",
    "error_code": "TIMEOUT"
  }
]
```

## Upload Conversation Records

### Basic Upload

```python
from monkai_trace import MonkAIClient

client = MonkAIClient(tracer_token="tk_your_token_here")

# Upload all records from file
result = client.upload_records_from_json("conversations.json")

print(f"✅ Uploaded {result['total_inserted']} records")
print(f"   Total in file: {result['total_records']}")

if result['failures']:
    print(f"   ⚠️ {len(result['failures'])} chunks failed")
```

### Custom Chunk Size

```python
# Upload in smaller batches (good for rate limiting)
result = client.upload_records_from_json(
    file_path="conversations.json",
    chunk_size=50  # 50 records per batch
)
```

### Async Upload (Faster)

```python
from monkai_trace import AsyncMonkAIClient

async def upload_async():
    async with AsyncMonkAIClient(tracer_token="tk_xxx") as client:
        result = await client.upload_records_from_json(
            file_path="conversations.json",
            chunk_size=100,
            parallel=True  # Upload chunks in parallel
        )
        print(f"Uploaded {result['total_inserted']} records")

import asyncio
asyncio.run(upload_async())
```

## Upload Logs

### Basic Upload

```python
client = MonkAIClient(tracer_token="tk_your_token_here")

# Logs require namespace parameter
result = client.upload_logs_from_json(
    file_path="logs.json",
    namespace="customer-support"  # Required for logs
)

print(f"✅ Uploaded {result['total_inserted']} logs")
```

### Async Parallel Upload

```python
async with AsyncMonkAIClient(tracer_token="tk_xxx") as client:
    result = await client.upload_logs_from_json(
        file_path="logs.json",
        namespace="customer-support",
        chunk_size=200,
        parallel=True
    )
```

## Programmatic JSON Generation

### Generate Records Programmatically

```python
import json
from datetime import datetime

# Create records
records = [
    {
        "namespace": "sales-bot",
        "agent": "sales-assistant",
        "session_id": f"session-{i}",
        "msg": {
            "role": "assistant",
            "content": f"Message {i}"
        },
        "input_tokens": 10,
        "output_tokens": 20,
        "inserted_at": datetime.utcnow().isoformat()
    }
    for i in range(100)
]

# Save to JSON
with open("generated_records.json", "w") as f:
    json.dump(records, f, indent=2)

# Upload
result = client.upload_records_from_json("generated_records.json")
```

## OpenAI Agents Export to JSON

Export OpenAI Agents data and upload later:

```python
from monkai_trace.integrations.openai_agents import MonkAIRunHooks
import json

# Initialize hooks with auto_upload=False
hooks = MonkAIRunHooks(
    tracer_token="tk_xxx",
    namespace="my-agent",
    auto_upload=False  # Disable automatic upload
)

# Run your agents
result = await Runner.run(agent, "Hello", hooks=hooks)

# Export buffered records to JSON
records = hooks._batch_buffer
with open("agent_conversations.json", "w") as f:
    json.dump(
        [r.model_dump(exclude_none=True) for r in records],
        f,
        indent=2
    )

# Later: upload from file
client = MonkAIClient(tracer_token="tk_xxx")
client.upload_records_from_json("agent_conversations.json")
```

## Error Handling

```python
result = client.upload_records_from_json("conversations.json")

# Check for failures
if result['failures']:
    print("Some chunks failed to upload:")
    for failure in result['failures']:
        print(f"  Chunk {failure['chunk']}: {failure['error']}")
    
    # Optionally retry failed chunks
    # (Implementation depends on your error handling strategy)
```

## Large File Handling

For very large JSON files (>1GB), process in streaming mode:

```python
import json
from pathlib import Path

def upload_large_file(file_path: str, client: MonkAIClient, chunk_size: int = 100):
    """Upload large JSON file in streaming mode"""
    records_buffer = []
    total_uploaded = 0
    
    with open(file_path, 'r') as f:
        data = json.load(f)
        
        for record_dict in data:
            records_buffer.append(ConversationRecord(**record_dict))
            
            if len(records_buffer) >= chunk_size:
                result = client.upload_records_batch(records_buffer)
                total_uploaded += result['total_inserted']
                records_buffer.clear()
                print(f"Uploaded {total_uploaded} records so far...")
        
        # Upload remaining records
        if records_buffer:
            result = client.upload_records_batch(records_buffer)
            total_uploaded += result['total_inserted']
    
    print(f"✅ Total uploaded: {total_uploaded} records")
    return total_uploaded

# Usage
upload_large_file("large_conversations.json", client)
```

## File Validation

Validate JSON before upload:

```python
from monkai_trace.file_handlers import FileHandler
from monkai_trace.exceptions import MonkAIValidationError

try:
    # This validates all records
    records = FileHandler.load_records("conversations.json")
    print(f"✅ File valid: {len(records)} records")
    
    # Now upload
    result = client.upload_records_batch(records)
    
except MonkAIValidationError as e:
    print(f"❌ Validation error: {e}")
except FileNotFoundError:
    print("❌ File not found")
except json.JSONDecodeError as e:
    print(f"❌ Invalid JSON: {e}")
```

## Best Practices

1. **Use chunking for large files:**
   ```python
   # Good: Upload in chunks
   result = client.upload_records_from_json("large.json", chunk_size=100)
   
   # Avoid: Single request with 10,000 records
   ```

2. **Enable parallel uploads for speed:**
   ```python
   async with AsyncMonkAIClient(...) as client:
       await client.upload_records_from_json(..., parallel=True)
   ```

3. **Validate before upload:**
   ```python
   records = FileHandler.load_records("file.json")  # Validates
   client.upload_records_batch(records)
   ```

4. **Handle failures gracefully:**
   ```python
   result = client.upload_records_from_json("data.json")
   if result['failures']:
       # Log and alert
       send_alert(f"{len(result['failures'])} chunks failed")
   ```

5. **Use meaningful filenames:**
   ```python
   # Good
   "customer_support_2024_01_01.json"
   
   # Avoid
   "data.json"
   ```

## Performance Benchmarks

Typical upload speeds (1000 records):

- **Sync client, chunk_size=100**: ~5 seconds
- **Async client, chunk_size=100, parallel=False**: ~3 seconds
- **Async client, chunk_size=100, parallel=True**: ~1 second

Optimize for your use case:
- **Small files (<100 records)**: Use sync client
- **Medium files (100-1000 records)**: Use async client, parallel=False
- **Large files (>1000 records)**: Use async client, parallel=True
