# MonkAI Trace REST API — Migration Guide

This guide is for clients integrating with the MonkAI Trace REST API
(not for the Python SDK — the SDK upgrades are tracked in
[`../CHANGELOG.md`](../CHANGELOG.md)).

The current contract is **v1** ([API changelog](./API_CHANGELOG.md)).
Two forward-looking changes happened on 2026-05-01 that are
**non-breaking** but recommended:

1. URL prefix → `/v1/`
2. Auth header → `Authorization: Bearer`

Plus a behaviour change you can opt into for free:

3. `X-Request-ID` round-trip for support correlation

---

## 1. URL prefix → `/v1/`

### Before

```
POST https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api/sessions/create
```

### After (recommended)

```
POST https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api/v1/sessions/create
```

### Why

Pinning to `/v1/` guarantees the contract you integrated against won't
change under your feet. Future breaking changes will land under `/v2/`,
and you can opt in when ready. Unversioned URLs keep working
indefinitely as a `v1` alias, but new integrations should pin.

### How

Search and replace your base URL:

```diff
- BASE_URL = "https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api"
+ BASE_URL = "https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api/v1"
```

Generated clients pick this up automatically — the OpenAPI spec lists
`/v1/` as the primary `servers[0]` entry.

---

## 2. Auth header → `Authorization: Bearer`

### Before

```http
tracer_token: tk_abc123...
```

### After (recommended)

```http
Authorization: Bearer tk_abc123...
```

### Why

`Authorization: Bearer` is the RFC 6750 standard. Tools, generated
clients, API gateways, and HTTP libraries support it natively. The
legacy `tracer_token` custom header sometimes breaks integrations with
no-code platforms or proxies that strip non-standard headers.

### How

#### curl

```diff
- curl -H "tracer_token: tk_abc"
+ curl -H "Authorization: Bearer tk_abc"
```

#### Node.js (fetch)

```diff
  const headers = {
-   "tracer_token": process.env.MONKAI_TRACER_TOKEN,
+   "Authorization": `Bearer ${process.env.MONKAI_TRACER_TOKEN}`,
    "Content-Type": "application/json",
  };
```

#### Python (requests)

```diff
  headers = {
-     "tracer_token": TRACER_TOKEN,
+     "Authorization": f"Bearer {TRACER_TOKEN}",
      "Content-Type": "application/json",
  }
```

### Precedence (during the deprecation window)

If a client sends **both** headers, the legacy `tracer_token` wins.
This is deterministic and lets you migrate one service at a time
without surprises. We will announce a deprecation date for
`tracer_token` only after the SDK migration completes — for now it
continues to work indefinitely.

---

## 3. `X-Request-ID` for support correlation

This is **opt-in** and purely additive — nothing breaks if you ignore
it. Highly recommended for production integrations.

### Behaviour

- Every response (200, 4xx, 5xx) carries `X-Request-ID: <id>`.
- If the client sends `X-Request-ID: <id>` in the request, the value
  is **preserved** in the response (round-trip). This lets you
  correlate logs across multiple services without coordination.
- If the client doesn't send one, the server generates a UUIDv4.

### Recommended client pattern

Generate the ID once per logical operation (one user request, one
distributed trace) and pass it through:

```javascript
const requestId = crypto.randomUUID();
const res = await fetch(url, {
  headers: { "Authorization": `Bearer ${token}`, "X-Request-ID": requestId },
  ...
});
console.log("trace", requestId, "→", res.status);

if (!res.ok) {
  // Quote requestId in any error report or support ticket.
  throw new Error(`Trace ${requestId} failed: ${res.status}`);
}
```

When something goes wrong, the `X-Request-ID` you logged on the client
side is enough for MonkAI support to pinpoint the exact server-side
log entry — no more "what time did this happen?" ping-pong.

---

## 4. Error response shape

Pre-Phase-2 every error response was a bare string under `error`:

```json
{ "error": "Missing tracer_token header" }
```

Phase 2 wraps it in a structured envelope:

```json
{
  "error": {
    "code": "missing_token",
    "message": "Missing tracer token (use ...)",
    "request_id": "8c5d96f1-..."
  }
}
```

### Why

`error.code` is stable, machine-readable, and lets clients branch
deterministically without fragile substring matching of the message.
`error.request_id` mirrors the `X-Request-ID` response header so
clients that log only the JSON body can still correlate with server
logs.

### Compatibility table

| Client pattern | Behaviour after migration |
|---|---|
| `if (response.error)` (truthy check) | ✅ Works — `error` is still truthy (object instead of string) |
| `console.log(response.error)` (renders as string) | ⚠️ Logs `[object Object]` — switch to `response.error.message` |
| `response.error.code` (new) | ✅ Recommended — stable across versions |
| `response.error.request_id` (new) | ✅ Use in support tickets and bug reports |

### How

#### JavaScript / TypeScript

```diff
  if (!res.ok) {
    const body = await res.json();
-   throw new Error(`MonkAI failed: ${body.error}`);
+   throw new Error(`MonkAI ${body.error.code}: ${body.error.message} (req ${body.error.request_id})`);
  }
```

#### Python

```diff
  if r.status_code >= 400:
      body = r.json()
-     raise RuntimeError(f"MonkAI: {body['error']}")
+     err = body["error"]
+     raise RuntimeError(f"MonkAI {err['code']}: {err['message']} (req {err['request_id']})")
```

### Branching on `code`

The recommended pattern is to branch on the canonical code, not on
the message:

```javascript
const { error } = await res.json();
switch (error.code) {
  case "missing_token":
  case "invalid_token":
  case "token_expired":
    return refreshToken();
  case "namespace_taken":
  case "namespace_too_similar":
    return suggestAlternativeNamespace(error);
  case "internal_error":
    return retryWithBackoff();
  default:
    throw new Error(`Unhandled MonkAI error: ${error.code}`);
}
```

The full list of canonical codes is in
[`http_rest_api.md`](./http_rest_api.md#canonical-error-codes) and
the OpenAPI [`Error` schema](./openapi.yaml).

### Endpoints with extra context

A few endpoints emit context fields **next to** the envelope:

- `POST /namespace/register` (409 with `similar_namespaces` and
  `suggestion`, or 500 with `details`)
- `POST /records/upload` and `POST /logs/upload` on namespace gating
  (403 with `unregistered_namespaces` and `namespaces_without_token`)
- `PUT /anonymization-rules` (400 with `issues` array)

The shape is `{ error: {...envelope}, ...extra_fields }` — the
envelope is always the first key and always carries `code`, `message`,
and `request_id`. Treat the extra fields as documented per endpoint.

---

## 5. Safe retries with `Idempotency-Key`

This is **opt-in** and purely additive — clients that don't send the
header keep the pre-Phase-3 behaviour. Strongly recommended for any
production code that retries.

### Behaviour

Trace endpoints (`/v1/traces/llm`, `/tool`, `/handoff`, `/log`,
`/traces/batch`) accept an `Idempotency-Key` request header. The
server caches the response under `(tenant, key)` for 24h:

| Same key + same body | Same key + different body | Different / missing key |
|---|---|---|
| Cached replay (no DB inserts, no token charges) with `Idempotency-Replay: true` | `422 idempotency_key_conflict` | Fresh execution |

Errors are **not** cached, so retrying a failed call with the same
key naturally re-executes.

### Recommended client pattern

Generate one UUID per **logical operation** and reuse it across all
retries of that operation:

```javascript
async function trackOnce(makeRequest) {
  const opId = crypto.randomUUID();          // generated once
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      return await makeRequest({ "Idempotency-Key": opId });
    } catch (err) {
      if (err.transient && attempt < 3) continue;
      throw err;
    }
  }
}
```

The first attempt records the response; if the network drops between
the server writing the DB and the client reading the body, retry
attempts replay the same response — the trace is never duplicated
and credits are never double-charged.

### Reading the replay headers

```javascript
const res = await fetch(url, {
  headers: { "Authorization": `Bearer ${token}`, "Idempotency-Key": opId },
  ...
});

if (res.headers.get("Idempotency-Replay") === "true") {
  console.log(
    "Replayed result of original request",
    res.headers.get("Idempotency-Original-Request-ID"),
  );
}
```

### Conflict handling

If you reuse a key with a different body, the server returns
`422 idempotency_key_conflict`. The fix is to pick a new key (or
fix the body so it matches the original):

```diff
- // BUG: same key, body changed across retries
- await fetch(url, { headers: { "Idempotency-Key": "static-key" }, body: latestBody });
+ const opId = crypto.randomUUID();
+ await fetch(url, { headers: { "Idempotency-Key": opId }, body: latestBody });
```

### Endpoints supported

| Endpoint | Idempotency support |
|---|---|
| `POST /v1/traces/llm` | ✅ |
| `POST /v1/traces/tool` | ✅ |
| `POST /v1/traces/handoff` | ✅ |
| `POST /v1/traces/log` | ✅ |
| `POST /v1/traces/batch` | ✅ |
| Other endpoints | Not yet — body-level dedup applies on bulk uploads |

---

## Summary table

| Change | Action | Required by |
|---|---|---|
| URL → `/v1/` | Search-replace base URL | Optional, recommended |
| Auth → `Bearer` | Replace one header | Optional, recommended |
| `X-Request-ID` | Generate per call, log on errors | Optional, recommended for prod |
| Error shape | Read `error.message` and `error.code` | Required if you rendered `error` as a string |
| `Idempotency-Key` | Generate per logical operation, reuse across retries | Optional, recommended for prod |

---

## Compatibility window

| Item | Status | Earliest removal |
|---|---|---|
| Unversioned `/<path>` URLs | Aliased to `/v1/` | Not announced |
| `tracer_token` request header | Fully supported | Not announced |
| Bulk endpoints `/records/upload` and `/logs/upload` | First-class (Python SDK uses them) | No plan to remove |

Removals will be announced with at least one minor version of advance
notice in [`API_CHANGELOG.md`](./API_CHANGELOG.md). When a removal date
is set, this guide will get a banner at the top.
