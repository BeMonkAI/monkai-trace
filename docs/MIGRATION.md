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

## Summary table

| Change | Action | Required by |
|---|---|---|
| URL → `/v1/` | Search-replace base URL | Optional, recommended |
| Auth → `Bearer` | Replace one header | Optional, recommended |
| `X-Request-ID` | Generate per call, log on errors | Optional, recommended for prod |

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
