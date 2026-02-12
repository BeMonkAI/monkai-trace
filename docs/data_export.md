# Data Export Guide

Export your MonkAI Trace data programmatically using the Python SDK.

## Quick Start

```python
from monkai_trace import MonkAIClient

client = MonkAIClient(tracer_token="tk_your_token")

# Export all conversations to JSON
records = client.export_records(
    namespace="my-agent",
    output_file="conversations.json"
)

# Export error logs to CSV
client.export_logs(
    namespace="my-agent",
    level="error",
    format="csv",
    output_file="errors.csv"
)
```

## Querying Data

### Query Records

Retrieve conversation records with filters and pagination:

```python
result = client.query_records(
    namespace="customer-support",
    agent="Triage Agent",        # optional
    session_id="sess_abc123",    # optional
    start_date="2025-01-01",     # optional, ISO-8601
    end_date="2025-02-01",       # optional, ISO-8601
    limit=100,                   # default: 100
    offset=0                     # default: 0
)

print(f"Total: {result['count']}")
for record in result['records']:
    print(record['agent'], record['session_id'])
```

### Query Logs

```python
result = client.query_logs(
    namespace="customer-support",
    level="error",               # optional: info, warn, error
    resource_id="res_123",       # optional
    start_date="2025-01-01",     # optional
    end_date="2025-02-01",       # optional
    limit=50,
    offset=0
)

for log in result['logs']:
    print(f"[{log['level']}] {log['message']}")
```

### Pagination

```python
all_records = []
offset = 0

while True:
    result = client.query_records(
        namespace="my-agent",
        limit=100,
        offset=offset
    )
    records = result.get("records", [])
    if not records:
        break
    all_records.extend(records)
    offset += 100

print(f"Total records fetched: {len(all_records)}")
```

## Exporting Data

Export methods handle pagination automatically on the server side, fetching up to 50,000 records in a single call.

### Export Records

```python
# Export as JSON (returns list of dicts)
records = client.export_records(
    namespace="customer-support",
    agent="Support Bot",
    start_date="2025-01-01",
    format="json",
    output_file="export.json"     # optional: saves to file
)

# Export as CSV (returns CSV string)
csv = client.export_records(
    namespace="customer-support",
    format="csv",
    output_file="export.csv"
)
```

### Export Logs

```python
# Export error logs as JSON
logs = client.export_logs(
    namespace="customer-support",
    level="error",
    format="json",
    output_file="errors.json"
)

# Export all logs as CSV
csv = client.export_logs(
    namespace="customer-support",
    format="csv",
    output_file="all_logs.csv"
)
```

## Async Usage

All methods are available in the async client:

```python
from monkai_trace.async_client import AsyncMonkAIClient

async with AsyncMonkAIClient(tracer_token="tk_xxx") as client:
    # Query
    result = await client.query_records(
        namespace="my-agent",
        limit=50
    )
    
    # Export
    records = await client.export_records(
        namespace="my-agent",
        format="json",
        output_file="export.json"
    )
```

## CSV Format

### Records CSV Columns

| Column | Description |
|--------|-------------|
| id | Record UUID |
| namespace | Workspace namespace |
| agent | Agent name |
| session_id | Conversation session ID |
| inserted_at | When the record was uploaded |
| created_at | Record creation timestamp |
| input_tokens | User input tokens |
| output_tokens | Agent output tokens |
| process_tokens | System/processing tokens |
| memory_tokens | Context/memory tokens |
| total_tokens | Sum of all tokens |
| external_user_id | End-user identifier |
| external_user_name | End-user name |
| external_user_channel | Channel (whatsapp, web, etc.) |
| msg | Messages (JSON) |
| transfers | Agent transfers (JSON) |

### Logs CSV Columns

| Column | Description |
|--------|-------------|
| id | Log UUID |
| namespace | Workspace namespace |
| level | Log level (info, warn, error) |
| message | Log message |
| resource_id | Resource identifier |
| timestamp | Log timestamp |
| created_at | When the log was stored |
| custom_object | Custom metadata (JSON) |

## Limits

- **Query**: Up to 1,000 records per request (use pagination for more)
- **Export**: Up to 50,000 records per export call
- **Timeout**: Export requests have a 120-second timeout for large datasets
