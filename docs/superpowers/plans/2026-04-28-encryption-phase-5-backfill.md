# Encryption Phase 5: Backfill Legacy Plaintext + Drop `msg`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Encrypt every existing row in `agent_conversation_records` that still has plaintext in `msg`, then drop the `msg` column. Add a permanent plaintext-audit cron so the system never silently regresses.

**Architecture:** A scheduled Supabase function (`backfill_encrypt`) runs hourly. Each invocation pulls up to 1000 rows where `msg IS NOT NULL AND msg_ciphertext IS NULL`, encrypts each one with the appropriate tenant `KeyProvider`, populates the ciphertext columns, and then nulls `msg`. A daily cron (`plaintext_audit`) counts surviving plaintext and pages ops if non-zero outside the migration window. After 7 consecutive days of `backfill_pending = 0`, a final migration drops the column.

**Tech Stack:** Supabase scheduled functions (pg_cron + supabase_functions), Deno runtime, the same KeyProvider abstraction from Phase 4.

**Spec reference:** § Data flows / Backfill; § Testing / Compliance and red-team.

**Depends on:** Phases 1–4 merged. The legacy `msg` column is still being **written** in parallel during Phases 1–3; this phase first turns off parallel writes, then drains, then drops the column.

---

## File structure

`monkai-agent-hub`:
- Create `supabase/functions/backfill_encrypt/index.ts` — the cron-triggered backfill worker
- Create `supabase/functions/plaintext_audit/index.ts` — the audit worker
- Create `supabase/migrations/20260526120000_disable_legacy_msg_writes.sql` — adds a guarding flag
- Create `supabase/migrations/20260526121000_schedule_backfill_jobs.sql` — pg_cron schedules
- Create `supabase/migrations/20260615120000_drop_msg_column.sql` — final drop, applied later
- Modify `supabase/functions/monkai-api/index.ts` — stop writing the legacy `msg` column once the gate is on

---

## Task 1: stop writing the legacy `msg` column

**Files:** `supabase/migrations/20260526120000_disable_legacy_msg_writes.sql`, `supabase/functions/monkai-api/index.ts`

This is the first observable change. Until now the edge function wrote both `msg` and `msg_ciphertext` for rollback safety. Now we trust the ciphertext path enough to stop writing plaintext.

- [ ] **Step 1: Add a feature flag column for safety**

```sql
-- migration
INSERT INTO feature_flags (key, enabled) VALUES ('legacy_msg_write_disabled', true)
ON CONFLICT (key) DO UPDATE SET enabled = EXCLUDED.enabled;
```

If `feature_flags` does not exist in this codebase, skip the table-based gate and rely on a code-level constant (next step).

- [ ] **Step 2: Code-level gate — remove the `msg` field from INSERT**

In `monkai-api/index.ts`, every `agent_conversation_records.insert({...})` should drop the `msg: messages` line. Only `msg_ciphertext` and friends are written from now on.

- [ ] **Step 3: Add a regression test**

```typescript
Deno.test("phase 5: insert no longer writes plaintext msg", async () => {
  // POST a conversation, then SELECT and assert msg IS NULL but msg_ciphertext IS NOT NULL.
});
```

- [ ] **Step 4: Commit**

```bash
git add supabase/functions/monkai-api/index.ts supabase/migrations/20260526120000_disable_legacy_msg_writes.sql
git commit -m "feat(edge): stop writing legacy msg column"
```

---

## Task 2: backfill_encrypt scheduled function

**Files:** Create `supabase/functions/backfill_encrypt/index.ts`

- [ ] **Step 1: Implement**

```typescript
// supabase/functions/backfill_encrypt/index.ts
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { Vault } from "../_shared/vault.ts";
import { encryptForStorage } from "../_shared/crypto/at_rest.ts";
import { getProviderFor } from "../_shared/crypto/providers/factory.ts";

const BATCH = 1000;

Deno.serve(async () => {
  const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const vault = new Vault(admin);

  const { data: rows, error } = await admin
    .from("agent_conversation_records")
    .select("id, tenant_id, msg")
    .not("msg", "is", null)
    .is("msg_ciphertext", null)
    .limit(BATCH);

  if (error) return new Response(JSON.stringify({ error: error.message }), { status: 500 });
  if (!rows?.length) return new Response(JSON.stringify({ done: true, processed: 0 }));

  let succeeded = 0;
  const failures: { id: string; error: string }[] = [];

  for (const row of rows) {
    try {
      const provider = await getProviderFor(row.tenant_id, admin, vault);
      const blob = await encryptForStorage(JSON.stringify(row.msg), provider);
      const upd = await admin.from("agent_conversation_records")
        .update({
          msg_ciphertext: bytesToHex(blob.ciphertext),
          nonce: bytesToHex(blob.nonce),
          key_id: blob.keyId,
          encryption_version: 1,
        })
        .eq("id", row.id)
        .is("msg_ciphertext", null);  // guard against concurrent runs
      if (upd.error) throw upd.error;

      const clr = await admin.from("agent_conversation_records")
        .update({ msg: null })
        .eq("id", row.id)
        .not("msg_ciphertext", "is", null);  // only null msg if ciphertext landed
      if (clr.error) throw clr.error;

      succeeded++;
    } catch (e) {
      failures.push({ id: row.id, error: (e as Error).message });
    }
  }

  return new Response(JSON.stringify({ processed: rows.length, succeeded, failures }));
});

function bytesToHex(b: Uint8Array): string {
  return "\\x" + Array.from(b).map(x => x.toString(16).padStart(2, "0")).join("");
}
```

- [ ] **Step 2: Schedule via pg_cron**

```sql
-- migration 20260526121000
SELECT cron.schedule(
  'backfill_encrypt_hourly',
  '17 * * * *',
  $$ SELECT net.http_post(
       url := 'https://<project-ref>.supabase.co/functions/v1/backfill_encrypt',
       headers := jsonb_build_object('Authorization', 'Bearer ' || current_setting('supabase.functions.secret')),
       body := '{}'::jsonb
     ); $$
);
```

- [ ] **Step 3: Add metrics emission**

In the function, after computing `succeeded` and `failures`, write to a `backfill_metrics` table (one row per run) for trending:

```sql
CREATE TABLE IF NOT EXISTS backfill_metrics (
  ran_at timestamptz PRIMARY KEY DEFAULT now(),
  processed int NOT NULL,
  succeeded int NOT NULL,
  failed int NOT NULL,
  notes jsonb
);
```

- [ ] **Step 4: Manual smoke test**

Call the function URL directly with a few staged plaintext rows in a test schema. Assert:

```sql
SELECT count(*) FROM agent_conversation_records WHERE msg IS NOT NULL AND msg_ciphertext IS NULL;
```

returns 0 after running the function once.

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/backfill_encrypt supabase/migrations/20260526121000_schedule_backfill_jobs.sql
git commit -m "feat(backfill): hourly encrypt-and-null worker"
```

---

## Task 3: plaintext_audit scheduled function

**Files:** Create `supabase/functions/plaintext_audit/index.ts`

This function runs daily and emits an alert if any plaintext is left after the migration window has closed.

- [ ] **Step 1: Implement**

```typescript
// supabase/functions/plaintext_audit/index.ts
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

Deno.serve(async () => {
  const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { count, error } = await admin
    .from("agent_conversation_records")
    .select("id", { count: "exact", head: true })
    .not("msg", "is", null);

  if (error) return new Response(JSON.stringify({ error: error.message }), { status: 500 });

  const ALLOWED_DURING_MIGRATION = Number(Deno.env.get("PLAINTEXT_AUDIT_GRACE") ?? "0");
  const status = (count ?? 0) > ALLOWED_DURING_MIGRATION ? "FAIL" : "OK";

  await admin.from("plaintext_audit_log").insert({
    plaintext_count: count,
    status,
  });

  if (status === "FAIL") {
    // Hook into existing alert mechanism (Slack webhook, email, etc.)
    await alertOps(`Plaintext audit FAIL: ${count} rows still have msg IS NOT NULL`);
  }

  return new Response(JSON.stringify({ count, status }));
});

async function alertOps(message: string) {
  const url = Deno.env.get("OPS_ALERT_WEBHOOK");
  if (!url) return;
  await fetch(url, { method: "POST", body: JSON.stringify({ text: message }) });
}
```

- [ ] **Step 2: Schedule**

```sql
SELECT cron.schedule(
  'plaintext_audit_daily',
  '0 9 * * *',
  $$ SELECT net.http_post(
       url := 'https://<project-ref>.supabase.co/functions/v1/plaintext_audit',
       headers := jsonb_build_object('Authorization', 'Bearer ' || current_setting('supabase.functions.secret'))
     ); $$
);
```

Add the schedule to the same migration as the backfill schedule.

- [ ] **Step 3: Set `PLAINTEXT_AUDIT_GRACE` during migration**

While the backfill drains, set `PLAINTEXT_AUDIT_GRACE=999999` in Function App environment. Once `processed = 0` rows return for 7 consecutive days, set it to `0` (the strict check).

- [ ] **Step 4: Commit**

```bash
git add supabase/functions/plaintext_audit
git commit -m "feat(audit): daily plaintext audit cron"
```

---

## Task 4: drain monitoring + final drop

**Files:** Create `supabase/migrations/20260615120000_drop_msg_column.sql`

- [ ] **Step 1: Watch the metrics**

For 7 consecutive days, check that:

```sql
SELECT
  count(*) FILTER (WHERE msg IS NOT NULL) AS pending,
  date_trunc('day', max(ran_at)) AS last_run
FROM agent_conversation_records;
```

returns `pending = 0`.

- [ ] **Step 2: Lock writes briefly to confirm no producer is still writing `msg`**

This is just a SQL audit — the edge function already stopped writing in Task 1. Confirm with:

```sql
SELECT max(created_at) FROM agent_conversation_records WHERE msg IS NOT NULL;
```

The result should be older than the Task 1 deploy date.

- [ ] **Step 3: Migration to drop the column**

```sql
-- 20260615120000_drop_msg_column.sql
-- Final drop after 7 days of plaintext_audit reporting 0.
ALTER TABLE agent_conversation_records DROP COLUMN msg;
```

- [ ] **Step 4: Apply, watch CI, deploy via dev → main**

```bash
supabase migration up
git add supabase/migrations/20260615120000_drop_msg_column.sql
git commit -m "chore(db): drop legacy msg column"
```

- [ ] **Step 5: Set `PLAINTEXT_AUDIT_GRACE=0` in prod env**

After the column is dropped, the daily audit query becomes a count of zero by definition (the column no longer exists). Update the audit function to detect column absence and skip gracefully:

```typescript
const { error } = await admin.rpc("check_msg_column_exists");
if (error?.code === "42703" /* undefined column */) {
  // Column is gone — audit succeeded by construction.
  return new Response(JSON.stringify({ count: 0, status: "OK", note: "column_dropped" }));
}
```

Or simpler: switch the audit to verify ciphertext invariants instead, e.g. "all rows have `msg_ciphertext IS NOT NULL`". Decide based on what you want to keep monitoring long-term — the spec recommends the latter.

- [ ] **Step 6: Commit the audit refresh**

```bash
git add supabase/functions/plaintext_audit/index.ts
git commit -m "feat(audit): switch to ciphertext-presence invariant after column drop"
```

---

## Task 5: PR + production rollout

- [ ] PR everything (Tasks 1–3) against `development`, validate in dev with synthetic data.
- [ ] Merge `development → main` and start the production drain. The pg_cron will kick in automatically.
- [ ] Watch `backfill_metrics` daily for ~7 days. Note: drain time scales with the size of `agent_conversation_records.msg` — at 1k rows/hour, 1M rows takes ~6 weeks. If volume is larger, increase `BATCH` and/or run multiple parallel invocations.
- [ ] After 7 consecutive days of `pending = 0`, open the Task 4 column-drop PR, merge to `main`, deploy.

## Self-review checklist

- The legacy `msg` column is no longer **written** by the edge function before the cron starts running, otherwise the worker chases a moving target.
- The worker uses `is("msg_ciphertext", null)` and `not("msg_ciphertext", "is", null)` guards to be safe against concurrent runs and to never null `msg` until ciphertext is committed.
- `PLAINTEXT_AUDIT_GRACE` starts permissive during migration and drops to 0 after the column is gone — never set to 0 too early or it pages ops every day.
- The final `DROP COLUMN msg` only runs after the audit reports 0 for at least 7 days.

## Post-rollout

- Delete `PLAINTEXT_AUDIT_GRACE` from environment after column drop.
- Update spec document to mark Phase 5 done and link to the audit dashboard.
- Open a follow-up issue tracking the next ops task: scheduled KEK rotation (every 90 days) — out of scope for this spec but unlocked by the infrastructure here.
