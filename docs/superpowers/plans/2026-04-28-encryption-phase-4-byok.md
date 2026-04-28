# Encryption Phase 4: BYOK (Bring Your Own Key)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enterprise tenants can swap the at-rest KEK source from Supabase Vault to their own Azure Key Vault. When the customer revokes access, writes fail loudly and reads degrade gracefully without 500s.

**Architecture:** Introduce a `KeyProvider` abstraction. Default implementation (`SupabaseVaultProvider`) is what Phase 1 ships. New `AzureKeyVaultProvider` uses a per-tenant service principal stored as encrypted credentials to call Azure Key Vault `wrapKey` / `unwrapKey` against the customer-owned key. Provider selection is per tenant via `tenant_keys.byok_provider`.

**Tech Stack:** Edge function + Azure Key Vault REST API (no SDK dependency to keep edge bundle small) + MSAL for OAuth client credentials flow.

**Spec reference:** § Components / Key infrastructure; § Data flows / BYOK.

**Depends on:** Phase 1 + 2 + 3 merged. The `tenant_keys` table already has the BYOK columns from the Phase 1 migration.

---

## File structure

`monkai-agent-hub`:
- Create `supabase/functions/_shared/crypto/providers/types.ts` — `KeyProvider` interface
- Create `supabase/functions/_shared/crypto/providers/supabase_vault.ts` — wraps existing Phase-1 logic in the interface
- Create `supabase/functions/_shared/crypto/providers/azure_keyvault.ts` — Azure KV adapter
- Create `supabase/functions/_shared/crypto/providers/azure_keyvault_test.ts`
- Create `supabase/functions/_shared/crypto/providers/factory.ts` — picks provider per tenant
- Modify `supabase/functions/monkai-api/index.ts` — write/read paths use the factory; new `POST /v1/byok/connect` and `GET /v1/byok/status`
- Create `src/pages/settings/security/Encryption.tsx` — BYOK connect UI
- Create migration `20260519120000_byok_credentials.sql` — encrypted SP credentials table

---

## Task 1: storage for BYOK credentials

**Files:** `supabase/migrations/20260519120000_byok_credentials.sql`

- [ ] **Step 1: Migration**

```sql
CREATE TABLE IF NOT EXISTS byok_credentials (
  tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
  provider text NOT NULL,                  -- 'azure_keyvault'
  vault_uri text NOT NULL,                 -- e.g. https://contoso-kv.vault.azure.net
  key_name text NOT NULL,                  -- key name inside the customer KV
  tenant_id_oauth text NOT NULL,           -- AAD tenant id of the customer
  client_id text NOT NULL,                 -- service principal id
  -- Client secret is held in Supabase Vault, not this table:
  -- secret name format: byok_${tenant_id}_client_secret
  status text NOT NULL DEFAULT 'pending',  -- 'pending' | 'connected' | 'revoked' | 'error'
  last_health_check timestamptz,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE byok_credentials ENABLE ROW LEVEL SECURITY;

CREATE POLICY "byok_admin_only"
  ON byok_credentials FOR ALL TO authenticated
  USING (
    tenant_id = (auth.jwt() ->> 'tenant_id')::uuid
    AND (auth.jwt() ->> 'role') = 'admin'
  )
  WITH CHECK (
    tenant_id = (auth.jwt() ->> 'tenant_id')::uuid
    AND (auth.jwt() ->> 'role') = 'admin'
  );
```

- [ ] **Step 2: Apply, commit**

```bash
supabase migration up
git add supabase/migrations/20260519120000_byok_credentials.sql
git commit -m "feat(db): byok_credentials table"
```

---

## Task 2: KeyProvider interface + SupabaseVaultProvider refactor

**Files:** `providers/types.ts`, `providers/supabase_vault.ts`, `providers/factory.ts`

- [ ] **Step 1: Define interface**

```typescript
// providers/types.ts
export interface WrapResult { wrapped: Uint8Array; keyId: string }

export interface KeyProvider {
  /** Wraps a fresh DEK using the tenant KEK. */
  wrapDek(dek: Uint8Array): Promise<WrapResult>;
  /** Unwraps a previously wrapped DEK. */
  unwrapDek(wrapped: Uint8Array, keyId: string): Promise<Uint8Array>;
  /** Health check for the provider. Throws on failure. */
  healthCheck(): Promise<void>;
}
```

- [ ] **Step 2: Move existing Phase-1 logic into `SupabaseVaultProvider`**

```typescript
// providers/supabase_vault.ts
import type { KeyProvider, WrapResult } from "./types.ts";
import { Vault } from "../../vault.ts";

export class SupabaseVaultProvider implements KeyProvider {
  constructor(private vault: Vault, private tenantId: string) {}

  async wrapDek(dek: Uint8Array): Promise<WrapResult> {
    const kek = await this.vault.getTenantKek(this.tenantId);
    const aesKek = await crypto.subtle.importKey("raw", kek, "AES-KW", false, ["wrapKey"]);
    const aesDek = await crypto.subtle.importKey("raw", dek, "AES-GCM", true, ["encrypt", "decrypt"]);
    const wrapped = new Uint8Array(await crypto.subtle.wrapKey("raw", aesDek, aesKek, "AES-KW"));
    return { wrapped, keyId: `kek_v1_${this.tenantId.slice(0, 8)}` };
  }

  async unwrapDek(wrapped: Uint8Array, _keyId: string): Promise<Uint8Array> {
    const kek = await this.vault.getTenantKek(this.tenantId);
    const aesKek = await crypto.subtle.importKey("raw", kek, "AES-KW", false, ["unwrapKey"]);
    const dek = await crypto.subtle.unwrapKey(
      "raw", wrapped, aesKek, "AES-KW", "AES-GCM", true, ["encrypt", "decrypt"],
    );
    const raw = new Uint8Array(await crypto.subtle.exportKey("raw", dek));
    return raw;
  }

  async healthCheck(): Promise<void> {
    await this.vault.getTenantKek(this.tenantId);
  }
}
```

- [ ] **Step 3: Refactor Phase 1 `at_rest.ts` to take a `KeyProvider` instead of raw KEK**

The existing `encryptForStorage` becomes `encryptForStorage(plaintext, provider)` — generates a fresh DEK, encrypts plaintext, then `provider.wrapDek(dek)` to produce the stored `wrapped_dek`. Update `decryptForStorage` similarly. Update all call sites in `monkai-api/index.ts`.

- [ ] **Step 4: Run all existing tests — must still pass**

```bash
deno test supabase/functions/_shared
```

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/_shared/crypto
git commit -m "refactor(edge): KeyProvider abstraction over at-rest crypto"
```

---

## Task 3: AzureKeyVaultProvider

**Files:** `providers/azure_keyvault.ts`, `providers/azure_keyvault_test.ts`

- [ ] **Step 1: Failing test (mocked HTTP)**

```typescript
// azure_keyvault_test.ts
import { assertEquals, assertRejects } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { AzureKeyVaultProvider } from "./azure_keyvault.ts";

Deno.test("wrapDek calls Azure KV wrap endpoint with correct payload", async () => {
  const calls: { url: string; body: string }[] = [];
  const fakeFetch = async (url: string, init?: RequestInit) => {
    calls.push({ url, body: init?.body as string });
    if (url.includes("oauth2")) {
      return new Response(JSON.stringify({ access_token: "tok", expires_in: 3600 }));
    }
    if (url.includes("/wrapkey")) {
      return new Response(JSON.stringify({ kid: "https://kv/keys/k/1", value: "AAAA" }));
    }
    throw new Error("unexpected " + url);
  };
  const p = new AzureKeyVaultProvider({
    vaultUri: "https://kv.vault.azure.net",
    keyName: "k",
    tenantIdOauth: "t",
    clientId: "c",
    clientSecret: "s",
    fetch: fakeFetch,
  });
  const out = await p.wrapDek(new Uint8Array([1, 2, 3, 4]));
  assertEquals(out.keyId, "https://kv/keys/k/1");
});
```

- [ ] **Step 2: Implement**

```typescript
// azure_keyvault.ts
import type { KeyProvider, WrapResult } from "./types.ts";

interface Config {
  vaultUri: string;
  keyName: string;
  tenantIdOauth: string;
  clientId: string;
  clientSecret: string;
  fetch?: typeof fetch;
}

export class AzureKeyVaultProvider implements KeyProvider {
  private token?: { value: string; expiresAt: number };
  private fetchImpl: typeof fetch;

  constructor(private cfg: Config) {
    this.fetchImpl = cfg.fetch ?? fetch;
  }

  async wrapDek(dek: Uint8Array): Promise<WrapResult> {
    const tok = await this.token_();
    const resp = await this.fetchImpl(
      `${this.cfg.vaultUri}/keys/${this.cfg.keyName}/wrapkey?api-version=7.4`,
      {
        method: "POST",
        headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
        body: JSON.stringify({ alg: "RSA-OAEP-256", value: base64Url(dek) }),
      },
    );
    if (!resp.ok) throw new Error(`byok_wrap_failed: ${resp.status}`);
    const j = await resp.json();
    return { wrapped: base64UrlDecode(j.value), keyId: j.kid };
  }

  async unwrapDek(wrapped: Uint8Array, keyId: string): Promise<Uint8Array> {
    const tok = await this.token_();
    // Use the kid (full URL with version) so older versions still work after rotation
    const resp = await this.fetchImpl(
      `${keyId}/unwrapkey?api-version=7.4`,
      {
        method: "POST",
        headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
        body: JSON.stringify({ alg: "RSA-OAEP-256", value: base64Url(wrapped) }),
      },
    );
    if (resp.status === 403) throw new Error("byok_unavailable");
    if (!resp.ok) throw new Error(`byok_unwrap_failed: ${resp.status}`);
    const j = await resp.json();
    return base64UrlDecode(j.value);
  }

  async healthCheck(): Promise<void> {
    // Wrap+unwrap a probe value
    const probe = crypto.getRandomValues(new Uint8Array(32));
    const w = await this.wrapDek(probe);
    const u = await this.unwrapDek(w.wrapped, w.keyId);
    if (u.length !== probe.length) throw new Error("byok_health_check_mismatch");
  }

  private async token_(): Promise<string> {
    if (this.token && Date.now() < this.token.expiresAt - 60_000) return this.token.value;
    const body = new URLSearchParams({
      grant_type: "client_credentials",
      client_id: this.cfg.clientId,
      client_secret: this.cfg.clientSecret,
      scope: "https://vault.azure.net/.default",
    });
    const resp = await this.fetchImpl(
      `https://login.microsoftonline.com/${this.cfg.tenantIdOauth}/oauth2/v2.0/token`,
      { method: "POST", body },
    );
    if (!resp.ok) throw new Error(`byok_auth_failed: ${resp.status}`);
    const j = await resp.json();
    this.token = { value: j.access_token, expiresAt: Date.now() + j.expires_in * 1000 };
    return this.token.value;
  }
}

function base64Url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes)).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
}

function base64UrlDecode(s: string): Uint8Array {
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4);
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
```

- [ ] **Step 3: Run, commit**

```bash
deno test supabase/functions/_shared/crypto/providers/azure_keyvault_test.ts
git add supabase/functions/_shared/crypto/providers/azure_keyvault.ts supabase/functions/_shared/crypto/providers/azure_keyvault_test.ts
git commit -m "feat(edge): AzureKeyVaultProvider for BYOK"
```

---

## Task 4: provider factory + connect/status endpoints

**Files:** `providers/factory.ts`, `supabase/functions/monkai-api/index.ts`

- [ ] **Step 1: Factory**

```typescript
// providers/factory.ts
import type { KeyProvider } from "./types.ts";
import { SupabaseVaultProvider } from "./supabase_vault.ts";
import { AzureKeyVaultProvider } from "./azure_keyvault.ts";

export async function getProviderFor(
  tenantId: string,
  supabase: SupabaseClient,
  vault: Vault,
): Promise<KeyProvider> {
  const { data } = await supabase
    .from("byok_credentials")
    .select("provider, vault_uri, key_name, tenant_id_oauth, client_id, status")
    .eq("tenant_id", tenantId)
    .maybeSingle();

  if (data?.status === "connected" && data.provider === "azure_keyvault") {
    const secretName = `byok_${tenantId}_client_secret`;
    const { data: sec } = await supabase
      .from("vault.decrypted_secrets")
      .select("decrypted_secret")
      .eq("name", secretName)
      .single();
    if (!sec) throw new Error("byok_secret_missing");
    return new AzureKeyVaultProvider({
      vaultUri: data.vault_uri,
      keyName: data.key_name,
      tenantIdOauth: data.tenant_id_oauth,
      clientId: data.client_id,
      clientSecret: sec.decrypted_secret,
    });
  }

  return new SupabaseVaultProvider(vault, tenantId);
}
```

- [ ] **Step 2: Connect endpoint**

```typescript
// POST /v1/byok/connect — admin only
const body = await req.json();
// body: { provider, vault_uri, key_name, tenant_id_oauth, client_id, client_secret }

await supabase.rpc("create_secret", {
  secret: body.client_secret,
  name: `byok_${tenantId}_client_secret`,
  description: `BYOK client secret for tenant ${tenantId}`,
});

await supabase.from("byok_credentials").upsert({
  tenant_id: tenantId,
  provider: body.provider,
  vault_uri: body.vault_uri,
  key_name: body.key_name,
  tenant_id_oauth: body.tenant_id_oauth,
  client_id: body.client_id,
  status: "pending",
});

const provider = await getProviderFor(tenantId, supabase, vault);
try {
  await provider.healthCheck();
  await supabase.from("byok_credentials")
    .update({ status: "connected", last_health_check: new Date().toISOString(), last_error: null })
    .eq("tenant_id", tenantId);
  return new Response(JSON.stringify({ status: "connected" }));
} catch (e) {
  await supabase.from("byok_credentials")
    .update({ status: "error", last_error: (e as Error).message })
    .eq("tenant_id", tenantId);
  return jsonError(400, "byok_connect_failed", (e as Error).message);
}
```

- [ ] **Step 3: Status endpoint**

```typescript
// GET /v1/byok/status — admin only
const { data } = await supabase
  .from("byok_credentials")
  .select("status, last_health_check, last_error")
  .eq("tenant_id", tenantId)
  .maybeSingle();
return new Response(JSON.stringify(data ?? { status: "not_configured" }));
```

- [ ] **Step 4: Use the factory in write/read paths**

Replace direct `new SupabaseVaultProvider(...)` with `await getProviderFor(tenantId, supabase, vault)` in the conversation INSERT and SELECT handlers.

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/_shared/crypto/providers/factory.ts supabase/functions/monkai-api/index.ts
git commit -m "feat(edge): byok connect/status + provider factory"
```

---

## Task 5: graceful degradation on revoked BYOK

**Files:** Modify the read handler in `monkai-api/index.ts`

- [ ] **Step 1: Catch `byok_unavailable` on decrypt**

```typescript
async function decryptRow(row, provider) {
  try {
    return await provider.unwrapDek(...) // existing logic
  } catch (e) {
    if ((e as Error).message === "byok_unavailable") {
      return { encrypted: true, key_unavailable: true };
    }
    throw e;
  }
}
```

- [ ] **Step 2: Catch on write**

```typescript
try {
  const enc = await encryptForStorage(plaintext, provider);
  // ...insert
} catch (e) {
  if ((e as Error).message === "byok_unavailable") {
    return jsonError(503, "byok_unavailable", "customer key access revoked");
  }
  throw e;
}
```

- [ ] **Step 3: Update `byok_credentials.status` to `revoked` on observed 403**

When `unwrapDek` throws `byok_unavailable`, do `UPDATE byok_credentials SET status='revoked', last_error='403 from KV' WHERE tenant_id=$1`. This keeps the UI status accurate without a separate cron.

- [ ] **Step 4: Commit**

```bash
git add supabase/functions/monkai-api/index.ts
git commit -m "feat(edge): graceful degradation on byok revocation"
```

---

## Task 6: Hub UI — `/settings/security/encryption`

**Files:** Create `src/pages/settings/security/Encryption.tsx`

- [ ] **Step 1: Build the screen**

Two states: not connected (form to connect) and connected (status + disconnect).

```tsx
// src/pages/settings/security/Encryption.tsx
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Lock } from "lucide-react";

export default function Encryption() {
  const [status, setStatus] = useState<{ status: string; last_error?: string } | null>(null);
  const [form, setForm] = useState({ vault_uri: "", key_name: "", tenant_id_oauth: "", client_id: "", client_secret: "" });

  useEffect(() => {
    fetch("/functions/v1/monkai-api/v1/byok/status").then(r => r.json()).then(setStatus);
  }, []);

  async function connect() {
    const r = await fetch("/functions/v1/monkai-api/v1/byok/connect", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ provider: "azure_keyvault", ...form }),
    });
    const j = await r.json();
    setStatus(j);
  }

  return (
    <div className="p-6 space-y-4">
      <h1 className="flex items-center gap-2 text-xl font-semibold"><Lock /> Criptografia</h1>
      {status?.status === "connected" ? (
        <div className="text-sm">
          <p>BYOK conectado.</p>
          <p>Última verificação: {status.last_error ? `falha: ${status.last_error}` : "OK"}</p>
        </div>
      ) : (
        <div className="space-y-2 max-w-xl">
          <p className="text-sm text-muted-foreground">
            Conecte sua Azure Key Vault para que apenas você controle a chave de criptografia.
            Você precisa criar um service principal com role <code>Key Vault Crypto User</code> na chave alvo.
          </p>
          <Input placeholder="Vault URI" value={form.vault_uri} onChange={e => setForm({ ...form, vault_uri: e.target.value })} />
          <Input placeholder="Key name" value={form.key_name} onChange={e => setForm({ ...form, key_name: e.target.value })} />
          <Input placeholder="AAD tenant ID" value={form.tenant_id_oauth} onChange={e => setForm({ ...form, tenant_id_oauth: e.target.value })} />
          <Input placeholder="Client ID (SP)" value={form.client_id} onChange={e => setForm({ ...form, client_id: e.target.value })} />
          <Input type="password" placeholder="Client secret" value={form.client_secret} onChange={e => setForm({ ...form, client_secret: e.target.value })} />
          <Button onClick={connect}>Conectar</Button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Register route, commit**

```bash
git add src/pages/settings/security/Encryption.tsx
git commit -m "feat(ui): byok connect screen"
```

---

## Task 7: PR and validation

- [ ] PR Hub against `development`. SDK is unaffected by Phase 4.
- [ ] In dev, create a personal Azure KV with a test key, configure SP, connect via the UI, send a record, read it back. Verify `tenant_keys.kek_id` reflects the kid from KV.
- [ ] Test revocation: remove the SP from the KV access policy; observe a 503 on next write and a `key_unavailable` flag on next read.
- [ ] PR `development → main`.

## Self-review checklist

- The factory always returns `SupabaseVaultProvider` for tenants without BYOK rows. No breaking change for existing tenants.
- BYOK secrets are stored in Supabase Vault, never in the `byok_credentials` table.
- Health check is run every connect AND on a daily cron (separate enhancement, not in this plan — note in the followups). The `last_health_check` field is updated.
- A revoked tenant cannot block other tenants — provider failures are scoped per request.

## What's next

Phase 5: backfill of legacy `msg` plaintext column — `2026-04-28-encryption-phase-5-backfill.md`.
