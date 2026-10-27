"""Tests for the Codex CLI integration: rollout parsing, incremental upload,
the hook entrypoint and ``install-hook --assistant codex``. Fixtures are
synthetic."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from monkai_trace import cli
from monkai_trace.client import MonkAIClient
from monkai_trace.integrations.codex import CodexTracer, _token_usage, find_rollout, run_codex_hook

SESSION = "019a0000-0000-7000-8000-000000000001"


class _StdIn:
    def __init__(self, text):
        self._text = text

    def read(self):
        return self._text


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Keep offsets, token and CODEX_HOME off the real home dir."""
    monkeypatch.setenv("MONKAI_TRACE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MONKAI_TRACE_TOKEN_FILE", str(tmp_path / "no_token_file"))
    monkeypatch.delenv("MONKAI_TRACE_TOKEN", raising=False)
    monkeypatch.delenv("MONKAI_TRACE_NAMESPACE", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))


def _mock_client(monkeypatch):
    mock = Mock(spec=MonkAIClient)
    mock.upload_records_batch.side_effect = lambda records, **kw: {
        "total_inserted": len(records),
        "total_records": len(records),
        "failures": [],
    }
    monkeypatch.setattr("monkai_trace.integrations.claude_code.MonkAIClient", lambda *a, **k: mock)
    return mock


def _line(kind, payload, ts="2026-09-30T10:00:00.000Z"):
    return {"timestamp": ts, "type": kind, "payload": payload}


def _msg(role, *texts, kinds=None):
    payload = {
        "type": "message",
        "role": role,
        "content": [
            {"type": "output_text" if role == "assistant" else "input_text", "text": t}
            for t in texts
        ],
    }
    if kinds:
        payload["internal_chat_message_metadata_passthrough"] = {"content_item_kinds": kinds}
    return _line("response_item", payload)


def _turn(turn_id, user, answer, ts, close=True, usage=None):
    lines = [
        _line("event_msg", {"type": "task_started", "turn_id": turn_id}, ts),
        _line("turn_context", {"turn_id": turn_id, "model": "gpt-test", "cwd": "/nowhere/x"}),
        _msg("developer", "<permissions>sandbox</permissions>"),
        _msg("user", user, kinds=["user.text"]),
        _msg("assistant", answer),
        _line(
            "token_usage_record",
            {
                "turn_id": turn_id,
                "turn_token_usage": usage
                or {
                    "input_tokens": 100,
                    "cached_input_tokens": 60,
                    "cache_write_input_tokens": 10,
                    "output_tokens": 7,
                    "reasoning_output_tokens": 2,
                    "total_tokens": 107,
                },
            },
        ),
    ]
    if close:
        lines.append(_line("event_msg", {"type": "task_complete", "turn_id": turn_id}))
    return lines


def _meta():
    return _line(
        "session_meta",
        {
            "id": SESSION,
            "cwd": "/nowhere",
            "originator": "codex-tui",
            "cli_version": "0.154.0",
            "base_instructions": {"text": "huge"},
        },
    )


def _rollout(tmp_path, lines, name=None) -> Path:
    day = tmp_path / "codex" / "sessions" / "2026" / "09" / "30"
    day.mkdir(parents=True, exist_ok=True)
    path = day / (name or f"rollout-2026-09-30T10-00-00-{SESSION}.jsonl")
    path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
    return path


def _tracer():
    return CodexTracer(tracer_token="tk_test", namespace="codex", auto_upload=False)


# --- parsing ---------------------------------------------------------------


def test_parse_groups_one_record_per_turn(tmp_path):
    lines = [_meta()] + _turn("t1", "hi", "hello", "2026-09-30T10:00:00Z")
    lines += _turn("t2", "again", "sure", "2026-09-30T10:05:00Z")
    records = _tracer()._parse_session(_rollout(tmp_path, lines))

    assert len(records) == 2
    first = records[0]
    assert first.session_id == SESSION
    assert first.source == "codex"
    assert first.agent == "codex"
    assert first.model == "gpt-test"
    assert first.inserted_at == "2026-09-30T10:00:00Z"
    assert [(m.role, m.content) for m in first.msg] == [("user", "hi"), ("assistant", "hello")]
    assert first.msg[1].sender == "gpt-test"
    assert records[1].inserted_at == "2026-09-30T10:05:00Z"


def test_parse_skips_injected_context(tmp_path):
    turn = _turn("t1", "real question", "ok", "2026-09-30T10:00:00Z")
    injected_tagged = _msg(
        "user",
        "# AGENTS.md instructions",
        "<environment_context>cwd</environment_context>",
        kinds=["agents_md.instructions", "environments.environment_context"],
    )
    skill = _msg("user", "skill body", kinds=["skills.selected_skill_instructions"])
    injected_untagged = _msg("user", "<user_instructions>x</user_instructions>")
    lines = [_meta()] + turn[:3] + [injected_tagged, injected_untagged] + turn[3:4]
    lines += [skill] + turn[4:]
    records = _tracer()._parse_session(_rollout(tmp_path, lines))

    assert records[0].msg[0].content == "real question"
    assert all("AGENTS" not in (m.content or "") for m in records[0].msg)


def test_parse_untagged_user_text_is_kept(tmp_path):
    # Older rollouts have no content_item_kinds: plain text is the user's.
    turn = _turn("t1", "x", "ok", "2026-09-30T10:00:00Z")
    turn[3] = _msg("user", "plain typed text")
    records = _tracer()._parse_session(_rollout(tmp_path, [_meta()] + turn))
    assert records[0].msg[0].content == "plain typed text"


def test_parse_tool_calls(tmp_path):
    turn = _turn("t1", "run it", "done", "2026-09-30T10:00:00Z")
    calls = [
        _line(
            "response_item",
            {
                "type": "function_call",
                "name": "exec_command",
                "arguments": '{"cmd": "ls"}',
                "call_id": "c1",
            },
        ),
        _line("response_item", {"type": "function_call_output", "call_id": "c1", "output": "x"}),
        _line(
            "response_item",
            {
                "type": "custom_tool_call",
                "name": "apply_patch",
                "input": "*** patch",
                "call_id": "c2",
            },
        ),
        _line("response_item", {"type": "reasoning", "encrypted_content": "zzz"}),
    ]
    lines = [_meta()] + turn[:4] + calls + turn[4:]
    msgs = _tracer()._parse_session(_rollout(tmp_path, lines))[0].msg

    tools = [m for m in msgs if m.role == "tool"]
    assert [t.tool_name for t in tools] == ["exec_command", "apply_patch"]
    assert tools[0].tool_calls == [{"name": "exec_command", "arguments": {"cmd": "ls"}, "id": "c1"}]
    assert tools[1].tool_calls[0]["arguments"] == "*** patch"
    # tool outputs are never sent
    assert all("x" != m.content for m in msgs)


def test_parse_token_mapping(tmp_path):
    lines = [_meta()] + _turn("t1", "hi", "hello", "2026-09-30T10:00:00Z")
    record = _tracer()._parse_session(_rollout(tmp_path, lines))[0]
    assert record.input_tokens == 30  # 100 - 60 cached - 10 cache write
    assert record.memory_tokens == 60
    assert record.process_tokens == 10
    assert record.output_tokens == 7
    assert record.total_tokens == 107


def test_parse_tokens_from_token_count_when_no_usage_record(tmp_path):
    turn = [ln for ln in _turn("t1", "hi", "hello", "2026-09-30T10:00:00Z")]
    turn = [ln for ln in turn if ln["type"] != "token_usage_record"]
    counts = [
        _line(
            "event_msg",
            {
                "type": "token_count",
                "info": {"last_token_usage": {"input_tokens": n, "output_tokens": 1}},
            },
        )
        for n in (10, 20)
    ]
    lines = [_meta()] + turn[:-1] + counts + turn[-1:]
    record = _tracer()._parse_session(_rollout(tmp_path, lines))[0]
    assert (record.input_tokens, record.output_tokens, record.total_tokens) == (30, 2, 32)


def test_token_usage_handles_missing_usage():
    assert _token_usage(None).total_tokens == 0
    assert _token_usage({"input_tokens": 5, "cached_input_tokens": 9}).input_tokens == 0


def test_incomplete_trailing_turn_is_held_back(tmp_path):
    lines = [_meta()] + _turn("t1", "hi", "hello", "2026-09-30T10:00:00Z")
    lines += _turn("t2", "running", "...", "2026-09-30T10:05:00Z", close=False)
    assert len(_tracer()._parse_session(_rollout(tmp_path, lines))) == 1


def test_unclosed_turn_counts_once_a_later_turn_starts(tmp_path):
    lines = [_meta()] + _turn("t1", "interrupted", "...", "2026-09-30T10:00:00Z", close=False)
    lines += _turn("t2", "next", "ok", "2026-09-30T10:05:00Z")
    records = _tracer()._parse_session(_rollout(tmp_path, lines))
    assert [r.msg[0].content for r in records] == ["interrupted", "next"]


def test_metadata_has_session_fields_and_no_absolute_path(tmp_path):
    lines = [_meta()] + _turn("t1", "hi", "hello", "2026-09-30T10:00:00Z")
    record = _tracer()._parse_session(_rollout(tmp_path, lines))[0]
    assert record.metadata == {"entrypoint": "codex-tui", "client_version": "0.154.0"}
    assert "/nowhere" not in json.dumps(record.to_api_format())


def test_parse_empty_rollout(tmp_path):
    assert _tracer()._parse_session(_rollout(tmp_path, [])) == []


# --- incremental upload + hook ---------------------------------------------


def test_incremental_second_run_uploads_only_new_turns(tmp_path, monkeypatch):
    mock = _mock_client(monkeypatch)
    tracer = CodexTracer(tracer_token="tk_test", namespace="codex")
    lines = [_meta()] + _turn("t1", "hi", "hello", "2026-09-30T10:00:00Z")
    lines += _turn("t2", "running", "...", "2026-09-30T10:05:00Z", close=False)
    path = _rollout(tmp_path, lines)

    assert tracer.upload_session_incremental(str(path))["total_inserted"] == 1
    lines.append(_line("event_msg", {"type": "task_complete", "turn_id": "t2"}))
    path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
    result = tracer.upload_session_incremental(str(path))

    assert result["total_inserted"] == 1
    assert result["skipped"] == 1
    sent = mock.upload_records_batch.call_args[0][0]
    assert [r.msg[0].content for r in sent] == ["running"]


def test_find_rollout_by_transcript_path_or_session_id(tmp_path):
    path = _rollout(tmp_path, [_meta()])
    assert find_rollout({"transcript_path": str(path)}) == str(path)
    assert find_rollout({"session_id": SESSION}) == str(path)
    assert find_rollout({"session_id": "missing"}) is None
    assert find_rollout({}) is None


def test_run_codex_hook_uploads(tmp_path, monkeypatch):
    mock = _mock_client(monkeypatch)
    monkeypatch.setenv("MONKAI_TRACE_TOKEN", "tk_test")
    _rollout(tmp_path, [_meta()] + _turn("t1", "hi", "hello", "2026-09-30T10:00:00Z"))

    assert run_codex_hook(_StdIn(json.dumps({"session_id": SESSION}))) == 0
    sent = mock.upload_records_batch.call_args[0][0]
    assert sent[0].namespace == "codex"


@pytest.mark.parametrize("stdin", ["not json", "[1, 2]", "", '{"session_id": 5}'])
def test_run_codex_hook_never_raises_on_garbage(stdin, monkeypatch):
    monkeypatch.setenv("MONKAI_TRACE_TOKEN", "tk_test")
    assert run_codex_hook(_StdIn(stdin)) == 0


def test_run_codex_hook_missing_file_is_swallowed(tmp_path, monkeypatch):
    monkeypatch.setenv("MONKAI_TRACE_TOKEN", "tk_test")
    payload = {"transcript_path": str(tmp_path / "gone.jsonl"), "session_id": "gone"}
    assert run_codex_hook(_StdIn(json.dumps(payload))) == 0


# --- install / uninstall ---------------------------------------------------


def _hooks(tmp_path) -> dict:
    return json.loads((tmp_path / "codex" / "hooks.json").read_text())


def test_install_codex_hook_idempotent_and_preserves_foreign(tmp_path):
    hooks_file = tmp_path / "codex" / "hooks.json"
    hooks_file.parent.mkdir(parents=True)
    foreign = {"hooks": [{"type": "command", "command": "other", "timeout": 3}]}
    hooks_file.write_text(json.dumps({"description": "mine", "hooks": {"SessionEnd": [foreign]}}))

    assert cli.main(["install-hook", "--assistant", "codex"]) == 0
    assert cli.main(["install-hook", "--assistant", "codex"]) == 0
    data = _hooks(tmp_path)

    assert data["description"] == "mine"
    assert foreign in data["hooks"]["SessionEnd"]
    for event in ("Stop", "SessionEnd"):
        cmds = [h["command"] for e in data["hooks"][event] for h in e["hooks"]]
        assert sum("codex-hook" in c for c in cmds) == 1
    ours = data["hooks"]["Stop"][0]["hooks"][0]
    assert ours["timeout"] == cli.HOOK_TIMEOUT


def test_uninstall_codex_hook_keeps_foreign(tmp_path):
    cli.main(["install-hook", "--assistant", "codex"])
    data = _hooks(tmp_path)
    data["hooks"]["Stop"].append({"hooks": [{"type": "command", "command": "other"}]})
    (tmp_path / "codex" / "hooks.json").write_text(json.dumps(data))

    assert cli.main(["uninstall-hook", "--assistant", "codex"]) == 0
    data = _hooks(tmp_path)
    assert "SessionEnd" not in data["hooks"]
    assert data["hooks"]["Stop"] == [{"hooks": [{"type": "command", "command": "other"}]}]


def test_uninstall_codex_hook_without_file(tmp_path):
    assert cli.main(["uninstall-hook", "--assistant", "codex"]) == 0
    assert not (tmp_path / "codex" / "hooks.json").exists()


def test_stop_hook_uploads_trailing_turn_once(tmp_path, monkeypatch):
    # Stop fires when the turn is over, possibly before task_complete is on disk.
    mock = _mock_client(monkeypatch)
    monkeypatch.setenv("MONKAI_TRACE_TOKEN", "tk_test")
    lines = [_meta()] + _turn("t1", "hi", "hello", "2026-09-30T10:00:00Z")
    lines += _turn("t2", "last", "bye", "2026-09-30T10:05:00Z", close=False)
    _rollout(tmp_path, lines)

    run_codex_hook(_StdIn(json.dumps({"session_id": SESSION, "hook_event_name": "Stop"})))
    assert [r.msg[0].content for r in mock.upload_records_batch.call_args[0][0]] == ["hi", "last"]
    mock.upload_records_batch.reset_mock()
    payload = {"session_id": SESSION, "hook_event_name": "SessionEnd"}
    run_codex_hook(_StdIn(json.dumps(payload)))
    mock.upload_records_batch.assert_not_called()
