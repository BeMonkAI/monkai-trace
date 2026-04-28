# Bot Framework Channel Inference Helper

**Date:** 2026-04-28
**Status:** Design approved, pending implementation plan
**Sub-project of:** `monkai-agent-hub/docs/superpowers/specs/2026-04-28-dedup-incident-coordination.md` (Fix 3)
**Repo:** `monkai-trace`
**Affected modules:** `monkai_trace/integrations/bot_framework.py` (new)

## Problem

The Vivo consumer in `Azure-Servers/.../tracing.py` hardcodes `_CHANNEL = "teams"` for every conversation it traces. The same handler serves messages from Microsoft Teams and from the Vivo Chat Hub web frontend; both currently end up in the dashboard labelled "teams". This was surfaced during the dedup incident investigation (`monkai-agent-hub#2`).

The fix needs the consumer to look at the inbound Bot Framework activity payload and emit the right channel string. Because `Azure-Servers` is currently under a merge freeze, this spec scopes the work to `monkai-trace` only: ship a reusable utility that any future Bot Framework consumer (Vivo, others) can drop in as a one-line replacement when their freeze lifts.

## Goals

- Provide a public helper `monkai_trace.integrations.bot_framework.infer_channel(payload)` that translates a Bot Framework activity's `channelId` into the channel string MonkAI's dashboard expects.
- Map the four Bot Framework channelIds in current use:
  - `msteams` → `teams`
  - `directline` → `web`
  - `webchat` → `web`
  - `emulator` → `emulator`
- Pass unknown values through (lower-cased) so the dashboard surfaces them rather than silently mislabelling.
- Treat missing/empty `channelId` as `unknown`.
- Be case-insensitive.
- Land on the next regular `monkai-trace` minor release; no special release flow.

## Non-goals

- Changing `Azure-Servers/.../tracing.py`. Repo is in freeze (`feedback_azure_servers_merge_freeze.md`). The Vivo adoption is a follow-up issue tracked separately.
- Introducing a `Channel` enum or constants module (`Channel.TEAMS`, etc.). Nice to have; defer until a second consumer lands and proves value.
- Inferring channel from secondary signals (`from.aadObjectId`, `from.empresa`). Single signal source (`channelId`) is sufficient for the use case and avoids defensive over-engineering.
- Renaming the historical `_NAMESPACE = "vivo-chatbot-teams"` constant in the Vivo consumer. Out of scope for this fix; would also require an alias in the Hub.
- Backfilling historical records currently labelled `external_user_channel = "teams"` that came from the web. Operational decision tracked separately.

## Design

### Module placement

`monkai_trace/integrations/bot_framework.py` — new file. Follows the existing `monkai_trace/integrations/` pattern. Other entries in this directory are runtime-hook classes (`MonkAIRunHooks`, `MonkAICallbackHandler`, `MonkAIAgentHooks`); this is a stateless utility function. The naming and location signal "Bot Framework integration" so that future helpers (e.g. payload extraction for `from.id`, `from.name`) can land in the same module without restructuring.

### Implementation

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
    """
    raw = (payload.get("channelId") or "").lower()
    return _CHANNEL_MAP.get(raw, raw or "unknown")
```

### Export

`monkai_trace/integrations/__init__.py` adds:

```python
from .bot_framework import infer_channel
```

and appends `"infer_channel"` to `__all__`. Callers may use either:

```python
from monkai_trace.integrations import infer_channel
# or
from monkai_trace.integrations.bot_framework import infer_channel
```

The flat re-export trades a small naming-collision risk (any future helper named `infer_channel` would clash) for ergonomic parity with the rest of the package.

## Testing

`tests/test_bot_framework_integration.py` (new file) covers:

- Each known mapping returns the expected channel string (`msteams`/`MSTEAMS`/`MsTeams` → `teams`; `directline`/`webchat` → `web`; `emulator` → `emulator`).
- Unknown values pass through lower-cased (`slack` → `slack`; `Slack` → `slack`).
- Missing key returns `unknown` (`{}`).
- Explicit `None` returns `unknown` (`{"channelId": None}`).
- Empty string returns `unknown` (`{"channelId": ""}`).
- Other payload fields are ignored (`{"channelId": "msteams", "from": {...}, "type": "message"}` returns `teams`).

Tests use `pytest.mark.parametrize` for the table-driven cases.

## Backward compatibility

Purely additive — new module, new public function, new export. No existing API changed. No migration required for current callers.

## Adoption follow-up

When the `Azure-Servers` freeze lifts, file an issue at `BeMonkAI/Azure-Servers` referencing this PR. The Vivo consumer change is approximately five lines:

1. Remove `_CHANNEL = "teams"` from `chatbot_vivo/tracing.py:20`.
2. Add `channel: str` keyword-only parameter to `trace_interaction`.
3. Replace `external_user_channel=_CHANNEL` with `external_user_channel=channel`.
4. In `triggers/vivo/vivo_teams_webhook.py`, import the helper and pass `channel=infer_channel(payload)` at the `trace_interaction(...)` call site.

## References

- Master coordination spec: `monkai-agent-hub/docs/superpowers/specs/2026-04-28-dedup-incident-coordination.md`
- Issue: https://github.com/BeMonkAI/monkai-agent-hub/issues/2 (Fix 3 description)
- Vivo consumer in freeze: `Azure-Servers/apps/services/azure/gateway/client_resources/vivo/chatbot_vivo/tracing.py`
- Bot Framework channelId reference: https://learn.microsoft.com/en-us/azure/bot-service/bot-service-channels-reference
