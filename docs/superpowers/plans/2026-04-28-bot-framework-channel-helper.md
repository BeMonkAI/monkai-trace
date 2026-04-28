# Bot Framework Channel Helper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship `monkai_trace.integrations.bot_framework.infer_channel(payload)` as a reusable utility, with a parametrised test suite, exported from `monkai_trace.integrations`.

**Architecture:** A single module file with one stateless function and a private mapping constant. Tests are table-driven with `pytest.mark.parametrize`. No runtime hooks, no IO.

**Tech Stack:** Python 3.8+, pytest. Zero new runtime dependencies.

**Spec reference:** `docs/superpowers/specs/2026-04-28-bot-framework-channel-helper-design.md`

---

## File structure

- Create: `monkai_trace/integrations/bot_framework.py`
- Create: `tests/test_bot_framework_integration.py`
- Modify: `monkai_trace/integrations/__init__.py` — re-export `infer_channel`

---

## Task 1: implement helper + tests + export

**Files:**
- Create: `monkai_trace/integrations/bot_framework.py`
- Create: `tests/test_bot_framework_integration.py`
- Modify: `monkai_trace/integrations/__init__.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bot_framework_integration.py`:

```python
"""Tests for the Bot Framework channel inference helper."""

import pytest
from monkai_trace.integrations.bot_framework import infer_channel


@pytest.mark.parametrize("channel_id, expected", [
    ("msteams", "teams"),
    ("directline", "web"),
    ("webchat", "web"),
    ("emulator", "emulator"),
])
def test_known_channel_ids_map_correctly(channel_id, expected):
    assert infer_channel({"channelId": channel_id}) == expected


@pytest.mark.parametrize("channel_id, expected", [
    ("MSTEAMS", "teams"),
    ("MsTeams", "teams"),
    ("DirectLine", "web"),
    ("WEBCHAT", "web"),
])
def test_known_channel_ids_are_case_insensitive(channel_id, expected):
    assert infer_channel({"channelId": channel_id}) == expected


@pytest.mark.parametrize("channel_id, expected", [
    ("slack", "slack"),
    ("Slack", "slack"),
    ("custom-bot", "custom-bot"),
])
def test_unknown_channel_ids_pass_through_lowercased(channel_id, expected):
    assert infer_channel({"channelId": channel_id}) == expected


@pytest.mark.parametrize("payload", [
    {},
    {"channelId": None},
    {"channelId": ""},
])
def test_missing_or_empty_channel_id_returns_unknown(payload):
    assert infer_channel(payload) == "unknown"


def test_other_payload_fields_are_ignored():
    payload = {
        "channelId": "msteams",
        "from": {"id": "user-123", "aadObjectId": "aad-456"},
        "type": "message",
        "text": "hello",
    }
    assert infer_channel(payload) == "teams"


def test_helper_is_exported_at_integrations_level():
    """Verify the flat re-export from monkai_trace.integrations works."""
    from monkai_trace.integrations import infer_channel as flat_export
    assert flat_export({"channelId": "msteams"}) == "teams"
```

- [ ] **Step 2: Run, confirm fail**

```bash
cd ~/Desktop/Monkai/monkai-trace
.venv/bin/pytest tests/test_bot_framework_integration.py -v --no-cov
```

Expected: import error — `monkai_trace.integrations.bot_framework` does not exist.

- [ ] **Step 3: Implement the module**

Create `monkai_trace/integrations/bot_framework.py`:

```python
"""Bot Framework integration helpers for monkai-trace.

Helps callers translate Microsoft Bot Framework activity payloads into the
fields monkai-trace's upload_record expects. Currently scoped to channel
inference; future helpers can land here as Bot Framework adoption grows.
"""

from typing import Mapping

# Microsoft Bot Framework channelId → MonkAI channel string.
# https://learn.microsoft.com/en-us/azure/bot-service/bot-service-channels-reference
_CHANNEL_MAP: Mapping[str, str] = {
    "msteams": "teams",
    "directline": "web",
    "webchat": "web",
    "emulator": "emulator",
}


def infer_channel(payload: dict) -> str:
    """Map a Bot Framework activity's `channelId` to a MonkAI channel string.

    Unknown values pass through lower-cased so the dashboard surfaces them
    for investigation rather than silently mislabelling. Missing or empty
    channelId returns "unknown".

    Args:
        payload: A Bot Framework activity payload (from ``await req.json()``
            in the webhook handler).

    Returns:
        The channel string suitable for ``MonkAIClient.upload_record``'s
        ``external_user_channel`` argument.
    """
    raw = (payload.get("channelId") or "").lower()
    return _CHANNEL_MAP.get(raw, raw or "unknown")
```

- [ ] **Step 4: Add the flat re-export**

Modify `monkai_trace/integrations/__init__.py` from:

```python
"""Integrations for popular AI agent frameworks"""

from .openai_agents import MonkAIRunHooks
from .logging import MonkAILogHandler
from .langchain import MonkAICallbackHandler
from .monkai_agent import MonkAIAgentHooks

__all__ = ["MonkAIRunHooks", "MonkAILogHandler", "MonkAICallbackHandler", "MonkAIAgentHooks"]
```

to:

```python
"""Integrations for popular AI agent frameworks"""

from .openai_agents import MonkAIRunHooks
from .logging import MonkAILogHandler
from .langchain import MonkAICallbackHandler
from .monkai_agent import MonkAIAgentHooks
from .bot_framework import infer_channel

__all__ = [
    "MonkAIRunHooks",
    "MonkAILogHandler",
    "MonkAICallbackHandler",
    "MonkAIAgentHooks",
    "infer_channel",
]
```

- [ ] **Step 5: Run tests until green**

```bash
.venv/bin/pytest tests/test_bot_framework_integration.py -v --no-cov
```

Expected: all parametrized cases pass — total 16 cases (4 known mappings + 4 case-insensitive + 3 passthrough + 3 missing/empty + 1 other-fields-ignored + 1 flat-export).

- [ ] **Step 6: Run regression to ensure no other test broke**

```bash
.venv/bin/pytest tests/test_baseline_anonymizer.py tests/test_client_anonymization.py tests/test_client.py tests/test_models.py tests/test_session_manager.py tests/test_bot_framework_integration.py --no-cov
```

Expected: same baseline pass count from prior PRs, plus the new 16 cases.

- [ ] **Step 7: Commit**

```bash
git add monkai_trace/integrations/bot_framework.py monkai_trace/integrations/__init__.py tests/test_bot_framework_integration.py
git commit -m "$(cat <<'EOF'
feat(integrations): add Bot Framework channel inference helper

Adds monkai_trace.integrations.bot_framework.infer_channel — a stateless
utility that maps a Microsoft Bot Framework activity's channelId to the
channel string MonkAI's dashboard expects. Reusable for any consumer
ingesting Bot Framework activities (Vivo, future integrations).

Mapping covers the four channelIds in current use (msteams/directline/
webchat/emulator); unknown values pass through lower-cased so the
dashboard surfaces them rather than silently mislabelling. Missing or
empty channelId returns "unknown".

This is the monkai-trace-side of Fix 3 of the dedup incident
coordination spec; the Vivo consumer adoption is a one-line change
deferred until the Azure-Servers freeze lifts.

Refs BeMonkAI/monkai-agent-hub#2

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: open PR

**Files:** None (process step).

- [ ] **Step 1: Push the branch**

```bash
cd ~/Desktop/Monkai/monkai-trace
git push -u origin feat/integrations/bot-framework-channel
```

- [ ] **Step 2: Open PR**

```bash
gh pr create --base main \
  --title "feat(integrations): Bot Framework channel helper (Fix 3 of agent-hub#2)" \
  --body "$(cat <<'EOF'
## O que foi feito

- Novo módulo `monkai_trace/integrations/bot_framework.py` com função pública `infer_channel(payload)`
- Mapeia o `channelId` do Microsoft Bot Framework activity payload para a string de channel que o dashboard MonkAI espera (`msteams → teams`, `directline | webchat → web`, `emulator → emulator`)
- Valores desconhecidos passam lower-cased; `channelId` ausente/vazio retorna `unknown`
- Re-export ergonômico via `monkai_trace.integrations.infer_channel`
- 16 casos parametrizados testando: 4 mapeamentos conhecidos × case-insensitive, passthrough de desconhecidos, missing/empty payloads, ignore de outros campos, flat-export funcional

## Por que

Fix 3 do incidente dedup ([BeMonkAI/monkai-agent-hub#2](https://github.com/BeMonkAI/monkai-agent-hub/issues/2)). O Vivo chatbot consumer em `Azure-Servers/.../tracing.py` hardcoda `_CHANNEL = "teams"` para todas as mensagens, mesmo as que vêm do Vivo Chat Hub web. Resultado: dashboard rotula web como Teams.

Como `Azure-Servers` está em freeze (memory `feedback_azure_servers_merge_freeze.md`), este PR ship a utility no SDK. Adoção pelo Vivo consumer é follow-up de ~5 linhas pós-freeze.

Master spec: `BeMonkAI/monkai-agent-hub:docs/superpowers/specs/2026-04-28-dedup-incident-coordination.md`

## Como testar

\`\`\`bash
.venv/bin/pytest tests/test_bot_framework_integration.py -v
\`\`\`

Esperado: 16 passing.

## Backward compatibility

Aditivo. Novo módulo, nova função, nova entrada em `__all__`. Nenhum API existente foi alterado.

## Versionamento

Vai junto com próximo bump regular do SDK.

## Adoção follow-up (issue separada pós-freeze)

Quando freeze do Azure-Servers cair:
- Remover `_CHANNEL = "teams"` em `chatbot_vivo/tracing.py:20`
- `trace_interaction` ganha kwarg `channel: str`
- Webhook chama `trace_interaction(..., channel=infer_channel(payload), ...)`

## Checklist

- [x] Testes passando (16/16 nos arquivos novos)
- [x] Conventional Commits + Co-Authored-By Claude
- [x] Sem mudanças quebradas no API público
- [x] Spec + plano commitados antes do código

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Capture PR URL**

`gh` prints it.

---

## Self-review checklist

- The function is stateless, pure, no side effects.
- The module is importable from `monkai_trace.integrations` AND `monkai_trace.integrations.bot_framework`.
- Unknown values pass through lower-cased — verified by the parametrized tests.
- Missing/null/empty `channelId` returns `unknown` — three explicit tests.
- No runtime dependencies added.
- Adoption follow-up documented in the spec for when the Azure-Servers freeze lifts.

## What's next

After merge: file an adoption issue in `BeMonkAI/Azure-Servers` (drafted but not opened until freeze lifts). Then Phase 1 Hub side encryption (now genuinely the largest unblocked workstream) or any other priority pick.
