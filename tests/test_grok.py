"""Tests for the Grok CLI integration: updates.jsonl parsing, estimated
tokens, incremental upload, the hook entrypoint and
``install-hook --assistant grok``. Fixtures are synthetic."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from monkai_trace import cli
from monkai_trace.client import MonkAIClient
from monkai_trace.integrations.grok import GrokTracer, find_session_dir, run_grok_hook

SESSION = "019b0000-0000-7000-8000-000000000002"
T0 = 1790000000000  # epoch ms


class _StdIn:
    def __init__(self, text):
        self._text = text

    def read(self):
        return self._text


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Keep offsets, token and GROK_HOME off the real home dir."""
    monkeypatch.setenv("MONKAI_TRACE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MONKAI_TRACE_TOKEN_FILE", str(tmp_path / "no_token_file"))
    monkeypatch.delenv("MONKAI_TRACE_TOKEN", raising=False)
    monkeypatch.delenv("MONKAI_TRACE_NAMESPACE", raising=False)
    monkeypatch.setenv("GROK_HOME", str(tmp_path / "grok"))


def _mock_client(monkeypatch):
    mock = Mock(spec=MonkAIClient)
    mock.upload_records_batch.side_effect = lambda records, **kw: {
        "total_inserted": len(records),
        "total_records": len(records),
        "failures": [],
    }
    monkeypatch.setattr("monkai_trace.integrations.claude_code.MonkAIClient", lambda *a, **k: mock)
    return mock


def _update(update, ms, **meta):
    return {
        "timestamp": ms // 1000,
        "method": "session/update",
        "params": {
            "sessionId": SESSION,
            "update": update,
            "_meta": {"agentTimestampMs": ms, **meta},
        },
    }


def _turn(index, prompt, answer, tokens, ms, close=True, tool=None):
    lines = [
        _update(
            {
                "sessionUpdate": "user_message_chunk",
                "content": {"type": "text", "text": prompt},
                "_meta": {"modelId": "grok-test", "promptIndex": index},
            },
            ms,
        ),
        _update(
            {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": answer}},
            ms + 1,
            totalTokens=tokens - 10,
            promptId=f"p{index}",
        ),
        _update(
            {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "!"}},
            ms + 2,
            totalTokens=tokens,
            promptId=f"p{index}",
        ),
    ]
    if tool:
        lines.append(
            _update(
                {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "call-1",
                    "title": "Read file",
                    "rawInput": {"target_file": "a.py"},
                    "_meta": {"x.ai/tool": {"name": tool}},
                },
                ms + 3,
                totalTokens=tokens,
                promptId=f"p{index}",
            )
        )
    if close:
        lines.append(_update({"sessionUpdate": "turn_completed"}, ms + 4, promptId=f"p{index}"))
    return lines


def _session(tmp_path, lines, summary=True) -> Path:
    path = tmp_path / "grok" / "sessions" / "%2Fnowhere" / SESSION
    path.mkdir(parents=True, exist_ok=True)
    (path / "updates.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    if summary:
        info = {"info": {"id": SESSION, "cwd": "/nowhere"}, "session_kind": "primary"}
        (path / "summary.json").write_text(json.dumps(info))
    return path


def _tracer():
    return GrokTracer(tracer_token="tk_test", namespace="grok", auto_upload=False)


def test_parse_one_record_per_user_turn(tmp_path):
    lines = _turn(0, "hi", "hello", 1000, T0, tool="read_file") + _turn(
        1, "next", "ok", 1500, T0 + 60000
    )
    records = _tracer()._parse_session(_session(tmp_path, lines))

    assert len(records) == 2
    first = records[0]
    assert first.session_id == SESSION
    assert first.source == "grok"
    assert first.agent == "grok"
    assert first.model == "grok-test"
    assert first.inserted_at == "2026-09-21T14:13:20+00:00"
    roles = [(m.role, m.content) for m in first.msg]
    assert roles[:2] == [("user", "hi"), ("assistant", "hello!")]
    tool = [m for m in first.msg if m.role == "tool"][0]
    assert tool.tool_name == "read_file"
    assert tool.tool_calls == [
        {"name": "read_file", "arguments": {"target_file": "a.py"}, "id": "call-1"}
    ]


def test_tokens_are_estimated_context_growth(tmp_path):
    lines = _turn(0, "a", "x", 1000, T0) + _turn(1, "b", "y", 1500, T0 + 1000)
    # compaction: the context shrinks, the estimate never goes negative
    lines += _turn(2, "c", "z", 400, T0 + 2000)
    records = _tracer()._parse_session(_session(tmp_path, lines))

    assert [r.input_tokens for r in records] == [1000, 500, 0]
    assert all(r.output_tokens == 0 for r in records)
    assert [r.total_tokens for r in records] == [1000, 500, 0]
    assert all(r.metadata["tokens_estimated"] is True for r in records)


def test_subagent_counter_is_ignored(tmp_path):
    lines = _turn(0, "a", "x", 1000, T0)
    lines.insert(
        -1,
        _update({"sessionUpdate": "tool_call_update"}, T0 + 3, totalTokens=50, promptId="subagent"),
    )
    assert _tracer()._parse_session(_session(tmp_path, lines))[0].input_tokens == 1000


def test_turn_without_token_counter_has_zero_tokens(tmp_path):
    lines = [
        _update(
            {
                "sessionUpdate": "user_message_chunk",
                "content": {"type": "text", "text": "a"},
                "_meta": {"promptIndex": 0},
            },
            T0,
        ),
        _update({"sessionUpdate": "turn_completed"}, T0 + 1),
    ]
    record = _tracer()._parse_session(_session(tmp_path, lines))[0]
    assert record.total_tokens == 0
    assert record.model is None


def test_prompt_chunks_are_joined(tmp_path):
    lines = _turn(0, "hel", "x", 10, T0)
    second_chunk = json.loads(json.dumps(lines[0]))
    second_chunk["params"]["update"]["content"]["text"] = "lo"
    lines.insert(1, second_chunk)
    assert _tracer()._parse_session(_session(tmp_path, lines))[0].msg[0].content == "hello"


def test_incomplete_trailing_turn_is_held_back(tmp_path):
    lines = _turn(0, "a", "x", 10, T0) + _turn(1, "b", "y", 20, T0 + 1000, close=False)
    assert len(_tracer()._parse_session(_session(tmp_path, lines))) == 1


def test_metadata_has_no_absolute_path(tmp_path):
    record = _tracer()._parse_session(_session(tmp_path, _turn(0, "a", "x", 10, T0)))[0]
    assert record.metadata == {"tokens_estimated": True}
    assert "/nowhere" not in json.dumps(record.to_api_format())


def test_parse_missing_updates_or_summary(tmp_path):
    empty = tmp_path / "grok" / "sessions" / "x" / "empty"
    empty.mkdir(parents=True)
    assert _tracer()._parse_session(empty) == []
    path = _session(tmp_path, _turn(0, "a", "x", 10, T0), summary=False)
    assert _tracer()._parse_session(path)[0].session_id == SESSION  # dir name


def test_incremental_second_run_uploads_only_new_turns(tmp_path, monkeypatch):
    mock = _mock_client(monkeypatch)
    tracer = GrokTracer(tracer_token="tk_test", namespace="grok")
    lines = _turn(0, "a", "x", 10, T0)
    path = _session(tmp_path, lines)
    assert tracer.upload_session_incremental(str(path))["total_inserted"] == 1

    _session(tmp_path, lines + _turn(1, "b", "y", 20, T0 + 1000))
    result = tracer.upload_session_incremental(str(path))
    assert result["total_inserted"] == 1
    assert result["skipped"] == 1
    assert [r.msg[0].content for r in mock.upload_records_batch.call_args[0][0]] == ["b"]


def test_find_session_dir(tmp_path):
    path = _session(tmp_path, _turn(0, "a", "x", 10, T0))
    assert find_session_dir({"sessionId": SESSION}) == str(path)
    assert find_session_dir({"session_id": SESSION}) == str(path)
    assert find_session_dir({"transcript_path": str(path / "updates.jsonl")}) == str(path)
    # unknown id: falls back to the most recently updated session
    assert find_session_dir({"sessionId": "unknown"}) == str(path)


def test_find_session_dir_without_sessions(tmp_path):
    assert find_session_dir({"sessionId": SESSION}) is None


def test_run_grok_hook_uploads(tmp_path, monkeypatch):
    mock = _mock_client(monkeypatch)
    monkeypatch.setenv("MONKAI_TRACE_TOKEN", "tk_test")
    _session(tmp_path, _turn(0, "a", "x", 10, T0))

    assert run_grok_hook(_StdIn(json.dumps({"sessionId": SESSION}))) == 0
    assert mock.upload_records_batch.call_args[0][0][0].namespace == "grok"


@pytest.mark.parametrize("stdin", ["not json", "[]", "", '{"sessionId": 1}'])
def test_run_grok_hook_never_raises_on_garbage(stdin, monkeypatch):
    monkeypatch.setenv("MONKAI_TRACE_TOKEN", "tk_test")
    assert run_grok_hook(_StdIn(stdin)) == 0


def test_run_grok_hook_corrupt_session_is_swallowed(tmp_path, monkeypatch):
    monkeypatch.setenv("MONKAI_TRACE_TOKEN", "tk_test")
    path = _session(tmp_path, [])
    (path / "updates.jsonl").write_text("{not json\n[1]\n")
    assert run_grok_hook(_StdIn(json.dumps({"sessionId": SESSION}))) == 0


# --- install / uninstall ---------------------------------------------------


def _hook_file(tmp_path) -> Path:
    return tmp_path / "grok" / "hooks" / "monkai-trace.json"


def test_install_grok_hook_idempotent(tmp_path):
    foreign = tmp_path / "grok" / "hooks" / "other.json"
    foreign.parent.mkdir(parents=True)
    foreign.write_text('{"hooks": {}}')

    assert cli.main(["install-hook", "--assistant", "grok"]) == 0
    assert cli.main(["install-hook", "--assistant", "grok"]) == 0
    data = json.loads(_hook_file(tmp_path).read_text())
    for event in ("Stop", "SessionEnd"):
        cmds = [h["command"] for e in data["hooks"][event] for h in e["hooks"]]
        assert len(cmds) == 1 and "grok-hook" in cmds[0]
    assert foreign.read_text() == '{"hooks": {}}'


def test_uninstall_grok_hook(tmp_path):
    cli.main(["install-hook", "--assistant", "grok", "--event", "Stop"])
    assert cli.main(["uninstall-hook", "--assistant", "grok"]) == 0
    assert json.loads(_hook_file(tmp_path).read_text()) == {"hooks": {}}


def test_claude_install_does_not_touch_grok_or_codex(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "CLAUDE_SETTINGS", tmp_path / "settings.json")
    assert cli.main(["install-hook"]) == 0
    assert not _hook_file(tmp_path).exists()
    data = json.loads((tmp_path / "settings.json").read_text())
    assert "claude-hook" in data["hooks"]["Stop"][0]["hooks"][0]["command"]


def test_session_end_hook_uploads_unfinished_trailing_turn(tmp_path, monkeypatch):
    # Subagent sessions never log turn_completed; SessionEnd flushes the turn.
    mock = _mock_client(monkeypatch)
    monkeypatch.setenv("MONKAI_TRACE_TOKEN", "tk_test")
    _session(tmp_path, _turn(0, "a", "x", 10, T0, close=False))

    run_grok_hook(_StdIn(json.dumps({"sessionId": SESSION, "hook_event_name": "Stop"})))
    mock.upload_records_batch.assert_not_called()
    run_grok_hook(_StdIn(json.dumps({"sessionId": SESSION, "hook_event_name": "SessionEnd"})))
    assert [r.msg[0].content for r in mock.upload_records_batch.call_args[0][0]] == ["a"]


def test_incremental_with_file_path_uses_session_offset(tmp_path, monkeypatch):
    _mock_client(monkeypatch)
    tracer = GrokTracer(tracer_token="tk_test", namespace="grok")
    path = _session(tmp_path, _turn(0, "a", "x", 10, T0))
    tracer.upload_session_incremental(str(path / "updates.jsonl"))
    assert tracer.upload_session_incremental(str(path))["skipped"] == 1
