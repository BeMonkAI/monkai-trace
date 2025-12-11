# HTTP REST API Reference

The MonkAI Trace HTTP REST API provides a language-agnostic way to send traces from any runtime (Python, Node.js, Go, Deno, etc.) without requiring a specific SDK.

## Base URL

```
https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api
```

## Authentication

All requests require a `tracer_token` header with your MonkAI tracer token.

```bash
curl -H "tracer_token: YOUR_TOKEN_HERE" ...
```

## Endpoints

### Create Session — `POST /sessions/create`

Creates a new session for tracking a conversation flow.

**Headers:**
- `tracer_token`: required
- `Content-Type`: `application/json`

**Body:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `namespace` | string | Yes | The namespace for this session |
| `user_id` | string | No | External user identifier (e.g., phone number, email) |
| `inactivity_timeout` | integer | No | Seconds of inactivity before session expires (default: 120) |
| `metadata` | object | No | Custom metadata for the session |

**Response:**
```json
{
  "session_id": "my-namespace-user123-20251210123456",
  "namespace": "my-namespace",
  "user_id": "user123",
  "inactivity_timeout": 120,
  "created_at": "2025-12-10T12:34:56.789Z",
  "metadata": { "platform": "whatsapp" }
}
```

**Example:**
```bash
curl -X POST https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api/sessions/create \
  -H "tracer_token: YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "namespace": "my-agent",
    "user_id": "user123",
    "inactivity_timeout": 120,
    "metadata": { "platform": "web" }
  }'
```

---

### Trace LLM Call — `POST /traces/llm`

Records an LLM (Large Language Model) call trace.

**Headers:**
- `tracer_token`: required
- `Content-Type`: `application/json`

**Body:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | Yes | Session ID from `/sessions/create` |
| `model` | string | No | Model name (e.g., "gpt-4", "gemini-2.5-flash") |
| `provider` | string | No | Provider name (e.g., "openai", "google") |
| `input` | object | No | Input messages `{ "messages": [...] }` |
| `output` | object | No | Output `{ "content": "...", "usage": {...} }` |
| `latency_ms` | integer | No | Call latency in milliseconds |
| `metadata` | object | No | Custom metadata |
| `timestamp` | string | No | ISO-8601 timestamp |

**Response:**
```json
{
  "success": true,
  "trace_type": "llm_call",
  "tokens": { "input": 100, "output": 50 }
}
```

**Example:**
```bash
curl -X POST https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api/traces/llm \
  -H "tracer_token: YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "my-agent-user123-20251210123456",
    "model": "gpt-4",
    "provider": "openai",
    "input": {
      "messages": [
        { "role": "user", "content": "Hello, how are you?" }
      ]
    },
    "output": {
      "content": "I am doing well, thank you!",
      "usage": { "prompt_tokens": 8, "completion_tokens": 10 }
    },
    "latency_ms": 450
  }'
```

---

### Trace Tool Call — `POST /traces/tool`

Records a tool/function call trace.

**Headers:**
- `tracer_token`: required
- `Content-Type`: `application/json`

**Body:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | Yes | Session ID |
| `tool_name` | string | Yes | Name of the tool |
| `arguments` | object | No | Tool arguments |
| `result` | any | No | Tool result |
| `latency_ms` | integer | No | Execution time |
| `agent` | string | No | Agent that called the tool |
| `metadata` | object | No | Custom metadata |
| `timestamp` | string | No | ISO-8601 timestamp |

**Response:**
```json
{
  "success": true,
  "trace_type": "tool_call",
  "tool_name": "get_weather"
}
```

**Example:**
```bash
curl -X POST https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api/traces/tool \
  -H "tracer_token: YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "my-agent-user123-20251210123456",
    "tool_name": "get_weather",
    "arguments": { "city": "São Paulo" },
    "result": { "temperature": 25, "condition": "sunny" },
    "latency_ms": 120,
    "agent": "weather-assistant"
  }'
```

---

### Trace Handoff — `POST /traces/handoff`

Records an agent-to-agent handoff trace.

**Headers:**
- `tracer_token`: required
- `Content-Type`: `application/json`

**Body:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | Yes | Session ID |
| `from_agent` | string | Yes | Source agent name |
| `to_agent` | string | Yes | Target agent name |
| `reason` | string | No | Handoff reason |
| `metadata` | object | No | Custom metadata |
| `timestamp` | string | No | ISO-8601 timestamp |

**Response:**
```json
{
  "success": true,
  "trace_type": "handoff",
  "from": "triage-agent",
  "to": "sales-agent"
}
```

**Example:**
```bash
curl -X POST https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api/traces/handoff \
  -H "tracer_token: YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "my-agent-user123-20251210123456",
    "from_agent": "triage-agent",
    "to_agent": "sales-agent",
    "reason": "Customer wants to purchase"
  }'
```

---

### Trace Log — `POST /traces/log`

Records a log entry trace.

**Headers:**
- `tracer_token`: required
- `Content-Type`: `application/json`

**Body:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | No | Session ID for context |
| `namespace` | string | Conditional | Required if no session_id |
| `level` | string | No | Log level (info, warn, error, debug) |
| `message` | string | Yes | Log message |
| `resource_id` | string | No | Resource identifier |
| `metadata` | object | No | Custom data |
| `timestamp` | string | No | ISO-8601 timestamp |

**Response:**
```json
{
  "success": true,
  "trace_type": "log"
}
```

**Example:**
```bash
curl -X POST https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api/traces/log \
  -H "tracer_token: YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "my-agent-user123-20251210123456",
    "level": "info",
    "message": "User completed onboarding flow",
    "metadata": { "step": 5, "duration_ms": 3200 }
  }'
```

---

## Legacy Endpoints

### Upload Logs — `POST /logs/upload`

Batch upload operational logs.

**Headers:**
- `tracer_token`: required

**Body:**
```json
{
  "logs": [
    {
      "level": "info",
      "message": "Log message",
      "namespace": "my-agent",
      "timestamp": "2025-12-10T12:34:56.789Z",
      "resource_id": "optional-resource-id",
      "custom_object": { "any": "data" }
    }
  ]
}
```

### Upload Records — `POST /records/upload`

Batch upload conversation records.

**Headers:**
- `tracer_token`: required

**Body:**
```json
{
  "records": [
    {
      "namespace": "my-agent",
      "agent": "support-bot",
      "user_id": "user123",
      "session_id": "session-abc",
      "msg": { "role": "assistant", "content": "Hello!" },
      "input_tokens": 10,
      "output_tokens": 5
    }
  ]
}
```

---

## Error Responses

All endpoints return standard error responses:

```json
{
  "error": "Error message description"
}
```

Common HTTP status codes:
- `400` - Bad Request (missing required fields)
- `401` - Unauthorized (invalid or missing token)
- `403` - Forbidden (token doesn't have access)
- `500` - Internal Server Error
