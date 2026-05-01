# HTTP REST API Reference

The MonkAI Trace HTTP REST API provides a language-agnostic way to send traces from any runtime (Python, Node.js, Go, Deno, etc.) without requiring a specific SDK.

> **Machine-readable contract**: see [`openapi.yaml`](./openapi.yaml) (OpenAPI 3.1).
> Use it to generate clients (`openapi-generator`, `openapi-typescript`, etc.) and
> validate requests/responses programmatically. Browse interactively via
> [`index.html`](./index.html) (Swagger UI) once GitHub Pages is enabled.

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

## Integrate from Node.js (no SDK)

Node.js 18+ has `fetch` natively — no dependencies required.

```javascript
// monkai-trace.mjs
const API = "https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api";
const TOKEN = process.env.MONKAI_TRACER_TOKEN; // never hard-code
const NAMESPACE = "my-agent";

const headers = {
  "tracer_token": TOKEN,
  "Content-Type": "application/json",
};

async function post(path, body) {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`MonkAI ${path} → ${res.status}: ${text}`);
  }
  return res.json();
}

export async function traceConversation({ phone, name, userMsg, botResponse }) {
  // 1. Get or create the session for this user (recommended for HTTP clients
  //    in stateless environments — keeps the session alive across requests
  //    based on inactivity_timeout).
  const session = await post("/sessions/get-or-create", {
    namespace: NAMESPACE,
    user_id: phone,
    inactivity_timeout: 300,
  });

  // 2. Trace the LLM call.
  await post("/traces/llm", {
    session_id: session.session_id,
    model: "gpt-4",
    provider: "openai",
    input: { messages: [{ role: "user", content: userMsg }] },
    output: { content: botResponse },
    external_user_id: phone,
    external_user_name: name,
    external_user_channel: "whatsapp",
  });

  // 3. (Optional) Trace a tool call.
  await post("/traces/tool", {
    session_id: session.session_id,
    tool_name: "get_fuel_price",
    arguments: { fuel_type: "gasoline", city: "São Paulo" },
    result: { price: 5.89, currency: "BRL" },
    latency_ms: 120,
    agent: "fuel-assistant",
    external_user_id: phone,
    external_user_name: name,
    external_user_channel: "whatsapp",
  });
}

// Usage:
//   MONKAI_TRACER_TOKEN=tk_xxx node monkai-trace.mjs
await traceConversation({
  phone: "5521999998888",
  name: "Italo",
  userMsg: "Qual o preço da gasolina?",
  botResponse: "O preço atual da gasolina é R$ 5,89/L.",
});
```

### Retry with backoff (production-ready)

```javascript
async function postWithRetry(path, body, { maxAttempts = 3 } = {}) {
  let lastErr;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await post(path, body);
    } catch (err) {
      lastErr = err;
      // Only retry on transient errors (5xx / 429 / network).
      const status = Number((err.message.match(/→ (\d+)/) || [])[1] || 0);
      const transient = status >= 500 || status === 429 || status === 0;
      if (!transient || attempt === maxAttempts) throw err;
      const delayMs = 250 * 2 ** (attempt - 1); // 250, 500, 1000 ms
      await new Promise(r => setTimeout(r, delayMs));
    }
  }
  throw lastErr;
}
```

### TypeScript types from the OpenAPI spec

If you want strict typing in TS:

```bash
npx openapi-typescript@7 \
  https://raw.githubusercontent.com/BeMonkAI/monkai-trace/main/docs/openapi.yaml \
  -o ./monkai-trace.d.ts
```

Then:

```typescript
import type { paths } from "./monkai-trace.d.ts";
type LlmTrace = paths["/traces/llm"]["post"]["requestBody"]["content"]["application/json"];
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

### HTTP Status Codes by Endpoint

Every endpoint may return any of the codes below. Use this table to decide
how to handle each response programmatically.

| Code | Meaning | When it happens | Retry? |
|------|---------|-----------------|--------|
| `200` | OK | Request succeeded; payload is in the response body | — |
| `400` | Bad Request | Required field missing, invalid JSON, type mismatch, body too large | ❌ Fix payload first |
| `401` | Unauthorized | `tracer_token` header missing or invalid | ❌ Refresh token |
| `403` | Forbidden | Token is valid but does not have access to that namespace/resource | ❌ Check permissions |
| `429` | Too Many Requests | Rate limit hit (planned in Phase 3 of API roadmap) | ✅ Backoff + retry |
| `500` | Internal Server Error | Backend bug or transient failure | ✅ Backoff + retry (max 3) |
| `502` / `503` / `504` | Gateway / Upstream | Edge function or upstream temporarily unavailable | ✅ Backoff + retry (max 3) |

### Retry Guidance

- **Permanent errors (4xx except 429)** — fix the request, do not retry blindly.
- **Transient errors (429, 5xx)** — exponential backoff, ~3 attempts max.
- **Idempotency** — most endpoints are NOT yet idempotent (Phase 3 introduces
  `Idempotency-Key`). For retries today, prefer reusing the same `session_id`
  and let server-side dedup on `/records/upload` handle duplicates.

### Per-Endpoint Notes

| Endpoint | Common 4xx triggers |
|---|---|
| `POST /sessions/create` | `400` if `namespace` missing |
| `POST /sessions/get-or-create` | `400` if `namespace` or `user_id` missing |
| `POST /traces/llm` | `400` if `session_id` missing or unknown |
| `POST /traces/tool` | `400` if `session_id` or `tool_name` missing |
| `POST /traces/handoff` | `400` if `session_id`, `from_agent`, or `to_agent` missing |
| `POST /traces/log` | `400` if `message` missing AND neither `session_id` nor `namespace` provided |
| `POST /records/upload` | `400` if `records` empty or items missing required fields (`namespace`, `agent`, `msg`) |
| `POST /logs/upload` | `400` if `logs` empty or items missing `namespace`/`level`/`message` |
| `POST /record_query` `POST /logs/query` | `400` if `namespace` missing |
| `POST /records/export` `POST /logs/export` | `400` if `namespace` missing or unsupported `format` |
