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

### Planned (Phase 3)
- `Idempotency-Key` header for `POST /traces/*` and `POST /v1/traces/batch`.
- Batch endpoint `POST /v1/traces/batch` for mixed `llm`/`tool`/`handoff`/`log` payloads.
- Rate-limit response headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`).
- `GET /v1/health` health-check endpoint.

### Planned (Phase 2 — remaining)
- Structured error envelope `{ "error": { "code": "...", "message": "...", "request_id": "..." } }`.
- Custom domain `https://api.monkai.ai/trace/v1`.

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
