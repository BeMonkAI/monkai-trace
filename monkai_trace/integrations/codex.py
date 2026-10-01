"""
Codex CLI integration for MonkAI Trace.

Parses Codex rollout logs and uploads one ConversationRecord per turn.

Codex stores each session at::

    $CODEX_HOME/sessions/YYYY/MM/DD/rollout-<timestamp>-<session-uuid>.jsonl

(``CODEX_HOME`` defaults to ``~/.codex``). Each line is
``{timestamp, type, payload}``; a turn spans ``event_msg/task_started`` to
``event_msg/task_complete`` (or ``turn_aborted``). Inside it:

- ``turn_context``: the model of the turn and its working directory.
- ``response_item/message``: ``user`` / ``assistant`` text. ``developer``
  messages and the context Codex injects as ``user`` (AGENTS.md,
  ``<environment_context>``, skill bodies) are skipped.
- ``response_item/function_call`` and ``custom_tool_call``: tool calls.
- ``token_usage_record.turn_token_usage``: running token total of the turn
  (older versions only have ``event_msg/token_count.info.last_token_usage``
  per request, which is summed instead).

Example:
    >>> from monkai_trace.integrations.codex import CodexTracer
    >>> tracer = CodexTracer(tracer_token="tk_your_token", namespace="codex")
    >>> tracer.upload_session_incremental("~/.codex/sessions/2026/09/30/rollout-...jsonl")
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from ..models import ConversationRecord, Message, TokenUsage
from .claude_code import ClaudeCodeTracer, _cwd_metadata, _run_hook

logger = logging.getLogger(__name__)

# Text of injected (non user-typed) context in rollouts without the
# per-item ``content_item_kinds`` tags (Codex < 0.150).
_INJECTED_PREFIXES = ("<", "# AGENTS.md")
_TOOL_CALLS = ("function_call", "custom_tool_call", "local_shell_call")


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()


class CodexTracer(ClaudeCodeTracer):
    """Parse Codex rollout logs and upload them to MonkAI Trace.

    Reuses :class:`ClaudeCodeTracer` for uploading (``upload_session``,
    ``upload_session_incremental``, ``flush``); only parsing differs. The
    Claude-specific project helpers (``upload_project``, ``list_projects``)
    do not apply to Codex.
    """

    def __init__(self, tracer_token: str, namespace: str, agent_name: str = "codex", **kwargs):
        super().__init__(tracer_token, namespace, agent_name, **kwargs)

    def _parse_session(self, path: Path) -> list[ConversationRecord]:
        lines = self._read_jsonl(path)
        meta = next(
            (ln.get("payload") or {} for ln in lines if ln.get("type") == "session_meta"), {}
        )
        session_meta = {
            k: v
            for k, v in {
                "entrypoint": meta.get("originator"),
                "client_version": meta.get("cli_version"),
            }.items()
            if v
        }
        session_id = meta.get("id") or meta.get("session_id") or path.stem

        records = []
        for turn in _group_turns(lines, self.include_unfinished):
            cwd = turn["cwd"] or meta.get("cwd")
            tokens = _token_usage(turn["usage"])
            records.append(
                ConversationRecord(
                    namespace=self.namespace,
                    agent=self.agent_name,
                    session_id=session_id,
                    msg=_turn_messages(
                        "\n".join(turn["user"]), turn["items"], turn["model"], self.agent_name
                    ),
                    input_tokens=tokens.input_tokens,
                    output_tokens=tokens.output_tokens,
                    process_tokens=tokens.process_tokens,
                    memory_tokens=tokens.memory_tokens,
                    total_tokens=tokens.total_tokens,
                    source="codex",
                    model=turn["model"],
                    inserted_at=turn["timestamp"],
                    metadata=_cwd_metadata(session_meta, cwd),
                )
            )
        logger.info("Parsed %d Codex turns from %s", len(records), path.name)
        return records


def _turn_messages(user: str, items: list, model: str | None, agent: str) -> list[Message]:
    """Messages of one turn: user text, then assistant text / tool calls in order.

    Each tool call becomes an assistant message carrying ``tool_calls`` plus a
    ``tool`` message, like the Claude Code integration. Tool outputs are not
    sent.
    """
    messages = [Message(role="user", content=user, sender="user")]
    for kind, value in items:
        if kind == "text":
            messages.append(Message(role="assistant", content=value, sender=model or agent))
            continue
        messages.append(
            Message(role="assistant", content=None, sender=model or agent, tool_calls=[value])
        )
        messages.append(
            Message(
                role="tool",
                content=f"Tool: {value['name']}",
                sender=agent,
                tool_name=value["name"],
                tool_calls=[value],
            )
        )
    return messages


def _group_turns(lines: list[dict], include_unfinished: bool = False) -> list[dict]:
    """Split a rollout into finished turns.

    A turn counts as finished once it is closed (``task_complete`` /
    ``turn_aborted``) or a later turn starts, so only the trailing in-flight
    turn is held back; the list therefore only grows, which keeps the
    record-count offsets of incremental uploads valid. ``include_unfinished``
    keeps that trailing turn too (the session has ended).
    """
    turns: list[dict] = []
    current: dict | None = None
    for line in lines:
        kind = line.get("type")
        payload = line.get("payload") or {}
        ptype = payload.get("type")

        if kind == "event_msg" and ptype == "task_started":
            if current:
                turns.append(current)
            current = {
                "timestamp": line.get("timestamp"),
                "model": None,
                "cwd": None,
                "user": [],
                "items": [],
                "usage": None,
                "request_usage": [],
            }
            continue
        if current is None:
            continue

        if kind == "event_msg" and ptype in ("task_complete", "turn_aborted"):
            turns.append(current)
            current = None
        elif kind == "turn_context":
            current["model"] = payload.get("model") or current["model"]
            current["cwd"] = payload.get("cwd") or current["cwd"]
        elif kind == "token_usage_record":
            current["usage"] = payload.get("turn_token_usage") or current["usage"]
        elif kind == "event_msg" and ptype == "token_count":
            last = (payload.get("info") or {}).get("last_token_usage")
            if last:
                current["request_usage"].append(last)
        elif kind == "response_item" and ptype == "message":
            if payload.get("role") == "user":
                current["user"].extend(_user_texts(payload))
            elif payload.get("role") == "assistant":
                text = "\n".join(c.get("text", "") for c in payload.get("content") or [])
                if text:
                    current["items"].append(("text", text))
        elif kind == "response_item" and ptype in _TOOL_CALLS:
            current["items"].append(("tool", _tool_call(payload)))

    if include_unfinished and current:
        turns.append(current)
    for turn in turns:
        if not turn["usage"] and turn["request_usage"]:
            keys = set().union(*turn["request_usage"])
            turn["usage"] = {k: sum(u.get(k) or 0 for u in turn["request_usage"]) for k in keys}
    return [t for t in turns if t["user"] or t["items"]]


def _user_texts(payload: dict) -> list[str]:
    """User-typed text of a ``user`` message, without injected context."""
    kinds = (payload.get("internal_chat_message_metadata_passthrough") or {}).get(
        "content_item_kinds"
    ) or []
    texts = []
    for i, item in enumerate(payload.get("content") or []):
        text = item.get("text") or ""
        kind = kinds[i] if i < len(kinds) else None
        typed = (
            kind.startswith("user.") if kind else not text.lstrip().startswith(_INJECTED_PREFIXES)
        )
        if typed and text:
            texts.append(text)
    return texts


def _tool_call(payload: dict) -> dict:
    raw = payload.get("arguments", payload.get("input", payload.get("action")))
    try:
        arguments = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        arguments = raw
    return {
        "name": payload.get("name") or payload.get("type", ""),
        "arguments": arguments if arguments is not None else {},
        "id": payload.get("call_id", ""),
    }


def _token_usage(usage: dict | None) -> TokenUsage:
    """Map Codex (OpenAI) usage onto MonkAI's token buckets.

    OpenAI's ``input_tokens`` already include cached and cache-write tokens
    and ``output_tokens`` include reasoning, so, matching the Anthropic
    mapping in :meth:`TokenUsage.from_anthropic_usage`:
    input = input - cached - cache_write, process = cache_write,
    memory = cached, output = output; the total equals Codex ``total_tokens``.
    """
    usage = usage or {}
    cached = usage.get("cached_input_tokens") or 0
    cache_write = usage.get("cache_write_input_tokens") or 0
    return TokenUsage(
        input_tokens=max(0, (usage.get("input_tokens") or 0) - cached - cache_write),
        output_tokens=usage.get("output_tokens") or 0,
        process_tokens=cache_write,
        memory_tokens=cached,
    )


def find_rollout(payload: dict) -> str | None:
    """Rollout file for a Codex hook payload (``transcript_path`` or ``session_id``)."""
    transcript = payload.get("transcript_path")
    if transcript and Path(transcript).expanduser().is_file():
        return transcript
    session_id = payload.get("session_id")
    if not session_id or not isinstance(session_id, str):
        return None
    matches = sorted((codex_home() / "sessions").glob(f"*/*/*/rollout-*-{session_id}.jsonl"))
    return str(matches[-1]) if matches else None


def run_codex_hook(stdin=None) -> int:
    """Entrypoint for the Codex ``Stop``/``SessionEnd`` hook (``monkai-trace codex-hook``).

    Same contract as :func:`~monkai_trace.integrations.claude_code.run_hook`:
    incremental upload, namespace from ``MONKAI_TRACE_NAMESPACE`` (default
    ``codex``), never raises, always returns 0.
    """
    return _run_hook(stdin, "Codex", find_rollout, CodexTracer, "codex")
