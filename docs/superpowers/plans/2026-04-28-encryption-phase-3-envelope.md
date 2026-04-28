# Encryption Phase 3: Envelope Encryption (Transit Defense-in-Depth)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** SDK seals the conversation payload client-side with a random per-record DEK wrapped to the tenant's RSA-OAEP public key. Edge function unwraps with the tenant private key from Vault, then runs the existing Phase-2 anonymization-reapply / Phase-1 at-rest encrypt path. After this phase, the legacy plaintext `messages` field on the wire is rejected.

**Architecture:** New per-tenant RSA-2048 keypair: public half published via `GET /v1/tenant-pubkey` (cacheable), private half stored in Supabase Vault. SDK generates a random 32-byte AES-256-GCM DEK per record, encrypts the JSON-serialized messages, wraps the DEK with the public key, and sends `{wrapped_dk, nonce, ciphertext, envelope_key_id}`. Edge function unwraps and decrypts before existing Phase-2 logic runs.

**Tech Stack:** SDK `cryptography` (PyCA) for RSA-OAEP wrap; edge function uses Web Crypto API `RSA-OAEP` import + decrypt.

**Spec reference:** § Components / SDK crypto/envelope.py, edge unseal.ts; § Data flows / Write.

**Depends on:** Phase 1 + Phase 2 merged to `main`.

---

## File structure

`monkai-agent-hub`:
- Create `supabase/migrations/20260512120000_envelope_keys.sql` — extend `tenant_keys` columns (already exist as nullable since Phase 1; this migration backfills for all tenants and adds NOT NULL after backfill)
- Create `supabase/functions/_shared/crypto/envelope_unseal.ts` + test
- Create `supabase/functions/_shared/crypto/envelope_keypair.ts` — generate-and-store
- Modify `supabase/functions/monkai-api/index.ts` — add `GET /v1/tenant-pubkey`; in write path, accept envelope payload, unseal, then continue
- Modify `scripts/provision_tenant_keys.ts` — also generate envelope keypair if missing

`monkai-trace`:
- Create `monkai_trace/crypto/__init__.py`
- Create `monkai_trace/crypto/envelope.py` + tests
- Modify `monkai_trace/client.py` and `async_client.py` — fetch pubkey on first use, seal before POST, change payload schema

---

## Task 1: per-tenant envelope keypair generation

**Files:** Create `supabase/functions/_shared/crypto/envelope_keypair.ts`, modify `scripts/provision_tenant_keys.ts`

- [ ] **Step 1: Implement keypair generation**

```typescript
// supabase/functions/_shared/crypto/envelope_keypair.ts
import type { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";
import { Vault } from "../vault.ts";

export async function ensureEnvelopeKeypair(
  client: SupabaseClient,
  vault: Vault,
  tenantId: string,
): Promise<{ pubkeyPem: string; keyId: string }> {
  const { data } = await client
    .from("tenant_keys")
    .select("envelope_pubkey, envelope_key_id")
    .eq("tenant_id", tenantId)
    .maybeSingle();

  if (data?.envelope_pubkey && data?.envelope_key_id) {
    return { pubkeyPem: new TextDecoder().decode(data.envelope_pubkey), keyId: data.envelope_key_id };
  }

  const kp = await crypto.subtle.generateKey(
    { name: "RSA-OAEP", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
    true,
    ["encrypt", "decrypt"],
  ) as CryptoKeyPair;

  const spki = new Uint8Array(await crypto.subtle.exportKey("spki", kp.publicKey));
  const pkcs8 = new Uint8Array(await crypto.subtle.exportKey("pkcs8", kp.privateKey));
  const pubkeyPem = toPem(spki, "PUBLIC KEY");
  const privkeyPem = toPem(pkcs8, "PRIVATE KEY");
  const keyId = `env_v1_${tenantId.slice(0, 8)}`;

  // Store private key in Vault.
  await client.rpc("create_secret", {
    secret: privkeyPem,
    name: `tenant_${tenantId}_envelope_priv`,
    description: `Envelope private key for tenant ${tenantId}`,
  });

  await client.from("tenant_keys").upsert({
    tenant_id: tenantId,
    envelope_pubkey: new TextEncoder().encode(pubkeyPem),
    envelope_key_id: keyId,
    kek_id: data?.kek_id ?? `tenant_${tenantId}_kek`,
  });

  return { pubkeyPem, keyId };
}

function toPem(bytes: Uint8Array, label: string): string {
  const b64 = btoa(String.fromCharCode(...bytes));
  const lines = b64.match(/.{1,64}/g)!.join("\n");
  return `-----BEGIN ${label}-----\n${lines}\n-----END ${label}-----\n`;
}
```

- [ ] **Step 2: Extend the provisioning script**

In `scripts/provision_tenant_keys.ts`, after `ensureTenantKek`, also call `ensureEnvelopeKeypair`. Run it against dev to backfill.

- [ ] **Step 3: Commit**

```bash
git add supabase/functions/_shared/crypto/envelope_keypair.ts scripts/provision_tenant_keys.ts
git commit -m "feat(edge): per-tenant envelope keypair generation"
```

---

## Task 2: GET /v1/tenant-pubkey endpoint

**Files:** Modify `supabase/functions/monkai-api/index.ts`

- [ ] **Step 1: Implement**

```typescript
if (url.pathname === "/v1/tenant-pubkey" && req.method === "GET") {
  const tenantId = await tenantFromAuth(req);
  const { pubkeyPem, keyId } = await ensureEnvelopeKeypair(supabase, vault, tenantId);
  return new Response(JSON.stringify({
    key_id: keyId,
    pubkey_pem: pubkeyPem,
    algorithm: "RSA-OAEP-SHA256",
  }), { headers: { "content-type": "application/json", "cache-control": "private, max-age=300" } });
}
```

- [ ] **Step 2: Smoke test**

```bash
curl -H "authorization: Bearer <dev_token>" http://localhost:54321/functions/v1/monkai-api/v1/tenant-pubkey
```

Expected: JSON with `key_id` and a PEM block.

- [ ] **Step 3: Commit**

```bash
git add supabase/functions/monkai-api/index.ts
git commit -m "feat(edge): GET /v1/tenant-pubkey"
```

---

## Task 3: edge function unseal helper

**Files:** Create `supabase/functions/_shared/crypto/envelope_unseal.ts` + test

- [ ] **Step 1: Failing test**

```typescript
// envelope_unseal_test.ts
import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { unsealEnvelope } from "./envelope_unseal.ts";

Deno.test("seals and unseals JSON payload", async () => {
  const kp = await crypto.subtle.generateKey(
    { name: "RSA-OAEP", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
    true, ["encrypt", "decrypt"],
  ) as CryptoKeyPair;

  const dek = crypto.getRandomValues(new Uint8Array(32));
  const aesKey = await crypto.subtle.importKey("raw", dek, "AES-GCM", false, ["encrypt", "decrypt"]);
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const plaintext = JSON.stringify({ msg: "hi" });
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, aesKey, new TextEncoder().encode(plaintext)));
  const wrapped = new Uint8Array(await crypto.subtle.encrypt({ name: "RSA-OAEP" }, kp.publicKey, dek));

  const privPkcs8 = new Uint8Array(await crypto.subtle.exportKey("pkcs8", kp.privateKey));
  const privPem = `-----BEGIN PRIVATE KEY-----\n${btoa(String.fromCharCode(...privPkcs8)).match(/.{1,64}/g)!.join("\n")}\n-----END PRIVATE KEY-----`;

  const out = await unsealEnvelope({ wrapped_dk: wrapped, nonce, ciphertext: ct }, privPem);
  assertEquals(out, plaintext);
});
```

- [ ] **Step 2: Implement**

```typescript
// envelope_unseal.ts
export interface SealedEnvelope {
  wrapped_dk: Uint8Array;
  nonce: Uint8Array;
  ciphertext: Uint8Array;
}

export async function unsealEnvelope(env: SealedEnvelope, privKeyPem: string): Promise<string> {
  const pkcs8 = pemToBytes(privKeyPem);
  const privKey = await crypto.subtle.importKey(
    "pkcs8",
    pkcs8,
    { name: "RSA-OAEP", hash: "SHA-256" },
    false,
    ["decrypt"],
  );
  const rawDek = new Uint8Array(await crypto.subtle.decrypt({ name: "RSA-OAEP" }, privKey, env.wrapped_dk));
  const aesKey = await crypto.subtle.importKey("raw", rawDek, "AES-GCM", false, ["decrypt"]);
  const pt = new Uint8Array(
    await crypto.subtle.decrypt({ name: "AES-GCM", iv: env.nonce }, aesKey, env.ciphertext),
  );
  return new TextDecoder().decode(pt);
}

function pemToBytes(pem: string): Uint8Array {
  const b64 = pem.replace(/-----[A-Z ]+-----/g, "").replace(/\s+/g, "");
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
```

- [ ] **Step 3: Run, commit**

```bash
deno test supabase/functions/_shared/crypto/envelope_unseal_test.ts
git add supabase/functions/_shared/crypto/envelope_unseal.ts supabase/functions/_shared/crypto/envelope_unseal_test.ts
git commit -m "feat(edge): RSA-OAEP envelope unseal"
```

---

## Task 4: SDK envelope seal

**Files:** Create `monkai_trace/crypto/envelope.py`, `tests/test_envelope.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_envelope.py
import json
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from monkai_trace.crypto.envelope import seal


def test_seal_roundtrip():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    pubkey_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    plaintext = json.dumps({"msg": "hello"})
    env = seal(plaintext.encode(), pubkey_pem)

    raw_dek = private_key.decrypt(
        env.wrapped_dk,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None),
    )
    assert len(raw_dek) == 32
    # AES-GCM decrypt to confirm
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    pt = AESGCM(raw_dek).decrypt(env.nonce, env.ciphertext, None).decode()
    assert pt == plaintext
```

- [ ] **Step 2: Implement**

```python
# monkai_trace/crypto/__init__.py
from monkai_trace.crypto.envelope import seal, SealedEnvelope

__all__ = ["seal", "SealedEnvelope"]
```

```python
# monkai_trace/crypto/envelope.py
import os
from dataclasses import dataclass
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass
class SealedEnvelope:
    wrapped_dk: bytes
    nonce: bytes
    ciphertext: bytes


def seal(plaintext: bytes, pubkey_pem: str) -> SealedEnvelope:
    pub = load_pem_public_key(pubkey_pem.encode())
    dek = os.urandom(32)
    nonce = os.urandom(12)
    ct = AESGCM(dek).encrypt(nonce, plaintext, None)
    wrapped = pub.encrypt(
        dek,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None),
    )
    return SealedEnvelope(wrapped_dk=wrapped, nonce=nonce, ciphertext=ct)
```

- [ ] **Step 3: Add `cryptography` to dependencies**

In `pyproject.toml`, add `cryptography>=42.0` to runtime deps.

- [ ] **Step 4: Run tests, commit**

```bash
pytest tests/test_envelope.py -v
git add monkai_trace/crypto pyproject.toml tests/test_envelope.py
git commit -m "feat(crypto): add envelope seal with RSA-OAEP wrap"
```

---

## Task 5: SDK — fetch pubkey, seal payload, change wire schema

**Files:** Modify `monkai_trace/client.py`, `monkai_trace/async_client.py`

- [ ] **Step 1: Add a PubkeyClient with backoff**

```python
# monkai_trace/crypto/pubkey_client.py
import time, requests, logging
logger = logging.getLogger(__name__)


class PubkeyUnavailable(Exception):
    pass


class PubkeyClient:
    def __init__(self, token, base_url):
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._cached = None
        self._cached_at = 0
        self._backoff = [1, 5, 30, 300]
        self._attempts = 0

    def get(self):
        # 1h hard cache; refresh on rotation via 5min cache headers (HTTP layer)
        if self._cached and time.time() - self._cached_at < 3600:
            return self._cached
        try:
            r = requests.get(f"{self._base_url}/v1/tenant-pubkey",
                             headers={"authorization": f"Bearer {self._token}"}, timeout=5)
            r.raise_for_status()
            self._cached = r.json()
            self._cached_at = time.time()
            self._attempts = 0
            return self._cached
        except Exception:
            logger.exception("pubkey fetch failed")
            self._attempts += 1
            if self._attempts >= len(self._backoff) * 4:
                raise PubkeyUnavailable("max retries")
            raise PubkeyUnavailable("transient")
```

- [ ] **Step 2: Update upload pipeline**

In `MonkAIClient._upload_single_record` (and chunk equivalents), after computing `sanitized_msg`:

```python
from .crypto import seal
import base64

pk = self._pubkey_client.get()
env = seal(json.dumps(sanitized_msg).encode(), pk["pubkey_pem"])
payload = {
    "namespace": record.namespace,
    "agent": record.agent,
    "wrapped_dk": base64.b64encode(env.wrapped_dk).decode(),
    "nonce": base64.b64encode(env.nonce).decode(),
    "ciphertext": base64.b64encode(env.ciphertext).decode(),
    "envelope_key_id": pk["key_id"],
    "anonymization_version": self._anonymization_version,
    # token usage and other metadata stays plaintext
    "input_tokens": record.input_tokens,
    "output_tokens": record.output_tokens,
    "process_tokens": record.process_tokens,
    "memory_tokens": record.memory_tokens,
    # ... other non-secret metadata
}
```

The legacy `msg` field is no longer sent.

- [ ] **Step 3: Mirror in async client**

Same logic, `aiohttp.ClientSession.post(json=payload)`.

- [ ] **Step 4: Update integration test**

Modify `tests/test_client_anonymization.py` and `tests/test_client_custom_rules.py` to mock the pubkey endpoint and assert payload contains `wrapped_dk` (not `msg`).

- [ ] **Step 5: Commit**

```bash
git add monkai_trace/crypto/pubkey_client.py monkai_trace/client.py monkai_trace/async_client.py tests/
git commit -m "feat(client): seal payload with envelope encryption"
```

---

## Task 6: edge function — accept envelope payload, reject legacy

**Files:** Modify `supabase/functions/monkai-api/index.ts`

- [ ] **Step 1: In the conversation INSERT handler, branch on payload shape**

```typescript
const body = await req.json();
let messages: unknown;

if (body.wrapped_dk && body.ciphertext && body.nonce) {
  const privPem = await vault.getEnvelopePriv(tenantId);
  const plaintext = await unsealEnvelope({
    wrapped_dk: base64ToBytes(body.wrapped_dk),
    nonce: base64ToBytes(body.nonce),
    ciphertext: base64ToBytes(body.ciphertext),
  }, privPem);
  messages = JSON.parse(plaintext);
} else if (body.msg) {
  // Legacy path — reject after Phase 3 ships.
  return jsonError(400, "envelope_required", "client must seal payload");
} else {
  return jsonError(400, "missing_payload", "");
}
```

- [ ] **Step 2: Add `Vault.getEnvelopePriv`**

```typescript
async getEnvelopePriv(tenantId: string): Promise<string> {
  const name = `tenant_${tenantId}_envelope_priv`;
  const { data, error } = await this.client
    .from("vault.decrypted_secrets")
    .select("decrypted_secret")
    .eq("name", name)
    .single();
  if (error || !data) throw new VaultError("envelope_priv_not_found", name);
  return data.decrypted_secret;
}
```

- [ ] **Step 3: Memory hygiene**

After the insert succeeds, overwrite the `messages` and `plaintext` variables with empty values so the GC reclaims fast.

- [ ] **Step 4: Commit**

```bash
git add supabase/functions/monkai-api/index.ts supabase/functions/_shared/vault.ts
git commit -m "feat(edge): accept envelope payload, reject legacy plaintext msg"
```

---

## Task 7: end-to-end test + PR + dev validation

- [ ] Add an end-to-end test in `integration_test.ts` that exercises the new path: GET pubkey, seal locally with WebCrypto in the test, POST, SELECT row, assert ciphertext stored.
- [ ] Open SDK + Hub PRs against `development`.
- [ ] In dev, **stagger the rollout**: deploy Hub first (still accepts legacy `msg` for one release window), then deploy SDK clients in order. After all SDK callers update, flip the Hub to `envelope_required`.
- [ ] PR `development → main`.

## Self-review checklist

- The Hub's pubkey endpoint returns the same `key_id` the SDK encoded in its payload; mismatched key_id triggers re-fetch.
- After flipping `envelope_required`, the `msg` field is rejected with `400 envelope_required`.
- Pubkey rotation: introducing a new envelope key for a tenant must keep the old private key in Vault for at least 24h so in-flight payloads keep working.

## What's next

Phase 4: BYOK — `2026-04-28-encryption-phase-4-byok.md`.
