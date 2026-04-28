# Trace → Hub: Encryption + User-Editable Anonymization

**Date:** 2026-04-28
**Status:** Design approved, pending implementation plan
**Repos affected:** `monkai-trace` (SDK), `monkai-agent-hub` (frontend + Supabase edge functions)
**Owner:** Arthur Vaz

## Problem

Conversation records sent from `monkai-trace` SDK to `monkai-agent-hub` travel as plaintext over TLS and are persisted in plaintext in the Supabase column `agent_conversation_records.msg`. This exposes three risks:

1. **Database/storage leak (A):** A backup, dump, or unauthorized DB access exposes full conversation content.
2. **PII visible in operator-facing surfaces (C):** Hub dashboards, exports, logs, and screenshots contain raw CPF, email, phone, internal IDs, etc., even though only sanitized signal is needed for product use.
3. **Defense-in-depth on transit (D):** TLS protects against passive sniffing but a compromised proxy or MITM at customer perimeter could capture full payload before it reaches the Hub.

Out of scope: end-to-end encryption where MonkAI itself cannot read content (the "server-blind" model). Hub features (dashboards, AI summarization, search) require the Hub backend to be able to read content.

## Goals

- `agent_conversation_records` stores ciphertext only; plaintext is never written to disk.
- Per-tenant keys so a single key compromise has bounded blast radius and supports crypto-shredding for LGPD compliance.
- Customer-managed keys (BYOK) available as an opt-in for enterprise tenants.
- A baseline set of PII redaction rules runs client-side in the SDK on every record, before transmission, with no configuration required.
- A per-tenant editable rule set (toggles + custom regex) defined in the Hub, fetched and applied by the SDK with server-side reapplication as a safety net.
- Migration path that backfills existing plaintext rows without data loss.

## Non-goals

- Server-blind encryption (the "MonkAI cannot read" model). Explicitly rejected by the requester.
- LLM-based semantic anonymization (e.g., redact "anything that looks like a person name"). Considered and deferred — over-engineered for v1.
- Tokenization with reversible mapping vault. Considered and deferred to a future iteration.
- Searching by encrypted plaintext content (full-text search on `msg`). The Hub backend decrypts in memory for read paths; SQL search on encrypted content is not supported.

## Threat model

**In scope:**

- DB-level access by anyone other than the Hub backend (DBAs, leaked backups, unauthorized Supabase access).
- Operators reading PII in Hub UI, exports, logs.
- Network-level interception between SDK and Hub even though TLS is in place.

**Out of scope:**

- Compromise of a Hub backend instance with valid Vault credentials.
- Compromise of the customer's own infrastructure (the `monkai-trace` SDK process).
- Side-channel attacks against the cryptographic implementation.

## High-level architecture

```
[Customer app]
    │
    ▼
┌─────────────────────────────────────────┐
│ monkai-trace SDK                        │
│  1. Baseline anonymizer (hardcoded regex)│
│  2. Custom rules (fetch + cache 5min)   │
│  3. Envelope encrypt (random DEK,       │
│     wrapped with tenant pubkey)         │
└─────────────────────────────────────────┘
    │ HTTPS + sealed envelope
    ▼
┌─────────────────────────────────────────┐
│ monkai-api edge function                │
│  4. Unwrap envelope (privkey from Vault)│
│  5. Reapply server rules if SDK behind  │
│  6. Encrypt at rest (new DEK + per-     │
│     tenant KEK from Vault)              │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ Supabase                                │
│  agent_conversation_records:            │
│    msg_ciphertext, nonce, key_id,       │
│    encryption_version,                  │
│    anonymization_version                │
│  anonymization_rules (per tenant)       │
│  tenant_keys (envelope pubkey, KEK ref, │
│    BYOK config)                         │
└─────────────────────────────────────────┘
    │
    ▼ (Hub UI reads via edge function which decrypts)
[Hub frontend: viewer + /settings/security/anonymization]
```

### Trust boundaries

- **SDK** holds: tenant envelope pubkey, anonymization rules JSON, the user's `tracer_token`. Holds no decryption key.
- **Edge function** holds (via Vault) the tenant envelope private key and the at-rest KEK. Holds no rules locally — fetches the same rules table the SDK does and reapplies if the SDK's `anonymization_version` is behind.
- **Vault** is the only source of cryptographic material. Default backend is Supabase Vault. BYOK swaps the at-rest KEK source for the customer's Azure Key Vault.
- **Frontend** never sees ciphertext. Reads always come from the edge function decrypted.

## Components

### `monkai-trace` SDK

New modules:

- `monkai_trace/anonymizer/baseline.py` — `BaselineAnonymizer` with compiled regexes for: CPF, CNPJ, email (RFC 5322 simplified), Brazilian phone numbers (with and without country code), credit card (validated by Luhn), IPv4, IPv6, RG. Each rule is `{name, pattern, replacement}`. Always applied; no fetch involved.
- `monkai_trace/anonymizer/rules_client.py` — `RulesClient(tracer_token, hub_url).fetch()` performs `GET /v1/anonymization-rules`, caches in process memory with 300s TTL. On fetch failure, returns last successful cache plus a warning log. If never fetched successfully, blocks upload (does not send raw).
- `monkai_trace/crypto/envelope.py` — `seal(plaintext: bytes, tenant_pubkey: bytes) -> SealedEnvelope`. Algorithm: AES-256-GCM with a random 32-byte DEK plus RSA-OAEP-SHA256 key wrap. Pubkey is fetched once at startup via `GET /v1/tenant-pubkey` and cached in memory.

Modified:

- `monkai_trace/client.py`, `monkai_trace/async_client.py` — `upload_record()` and `upload_batch()` add a pipeline step: serialize messages → baseline anonymize → custom rules → envelope seal → POST. Payload schema gets new fields: `wrapped_dk`, `nonce`, `ciphertext`, `envelope_key_id`, `anonymization_version`. The legacy `messages` field is removed from outbound payloads (server rejects payloads that include it once Phase 3 lands).

### `monkai-api` edge function (Supabase)

New modules:

- `crypto/unseal.ts` — `unsealEnvelope(payload, tenantId)` calls `vault.decrypt('tenant_${id}_envelope_priv', wrapped_dk)` and AES-GCM-decrypts the ciphertext using the unwrapped DEK and the supplied nonce.
- `crypto/at_rest.ts` — `encryptForStorage(plaintext, tenantId)` returns `{ciphertext, nonce, key_id}`. Uses the per-tenant KEK in Vault to wrap a fresh per-record DEK. AES-256-GCM with random nonce. `decryptForStorage(row, tenantId)` is the inverse.
- `anonymization/server_apply.ts` — when `payload.anonymization_version < currentRulesVersion(tenantId)`, runs the rules introduced in versions `[payload.anonymization_version + 1 .. current]` against the unsealed plaintext before re-encrypting.

New endpoints:

- `GET /v1/tenant-pubkey` — returns `{key_id, pubkey, algorithm}` for the SDK.
- `GET /v1/anonymization-rules` — returns `{version, rules: {toggles, custom: []}}` for the authenticated tenant.
- `PUT /v1/anonymization-rules` — admin only; validates each rule (regex compiles, completes within a 10ms timeout against a 10kb test string, replacement references are valid), increments `version`.

### Supabase schema

```sql
ALTER TABLE agent_conversation_records
  ADD COLUMN msg_ciphertext bytea,
  ADD COLUMN nonce bytea,
  ADD COLUMN key_id text,
  ADD COLUMN encryption_version smallint DEFAULT 1,
  ADD COLUMN anonymization_version int DEFAULT 0;
-- existing column msg remains until Phase 5 backfill is complete.

CREATE TABLE anonymization_rules (
  tenant_id uuid PRIMARY KEY REFERENCES tenants(id),
  rules jsonb NOT NULL DEFAULT '{"toggles":{},"custom":[]}',
  version int NOT NULL DEFAULT 1,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid REFERENCES users(id)
);

CREATE TABLE tenant_keys (
  tenant_id uuid PRIMARY KEY REFERENCES tenants(id),
  envelope_pubkey bytea NOT NULL,
  envelope_key_id text NOT NULL,
  kek_id text NOT NULL,
  byok_provider text,        -- 'azure_keyvault' or null
  byok_key_uri text,
  byok_status text,          -- 'connected' | 'revoked' | null
  rotated_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

RLS: only tenant members can read their own rows in all three tables. The Hub backend uses the service role to read across tenants for admin functions.

### Hub frontend (`monkai-agent-hub/src`)

- `pages/settings/security/AnonymizationRules.tsx` — toggles for the baseline classes (which baseline regexes to apply on top of the always-on set), a CRUD table for custom rules (`name`, `pattern`, `replacement`), and a live preview against a test input. Saves via `PUT /v1/anonymization-rules`.
- `pages/settings/security/Encryption.tsx` (Phase 4) — BYOK status, "Connect Azure Key Vault" flow, role assignment instructions, connectivity health check.
- `components/conversation/EncryptionBadge.tsx` — `lucide-react` `Lock` icon plus tooltip "Encrypted at rest, key {key_id}".

### Key infrastructure

- **Default backend**: Supabase Vault stores per-tenant secrets `tenant_{id}_envelope_priv` and `tenant_{id}_kek`. RLS blocks direct user access; only the edge function service role reads.
- **BYOK adapter** (Phase 4): an `interface KeyProvider` with implementations `SupabaseVaultProvider` (default) and `AzureKeyVaultProvider`. The tenant's `tenant_keys.byok_provider` selects which one is used at runtime.
- **Rotation**: rotating means creating `kek_v2` in Vault, updating `tenant_keys.envelope_key_id` and `kek_id`, and recording `rotated_at`. Reads use the `key_id` stored on each row, so old ciphertext keeps working until its KEK version is destroyed. A background job can opt-in re-encrypt to the new KEK.

## Data flows

The flows below describe the post-Phase-3 end state. During Phases 1–2 the SDK posts the sanitized JSON over TLS without the envelope; the edge function still encrypts at rest. Phase 3 introduces the `wrapped_dk` / `nonce` / `ciphertext` payload and removes the legacy `messages` field.

### Write (Trace → Hub)

1. App calls `client.upload_record(messages=[...], namespace="x")`.
2. SDK serializes `messages` to JSON.
3. SDK applies `BaselineAnonymizer` to every `content`.
4. SDK calls `rules_client.get()` (cache hit, or refetch if expired).
5. SDK applies custom rules, annotates `anonymization_version=N`.
6. SDK generates a 32-byte random DEK, AES-GCM encrypts the JSON, generates a random 12-byte nonce.
7. SDK wraps the DEK with the tenant pubkey using RSA-OAEP-SHA256.
8. SDK POSTs `/v1/conversations` with `{namespace, agent, tokens, wrapped_dk, nonce, ciphertext, envelope_key_id, anonymization_version}`.
9. Edge function calls `vault.unwrap(wrapped_dk, tenant_id)` to recover the DEK.
10. Edge function AES-GCM-decrypts the ciphertext using the DEK and nonce.
11. Edge function reads `anonymization_rules.version`. If `payload.anonymization_version < current`, it reapplies the missing rules.
12. Edge function generates a new at-rest DEK, encrypts the (sanitized) plaintext, and wraps the DEK with the tenant KEK in Vault, producing `{msg_ciphertext, at_rest_key_id, nonce}`.
13. INSERT into `agent_conversation_records`. The `msg` column is left null on writes from this point forward.
14. Edge function zeroes plaintext buffers in memory before returning 200.

### Read (Hub UI → user)

1. Authenticated UI calls `GET /v1/conversations/:id`.
2. Edge function SELECTs the row and validates RLS (tenant match).
3. Edge function calls `vault.unwrap(at_rest_key_id, tenant_id)` to recover the at-rest DEK.
4. Edge function AES-GCM-decrypts `msg_ciphertext` using the DEK and stored `nonce`.
5. Returns plaintext JSON to the frontend.
6. Frontend renders the viewer plus the encryption badge.

### Rules update (admin in the Hub)

1. Admin opens `/settings/security/anonymization`.
2. UI loads rules via `GET /v1/anonymization-rules`.
3. Admin edits — toggles baseline classes, adds custom rules with `{name, pattern, replacement}`.
4. UI runs a client-side preview against a test input before saving.
5. UI sends `PUT /v1/anonymization-rules` with the new JSON.
6. Edge function validates each regex: compiles it, runs it against a 10kb test input with a 10ms timeout, rejects catastrophic patterns. Validates replacement references.
7. Edge function increments `version`, saves, returns `{version: N+1}`.
8. SDKs in flight pick up the new rules on their next 5-minute fetch tick. Records uploaded with the older version are reapplied server-side at write time (step 11 of the write flow).

### Pubkey rotation (operational)

1. Admin or scheduled job runs `vault.create_key('tenant_{id}_envelope_v2')`.
2. Updates `tenant_keys.envelope_pubkey` and `envelope_key_id`.
3. SDKs with cached pubkey continue working until cache expires (5 minutes); new uploads use the fresh pubkey.
4. The previous private key is preserved in Vault for unwrapping in-flight payloads sealed with the older pubkey.
5. After a 24-hour safety window, the old envelope private key may be destroyed.

### BYOK (Phase 4)

1. Admin connects: provides Azure Key Vault URI and a service principal granted "Key Vault Crypto User" on the target key.
2. Hub tests connectivity by wrapping a probe value through the customer's KV. On success, sets `byok_status = 'connected'`.
3. Subsequent writes use the customer's KV as the at-rest KEK source instead of Supabase Vault.
4. If the customer revokes access, writes return `503 byok_unavailable` and reads return `{encrypted: true, key_unavailable: true}`. The UI surfaces an "Unavailable, contact admin" state.
5. Crypto-shredding: deleting the customer's KEK in their KV makes all of that tenant's ciphertext permanently unrecoverable, satisfying LGPD right-to-erasure.

### Backfill (Phase 5)

1. A cron-driven Supabase function runs hourly and selects up to 1000 rows where `msg IS NOT NULL AND msg_ciphertext IS NULL`.
2. For each row: encrypts the plaintext `msg` with the current tenant KEK, populates `msg_ciphertext`, `nonce`, `key_id`, `encryption_version`. The `msg` column is preserved at this point.
3. After the row's INSERT/UPDATE commits, a second statement runs `UPDATE SET msg = NULL` on the same row.
4. Telemetry counters: `backfill_pending`, `backfill_done`, `backfill_failed`.
5. When `backfill_pending = 0` for 7 consecutive days, an `ALTER TABLE DROP COLUMN msg` migration runs.

## Error handling

The non-negotiable rule: the SDK never falls back to sending plaintext, and the edge function never persists plaintext. Any unrecoverable cryptographic failure drops the record locally and logs.

### SDK

| Scenario | Behavior |
|---|---|
| `GET /v1/tenant-pubkey` fails at startup | Block uploads. Retry with exponential backoff (1s, 5s, 30s, 5min). After 1h with no success, raise `MonkAIPubkeyUnavailable`. |
| `GET /v1/anonymization-rules` fails | If a valid cache exists, use it and warn. If never fetched successfully, block upload. |
| Malformed custom rule in cache | Skip just that rule with a warning. Other rules still apply. |
| AES-GCM encrypt fails | `logger.exception`, drop the record, increment `monkai_trace_encrypt_failures`. No retry — failure is local and deterministic. |
| Pubkey wrap fails (rotation race) | Refetch pubkey, retry once. If it still fails, drop and log. |
| POST `/v1/conversations` returns 4xx | Do not retry — client-side error. `logger.exception` with response body. |
| POST `/v1/conversations` returns 5xx or times out | Retry with the existing backoff. After max retries, drop and log. |

### Edge function

| Scenario | Behavior |
|---|---|
| Envelope unwrap fails | Return `400 invalid_envelope` with a `correlation_id`. Log `tenant_id` and `key_id`. Never log ciphertext. |
| Vault unavailable | Return `503 vault_unavailable`. Page ops. SDK retries. |
| `payload.anonymization_version` ahead of server (cache desync) | Accept; do not reapply. Warn-level log. |
| Server rule reapply triggers regex catastrophic backtrack | Per-rule 50ms timeout. On timeout, skip the rule, log, alert ops — the rule must be rewritten. |
| At-rest encrypt fails | Return `500 storage_encrypt_failed`. Log. The record is **not** inserted. SDK retries. |
| At-rest decrypt fails on read (key destroyed prematurely) | UI receives `{encrypted: true, decrypt_error: "key_destroyed"}`. Frontend shows "Content unrecoverable (key rotated)". Log with `key_id`. |
| BYOK revoked | Read: `{encrypted: true, key_unavailable: true}`. Write: `503 byok_unavailable`. SDK retries on a longer backoff; record remains queued. |

### `PUT /v1/anonymization-rules`

| Scenario | Behavior |
|---|---|
| Regex fails to compile | `400 invalid_regex` with `rule_index, error`. Not persisted. |
| Regex compiles but exceeds the 10ms test timeout | `400 regex_too_slow`. |
| Replacement references a non-existent capture group | `400 invalid_replacement`. |
| Concurrent edit (stale version) | `409 version_conflict`. UI reloads and shows a diff. |

### Logging and observability

- Plaintext is never written to logs, full stop. If a `logger.exception` call would occur in a frame where plaintext is in scope, the exception handler must construct its message from non-content fields only.
- Metrics: `encrypt_latency_ms`, `decrypt_latency_ms`, `vault_calls_total`, `anonymization_apply_ms`, `rules_fetch_failures`, `backfill_pending`, `backfill_done`, `backfill_failed`.
- Critical alerts: `vault_unavailable` for >1 minute, `decrypt_failures` exceeding 0.1% of read rate, any `backfill_failed` outside expected ranges.

### Memory hygiene

- Edge function: clear plaintext buffers (`Buffer.fill(0)`) before returning the response.
- SDK Python: rely on the GC; do not pass plaintext between threads or accumulate it in long-lived structures.

## Testing

### SDK

Unit tests:

- Each baseline regex with at least 5 positive cases and 5 negative cases (e.g., a number that is not a CPF). Snapshot test for redacted output.
- `BaselineAnonymizer.apply()` against messages with multiple PII types in the same content.
- `RulesClient` cache TTL respected; stale cache used when fetch fails; upload blocked when never fetched.
- `crypto.envelope.seal()` plus roundtrip with `unseal()` (test uses an in-memory keypair).
- `client.upload_record` end-to-end with a transport mock — assert the wire payload contains no raw PII and no plaintext content.

Integration:

- SDK against a locally running edge function (Supabase CLI). Upload then read; assert read output equals what the SDK applied (sanitized).
- Custom-rule-just-added case: SDK with a stale cache uploads `version N-1`. Server reapplies the diff. Read returns the correctly sanitized content.

### Edge function

Unit tests (Deno test):

- `unsealEnvelope` with a mocked Vault: happy path plus corrupted DEK plus invalid `key_id`.
- `encryptForStorage` / `decryptForStorage` roundtrip; `key_id` is correct; graceful failure when KEK does not exist.
- `serverApplyRules` for `payload.anonymization_version` `<`, `==`, and `>` server version.
- `validateRegex` on PUT rules: accepts normal regexes, rejects `(a+)+$` (catastrophic), rejects malformed patterns, rejects `$N` references out of range.

Integration:

- POST a valid envelope → row in DB is encrypted (`msg_ciphertext IS NOT NULL`); plaintext column never receives data (`msg IS NULL`).
- GET conversation → correct plaintext returned.
- Vault returning 503 → response 503 propagates correctly to the SDK.

### Schema and migration

- Migrations run against a test DB seeded with 10k synthetic rows. Post-backfill, every row has `msg_ciphertext IS NOT NULL`. Post-cleanup, every row has `msg IS NULL`.
- Rollback test: reversing the migration must not lose data (the `msg` plaintext column is preserved in parallel until cleanup).

### Hub frontend

- `AnonymizationRules.tsx`: Vitest + RTL for rule CRUD, preview against a test input, basic client-side regex validation.
- `EncryptionBadge`: snapshot tests for varying `key_id` values.

### Compliance and red-team

- **Plaintext audit**: a SQL query that fails the test if any row in `agent_conversation_records` has `msg IS NOT NULL` after Phase 5 completes. Runs daily as a cron in production.
- **DB dump test**: dump the table and grep for known PII patterns (CPF format, common email domains). Zero hits expected.
- **Vault isolation**: a test that selects ciphertext directly and attempts to decrypt without a Vault key — must fail.
- **Key destruction**: in a staging environment, destroy a tenant KEK and confirm reads return a structured error rather than a 500.

### Performance

- Write latency: target +<15ms p50, +<30ms p95 versus pre-encryption baseline.
- Read latency: target +<10ms p50.
- Batch throughput: 100 records/request must not degrade by more than 20%.
- Backfill: sustains 1000 rows/minute without degrading production query latency.

### CI

- Tests run on every PR in `monkai-trace` and `monkai-agent-hub`.
- The plaintext-audit query runs as a daily cron in production and alerts if the count exceeds zero outside the migration window.

## Phasing

Implementation lands in five phases, each independently shippable behind a feature flag where useful. The spec is approved as a whole; the implementation plan will define gating between phases.

- **Phase 1 — At-rest encryption + baseline anonymization.** New schema columns, per-tenant KEK in Supabase Vault, baseline regexes hardcoded in the SDK, edge function encrypts before INSERT, decrypts on read. The `msg` plaintext column remains and continues to be written in parallel during this phase to keep rollback cheap. Target: ~1 week.
- **Phase 2 — User-editable rules.** `anonymization_rules` table, GET/PUT endpoints, regex validator, frontend `AnonymizationRules.tsx`, SDK `RulesClient`, server-side reapply for version drift. Target: ~1 week.
- **Phase 3 — Envelope encryption (defense in depth on transit).** `tenant-pubkey` endpoint, SDK envelope `seal`, edge function `unseal`, payload schema migration. After this phase, the legacy `messages` plaintext field is rejected by the server. Target: ~3 days.
- **Phase 4 — BYOK.** `KeyProvider` interface plus `AzureKeyVaultProvider`, BYOK fields in `tenant_keys`, frontend connect flow, error handling for revoked-key state. Target: ~1–2 weeks.
- **Phase 5 — Backfill and cleanup.** Cron-driven backfill function, per-row encrypt-then-null on `msg`, plaintext-audit cron, final `ALTER TABLE DROP COLUMN msg` once `backfill_pending = 0` for 7 days. Target: ~3 days plus the time the job needs to run.

## Open questions

None. All major forks (threat model, anonymization location, key management, rule UX, phasing) were resolved during brainstorming.

## References

- `monkai-trace/monkai_trace/client.py` — current `upload_record` implementation.
- `monkai-agent-hub/supabase/functions/monkai-api/index.ts` — current write/read paths and `agent_conversation_records.msg` access.
- Supabase Vault: https://supabase.com/docs/guides/database/vault
- Azure Key Vault Crypto API (BYOK target): https://learn.microsoft.com/en-us/azure/key-vault/keys/about-keys
