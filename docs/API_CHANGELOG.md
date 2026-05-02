# MonkAI Trace REST API — Changelog

This file tracks changes to the **REST API contract** (the surface
documented in [`openapi.yaml`](./openapi.yaml) and [`http_rest_api.md`](./http_rest_api.md)).
It is intentionally separate from [`../CHANGELOG.md`](../CHANGELOG.md), which
tracks the Python SDK package.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The API itself is versioned via the URL prefix (`/v1/`) — breaking
changes will land under a new prefix (`/v2/`) while older versions
keep working during a deprecation window.

## [Unreleased]

### Planned (Phase 3 — remaining)
- Rate-limit response headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`).

### Planned (Phase 2 — remaining)
- Custom domain `https://api.monkai.ai/trace/v1`.

## [v1.3] — 2026-05-02

### Added
- **`Idempotency-Key` request header** on `POST /v1/traces/llm`,
  `/v1/traces/tool`, `/v1/traces/handoff`, `/v1/traces/log`, and
  `/v1/traces/batch`. Same key + identical body within 24h → cached
  replay (no DB inserts, no token charges). Same key + different body
  → `422 idempotency_key_conflict`. Different/missing key → fresh
  execution. References:
  [BeMonkAI/monkai-agent-hub#25](https://github.com/BeMonkAI/monkai-agent-hub/pull/25)
  (edge function + migration) and
  [`docs/MIGRATION.md`](./MIGRATION.md#5-safe-retries-with-idempotency-key)
  (client adoption guide).
- **`Idempotency-Replay`** response header (`"true"` only) on cached
  replays.
- **`Idempotency-Original-Request-ID`** response header on cached
  replays — mirrors the `X-Request-ID` of the first call so logs can
  be correlated across retries.
- New canonical error code: **`idempotency_key_conflict`**
  (HTTP 422). Listed in the OpenAPI `Error` schema enum.

### Notes
- Errors are **not** cached. Retrying a failed call with the same key
  naturally re-executes — no risk of getting "stuck" replaying a
  transient failure.
- Cache failures (DB unavailable) are degraded to a miss: the request
  proceeds normally without idempotency protection, with a warning
  logged server-side. Idempotency is never a single point of failure.
- Storage: per-tenant Postgres table `monkai_idempotency_keys` with
  24h retention via `expires_at`. RLS-locked, service-role only.

## [v1.2] — 2026-05-02

### Added
- **`GET /v1/health`** (and `HEAD /v1/health`) — unauthenticated
  liveness probe returning `{status, service, api_version, timestamp}`.
  No auth required; suitable for monitors, uptime checks, and
  post-deploy smoke tests. Reference: [BeMonkAI/monkai-agent-hub#22](https://github.com/BeMonkAI/monkai-agent-hub/pull/22).
- **`POST /v1/traces/batch`** — submit up to 100 mixed traces
  (`llm` | `tool` | `handoff` | `log`) in a single request. Partial
  success is allowed: response is always 200 when the outer envelope
  is well-formed, with per-item `status: "ok" | "error"`. Cuts N
  round-trips down to 1 for clients that produce multiple traces per
  user interaction. Reference: [BeMonkAI/monkai-agent-hub#23](https://github.com/BeMonkAI/monkai-agent-hub/pull/23).

## [v1.1] — 2026-05-02

### Added
- **Structured error envelope** for every 4xx/5xx response. The body
  shape is now `{ "error": { "code": "...", "message": "...", "request_id": "..." } }`
  instead of a bare `{ "error": "string" }`. Clients should branch on
  `error.code` (machine-readable, stable). See
  [`MIGRATION.md`](./MIGRATION.md#4-error-response-shape) for the
  client-side change. Reference: [BeMonkAI/monkai-agent-hub#20](https://github.com/BeMonkAI/monkai-agent-hub/pull/20)
  + [BeMonkAI/monkai-agent-hub#21](https://github.com/BeMonkAI/monkai-agent-hub/pull/21).
- **16 canonical error codes**: `bad_request`, `missing_field`,
  `invalid_payload`, `namespace_taken`, `namespace_too_similar`,
  `unauthorized`, `missing_token`, `invalid_token`, `token_expired`,
  `token_inactive`, `forbidden`, `not_found`, `internal_error`,
  `encryption_error`, `anonymization_error`. Listed in the OpenAPI
  `Error` schema; clients should treat unknown codes as the generic
  family code.

### Compatibility
- Clients that only check `response.error` for truthiness keep working
  unchanged.
- Clients that rendered `error` directly as a string now see
  `[object Object]` and should switch to `error.message`.
- The Python SDK stringifies the entire JSON via
  `str(response.json())`; its exception messages remain informative
  without code changes.

## [v1] — 2026-05-01

First versioned contract. Snapshot of what is currently live in
production (`monkai-api` edge function on Supabase project
`lpvbvnqrozlwalnkvrgk`, version 134).

### Added
- **`/v1/` URL prefix** — every endpoint now also responds under
  `/functions/v1/monkai-api/v1/<path>`. Unversioned URLs continue to
  work for backwards compatibility. New integrations should pin to
  `/v1/`. Reference: [BeMonkAI/monkai-agent-hub#16](https://github.com/BeMonkAI/monkai-agent-hub/pull/16).
- **`Authorization: Bearer tk_<token>`** auth scheme. The legacy
  `tracer_token` request header still works; both schemes accept the
  same `tk_<hex>` token. New integrations should prefer `Bearer`.
  Reference: [BeMonkAI/monkai-agent-hub#17](https://github.com/BeMonkAI/monkai-agent-hub/pull/17).
- **`X-Request-ID` response header** on every response (200, 4xx, 5xx).
  Round-trips when the client sends one; otherwise a UUIDv4 is
  generated. Useful for support correlation and distributed traces.
  Reference: [BeMonkAI/monkai-agent-hub#18](https://github.com/BeMonkAI/monkai-agent-hub/pull/18).
- **OpenAPI 3.1 spec** at [`docs/openapi.yaml`](./openapi.yaml) covering
  all 12 endpoints. Generates clients via `openapi-typescript`,
  `openapi-generator`, etc. Browse interactively at
  [`docs/index.html`](./index.html) (ReDoc).
- **`.http` collection** at [`examples/monkai_trace.http`](../examples/monkai_trace.http)
  ready for VS Code REST Client and JetBrains HTTP Client.

### Notes
- `tracer_token` header **wins** when both `Authorization: Bearer` and
  `tracer_token` are present on the same request — deterministic during
  the deprecation window.
- The bulk endpoints `POST /records/upload` and `POST /logs/upload` are
  the primary path used by the Python SDK and remain fully supported.

## [pre-v1]

Endpoints existed unversioned before 2026-05-01. They keep working
indefinitely; treat them as `v1` semantics until further notice.
