"""
Grok CLI integration for MonkAI Trace.

Parses Grok session logs and uploads one ConversationRecord per user turn.

Grok stores each session in a directory::

    $GROK_HOME/sessions/<url-encoded-cwd>/<session-uuid>/

(``GROK_HOME`` defaults to ``~/.grok``). The turns are read from
``updates.jsonl``, the append-only stream of session updates:
``chat_history.jsonl`` is rewritten on context compaction, so earlier turns
disappear from it and its record count would break incremental offsets.

- ``user_message_chunk`` opens a turn (chunks with the same ``promptIndex``
  are one prompt); ``turn_completed`` closes it.
- ``agent_message_chunk``: assistant text; ``tool_call``: tool calls.
- ``params._meta.totalTokens``: size of the context at that point. Grok logs
  no per-request input/output split, so a turn's tokens are ESTIMATED as the
  growth of that counter since the previous turn (never negative: compaction
  shrinks it), sent as ``input_tokens`` with ``metadata.tokens_estimated``.

``summary.json`` gives the session's ``cwd``.

Example:
    >>> from monkai_trace.integrations.grok import GrokTracer
    >>> tracer = GrokTracer(tracer_token="tk_your_token", namespace="grok")
    >>> tracer.upload_session_incremental("~/.grok/sessions/%2FUsers%2Fme/<uuid>")
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from ..models import ConversationRecord
from .claude_code import ClaudeCodeTracer, _cwd_metadata, _run_hook
from .codex import _turn_messages

logger = logging.getLogger(__name__)


def grok_home() -> Path:
    return Path(os.environ.get("GROK_HOME", str(Path.home() / ".grok"))).expanduser()


class GrokTracer(ClaudeCodeTracer):
    """Parse Grok session directories and upload them to MonkAI Trace.

    Reuses :class:`ClaudeCodeTracer` for uploading; pass the session
    DIRECTORY to ``upload_session`` / ``upload_session_incremental``. The
    Claude-specific project helpers do not apply to Grok.
    """

    def __init__(self, tracer_token: str, namespace: str, agent_name: str = "grok", **kwargs):
        super().__init__(tracer_token, namespace, agent_name, **kwargs)

    def upload_session_incremental(self, session_path: str) -> dict:
        # Offsets are keyed by the path stem: use the session dir, not a file in it.
        path = Path(session_path).expanduser()
        return super().upload_session_incremental(str(path.parent if path.is_file() else path))

    def _parse_session(self, path: Path) -> list[ConversationRecord]:
        if path.is_file():
            path = path.parent
        updates = path / "updates.jsonl"
        if not updates.is_file():
            return []
        try:
            summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            summary = {}
        info = summary.get("info") if isinstance(summary, dict) else None
        info = info if isinstance(info, dict) else {}
        session_id = info.get("id") or path.name
        metadata = _cwd_metadata({}, info.get("cwd"))

        records = []
        previous_total = 0
        for turn in _group_turns(self._read_jsonl(updates), self.include_unfinished):
            total = turn["context_tokens"]
            tokens = max(0, total - previous_total) if total is not None else 0
            previous_total = total if total is not None else previous_total
            records.append(
                ConversationRecord(
                    namespace=self.namespace,
                    agent=self.agent_name,
                    session_id=session_id,
                    msg=_turn_messages(
                        "".join(turn["user"]), turn["items"], turn["model"], self.agent_name
                    ),
                    input_tokens=tokens,
                    output_tokens=0,
                    total_tokens=tokens,
                    source="grok",
                    model=turn["model"],
                    inserted_at=turn["timestamp"],
                    metadata={**(metadata or {}), "tokens_estimated": True},
                )
            )
        logger.info("Parsed %d Grok turns from %s", len(records), path.name)
        return records


def _group_turns(lines: list[dict], include_unfinished: bool = False) -> list[dict]:
    """Split ``updates.jsonl`` into finished user turns.

    A turn is finished once ``turn_completed`` arrives or the next prompt
    starts, so only the in-flight trailing turn is held back and the list
    only grows (keeps incremental offsets valid). ``include_unfinished``
    keeps that trailing turn too (the session has ended; subagent sessions
    never log ``turn_completed``).
    """
    turns: list[dict] = []
    current: dict | None = None
    for line in lines:
        params = line.get("params") or {}
        update = params.get("update") or {}
        meta = params.get("_meta") or {}
        kind = update.get("sessionUpdate")

        if kind == "user_message_chunk":
            prompt = (update.get("_meta") or {}).get("promptIndex")
            text = (update.get("content") or {}).get("text") or ""
            if current is not None and current["prompt"] == prompt and not current["items"]:
                current["user"].append(text)
                continue
            if current is not None:
                turns.append(current)
            current = {
                "prompt": prompt,
                "user": [text],
                "items": [],
                "model": (update.get("_meta") or {}).get("modelId"),
                "timestamp": _iso(meta.get("agentTimestampMs"), line.get("timestamp")),
                "context_tokens": None,
            }
            continue
        if current is None:
            continue

        # Subagent updates carry their own (smaller) context counter.
        if isinstance(meta.get("totalTokens"), int) and meta.get("promptId") != "subagent":
            current["context_tokens"] = meta["totalTokens"]
        if kind == "turn_completed":
            turns.append(current)
            current = None
        elif kind == "agent_message_chunk":
            text = (update.get("content") or {}).get("text") or ""
            if current["items"] and current["items"][-1][0] == "text":
                current["items"][-1] = ("text", current["items"][-1][1] + text)
            elif text:
                current["items"].append(("text", text))
        elif kind == "tool_call":
            tool = (update.get("_meta") or {}).get("x.ai/tool") or {}
            current["items"].append(
                (
                    "tool",
                    {
                        "name": tool.get("name") or update.get("title") or "",
                        "arguments": update.get("rawInput") or {},
                        "id": update.get("toolCallId", ""),
                    },
                )
            )
    if include_unfinished and current is not None:
        turns.append(current)
    return turns


def _iso(ms, seconds) -> str | None:
    """ISO-8601 UTC time from epoch milliseconds, else epoch seconds."""
    for value, scale in ((ms, 1000.0), (seconds, 1.0)):
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / scale, tz=timezone.utc).isoformat()
    return None


def find_session_dir(payload: dict) -> str | None:
    """Session directory for a Grok hook payload.

    Tries an explicit path (``transcript_path`` / ``session_path``), then the
    session id (``sessionId`` / ``session_id``), then the most recently
    updated session.
    """
    for key in ("transcript_path", "session_path"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            path = Path(value).expanduser()
            path = path if path.is_dir() else path.parent
            if (path / "updates.jsonl").is_file():
                return str(path)

    sessions = grok_home() / "sessions"
    session_id = payload.get("sessionId") or payload.get("session_id")
    if isinstance(session_id, str) and session_id and "/" not in session_id:
        matches = [p for p in sessions.glob(f"*/{session_id}") if p.is_dir()]
        if matches:
            return str(matches[0])

    candidates = [p.parent for p in sessions.glob("*/*/updates.jsonl")]
    if not candidates:
        return None
    return str(max(candidates, key=lambda p: (p / "updates.jsonl").stat().st_mtime))


def run_grok_hook(stdin=None) -> int:
    """Entrypoint for the Grok ``Stop``/``SessionEnd`` hook (``monkai-trace grok-hook``).

    Same contract as :func:`~monkai_trace.integrations.claude_code.run_hook`:
    incremental upload, namespace from ``MONKAI_TRACE_NAMESPACE`` (default
    ``grok``), never raises, always returns 0.
    """
    return _run_hook(stdin, "Grok", find_session_dir, GrokTracer, "grok")
