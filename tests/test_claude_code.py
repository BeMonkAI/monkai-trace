"""Tests for the Claude Code integration: transcript parsing, incremental
upload + offsets, token resolution, the hook entrypoint, watch, and the
settings.json hook install/uninstall."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from monkai_trace import cli
from monkai_trace.client import MonkAIClient
from monkai_trace.integrations.claude_code import (
    ClaudeCodeTracer,
    resolve_token,
    run_hook,
)


def _write_jsonl(path: Path, lines: list) -> Path:
    path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
    return path


def _turn(user: str, text: str) -> list:
    return [
        {"type": "user", "message": {"content": user}},
        {
            "type": "assistant",
            "message": {
                "model": "claude-opus-4",
                "content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": 5, "output_tokens": 4},
            },
        },
    ]


SAMPLE_SESSION = [
    {"type": "user", "message": {"content": "List the files"}},
    {
        "type": "assistant",
        "message": {
            "model": "claude-opus-4",
            "content": [
                {"type": "text", "text": "Sure, listing now."},
                {"type": "tool_use", "name": "Bash", "input": {"cmd": "ls"}, "id": "t1"},
            ],
            "usage": {"input_tokens": 12, "output_tokens": 8},
        },
    },
]

TWO_TURNS = _turn("first question", "first answer") + _turn("second question", "second answer")


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """Keep offsets and token resolution off the real home dir."""
    monkeypatch.setenv("MONKAI_TRACE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MONKAI_TRACE_TOKEN_FILE", str(tmp_path / "no_token_file"))
    monkeypatch.delenv("MONKAI_TRACE_TOKEN", raising=False)
    yield


def _mock_client(monkeypatch, inserted=1):
    mock = Mock(spec=MonkAIClient)
    mock.upload_records_batch.return_value = {
        "total_inserted": inserted,
        "total_records": inserted,
        "failures": [],
    }
    monkeypatch.setattr("monkai_trace.integrations.claude_code.MonkAIClient", lambda *a, **k: mock)
    return mock


class _StdIn:
    def __init__(self, text):
        self._text = text

    def read(self):
        return self._text


# --- parsing ---------------------------------------------------------------


def test_parse_session_builds_records(tmp_path):
    session = _write_jsonl(tmp_path / "abc123.jsonl", SAMPLE_SESSION)
    tracer = ClaudeCodeTracer(tracer_token="tk_test", namespace="claude-code", auto_upload=False)

    records = tracer._parse_session(session)

    assert len(records) == 1
    rec = records[0]
    assert rec.session_id == "abc123"
    assert rec.namespace == "claude-code"
    assert [m.role for m in rec.msg] == ["user", "assistant", "tool"]
    assert rec.input_tokens == 12
    assert rec.output_tokens == 8


def test_parse_session_empty_file(tmp_path):
    empty = _write_jsonl(tmp_path / "empty.jsonl", [])
    tracer = ClaudeCodeTracer(tracer_token="tk_test", namespace="claude-code", auto_upload=False)
    assert tracer._parse_session(empty) == []


# --- token resolution ------------------------------------------------------


def test_resolve_token_env_wins(monkeypatch):
    monkeypatch.setenv("MONKAI_TRACE_TOKEN", "tk_env")
    assert resolve_token() == "tk_env"


def test_resolve_token_from_file(tmp_path, monkeypatch):
    tok = tmp_path / "tok"
    tok.write_text("tk_file\n", encoding="utf-8")
    monkeypatch.setenv("MONKAI_TRACE_TOKEN_FILE", str(tok))
    assert resolve_token() == "tk_file"


def test_resolve_token_none_when_no_env_no_file():
    assert resolve_token() is None


# --- incremental upload + offsets ------------------------------------------


def test_upload_session_incremental_skips_already_uploaded(tmp_path, monkeypatch):
    session = _write_jsonl(tmp_path / "s.jsonl", TWO_TURNS)
    mock = _mock_client(monkeypatch, inserted=2)
    tracer = ClaudeCodeTracer(tracer_token="tk", namespace="claude-code")

    first = tracer.upload_session_incremental(str(session))
    assert first["total_inserted"] == 2
    assert first["skipped"] == 0

    second = tracer.upload_session_incremental(str(session))
    assert second["total_records"] == 0
    assert second["skipped"] == 2
    assert mock.upload_records_batch.call_count == 1  # no re-upload


def test_upload_session_incremental_uploads_only_new_turn(tmp_path, monkeypatch):
    session = tmp_path / "grow.jsonl"
    _write_jsonl(session, _turn("q1", "a1"))
    mock = _mock_client(monkeypatch, inserted=1)
    tracer = ClaudeCodeTracer(tracer_token="tk", namespace="claude-code")

    tracer.upload_session_incremental(str(session))  # uploads turn 1
    _write_jsonl(session, TWO_TURNS)  # transcript grew to 2 turns
    result = tracer.upload_session_incremental(str(session))

    assert result["skipped"] == 1
    assert result["total_inserted"] == 1  # only the new turn
    # second call uploaded exactly one new record (the 2nd turn)
    _, args, _ = mock.upload_records_batch.mock_calls[1]
    assert len(args[0]) == 1


# --- run_hook --------------------------------------------------------------


def test_run_hook_uploads_session(tmp_path, monkeypatch):
    session = _write_jsonl(tmp_path / "sess.jsonl", SAMPLE_SESSION)
    monkeypatch.setenv("MONKAI_TRACE_TOKEN", "tk_test")
    mock = _mock_client(monkeypatch)

    payload = json.dumps({"transcript_path": str(session), "session_id": "sess"})
    assert run_hook(stdin=_StdIn(payload)) == 0
    mock.upload_records_batch.assert_called_once()


def test_run_hook_incremental_second_call_noop(tmp_path, monkeypatch):
    session = _write_jsonl(tmp_path / "sess.jsonl", SAMPLE_SESSION)
    monkeypatch.setenv("MONKAI_TRACE_TOKEN", "tk_test")
    mock = _mock_client(monkeypatch)

    payload = json.dumps({"transcript_path": str(session)})
    run_hook(stdin=_StdIn(payload))
    run_hook(stdin=_StdIn(payload))  # nothing new to upload
    assert mock.upload_records_batch.call_count == 1


def test_run_hook_token_from_file(tmp_path, monkeypatch):
    session = _write_jsonl(tmp_path / "sess.jsonl", SAMPLE_SESSION)
    tok = tmp_path / "tok"
    tok.write_text("tk_file", encoding="utf-8")
    monkeypatch.setenv("MONKAI_TRACE_TOKEN_FILE", str(tok))
    mock = _mock_client(monkeypatch)

    payload = json.dumps({"transcript_path": str(session)})
    assert run_hook(stdin=_StdIn(payload)) == 0
    mock.upload_records_batch.assert_called_once()  # token came from file


def test_run_hook_without_token_skips_upload(tmp_path, monkeypatch):
    session = _write_jsonl(tmp_path / "sess.jsonl", SAMPLE_SESSION)
    # autouse fixture already removes env + points token file at a missing path
    monkeypatch.setattr(
        "monkai_trace.integrations.claude_code.ClaudeCodeTracer",
        Mock(side_effect=AssertionError("tracer must not be built without token")),
    )
    payload = json.dumps({"transcript_path": str(session)})
    assert run_hook(stdin=_StdIn(payload)) == 0


def test_run_hook_no_transcript_path():
    assert run_hook(stdin=_StdIn(json.dumps({"session_id": "x"}))) == 0


def test_run_hook_invalid_json_does_not_raise():
    assert run_hook(stdin=_StdIn("not-json{{")) == 0


def test_run_hook_upload_failure_is_swallowed(tmp_path, monkeypatch):
    session = _write_jsonl(tmp_path / "sess.jsonl", SAMPLE_SESSION)
    monkeypatch.setenv("MONKAI_TRACE_TOKEN", "tk_test")
    mock = _mock_client(monkeypatch)
    mock.upload_records_batch.side_effect = RuntimeError("network down")
    payload = json.dumps({"transcript_path": str(session)})
    assert run_hook(stdin=_StdIn(payload)) == 0  # never propagates


# --- watch -----------------------------------------------------------------


def test_watch_uploads_incrementally_then_stops(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    _write_jsonl(proj / "a.jsonl", SAMPLE_SESSION)
    _mock_client(monkeypatch, inserted=1)
    tracer = ClaudeCodeTracer(tracer_token="tk", namespace="claude-code")

    result = tracer.watch(str(proj), interval=0, max_iterations=1)
    assert result["iterations"] == 1
    assert result["total_inserted"] == 1


# --- install/uninstall hook ------------------------------------------------


@pytest.fixture
def fake_settings(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(cli, "CLAUDE_SETTINGS", settings_path)
    return settings_path


def _all_commands(settings_path: Path, event: str = "SessionEnd") -> list:
    data = json.loads(settings_path.read_text())
    return [i["command"] for h in data["hooks"][event] for i in h["hooks"]]


def test_install_hook_registers_resolvable_command(fake_settings):
    assert cli.main(["install-hook"]) == 0
    cmds = _all_commands(fake_settings)
    # command carries the stable marker and an absolute/`-m` invocation
    assert any(cli.HOOK_MARKER in c for c in cmds)
    assert any(("/" in c) or ("-m monkai_trace.cli" in c) for c in cmds)


def test_install_hook_is_idempotent(fake_settings):
    assert cli.main(["install-hook"]) == 0
    assert cli.main(["install-hook"]) == 0  # no-op
    monkai = [c for c in _all_commands(fake_settings) if cli.HOOK_MARKER in c]
    assert len(monkai) == 1


def test_install_hook_preserves_existing_hooks(fake_settings):
    fake_settings.write_text(
        json.dumps(
            {"hooks": {"SessionEnd": [{"hooks": [{"type": "command", "command": "other"}]}]}}
        )
    )
    assert cli.main(["install-hook"]) == 0
    cmds = _all_commands(fake_settings)
    assert "other" in cmds
    assert any(cli.HOOK_MARKER in c for c in cmds)


def test_install_hook_token_file_is_baked(fake_settings):
    assert cli.main(["install-hook", "--token-file", "/home/me/.tok"]) == 0
    cmds = _all_commands(fake_settings)
    assert any("MONKAI_TRACE_TOKEN_FILE=" in c and "/home/me/.tok" in c for c in cmds)


def test_install_hook_default_registers_stop_and_sessionend(fake_settings):
    # Default now registers BOTH: Stop (per-turn, near-realtime) + SessionEnd
    # (end-of-session safety net). Incremental offset makes the overlap a no-op.
    assert cli.main(["install-hook"]) == 0
    for event in ("Stop", "SessionEnd"):
        cmds = _all_commands(fake_settings, event=event)
        assert any(cli.HOOK_MARKER in c for c in cmds), f"missing hook on {event}"


def test_install_hook_default_is_idempotent_across_events(fake_settings):
    assert cli.main(["install-hook"]) == 0
    assert cli.main(["install-hook"]) == 0  # no-op on both events
    for event in ("Stop", "SessionEnd"):
        monkai = [c for c in _all_commands(fake_settings, event=event) if cli.HOOK_MARKER in c]
        assert len(monkai) == 1, f"duplicate hook on {event}"


def test_install_hook_custom_event(fake_settings):
    # A single --event overrides the dual default — only Stop is registered.
    assert cli.main(["install-hook", "--event", "Stop"]) == 0
    cmds = _all_commands(fake_settings, event="Stop")
    assert any(cli.HOOK_MARKER in c for c in cmds)
    assert "SessionEnd" not in json.loads(fake_settings.read_text()).get("hooks", {})


def test_uninstall_hook_removes_only_monkai(fake_settings):
    cli.main(["install-hook"])
    assert cli.main(["uninstall-hook"]) == 0
    data = json.loads(fake_settings.read_text())
    assert "SessionEnd" not in data.get("hooks", {})


def test_uninstall_hook_no_settings(fake_settings):
    assert not fake_settings.exists()
    assert cli.main(["uninstall-hook"]) == 0
