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

## User Identification

All trace endpoints support optional user identification fields to track who is interacting with your agent:

| Field | Type | Description |
|-------|------|-------------|
| `external_user_id` | string | Unique external user identifier (e.g., phone number, email, customer ID) |
| `external_user_name` | string | Human-readable display name (e.g., "João Silva") |
| `external_user_channel` | string | Origin channel: `whatsapp`, `web`, `telegram`, `slack`, `email`, etc. |

These fields enable:
- **User filtering** in the dashboard by phone/email/ID
- **Name display** showing actual user names instead of IDs
- **Channel analytics** to track which platforms users prefer

---

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
| `user_id` | string | No | External user identifier (used in session_id generation) |
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
    "user_id": "5521999998888",
    "inactivity_timeout": 300,
    "metadata": { "platform": "whatsapp" }
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
| `external_user_id` | string | No | External user identifier (e.g., phone, email) |
| `external_user_name` | string | No | User display name (e.g., "João Silva") |
| `external_user_channel` | string | No | Channel: whatsapp, web, telegram, etc. |

**Response:**
```json
{
  "success": true,
  "trace_type": "llm_call",
  "tokens": { "input": 100, "output": 50 }
}
```

**Example (with user identification):**
```bash
curl -X POST https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api/traces/llm \
  -H "tracer_token: YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "my-agent-5521999998888-20251210123456",
    "model": "gpt-4",
    "provider": "openai",
    "input": {
      "messages": [
        { "role": "user", "content": "Qual o preço da gasolina?" }
      ]
    },
    "output": {
      "content": "O preço atual da gasolina é R$ 5,89/L.",
      "usage": { "prompt_tokens": 12, "completion_tokens": 15 }
    },
    "latency_ms": 450,
    "external_user_id": "5521999998888",
    "external_user_name": "Italo",
    "external_user_channel": "whatsapp"
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
| `external_user_id` | string | No | External user identifier |
| `external_user_name` | string | No | User display name |
| `external_user_channel` | string | No | Origin channel |

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
    "session_id": "my-agent-5521999998888-20251210123456",
    "tool_name": "get_fuel_price",
    "arguments": { "fuel_type": "gasoline", "city": "São Paulo" },
    "result": { "price": 5.89, "currency": "BRL" },
    "latency_ms": 120,
    "agent": "fuel-assistant",
    "external_user_id": "5521999998888",
    "external_user_name": "Italo",
    "external_user_channel": "whatsapp"
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
| `external_user_id` | string | No | External user identifier |
| `external_user_name` | string | No | User display name |
| `external_user_channel` | string | No | Origin channel |

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
    "session_id": "my-agent-5521999998888-20251210123456",
    "from_agent": "triage-agent",
    "to_agent": "sales-agent",
    "reason": "Customer wants to purchase fuel",
    "external_user_id": "5521999998888",
    "external_user_name": "Italo",
    "external_user_channel": "whatsapp"
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
      "output_tokens": 5,
      "external_user_id": "5521999998888",
      "external_user_name": "João Silva",
      "external_user_channel": "whatsapp"
    }
  ]
}
```

---

## WhatsApp Integration Example

Here's a complete example for integrating with WhatsApp:

```python
import requests

MONKAI_API = "https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api"
TRACER_TOKEN = "tk_your_token_here"
NAMESPACE = "trackfuel"

def process_whatsapp_message(phone: str, name: str, user_msg: str, bot_response: str):
    """Process and trace a WhatsApp message."""
    
    # 1. Create session with user's phone as ID
    session = requests.post(
        f"{MONKAI_API}/sessions/create",
        headers={"tracer_token": TRACER_TOKEN, "Content-Type": "application/json"},
        json={
            "namespace": NAMESPACE,
            "user_id": phone,
            "inactivity_timeout": 300
        }
    ).json()
    
    # 2. Trace the LLM call with full user identification
    requests.post(
        f"{MONKAI_API}/traces/llm",
        headers={"tracer_token": TRACER_TOKEN, "Content-Type": "application/json"},
        json={
            "session_id": session["session_id"],
            "model": "gpt-4",
            "input": {"messages": [{"role": "user", "content": user_msg}]},
            "output": {"content": bot_response},
            # IMPORTANT: User identification fields
            "external_user_id": phone,         # e.g., "5521997772643"
            "external_user_name": name,        # e.g., "Italo"
            "external_user_channel": "whatsapp"
        }
    )
    
    print(f"✓ Traced message from {name} ({phone})")

# Usage
process_whatsapp_message(
    phone="5521997772643",
    name="Italo",
    user_msg="Qual o preço do combustível?",
    bot_response="O preço atual da gasolina é R$ 5,89/L."
)
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
