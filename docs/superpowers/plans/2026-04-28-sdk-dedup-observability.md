# SDK Dedup Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `strict_dedup` constructor flag to `MonkAIClient`/`AsyncMonkAIClient` plus a helper that inspects every upload response, emits a `WARNING` log when the Hub reports drops, and raises `MonkAIRecordDiscardedError` when strict mode is on.

**Architecture:** A small file-local helper `_check_dedup_response(response_dict, total_records)` is wired into the two converging upload sites (`_upload_single_record`, `_upload_records_chunk`) on both clients. New exception class extends the existing `MonkAIAPIError` so it is caught by code that already handles API errors generically.

**Tech Stack:** Python 3.8+, existing `requests`/`aiohttp` transport, standard `logging`. No new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-04-28-sdk-dedup-observability-design.md`

---

## File structure

- Modify: `monkai_trace/exceptions.py` — add `MonkAIRecordDiscardedError`
- Modify: `monkai_trace/client.py` — add constructor flag, helper, wire into 2 return sites
- Modify: `monkai_trace/async_client.py` — same as sync
- Modify: `monkai_trace/__init__.py` — export `MonkAIRecordDiscardedError`
- Create: `tests/test_client_dedup_observability.py` — sync client tests
- Create: `tests/test_async_client_dedup_observability.py` — async client tests

---

## Task 1: exception class

**Files:**
- Modify: `monkai_trace/exceptions.py`
- Modify: `monkai_trace/__init__.py`

- [ ] **Step 1: Read the existing exceptions module**

```bash
cat ~/Desktop/Monkai/monkai-trace/monkai_trace/exceptions.py
```

Confirm `MonkAIAPIError` exists and note its constructor signature so the new class extends correctly.

- [ ] **Step 2: Append the new exception class**

In `monkai_trace/exceptions.py`, after the existing `MonkAIAPIError` class, append:

```python
class MonkAIRecordDiscardedError(MonkAIAPIError):
    """Raised in strict_dedup mode when the server reports records were deduplicated.

    Attributes:
        dropped_count: number of records the server dropped as duplicates
        inserted_count: number of records the server actually inserted
        total_received: total records sent in the request
    """
    def __init__(
        self,
        message: str,
        dropped_count: int,
        inserted_count: int,
        total_received: int,
    ):
        super().__init__(message)
        self.dropped_count = dropped_count
        self.inserted_count = inserted_count
        self.total_received = total_received
```

If `MonkAIAPIError`'s constructor takes additional positional arguments (e.g. status_code), adapt the `super().__init__(...)` call to match. Read the file first.

- [ ] **Step 3: Export from `__init__.py`**

In `monkai_trace/__init__.py`, find the `from .exceptions import (` block. Add `MonkAIRecordDiscardedError` to the import list. Find the `__all__` list and add `"MonkAIRecordDiscardedError"`.

- [ ] **Step 4: Smoke check the import works**

```bash
cd ~/Desktop/Monkai/monkai-trace
.venv/bin/python -c "from monkai_trace import MonkAIRecordDiscardedError; e = MonkAIRecordDiscardedError('test', 1, 0, 1); print(e.dropped_count, e.inserted_count, e.total_received)"
```

Expected output: `1 0 1`.

- [ ] **Step 5: Commit**

```bash
git add monkai_trace/exceptions.py monkai_trace/__init__.py
git commit -m "$(cat <<'EOF'
feat(exceptions): add MonkAIRecordDiscardedError

Raised in strict_dedup mode when the server reports records were
deduplicated. Carries dropped_count, inserted_count, total_received
for callers that need to act on the loss.

Refs BeMonkAI/monkai-agent-hub#2

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: sync client — constructor flag, helper, wiring, tests

**Files:**
- Modify: `monkai_trace/client.py`
- Create: `tests/test_client_dedup_observability.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_client_dedup_observability.py`:

```python
"""Verify the SDK surfaces server-side dedup drops to callers."""

import logging
from unittest.mock import patch, MagicMock
import pytest
from monkai_trace import MonkAIClient, MonkAIRecordDiscardedError


def _fake_response(json_payload, status=201):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_payload
    return resp


def test_clean_insert_no_warning_no_raise(caplog):
    client = MonkAIClient(tracer_token="tk_test", strict_dedup=True)

    with patch("requests.Session.request", return_value=_fake_response({"inserted_count": 1})):
        with caplog.at_level(logging.WARNING, logger="monkai_trace.client"):
            result = client.upload_record(
                namespace="t", agent="a",
                messages=[{"role": "user", "content": "hi"}],
            )

    assert result == {"inserted_count": 1}
    assert "dropped" not in caplog.text.lower()


def test_all_dup_emits_warning(caplog):
    client = MonkAIClient(tracer_token="tk_test")

    payload = {"inserted_count": 0, "duplicate": True, "tokens_processed": 0}
    with patch("requests.Session.request", return_value=_fake_response(payload, status=200)):
        with caplog.at_level(logging.WARNING, logger="monkai_trace.client"):
            client.upload_record(
                namespace="t", agent="a",
                messages=[{"role": "user", "content": "hi"}],
            )

    assert "dropped 1/1" in caplog.text.lower()


def test_partial_drop_emits_warning_for_batch(caplog):
    from monkai_trace.models import ConversationRecord

    client = MonkAIClient(tracer_token="tk_test")
    records = [
        ConversationRecord(namespace="t", agent="a",
                           msg=[{"role": "user", "content": f"msg_{i}"}])
        for i in range(10)
    ]
    payload = {"inserted_count": 8, "duplicates_skipped": 2}

    with patch("requests.Session.request", return_value=_fake_response(payload)):
        with caplog.at_level(logging.WARNING, logger="monkai_trace.client"):
            client.upload_records_batch(records, chunk_size=10)

    assert "dropped 2/10" in caplog.text.lower()


def test_strict_mode_raises_on_drop():
    client = MonkAIClient(tracer_token="tk_test", strict_dedup=True)

    payload = {"inserted_count": 0, "duplicate": True}
    with patch("requests.Session.request", return_value=_fake_response(payload, status=200)):
        with pytest.raises(MonkAIRecordDiscardedError) as exc_info:
            client.upload_record(
                namespace="t", agent="a",
                messages=[{"role": "user", "content": "hi"}],
            )

    err = exc_info.value
    assert err.dropped_count == 1
    assert err.inserted_count == 0
    assert err.total_received == 1


def test_strict_mode_no_raise_on_clean():
    client = MonkAIClient(tracer_token="tk_test", strict_dedup=True)

    with patch("requests.Session.request", return_value=_fake_response({"inserted_count": 1})):
        # No raise.
        client.upload_record(
            namespace="t", agent="a",
            messages=[{"role": "user", "content": "hi"}],
        )
```

- [ ] **Step 2: Run tests, confirm fail**

```bash
.venv/bin/pytest tests/test_client_dedup_observability.py -v --no-cov
```

Expected: at least the strict_mode test errors with `TypeError: ... unexpected keyword argument 'strict_dedup'`. Other tests may pass-by-accident if no warning shows up — log assertions will fail.

- [ ] **Step 3: Add the constructor flag and helper**

In `monkai_trace/client.py`:

a) At the top, add the import:

```python
from .exceptions import (
    MonkAIAuthError,
    MonkAIValidationError,
    MonkAIServerError,
    MonkAINetworkError,
    MonkAIAPIError,
    MonkAIRecordDiscardedError,
)
```

(Update the existing `from .exceptions import (...)` line — the surrounding imports already use this style.)

b) Modify `MonkAIClient.__init__`. Add the new parameter to the signature (after `max_retries: int = 3`):

```python
strict_dedup: bool = False,
```

Update the docstring to mention it. In the body, after the existing assignments (`self._anonymizer = BaselineAnonymizer()` from Phase 1):

```python
self._strict_dedup = strict_dedup
```

c) Add the helper method on `MonkAIClient`. Place it next to the other private helpers (e.g. near `_anonymize_messages`):

```python
def _check_dedup_response(self, response_dict, total_records):
    """Inspect upload response for server-side dedup drops.

    Logs a warning whenever the server reports drops. In strict_dedup mode,
    raises MonkAIRecordDiscardedError. Returns the response_dict unchanged.
    """
    inserted = response_dict.get("inserted_count", total_records)
    skipped = response_dict.get("duplicates_skipped", 0)
    is_all_dup = response_dict.get("duplicate") is True

    if is_all_dup:
        dropped = total_records
    else:
        dropped = skipped

    if dropped > 0:
        logger.warning(
            f"MonkAI dropped {dropped}/{total_records} records as duplicates within 60s window"
        )
        if self._strict_dedup:
            raise MonkAIRecordDiscardedError(
                f"Server discarded {dropped}/{total_records} records as duplicates",
                dropped_count=dropped,
                inserted_count=inserted,
                total_received=total_records,
            )

    return response_dict
```

d) Wire into the two return sites:

In `_upload_single_record` (currently around line 323), replace:
```python
return response.json()
```
with:
```python
return self._check_dedup_response(response.json(), total_records=1)
```

In `_upload_records_chunk` (currently around line 330), replace:
```python
return response.json()
```
with:
```python
return self._check_dedup_response(response.json(), total_records=len(records))
```

- [ ] **Step 4: Run tests until green**

```bash
.venv/bin/pytest tests/test_client_dedup_observability.py -v --no-cov
```

Expected: 5 passing.

- [ ] **Step 5: Commit**

```bash
git add monkai_trace/client.py tests/test_client_dedup_observability.py
git commit -m "$(cat <<'EOF'
feat(client): surface server dedup drops via warning + strict mode

MonkAIClient gains a strict_dedup constructor flag (default False).
A new helper inspects every upload response (single + batch) and
logs a WARNING when the server reports drops. In strict_dedup mode
the helper raises MonkAIRecordDiscardedError instead of returning.
Backward compatible: callers that ignored the response dict keep
working.

Refs BeMonkAI/monkai-agent-hub#2

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: async client mirror

**Files:**
- Modify: `monkai_trace/async_client.py`
- Create: `tests/test_async_client_dedup_observability.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_async_client_dedup_observability.py`:

```python
"""Verify the async SDK client surfaces server-side dedup drops."""

import logging
from unittest.mock import patch, MagicMock, AsyncMock
import pytest
from monkai_trace import AsyncMonkAIClient, MonkAIRecordDiscardedError


def _fake_aiohttp_response(json_payload, status=201):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_payload)
    resp.text = AsyncMock(return_value="")
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


@pytest.mark.asyncio
async def test_clean_insert_no_warning_no_raise(caplog):
    client = AsyncMonkAIClient(tracer_token="tk_test", strict_dedup=True)

    fake = _fake_aiohttp_response({"inserted_count": 1})
    with patch("aiohttp.ClientSession.request", return_value=fake):
        async with client:
            with caplog.at_level(logging.WARNING, logger="monkai_trace.async_client"):
                result = await client.upload_record(
                    namespace="t", agent="a",
                    messages=[{"role": "user", "content": "hi"}],
                )

    assert result == {"inserted_count": 1}
    assert "dropped" not in caplog.text.lower()


@pytest.mark.asyncio
async def test_all_dup_emits_warning(caplog):
    client = AsyncMonkAIClient(tracer_token="tk_test")

    fake = _fake_aiohttp_response({"inserted_count": 0, "duplicate": True}, status=200)
    with patch("aiohttp.ClientSession.request", return_value=fake):
        async with client:
            with caplog.at_level(logging.WARNING, logger="monkai_trace.async_client"):
                await client.upload_record(
                    namespace="t", agent="a",
                    messages=[{"role": "user", "content": "hi"}],
                )

    assert "dropped 1/1" in caplog.text.lower()


@pytest.mark.asyncio
async def test_strict_mode_raises_on_drop():
    client = AsyncMonkAIClient(tracer_token="tk_test", strict_dedup=True)

    fake = _fake_aiohttp_response({"inserted_count": 0, "duplicate": True}, status=200)
    with patch("aiohttp.ClientSession.request", return_value=fake):
        async with client:
            with pytest.raises(MonkAIRecordDiscardedError) as exc_info:
                await client.upload_record(
                    namespace="t", agent="a",
                    messages=[{"role": "user", "content": "hi"}],
                )

    err = exc_info.value
    assert err.dropped_count == 1
    assert err.total_received == 1


@pytest.mark.asyncio
async def test_strict_mode_no_raise_on_clean():
    client = AsyncMonkAIClient(tracer_token="tk_test", strict_dedup=True)

    fake = _fake_aiohttp_response({"inserted_count": 1})
    with patch("aiohttp.ClientSession.request", return_value=fake):
        async with client:
            await client.upload_record(
                namespace="t", agent="a",
                messages=[{"role": "user", "content": "hi"}],
            )
```

If the repo already has an `pytest-asyncio` config (check `pyproject.toml`), the `@pytest.mark.asyncio` decorator should just work. If not, add `pytest-asyncio` to dev dependencies and a `pyproject.toml` config block setting `asyncio_mode = "auto"`. Confirm by reading `pyproject.toml` first.

(The plan deliberately omits the partial-drop batch test on async because the async client's batch path mirrors the sync one and a single representative case is enough for the smaller branch.)

- [ ] **Step 2: Run, confirm fail**

```bash
.venv/bin/pytest tests/test_async_client_dedup_observability.py -v --no-cov
```

Expected: TypeError on `strict_dedup` keyword and missing-helper failures.

- [ ] **Step 3: Mirror the change in `async_client.py`**

a) Update the imports — same change as sync, plus the existing `logger = logging.getLogger(__name__)` line if not present (check the file).

b) Add `strict_dedup: bool = False` to `AsyncMonkAIClient.__init__` signature; assign `self._strict_dedup = strict_dedup` in the body.

c) Add the same `_check_dedup_response` method on `AsyncMonkAIClient` (the helper is synchronous — no `await`s — so the method is `def`, not `async def`).

d) Replace the two `return response.json()` (or `await response.json()`) sites in `_upload_single_record` and `_upload_records_chunk` with:

```python
return self._check_dedup_response(await response.json(), total_records=1)
```

and

```python
return self._check_dedup_response(await response.json(), total_records=len(records))
```

(Adjust to whatever the async client's exact response.json access pattern is — read it first.)

- [ ] **Step 4: Run tests until green**

```bash
.venv/bin/pytest tests/test_async_client_dedup_observability.py -v --no-cov
```

Expected: 4 passing.

- [ ] **Step 5: Run the full SDK suite to ensure no regression**

```bash
.venv/bin/pytest tests/test_baseline_anonymizer.py tests/test_client_anonymization.py tests/test_client.py tests/test_models.py tests/test_session_manager.py tests/test_client_dedup_observability.py tests/test_async_client_dedup_observability.py --no-cov
```

Expected: all green. Pre-existing test errors from missing optional deps (langchain, openai-agents, monkai_agent integration tests) are noise — confirm they look like the same failures present before this task started.

- [ ] **Step 6: Commit**

```bash
git add monkai_trace/async_client.py tests/test_async_client_dedup_observability.py
git commit -m "$(cat <<'EOF'
feat(async-client): mirror dedup observability + strict mode

Same strict_dedup constructor flag and _check_dedup_response helper
as the sync client. Closes the parity gap that existed in Phase 1
(only the sync client had an integration test).

Refs BeMonkAI/monkai-agent-hub#2

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: open PR to main

**Files:** None (process step).

- [ ] **Step 1: Push the branch**

```bash
cd ~/Desktop/Monkai/monkai-trace
git push -u origin feat/security/sdk-dedup-observability
```

- [ ] **Step 2: Open PR**

```bash
gh pr create --base main \
  --title "feat(client): dedup observability + strict mode (Fix 2 of agent-hub#2)" \
  --body "$(cat <<'EOF'
## O que foi feito

- Novo constructor flag `strict_dedup: bool = False` em `MonkAIClient` e `AsyncMonkAIClient`
- Helper `_check_dedup_response` inspeciona toda response de upload e loga `WARNING` quando o servidor reporta drops
- Em modo strict, levanta `MonkAIRecordDiscardedError` (extends `MonkAIAPIError`) com `dropped_count`, `inserted_count`, `total_received`
- 9 testes novos (5 sync + 4 async) cobrindo: clean response, all-dup, partial drop, strict + drop, strict + clean

## Por que

Issue [BeMonkAI/monkai-agent-hub#2](https://github.com/BeMonkAI/monkai-agent-hub/issues/2) — Fix 2 do incidente. Após o Fix 1 (PR agent-hub#3, mergeado) o servidor para de dropar mensagens legítimas, mas a SDK ainda não inspeciona `inserted_count` na resposta. Wrappers como `Azure-Servers/.../tracing.py:152` logam "Record uploaded" cegamente em qualquer 200, escondendo retries genuínos do operador.

Com este fix:
- Default: warning logado quando server reporta drop (não-breaking)
- Opt-in: `MonkAIClient(strict_dedup=True)` para callers que querem falha hard (testes E2E, alertas)

Master spec do incidente: `monkai-agent-hub/docs/superpowers/specs/2026-04-28-dedup-incident-coordination.md`

## Como testar

\`\`\`bash
.venv/bin/pytest tests/test_client_dedup_observability.py tests/test_async_client_dedup_observability.py -v
\`\`\`

Esperado: 9 passing.

## Backward compatibility

- `strict_dedup=False` é o default → comportamento atual preservado
- `MonkAIRecordDiscardedError extends MonkAIAPIError` → callers com `except MonkAIAPIError` continuam funcionando
- Apenas adições à API; nenhuma assinatura de método público mudou

## Versionamento

Bump minor na próxima release no PyPI.

## Checklist

- [x] Testes passando (9/9 nos arquivos novos)
- [x] Conventional Commits + Co-Authored-By Claude
- [x] Sem mudanças quebradas no API público
- [x] Spec + plano commitados juntos no mesmo PR

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Capture the PR URL**

The `gh` command prints it. Note for status tracking.

---

## Self-review checklist

- The helper `_check_dedup_response` is identical (modulo logger import) on both clients. If they differ, that's an inconsistency to fix.
- All four upload entry points (`upload_record`, `upload_records_batch`, `upload_records_from_json` for sync; same set for async) flow through `_upload_single_record` or `_upload_records_chunk`, so the wiring at those two methods is sufficient.
- `MonkAIRecordDiscardedError` extends `MonkAIAPIError` so existing exception handlers catch it.
- No public API removed or renamed.
- Default `strict_dedup=False` preserves existing behaviour.
- Tests use the same mock patch target (`requests.Session.request` for sync, `aiohttp.ClientSession.request` for async) that Phase 1's integration tests established.

## What's next

After merge: SDK release on PyPI (minor bump). The Vivo `Azure-Servers/.../tracing.py` wrapper will start logging the warnings on its own without code changes — the warning level is enough to surface drops in App Insights.

Then: resume Phase 1 Hub side of the encryption rollout (now unblocked since Fix 1 is in production, dedup is correct, and the SDK observability will let us spot any regression). Plan: `docs/superpowers/plans/2026-04-28-encryption-phase-1-at-rest.md` Tasks 4-11.
