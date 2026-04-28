# Encryption Phase 1: At-Rest Encryption + Baseline Anonymization

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship at-rest encryption of conversation content per tenant, plus a hardcoded baseline anonymizer in the SDK that strips common PII (CPF, CNPJ, email, phone, credit card, IPs, RG) before transmission.

**Architecture:** SDK applies regex-based anonymization client-side. Edge function `monkai-api` encrypts the (already-sanitized) plaintext using a per-tenant KEK stored in Supabase Vault before INSERT, and decrypts on SELECT. The legacy `msg` plaintext column is left in place during this phase for cheap rollback; ciphertext lives in new columns alongside.

**Tech Stack:**
- SDK: Python 3.8+, `re` stdlib (regex), existing `requests`/`aiohttp`
- Edge function: Deno/TypeScript, Web Crypto API (`AES-GCM`), Supabase JS client
- DB: Supabase Postgres + Supabase Vault
- Repos: `monkai-trace` (SDK) and `monkai-agent-hub` (frontend + supabase functions/migrations)

**Spec reference:** `monkai-trace/docs/superpowers/specs/2026-04-28-trace-hub-encryption-anonymization-design.md`

---

## File structure

**`monkai-trace`** (Python SDK):
- Create `monkai_trace/anonymizer/__init__.py` — package init, exports `BaselineAnonymizer`
- Create `monkai_trace/anonymizer/baseline.py` — `BaselineAnonymizer` class and `BASELINE_RULES` list
- Create `tests/test_baseline_anonymizer.py` — unit tests for every regex
- Modify `monkai_trace/client.py` — apply anonymizer in `upload_record` and `_upload_records_chunk`
- Modify `monkai_trace/async_client.py` — same for async
- Modify `monkai_trace/__init__.py` — export `BaselineAnonymizer` for advanced users

**`monkai-agent-hub`** (frontend + supabase functions):
- Create `supabase/migrations/20260428120000_encryption_phase1.sql` — schema changes
- Create `supabase/functions/_shared/vault.ts` — wrapper around Supabase Vault RPC
- Create `supabase/functions/_shared/crypto/at_rest.ts` — encryptForStorage / decryptForStorage
- Create `supabase/functions/_shared/crypto/at_rest_test.ts` — Deno tests
- Modify `supabase/functions/monkai-api/index.ts` — call encrypt before INSERT, decrypt before returning rows
- Create `scripts/provision_tenant_keys.ts` — one-off script to create KEK for every existing tenant

---

## Task 1: SDK — create anonymizer package skeleton

**Files:**
- Create: `monkai-trace/monkai_trace/anonymizer/__init__.py`
- Create: `monkai-trace/monkai_trace/anonymizer/baseline.py`

- [ ] **Step 1: Write the failing test**

Create `monkai-trace/tests/test_baseline_anonymizer.py`:

```python
"""Tests for BaselineAnonymizer hardcoded PII rules."""

import pytest
from monkai_trace.anonymizer.baseline import BaselineAnonymizer


def test_anonymizer_can_be_instantiated():
    a = BaselineAnonymizer()
    assert a is not None


def test_apply_returns_string_for_string_input():
    a = BaselineAnonymizer()
    result = a.apply("hello world")
    assert isinstance(result, str)
    assert result == "hello world"
```

- [ ] **Step 2: Run the test, confirm it fails**

```bash
cd monkai-trace
pytest tests/test_baseline_anonymizer.py -v
```

Expected: `ImportError: No module named 'monkai_trace.anonymizer'`.

- [ ] **Step 3: Create the package skeleton**

`monkai_trace/anonymizer/__init__.py`:

```python
"""Client-side PII anonymization for monkai-trace."""

from monkai_trace.anonymizer.baseline import BaselineAnonymizer, BASELINE_RULES

__all__ = ["BaselineAnonymizer", "BASELINE_RULES"]
```

`monkai_trace/anonymizer/baseline.py`:

```python
"""Hardcoded baseline PII redaction rules. Always applied; no fetch involved."""

from dataclasses import dataclass
from typing import List, Pattern
import re


@dataclass(frozen=True)
class BaselineRule:
    name: str
    pattern: Pattern[str]
    replacement: str


BASELINE_RULES: List[BaselineRule] = []


class BaselineAnonymizer:
    """Applies BASELINE_RULES to text content. No configuration."""

    def __init__(self, rules: List[BaselineRule] = BASELINE_RULES):
        self._rules = rules

    def apply(self, text: str) -> str:
        if not text:
            return text
        for rule in self._rules:
            text = rule.pattern.sub(rule.replacement, text)
        return text
```

- [ ] **Step 4: Run tests — should pass**

```bash
pytest tests/test_baseline_anonymizer.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add monkai_trace/anonymizer tests/test_baseline_anonymizer.py
git commit -m "feat(anonymizer): add BaselineAnonymizer skeleton"
```

---

## Task 2: SDK — implement all baseline regex rules

**Files:**
- Modify: `monkai-trace/monkai_trace/anonymizer/baseline.py`
- Modify: `monkai-trace/tests/test_baseline_anonymizer.py`

- [ ] **Step 1: Write failing tests for every PII class**

Append to `tests/test_baseline_anonymizer.py`:

```python
@pytest.mark.parametrize("text, expected_redacted", [
    ("CPF 123.456.789-09 do cliente", "CPF [CPF] do cliente"),
    ("12345678909 sem mascara", "[CPF] sem mascara"),
])
def test_redacts_cpf(text, expected_redacted):
    assert BaselineAnonymizer().apply(text) == expected_redacted


def test_does_not_redact_invalid_cpf_length():
    assert BaselineAnonymizer().apply("number 1234") == "number 1234"


@pytest.mark.parametrize("text, expected_redacted", [
    ("CNPJ 12.345.678/0001-95", "CNPJ [CNPJ]"),
    ("12345678000195 raw", "[CNPJ] raw"),
])
def test_redacts_cnpj(text, expected_redacted):
    assert BaselineAnonymizer().apply(text) == expected_redacted


@pytest.mark.parametrize("text, expected_redacted", [
    ("contact arthur@monkai.com.br please", "contact [EMAIL] please"),
    ("first.last+tag@sub.example.io", "[EMAIL]"),
])
def test_redacts_email(text, expected_redacted):
    assert BaselineAnonymizer().apply(text) == expected_redacted


@pytest.mark.parametrize("text, expected_redacted", [
    ("call (11) 99999-1234 today", "call [PHONE] today"),
    ("+55 11 9 9999-1234", "[PHONE]"),
    ("11999991234", "[PHONE]"),
])
def test_redacts_brazilian_phone(text, expected_redacted):
    assert BaselineAnonymizer().apply(text) == expected_redacted


def test_redacts_credit_card_with_luhn():
    # 4111 1111 1111 1111 is the Visa test card (passes Luhn)
    assert BaselineAnonymizer().apply("card 4111 1111 1111 1111 ok") == "card [CARD] ok"


def test_does_not_redact_non_luhn_card_number():
    # 4111 1111 1111 1112 fails Luhn
    assert BaselineAnonymizer().apply("4111 1111 1111 1112") == "4111 1111 1111 1112"


@pytest.mark.parametrize("text, expected_redacted", [
    ("server 192.168.1.1 down", "server [IP] down"),
    ("ipv6 2001:0db8:85a3::8a2e:0370:7334", "ipv6 [IP]"),
])
def test_redacts_ip(text, expected_redacted):
    assert BaselineAnonymizer().apply(text) == expected_redacted


@pytest.mark.parametrize("text, expected_redacted", [
    ("RG 12.345.678-9", "RG [RG]"),
])
def test_redacts_rg(text, expected_redacted):
    assert BaselineAnonymizer().apply(text) == expected_redacted


def test_redacts_multiple_pii_in_same_text():
    text = "User arthur@monkai.com.br with CPF 123.456.789-09 from 192.168.1.1"
    expected = "User [EMAIL] with CPF [CPF] from [IP]"
    assert BaselineAnonymizer().apply(text) == expected
```

- [ ] **Step 2: Run, confirm failures**

```bash
pytest tests/test_baseline_anonymizer.py -v
```

Expected: many failures (rules empty).

- [ ] **Step 3: Implement rules**

Replace `BASELINE_RULES` and add a Luhn helper in `monkai_trace/anonymizer/baseline.py`:

```python
"""Hardcoded baseline PII redaction rules. Always applied; no fetch involved."""

from dataclasses import dataclass
from typing import List, Pattern
import re


@dataclass(frozen=True)
class BaselineRule:
    name: str
    pattern: Pattern[str]
    replacement: str


def _luhn_valid(digits: str) -> bool:
    digits = [int(c) for c in digits if c.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


_CARD_PATTERN = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _redact_card(match: re.Match) -> str:
    raw = match.group(0)
    if _luhn_valid(raw):
        return "[CARD]"
    return raw


# Order matters: longer/more-specific patterns first so they win against the
# generic phone matcher. CNPJ before CPF; CARD before phone; IP before phone.
BASELINE_RULES: List[BaselineRule] = [
    BaselineRule(
        name="email",
        pattern=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        replacement="[EMAIL]",
    ),
    BaselineRule(
        name="cnpj",
        pattern=re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),
        replacement="[CNPJ]",
    ),
    BaselineRule(
        name="cpf",
        pattern=re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
        replacement="[CPF]",
    ),
    BaselineRule(
        name="rg",
        pattern=re.compile(r"\b\d{1,2}\.\d{3}\.\d{3}-[\dxX]\b"),
        replacement="[RG]",
    ),
    BaselineRule(
        name="ipv6",
        pattern=re.compile(
            r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b"
        ),
        replacement="[IP]",
    ),
    BaselineRule(
        name="ipv4",
        pattern=re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        replacement="[IP]",
    ),
    BaselineRule(
        name="brazilian_phone",
        pattern=re.compile(
            r"(?:\+?55[\s-]?)?(?:\(\d{2}\)|\d{2})[\s-]?9?\s?\d{4}[\s-]?\d{4}"
        ),
        replacement="[PHONE]",
    ),
    # CARD uses a callable to enforce Luhn; we apply it last so it does not
    # accidentally swallow CPF/CNPJ.
]


class BaselineAnonymizer:
    """Applies BASELINE_RULES to text content. No configuration."""

    def __init__(self, rules: List[BaselineRule] = BASELINE_RULES):
        self._rules = rules
        self._card_pattern = _CARD_PATTERN

    def apply(self, text: str) -> str:
        if not text:
            return text
        for rule in self._rules:
            text = rule.pattern.sub(rule.replacement, text)
        text = self._card_pattern.sub(_redact_card, text)
        return text
```

- [ ] **Step 4: Run tests until they pass**

```bash
pytest tests/test_baseline_anonymizer.py -v
```

Expected: all green. If a regex bites a case it should not, narrow with word boundaries or anchors. Iterate.

- [ ] **Step 5: Commit**

```bash
git add monkai_trace/anonymizer/baseline.py tests/test_baseline_anonymizer.py
git commit -m "feat(anonymizer): implement baseline PII rules"
```

---

## Task 3: SDK — wire anonymizer into upload paths

**Files:**
- Modify: `monkai-trace/monkai_trace/client.py` (around `upload_record` line 63 and `_upload_records_chunk`)
- Modify: `monkai-trace/monkai_trace/async_client.py` (corresponding methods)
- Modify: `monkai-trace/monkai_trace/__init__.py` — export anonymizer
- Create: `monkai-trace/tests/test_client_anonymization.py`

- [ ] **Step 1: Write failing integration test**

`tests/test_client_anonymization.py`:

```python
"""Verify the SDK applies BaselineAnonymizer before transmission."""

import json
from unittest.mock import patch, MagicMock
from monkai_trace import MonkAIClient


def test_upload_record_anonymizes_message_content_before_send():
    client = MonkAIClient(tracer_token="tk_test")
    captured_payload = {}

    def fake_post(url, json=None, **kwargs):
        captured_payload.update(json)
        resp = MagicMock()
        resp.status_code = 201
        resp.json.return_value = {"inserted_count": 1}
        return resp

    with patch("requests.Session.post", side_effect=fake_post):
        client.upload_record(
            namespace="test",
            agent="bot",
            messages=[
                {"role": "user", "content": "my CPF is 123.456.789-09"},
                {"role": "assistant", "content": "ok arthur@monkai.com.br"},
            ],
        )

    serialized = json.dumps(captured_payload)
    assert "123.456.789-09" not in serialized
    assert "arthur@monkai.com.br" not in serialized
    assert "[CPF]" in serialized
    assert "[EMAIL]" in serialized
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest tests/test_client_anonymization.py -v
```

Expected: assertion error — raw PII still present in payload.

- [ ] **Step 3: Wire anonymizer into the sync client**

In `monkai_trace/client.py`, add at the top:

```python
from .anonymizer import BaselineAnonymizer
```

Add to `__init__`:

```python
self._anonymizer = BaselineAnonymizer()
```

Add a private helper:

```python
def _anonymize_messages(self, messages):
    """Apply BaselineAnonymizer to every message content. Returns a new list."""
    if isinstance(messages, dict):
        messages = [messages]
    out = []
    for msg in messages:
        if isinstance(msg, dict) and "content" in msg and isinstance(msg["content"], str):
            new_msg = dict(msg)
            new_msg["content"] = self._anonymizer.apply(msg["content"])
            out.append(new_msg)
        else:
            out.append(msg)
    return out
```

In `upload_record` (line 102 area), replace `msg=messages` with `msg=self._anonymize_messages(messages)`.

For `_upload_records_chunk` and any path that builds a payload from `ConversationRecord.msg`, make sure to anonymize before serialization. Look at `_upload_single_record` and `_upload_records_chunk` — apply `self._anonymize_messages` to `record.msg` when building the request body.

- [ ] **Step 4: Mirror the same change in `async_client.py`**

Same imports, same helper, same call sites in the async upload methods.

- [ ] **Step 5: Run all SDK tests**

```bash
pytest tests/ -v
```

Expected: all pass, including the new `test_client_anonymization.py`.

- [ ] **Step 6: Export anonymizer from package root**

In `monkai_trace/__init__.py`, add:

```python
from monkai_trace.anonymizer import BaselineAnonymizer
```

and append `"BaselineAnonymizer"` to `__all__`.

- [ ] **Step 7: Commit**

```bash
git add monkai_trace/client.py monkai_trace/async_client.py monkai_trace/__init__.py tests/test_client_anonymization.py
git commit -m "feat(client): apply BaselineAnonymizer before upload"
```

---

## Task 4: Hub — schema migration for at-rest encryption

**Files:**
- Create: `monkai-agent-hub/supabase/migrations/20260428120000_encryption_phase1.sql`

> Switch repos for the rest of Phase 1: `cd ~/Desktop/Monkai/monkai-agent-hub && git checkout -b feat/security/encryption-phase-1`

- [ ] **Step 1: Write the migration**

```sql
-- Phase 1 of Trace→Hub encryption rollout.
-- Adds ciphertext columns to agent_conversation_records and creates the
-- per-tenant key registry. The legacy plaintext column `msg` is preserved
-- in this phase to keep rollback cheap; it will be dropped in Phase 5.

ALTER TABLE agent_conversation_records
  ADD COLUMN IF NOT EXISTS msg_ciphertext bytea,
  ADD COLUMN IF NOT EXISTS nonce bytea,
  ADD COLUMN IF NOT EXISTS key_id text,
  ADD COLUMN IF NOT EXISTS encryption_version smallint NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS anonymization_version int NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS tenant_keys (
  tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
  envelope_pubkey bytea,
  envelope_key_id text,
  kek_id text NOT NULL,
  byok_provider text,
  byok_key_uri text,
  byok_status text,
  rotated_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE tenant_keys ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tenant_keys_service_role_only"
  ON tenant_keys
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- No SELECT policy for authenticated users: the edge function reads through
-- the service role only. Frontend never queries this table directly.
```

- [ ] **Step 2: Apply locally and verify**

```bash
cd ~/Desktop/Monkai/monkai-agent-hub
supabase db reset --linked  # destructive, dev only
# OR for an additive run:
supabase migration up
```

Then in psql or Supabase Studio:

```sql
\d agent_conversation_records
\d tenant_keys
```

Expected: new columns present; `tenant_keys` exists; RLS enabled.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260428120000_encryption_phase1.sql
git commit -m "feat(db): add ciphertext columns and tenant_keys table"
```

---

## Task 5: Hub — Vault wrapper

**Files:**
- Create: `monkai-agent-hub/supabase/functions/_shared/vault.ts`

Supabase Vault stores secrets in `vault.secrets`. The edge function reads via the `vault.decrypted_secrets` view (only accessible to service role). For per-tenant KEKs we use one secret per tenant: `tenant_${tenant_id}_kek`, holding a 32-byte raw AES-256 key encoded as base64.

- [ ] **Step 1: Write the wrapper**

```typescript
// supabase/functions/_shared/vault.ts
//
// Thin wrapper around Supabase Vault for tenant-scoped secrets.
// Used only by the service-role edge function client.

import type { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

export class VaultError extends Error {
  constructor(public code: string, message: string) {
    super(message);
    this.name = "VaultError";
  }
}

export class Vault {
  constructor(private client: SupabaseClient) {}

  /** Reads a tenant-scoped raw key (32 bytes, base64). */
  async getTenantKek(tenantId: string): Promise<Uint8Array> {
    const name = `tenant_${tenantId}_kek`;
    const { data, error } = await this.client
      .from("vault.decrypted_secrets")
      .select("decrypted_secret")
      .eq("name", name)
      .single();

    if (error || !data) {
      throw new VaultError("kek_not_found", `Vault secret ${name} missing`);
    }

    return base64ToBytes(data.decrypted_secret);
  }

  /** Creates a new 256-bit KEK for a tenant. Idempotent — no-op if exists. */
  async ensureTenantKek(tenantId: string): Promise<string> {
    const name = `tenant_${tenantId}_kek`;
    const existing = await this.client
      .from("vault.decrypted_secrets")
      .select("id")
      .eq("name", name)
      .maybeSingle();

    if (existing.data) return name;

    const key = crypto.getRandomValues(new Uint8Array(32));
    const { error } = await this.client.rpc("create_secret", {
      secret: bytesToBase64(key),
      name,
      description: `KEK for tenant ${tenantId}`,
    });

    if (error) {
      throw new VaultError("kek_create_failed", error.message);
    }
    return name;
  }
}

function bytesToBase64(bytes: Uint8Array): string {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function base64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
```

- [ ] **Step 2: Commit**

```bash
git add supabase/functions/_shared/vault.ts
git commit -m "feat(edge): add Vault wrapper for tenant KEKs"
```

---

## Task 6: Hub — at-rest encrypt/decrypt helpers with tests

**Files:**
- Create: `monkai-agent-hub/supabase/functions/_shared/crypto/at_rest.ts`
- Create: `monkai-agent-hub/supabase/functions/_shared/crypto/at_rest_test.ts`

- [ ] **Step 1: Write failing tests first**

```typescript
// supabase/functions/_shared/crypto/at_rest_test.ts
import { assertEquals, assertRejects } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { encryptForStorage, decryptForStorage } from "./at_rest.ts";

const TEST_KEK = crypto.getRandomValues(new Uint8Array(32));

Deno.test("encrypt/decrypt roundtrip recovers plaintext", async () => {
  const plaintext = JSON.stringify([{ role: "user", content: "[CPF]" }]);
  const enc = await encryptForStorage(plaintext, TEST_KEK);
  const dec = await decryptForStorage(enc, TEST_KEK);
  assertEquals(dec, plaintext);
});

Deno.test("encrypt produces different ciphertext on repeated calls (random nonce)", async () => {
  const text = "same plaintext";
  const a = await encryptForStorage(text, TEST_KEK);
  const b = await encryptForStorage(text, TEST_KEK);
  assertEquals(a.ciphertext.length, b.ciphertext.length);
  // Nonces differ → ciphertexts differ.
  let differ = false;
  for (let i = 0; i < a.ciphertext.length; i++) {
    if (a.ciphertext[i] !== b.ciphertext[i]) { differ = true; break; }
  }
  assertEquals(differ, true);
});

Deno.test("decrypt fails with a different key", async () => {
  const enc = await encryptForStorage("secret", TEST_KEK);
  const wrong = crypto.getRandomValues(new Uint8Array(32));
  await assertRejects(() => decryptForStorage(enc, wrong));
});
```

- [ ] **Step 2: Run, confirm fail (module missing)**

```bash
deno test supabase/functions/_shared/crypto/at_rest_test.ts
```

Expected: import error.

- [ ] **Step 3: Implement**

```typescript
// supabase/functions/_shared/crypto/at_rest.ts
//
// AES-256-GCM encryption using a per-tenant KEK from Supabase Vault.
// Phase 1 uses the KEK directly as the data-encryption key; key wrapping
// for per-record DEKs lands in Phase 3 alongside envelope encryption.

export interface EncryptedBlob {
  ciphertext: Uint8Array;
  nonce: Uint8Array;
  keyId: string;
  encryptionVersion: number;
}

const ENCRYPTION_VERSION = 1;

export async function encryptForStorage(
  plaintext: string,
  kek: Uint8Array,
  keyId = "kek_v1",
): Promise<EncryptedBlob> {
  const key = await crypto.subtle.importKey(
    "raw",
    kek,
    { name: "AES-GCM" },
    false,
    ["encrypt", "decrypt"],
  );
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const enc = new TextEncoder().encode(plaintext);
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, enc);
  return {
    ciphertext: new Uint8Array(ct),
    nonce,
    keyId,
    encryptionVersion: ENCRYPTION_VERSION,
  };
}

export async function decryptForStorage(
  blob: EncryptedBlob,
  kek: Uint8Array,
): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    kek,
    { name: "AES-GCM" },
    false,
    ["encrypt", "decrypt"],
  );
  const pt = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: blob.nonce },
    key,
    blob.ciphertext,
  );
  return new TextDecoder().decode(pt);
}
```

- [ ] **Step 4: Run tests**

```bash
deno test supabase/functions/_shared/crypto/at_rest_test.ts
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/_shared/crypto/at_rest.ts supabase/functions/_shared/crypto/at_rest_test.ts
git commit -m "feat(edge): add at-rest AES-GCM encrypt/decrypt"
```

---

## Task 7: Hub — wire encryption into write path

**Files:**
- Modify: `monkai-agent-hub/supabase/functions/monkai-api/index.ts` (the INSERT site near line 1135 for `agent_conversation_records`)

The current code inserts `{ namespace, agent, msg: messages, ... }`. We add ciphertext alongside, keeping `msg` populated for now (Phase 1 keeps both).

- [ ] **Step 1: Find every INSERT into `agent_conversation_records`**

```bash
grep -n "from('agent_conversation_records')" supabase/functions/monkai-api/index.ts
```

Expected matches: ~6–8 sites (records returned to listing queries plus 4 INSERT call sites discovered earlier — around lines 1135, 1204, 1267, and any record-receiving handler).

- [ ] **Step 2: Add a helper near the top of the file**

```typescript
// near the imports
import { Vault } from "../_shared/vault.ts";
import { encryptForStorage } from "../_shared/crypto/at_rest.ts";

async function buildEncryptedColumns(
  vault: Vault,
  tenantId: string,
  msg: unknown,
): Promise<{ msg_ciphertext: string; nonce: string; key_id: string; encryption_version: number }> {
  const kek = await vault.getTenantKek(tenantId);
  const blob = await encryptForStorage(JSON.stringify(msg), kek);
  return {
    msg_ciphertext: bytesToHex(blob.ciphertext),
    nonce: bytesToHex(blob.nonce),
    key_id: blob.keyId,
    encryption_version: blob.encryptionVersion,
  };
}

function bytesToHex(b: Uint8Array): string {
  return "\\x" + Array.from(b).map(x => x.toString(16).padStart(2, "0")).join("");
}
```

- [ ] **Step 3: For every `.from('agent_conversation_records').insert({...})` call, spread the encrypted columns**

Pattern:

```typescript
const enc = await buildEncryptedColumns(vault, tenantId, messages);
const { error } = await supabase
  .from("agent_conversation_records")
  .insert({
    namespace,
    agent,
    msg: messages,            // legacy plaintext, kept during Phase 1
    ...enc,                   // new ciphertext columns
    // ...other existing fields
  });
```

`tenantId` is already resolved earlier in the handler from the tracer token. If it isn't in scope at a given INSERT site, lift it up — do not synthesize one.

- [ ] **Step 4: Provision a Vault instance once at the top of the request handler**

```typescript
const vault = new Vault(supabaseAdmin);  // service-role client already exists
```

- [ ] **Step 5: Smoke test against local Supabase**

```bash
supabase start
supabase functions serve monkai-api --env-file .env.local
```

In another terminal, run an SDK upload against the local URL and SELECT the row:

```sql
SELECT id, msg, msg_ciphertext IS NOT NULL AS has_ct, key_id
FROM agent_conversation_records
ORDER BY created_at DESC LIMIT 1;
```

Expected: `has_ct = true`, `key_id = 'kek_v1'`, `msg` still populated (parallel write).

- [ ] **Step 6: Commit**

```bash
git add supabase/functions/monkai-api/index.ts
git commit -m "feat(edge): encrypt msg into ciphertext columns on insert"
```

---

## Task 8: Hub — wire decryption into read path

**Files:**
- Modify: `monkai-agent-hub/supabase/functions/monkai-api/index.ts` (every SELECT that returns `msg` to a client)

- [ ] **Step 1: Find every read site**

```bash
grep -n "agent_conversation_records" supabase/functions/monkai-api/index.ts | grep -i "select\|from"
```

- [ ] **Step 2: Add a decrypt helper**

Near the encrypt helper:

```typescript
import { decryptForStorage } from "../_shared/crypto/at_rest.ts";

async function decryptRow(
  vault: Vault,
  tenantId: string,
  row: { msg: unknown; msg_ciphertext?: string; nonce?: string; key_id?: string },
): Promise<unknown> {
  if (row.msg_ciphertext && row.nonce) {
    const kek = await vault.getTenantKek(tenantId);
    const blob = {
      ciphertext: hexToBytes(row.msg_ciphertext),
      nonce: hexToBytes(row.nonce),
      keyId: row.key_id ?? "kek_v1",
      encryptionVersion: 1,
    };
    return JSON.parse(await decryptForStorage(blob, kek));
  }
  // Fallback for rows from before Phase 1 finished writing ciphertext.
  return row.msg;
}

function hexToBytes(s: string): Uint8Array {
  const clean = s.startsWith("\\x") ? s.slice(2) : s;
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(clean.substr(i * 2, 2), 16);
  return out;
}
```

- [ ] **Step 3: Apply at every read site**

For each handler that fetches conversations and returns them to the UI, replace `row.msg` in the response builder with `await decryptRow(vault, tenantId, row)`. SELECT must include `msg, msg_ciphertext, nonce, key_id`.

- [ ] **Step 4: Manual smoke test — read after write produces plaintext**

Repeat the upload-then-fetch flow from Task 7 and confirm the API response contains the original messages (post-anonymization).

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/monkai-api/index.ts
git commit -m "feat(edge): decrypt msg_ciphertext on read"
```

---

## Task 9: Hub — provision tenant KEKs for existing tenants

**Files:**
- Create: `monkai-agent-hub/scripts/provision_tenant_keys.ts`

- [ ] **Step 1: Write the script**

```typescript
// scripts/provision_tenant_keys.ts
//
// One-off provisioning: ensure every existing tenant has a KEK in Vault and
// a row in tenant_keys. Idempotent — safe to rerun.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { Vault } from "../supabase/functions/_shared/vault.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const admin = createClient(SUPABASE_URL, SERVICE_ROLE);
const vault = new Vault(admin);

const { data: tenants, error } = await admin.from("tenants").select("id");
if (error) throw error;

for (const t of tenants ?? []) {
  const kekId = await vault.ensureTenantKek(t.id);
  await admin.from("tenant_keys").upsert({
    tenant_id: t.id,
    kek_id: kekId,
  });
  console.log(`ok ${t.id}`);
}
console.log(`provisioned ${tenants?.length ?? 0} tenants`);
```

- [ ] **Step 2: Run against the dev environment**

```bash
SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... deno run -A scripts/provision_tenant_keys.ts
```

Expected: one `ok <uuid>` per tenant, then a count line.

- [ ] **Step 3: Verify**

```sql
SELECT count(*) FROM tenant_keys;
SELECT count(*) FROM tenants;
```

Counts must match.

- [ ] **Step 4: Commit**

```bash
git add scripts/provision_tenant_keys.ts
git commit -m "feat(scripts): provision tenant KEKs idempotently"
```

---

## Task 10: end-to-end integration test

**Files:**
- Create: `monkai-agent-hub/supabase/functions/monkai-api/integration_test.ts`

- [ ] **Step 1: Write the test**

```typescript
// integration_test.ts — runs against a local supabase + functions serve
import { assert, assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";

const FN_URL = Deno.env.get("FN_URL") ?? "http://localhost:54321/functions/v1/monkai-api";
const TOKEN = Deno.env.get("TEST_TRACER_TOKEN")!;

Deno.test("upload then fetch returns sanitized plaintext, no PII in DB ciphertext", async () => {
  const upload = await fetch(`${FN_URL}/v1/conversations`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${TOKEN}` },
    body: JSON.stringify({
      namespace: "phase1-test",
      agent: "bot",
      msg: [{ role: "user", content: "CPF 123.456.789-09 + arthur@monkai.com.br" }],
    }),
  });
  assertEquals(upload.status, 201);
  const { id } = await upload.json();

  const read = await fetch(`${FN_URL}/v1/conversations/${id}`, {
    headers: { authorization: `Bearer ${TOKEN}` },
  });
  assertEquals(read.status, 200);
  const row = await read.json();

  const text = JSON.stringify(row);
  assert(!text.includes("123.456.789-09"));
  assert(!text.includes("arthur@monkai.com.br"));
  assert(text.includes("[CPF]") || text.includes("[EMAIL]"));
});
```

- [ ] **Step 2: Run**

```bash
supabase start
supabase functions serve monkai-api &
FN_URL=http://localhost:54321/functions/v1/monkai-api TEST_TRACER_TOKEN=<dev-token> \
  deno test -A supabase/functions/monkai-api/integration_test.ts
```

Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add supabase/functions/monkai-api/integration_test.ts
git commit -m "test(edge): end-to-end encryption phase 1"
```

---

## Task 11: PR to development, deploy to dev environment

- [ ] **Step 1: SDK PR**

```bash
cd ~/Desktop/Monkai/monkai-trace
git push -u origin feat/security/baseline-anonymizer  # SDK branch
gh pr create --base development --title "feat(security): baseline anonymizer (Phase 1)" \
  --body "$(cat <<'EOF'
## O que foi feito
- Adiciona `BaselineAnonymizer` com regras hardcoded (CPF, CNPJ, email, telefone BR, cartão Luhn, IP, RG)
- Aplica anonimização em `upload_record` (sync e async) antes do envio

## Por que
Fase 1 do plano de encryption + anonimização — ver spec em `docs/superpowers/specs/2026-04-28-trace-hub-encryption-anonymization-design.md`. Garante que PII comum nunca sai da máquina do cliente em texto cru.

## Como testar
1. `pytest tests/test_baseline_anonymizer.py tests/test_client_anonymization.py -v`
2. Upload manual com payload contendo CPF e verificar que o servidor recebe `[CPF]`

## Checklist
- [x] Testes passando
- [x] Lint passando
- [x] Documentação no spec atualizada
EOF
)"
```

- [ ] **Step 2: Hub PR**

```bash
cd ~/Desktop/Monkai/monkai-agent-hub
git push -u origin feat/security/encryption-phase-1
gh pr create --base development --title "feat(security): at-rest encryption per tenant (Phase 1)" \
  --body "(similar template — list migration, vault wrapper, encrypt/decrypt helpers, write/read wiring, provisioning script, integration test)"
```

- [ ] **Step 3: Validate in dev environment**

After both PRs merge to `development`:
- Run `provision_tenant_keys.ts` against the dev Supabase
- Smoke test from a real SDK install pointed at the dev Hub
- Run the daily plaintext-audit query (will be added in Phase 5; for Phase 1 just SELECT a few rows and visually confirm `msg_ciphertext IS NOT NULL`)

- [ ] **Step 4: PR development → main**

After dev validation, open `development → main` PRs in both repos, merge with `--no-ff`, and provision keys in production.

---

## Self-review checklist

Before handing off, the implementer should confirm:

- Every INSERT site for `agent_conversation_records` writes both `msg` and `msg_ciphertext`. (Until Phase 5 we keep both; rollback = ignore ciphertext.)
- Every read site that returns `msg` uses `decryptRow` so reads stay correct for both old plaintext rows and new ciphertext rows.
- `provision_tenant_keys.ts` ran for **every** existing tenant before SDK clients start sending payloads in production.
- Integration test passes against the dev environment, not just local.
- The SDK and Hub PRs land in matching order: SDK can't ship before Hub accepts plaintext anonymized payloads (it does — schema is additive in Phase 1, so this is naturally safe).

## What's next

Phase 2 plan: `2026-04-28-encryption-phase-2-custom-rules.md`. Phase 2 adds the user-editable rules table, `GET/PUT /v1/anonymization-rules`, the SDK `RulesClient`, and the frontend rules editor.
