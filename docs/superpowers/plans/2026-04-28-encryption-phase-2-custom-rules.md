# Encryption Phase 2: User-Editable Anonymization Rules

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Tenants can define their own anonymization rules in the Hub. The SDK fetches them and applies on top of the baseline. The edge function reapplies any rules the SDK was missing (version drift).

**Architecture:** New `anonymization_rules` table stores per-tenant `{toggles, custom: [{name, pattern, replacement}]}` plus a monotonic `version`. `GET /v1/anonymization-rules` and `PUT /v1/anonymization-rules` expose CRUD. SDK `RulesClient` fetches with 5-minute TTL cache; SDK applies rules client-side and stamps `anonymization_version` on the payload. Edge function compares against the current server `version` and reapplies missing diffs before encrypting at rest.

**Tech Stack:** Same as Phase 1 plus React (for the rules editor screen) and `re2-wasm` (or vetted regex timeout) for safe regex validation server-side.

**Spec reference:** `monkai-trace/docs/superpowers/specs/2026-04-28-trace-hub-encryption-anonymization-design.md` § Components, Data flows / Rules update.

**Depends on:** Phase 1 merged to `main`.

---

## File structure

`monkai-agent-hub`:
- Create `supabase/migrations/20260505120000_anonymization_rules.sql`
- Create `supabase/functions/_shared/anonymization/rules.ts` — apply, validate, diff
- Create `supabase/functions/_shared/anonymization/rules_test.ts`
- Modify `supabase/functions/monkai-api/index.ts` — register GET/PUT, hook `applyServerDiff` into write path
- Create `src/pages/settings/security/AnonymizationRules.tsx`
- Create `src/components/settings/security/RulePreview.tsx`
- Modify `src/App.tsx` (or router config) — register the new route

`monkai-trace`:
- Create `monkai_trace/anonymizer/rules_client.py`
- Create `tests/test_rules_client.py`
- Modify `monkai_trace/client.py` and `async_client.py` — call `RulesClient` and apply custom rules after baseline; stamp `anonymization_version` on outbound payload

---

## Task 1: schema for anonymization_rules

**Files:** Create `supabase/migrations/20260505120000_anonymization_rules.sql`

- [ ] **Step 1: Write migration**

```sql
CREATE TABLE IF NOT EXISTS anonymization_rules (
  tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
  rules jsonb NOT NULL DEFAULT '{"toggles":{},"custom":[]}'::jsonb,
  version int NOT NULL DEFAULT 1,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid REFERENCES users(id)
);

ALTER TABLE anonymization_rules ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anonymization_rules_tenant_read"
  ON anonymization_rules FOR SELECT TO authenticated
  USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

CREATE POLICY "anonymization_rules_admin_write"
  ON anonymization_rules FOR ALL TO authenticated
  USING (
    tenant_id = (auth.jwt() ->> 'tenant_id')::uuid
    AND (auth.jwt() ->> 'role') = 'admin'
  )
  WITH CHECK (
    tenant_id = (auth.jwt() ->> 'tenant_id')::uuid
    AND (auth.jwt() ->> 'role') = 'admin'
  );
```

- [ ] **Step 2: Apply and verify**

```bash
supabase migration up
psql -c "\d anonymization_rules"
```

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260505120000_anonymization_rules.sql
git commit -m "feat(db): add anonymization_rules per tenant"
```

---

## Task 2: server-side rule apply + regex validator

**Files:** Create `supabase/functions/_shared/anonymization/rules.ts` and `rules_test.ts`

- [ ] **Step 1: Write failing tests**

```typescript
// rules_test.ts
import { assert, assertEquals, assertRejects } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { applyRules, validateRule } from "./rules.ts";

Deno.test("applyRules redacts using a single custom rule", () => {
  const rules = [{ name: "mk_id", pattern: "MK-\\d{5}", replacement: "[MK_ID]" }];
  assertEquals(applyRules("user MK-12345 ok", rules), "user [MK_ID] ok");
});

Deno.test("validateRule rejects catastrophic regex", async () => {
  await assertRejects(
    () => validateRule({ name: "evil", pattern: "(a+)+$", replacement: "x" }),
    Error,
    "regex_too_slow",
  );
});

Deno.test("validateRule rejects malformed pattern", async () => {
  await assertRejects(
    () => validateRule({ name: "bad", pattern: "[unclosed", replacement: "x" }),
    Error,
    "invalid_regex",
  );
});

Deno.test("validateRule rejects out-of-range replacement reference", async () => {
  await assertRejects(
    () => validateRule({ name: "x", pattern: "(\\d)", replacement: "$3" }),
    Error,
    "invalid_replacement",
  );
});
```

- [ ] **Step 2: Implement**

```typescript
// rules.ts
export interface CustomRule {
  name: string;
  pattern: string;
  replacement: string;
}

const REGEX_TIMEOUT_MS = 10;
const TEST_INPUT = "x".repeat(10_000);

export function applyRules(text: string, rules: CustomRule[]): string {
  let out = text;
  for (const r of rules) {
    try {
      out = out.replace(new RegExp(r.pattern, "g"), r.replacement);
    } catch {
      // Skip malformed rules at runtime (validator should have caught them).
    }
  }
  return out;
}

export async function validateRule(rule: CustomRule): Promise<void> {
  let re: RegExp;
  try {
    re = new RegExp(rule.pattern, "g");
  } catch {
    throw new Error("invalid_regex");
  }

  const captureCount = countGroups(rule.pattern);
  for (const m of rule.replacement.matchAll(/\$(\d+)/g)) {
    if (parseInt(m[1], 10) > captureCount) throw new Error("invalid_replacement");
  }

  await runWithTimeout(
    () => TEST_INPUT.replace(re, rule.replacement),
    REGEX_TIMEOUT_MS,
    "regex_too_slow",
  );
}

function countGroups(pattern: string): number {
  return (pattern.match(/(?<!\\)\((?!\?)/g) ?? []).length;
}

async function runWithTimeout<T>(fn: () => T, ms: number, errorCode: string): Promise<T> {
  return await Promise.race([
    new Promise<T>((resolve) => resolve(fn())),
    new Promise<T>((_, reject) => setTimeout(() => reject(new Error(errorCode)), ms)),
  ]);
}
```

> Note: Deno's regex engine is V8 — vulnerable to catastrophic backtracking. The 10ms timeout against a 10kb test input is the safety net. If a future iteration moves to `re2-wasm`, `runWithTimeout` becomes a belt-and-suspenders check.

- [ ] **Step 3: Run tests**

```bash
deno test supabase/functions/_shared/anonymization/rules_test.ts
```

- [ ] **Step 4: Commit**

```bash
git add supabase/functions/_shared/anonymization/
git commit -m "feat(edge): server-side anonymization rule apply + validator"
```

---

## Task 3: GET/PUT /v1/anonymization-rules endpoints

**Files:** Modify `supabase/functions/monkai-api/index.ts`

- [ ] **Step 1: Add the routes**

Add a router branch for `/v1/anonymization-rules`:

```typescript
if (url.pathname === "/v1/anonymization-rules") {
  if (req.method === "GET") return getRules(req, supabase);
  if (req.method === "PUT") return putRules(req, supabase);
  return new Response("method not allowed", { status: 405 });
}
```

Implement:

```typescript
async function getRules(req: Request, supabase: SupabaseClient) {
  const tenantId = await tenantFromAuth(req);
  const { data, error } = await supabase
    .from("anonymization_rules")
    .select("rules, version")
    .eq("tenant_id", tenantId)
    .maybeSingle();
  if (error) return jsonError(500, "rules_fetch_failed", error.message);
  if (!data) {
    return new Response(JSON.stringify({ version: 0, rules: { toggles: {}, custom: [] } }), {
      headers: { "content-type": "application/json" },
    });
  }
  return new Response(JSON.stringify(data), { headers: { "content-type": "application/json" } });
}

async function putRules(req: Request, supabase: SupabaseClient) {
  const tenantId = await tenantFromAuth(req);
  const body = await req.json();
  for (const r of body.rules?.custom ?? []) {
    try {
      await validateRule(r);
    } catch (e) {
      return jsonError(400, (e as Error).message, `rule ${r.name}`);
    }
  }
  const { data, error } = await supabase
    .from("anonymization_rules")
    .upsert({
      tenant_id: tenantId,
      rules: body.rules,
      version: (body.expectedVersion ?? 0) + 1,
      updated_at: new Date().toISOString(),
    })
    .select("version")
    .single();
  if (error?.code === "23505") return jsonError(409, "version_conflict", "");
  if (error) return jsonError(500, "rules_save_failed", error.message);
  return new Response(JSON.stringify(data), { headers: { "content-type": "application/json" } });
}
```

- [ ] **Step 2: Add an integration test**

In `integration_test.ts`, add cases: PUT with a valid rule returns version 2; PUT with `(a+)+$` returns 400.

- [ ] **Step 3: Commit**

```bash
git add supabase/functions/monkai-api/index.ts supabase/functions/monkai-api/integration_test.ts
git commit -m "feat(edge): GET/PUT /v1/anonymization-rules"
```

---

## Task 4: server reapply on version drift in write path

**Files:** Modify `supabase/functions/monkai-api/index.ts` (write handler from Phase 1)

- [ ] **Step 1: Fetch current rules version + apply diff before encrypt**

```typescript
const { data: rulesRow } = await supabase
  .from("anonymization_rules")
  .select("rules, version")
  .eq("tenant_id", tenantId)
  .maybeSingle();

const serverVersion = rulesRow?.version ?? 0;
const payloadVersion = body.anonymization_version ?? 0;

let sanitized = body.msg;
if (payloadVersion < serverVersion && rulesRow?.rules?.custom?.length) {
  const text = JSON.stringify(sanitized);
  const reapplied = applyRules(text, rulesRow.rules.custom);
  sanitized = JSON.parse(reapplied);
}

const enc = await buildEncryptedColumns(vault, tenantId, sanitized);
// then INSERT including `anonymization_version: serverVersion`
```

- [ ] **Step 2: Add an integration test for version drift**

Upload with `anonymization_version: 0` and a rule existing at version 1. Read row back; assert custom rule was applied.

- [ ] **Step 3: Commit**

```bash
git add supabase/functions/monkai-api/index.ts
git commit -m "feat(edge): reapply server-side rules on version drift"
```

---

## Task 5: SDK — RulesClient with TTL cache

**Files:** Create `monkai_trace/anonymizer/rules_client.py` and `tests/test_rules_client.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_rules_client.py
from unittest.mock import patch
import pytest
from monkai_trace.anonymizer.rules_client import RulesClient, RulesUnavailable


def test_fetches_and_caches():
    with patch("monkai_trace.anonymizer.rules_client.requests.get") as g:
        g.return_value.status_code = 200
        g.return_value.json.return_value = {"version": 3, "rules": {"toggles": {}, "custom": []}}
        c = RulesClient(token="tk_x", base_url="http://h", ttl=300)
        a = c.get()
        b = c.get()
        assert a == b
        assert g.call_count == 1


def test_blocks_when_never_fetched_and_failing():
    with patch("monkai_trace.anonymizer.rules_client.requests.get", side_effect=RuntimeError):
        c = RulesClient(token="tk_x", base_url="http://h", ttl=300)
        with pytest.raises(RulesUnavailable):
            c.get()


def test_uses_stale_cache_on_failure_after_first_success():
    with patch("monkai_trace.anonymizer.rules_client.requests.get") as g:
        g.return_value.status_code = 200
        g.return_value.json.return_value = {"version": 1, "rules": {"toggles": {}, "custom": []}}
        c = RulesClient(token="tk_x", base_url="http://h", ttl=0)  # immediate expiry
        c.get()
        g.side_effect = RuntimeError
        result = c.get()
        assert result["version"] == 1
```

- [ ] **Step 2: Implement**

```python
# monkai_trace/anonymizer/rules_client.py
import time
import logging
import requests

logger = logging.getLogger(__name__)


class RulesUnavailable(Exception):
    pass


class RulesClient:
    def __init__(self, token: str, base_url: str, ttl: int = 300):
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._ttl = ttl
        self._cache = None
        self._cached_at = 0.0

    def get(self) -> dict:
        now = time.time()
        if self._cache and (now - self._cached_at) < self._ttl:
            return self._cache
        try:
            r = requests.get(
                f"{self._base_url}/v1/anonymization-rules",
                headers={"authorization": f"Bearer {self._token}"},
                timeout=5,
            )
            r.raise_for_status()
            self._cache = r.json()
            self._cached_at = now
            return self._cache
        except Exception:
            logger.exception("rules fetch failed")
            if self._cache is not None:
                return self._cache
            raise RulesUnavailable()
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_rules_client.py -v
```

- [ ] **Step 4: Commit**

```bash
git add monkai_trace/anonymizer/rules_client.py tests/test_rules_client.py
git commit -m "feat(anonymizer): RulesClient with TTL cache"
```

---

## Task 6: SDK — apply custom rules and stamp version on payload

**Files:** Modify `monkai_trace/client.py`, `monkai_trace/async_client.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/test_client_custom_rules.py
import json
from unittest.mock import patch, MagicMock
from monkai_trace import MonkAIClient


def test_applies_custom_rule_and_stamps_version():
    client = MonkAIClient(tracer_token="tk_test")
    client._rules_client._cache = {"version": 7, "rules": {
        "toggles": {},
        "custom": [{"name": "mk_id", "pattern": r"MK-\d+", "replacement": "[MK_ID]"}],
    }}
    client._rules_client._cached_at = 1e12

    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured.update(json)
        resp = MagicMock(); resp.status_code = 201
        resp.json.return_value = {"inserted_count": 1}
        return resp

    with patch("requests.Session.post", side_effect=fake_post):
        client.upload_record(
            namespace="t", agent="b",
            messages=[{"role": "user", "content": "id MK-12345 ok"}],
        )
    assert captured["anonymization_version"] == 7
    assert "MK-12345" not in json.dumps(captured)
    assert "[MK_ID]" in json.dumps(captured)
```

- [ ] **Step 2: Wire into client**

In `MonkAIClient.__init__`, instantiate `self._rules_client = RulesClient(tracer_token, self.base_url)`. In `_anonymize_messages`:

```python
def _anonymize_messages(self, messages):
    rules = self._rules_client.get()
    custom = rules["rules"].get("custom", [])
    if isinstance(messages, dict):
        messages = [messages]
    out = []
    for msg in messages:
        if isinstance(msg, dict) and "content" in msg and isinstance(msg["content"], str):
            new_msg = dict(msg)
            text = self._anonymizer.apply(msg["content"])
            for r in custom:
                text = re.sub(r["pattern"], r["replacement"], text)
            new_msg["content"] = text
            out.append(new_msg)
        else:
            out.append(msg)
    self._anonymization_version = rules["version"]
    return out
```

In `upload_record`, after building the record, set the payload's `anonymization_version` to `self._anonymization_version`.

- [ ] **Step 3: Mirror in async client**

Replace `requests` with `aiohttp`-equivalent fetch inside an async variant of `RulesClient.get_async()` (or wrap in `asyncio.to_thread`).

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_client_custom_rules.py -v
```

- [ ] **Step 5: Commit**

```bash
git add monkai_trace/client.py monkai_trace/async_client.py tests/test_client_custom_rules.py
git commit -m "feat(client): apply custom rules + stamp anonymization_version"
```

---

## Task 7: Hub UI — AnonymizationRules editor

**Files:** Create `src/pages/settings/security/AnonymizationRules.tsx` and `src/components/settings/security/RulePreview.tsx`

- [ ] **Step 1: Write the screen**

```tsx
// src/pages/settings/security/AnonymizationRules.tsx
import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { RulePreview } from "@/components/settings/security/RulePreview";

interface CustomRule { name: string; pattern: string; replacement: string }
interface RulesDoc { toggles: Record<string, boolean>; custom: CustomRule[] }

const BASELINE_TOGGLES = ["cpf", "cnpj", "email", "brazilian_phone", "credit_card", "ip", "rg"];

export default function AnonymizationRules() {
  const [doc, setDoc] = useState<RulesDoc>({ toggles: {}, custom: [] });
  const [version, setVersion] = useState(0);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch("/functions/v1/monkai-api/v1/anonymization-rules", {
      headers: { authorization: `Bearer ${supabase.auth.getSession().then(s => s.data.session?.access_token)}` },
    })
      .then(r => r.json())
      .then(j => { setDoc(j.rules); setVersion(j.version); });
  }, []);

  async function save() {
    setSaving(true);
    const r = await fetch("/functions/v1/monkai-api/v1/anonymization-rules", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ rules: doc, expectedVersion: version }),
    });
    setSaving(false);
    if (!r.ok) {
      alert(`Erro: ${(await r.json()).code}`);
      return;
    }
    setVersion((await r.json()).version);
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-semibold">Regras de anonimização</h1>
      <p className="text-sm text-muted-foreground">
        Versão atual: {version}. Mudanças propagam para SDKs em até 5 minutos.
      </p>

      <section>
        <h2 className="font-medium">Classes baseline</h2>
        {BASELINE_TOGGLES.map(t => (
          <label key={t} className="flex items-center gap-2 py-1">
            <Switch
              checked={doc.toggles[t] !== false}
              onCheckedChange={v => setDoc(d => ({ ...d, toggles: { ...d.toggles, [t]: v } }))}
            />
            <span>{t}</span>
          </label>
        ))}
      </section>

      <section>
        <h2 className="font-medium">Regras customizadas</h2>
        {doc.custom.map((r, i) => (
          <div key={i} className="grid grid-cols-4 gap-2 py-1">
            <Input value={r.name} onChange={e => updateRule(i, { name: e.target.value })} placeholder="nome" />
            <Input value={r.pattern} onChange={e => updateRule(i, { pattern: e.target.value })} placeholder="regex" />
            <Input value={r.replacement} onChange={e => updateRule(i, { replacement: e.target.value })} placeholder="substituição" />
            <Button variant="destructive" onClick={() => removeRule(i)}>Remover</Button>
          </div>
        ))}
        <Button onClick={addRule} className="mt-2">Adicionar regra</Button>
      </section>

      <RulePreview rules={doc} />

      <Button onClick={save} disabled={saving}>{saving ? "Salvando..." : "Salvar"}</Button>
    </div>
  );

  function updateRule(i: number, patch: Partial<CustomRule>) {
    setDoc(d => ({ ...d, custom: d.custom.map((x, j) => (j === i ? { ...x, ...patch } : x)) }));
  }
  function removeRule(i: number) {
    setDoc(d => ({ ...d, custom: d.custom.filter((_, j) => j !== i) }));
  }
  function addRule() {
    setDoc(d => ({ ...d, custom: [...d.custom, { name: "", pattern: "", replacement: "[REDACTED]" }] }));
  }
}
```

- [ ] **Step 2: Implement RulePreview**

```tsx
// src/components/settings/security/RulePreview.tsx
import { useMemo, useState } from "react";
import { Textarea } from "@/components/ui/textarea";

export function RulePreview({ rules }: { rules: { custom: { pattern: string; replacement: string }[] } }) {
  const [input, setInput] = useState("Texto de teste — CPF 123.456.789-09 + arthur@monkai.com.br");
  const output = useMemo(() => {
    let out = input;
    for (const r of rules.custom) {
      try { out = out.replace(new RegExp(r.pattern, "g"), r.replacement); } catch {}
    }
    return out;
  }, [input, rules.custom]);
  return (
    <section className="space-y-2">
      <h2 className="font-medium">Preview</h2>
      <Textarea value={input} onChange={e => setInput(e.target.value)} rows={3} />
      <Textarea value={output} readOnly rows={3} />
    </section>
  );
}
```

- [ ] **Step 3: Register route + add to settings nav**

Add `<Route path="/settings/security/anonymization" element={<AnonymizationRules />} />` and a nav entry.

- [ ] **Step 4: Vitest smoke test**

```tsx
// src/pages/settings/security/AnonymizationRules.test.tsx
import { render, screen } from "@testing-library/react";
import AnonymizationRules from "./AnonymizationRules";

test("renders baseline toggles", () => {
  render(<AnonymizationRules />);
  for (const t of ["cpf", "cnpj", "email"]) {
    expect(screen.getByText(t)).toBeInTheDocument();
  }
});
```

- [ ] **Step 5: Commit**

```bash
git add src/pages/settings/security src/components/settings/security
git commit -m "feat(ui): anonymization rules editor"
```

---

## Task 8: Open SDK + Hub PRs and validate in dev

- [ ] Open SDK PR for the `RulesClient` + custom rule application.
- [ ] Open Hub PR for the migration, edge function endpoints, and UI.
- [ ] After dev merge: visit `/settings/security/anonymization`, add a rule like `MK-\d+ → [MK_ID]`, save, send a test record from the SDK, and confirm reading it back shows `[MK_ID]`.
- [ ] PR `development → main` in both repos.

## Self-review checklist

- The PUT endpoint always validates every custom rule before persisting.
- Server reapply only kicks in when `payload.anonymization_version < server.version` AND there are custom rules. No-op otherwise.
- Frontend's "version" displayed matches what the server returned; saving sends `expectedVersion` so concurrent edits collide with `409 version_conflict`.
- The SDK never sends raw content if `RulesClient.get()` raises `RulesUnavailable` and there is no cache.

## What's next

Phase 3: envelope encryption client-side — see `2026-04-28-encryption-phase-3-envelope.md`.
