"""Tests for the Claude Code integration: transcript parsing, the SessionEnd
hook entrypoint, and settings.json hook install/uninstall."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from monkai_trace import cli
from monkai_trace.client import MonkAIClient
from monkai_trace.integrations.claude_code import ClaudeCodeTracer, run_hook


def _write_jsonl(path: Path, lines: list) -> Path:
    path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
    return path


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


# --- parsing ---------------------------------------------------------------


def test_parse_session_builds_records(tmp_path):
    session = _write_jsonl(tmp_path / "abc123.jsonl", SAMPLE_SESSION)
    tracer = ClaudeCodeTracer(tracer_token="tk_test", namespace="claude-code", auto_upload=False)

    records = tracer._parse_session(session)

    assert len(records) == 1
    rec = records[0]
    assert rec.session_id == "abc123"
    assert rec.namespace == "claude-code"
    roles = [m.role for m in rec.msg]
    assert roles == ["user", "assistant", "tool"]
    assert rec.input_tokens == 12
    assert rec.output_tokens == 8


def test_parse_session_empty_file(tmp_path):
    empty = _write_jsonl(tmp_path / "empty.jsonl", [])
    tracer = ClaudeCodeTracer(tracer_token="tk_test", namespace="claude-code", auto_upload=False)
    assert tracer._parse_session(empty) == []


# --- run_hook --------------------------------------------------------------


class _StdIn:
    def __init__(self, text):
        self._text = text

    def read(self):
        return self._text


def test_run_hook_uploads_session(tmp_path, monkeypatch):
    session = _write_jsonl(tmp_path / "sess.jsonl", SAMPLE_SESSION)
    monkeypatch.setenv("MONKAI_TRACE_TOKEN", "tk_test")

    mock_client = Mock(spec=MonkAIClient)
    mock_client.upload_records_batch.return_value = {
        "total_inserted": 1,
        "total_records": 1,
        "failures": [],
    }
    monkeypatch.setattr(
        "monkai_trace.integrations.claude_code.MonkAIClient",
        lambda *a, **k: mock_client,
    )

    payload = json.dumps({"transcript_path": str(session), "session_id": "sess"})
    assert run_hook(stdin=_StdIn(payload)) == 0
    mock_client.upload_records_batch.assert_called_once()


def test_run_hook_without_token_skips_upload(tmp_path, monkeypatch):
    session = _write_jsonl(tmp_path / "sess.jsonl", SAMPLE_SESSION)
    monkeypatch.delenv("MONKAI_TRACE_TOKEN", raising=False)

    # If a tracer were built, this would explode — proving no upload happens.
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
    mock_client = Mock(spec=MonkAIClient)
    mock_client.upload_records_batch.side_effect = RuntimeError("network down")
    monkeypatch.setattr(
        "monkai_trace.integrations.claude_code.MonkAIClient",
        lambda *a, **k: mock_client,
    )
    payload = json.dumps({"transcript_path": str(session)})
    assert run_hook(stdin=_StdIn(payload)) == 0  # never propagates


# --- install/uninstall hook ------------------------------------------------


@pytest.fixture
def fake_settings(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(cli, "CLAUDE_SETTINGS", settings_path)
    return settings_path


def test_install_hook_is_idempotent(fake_settings):
    assert cli.main(["install-hook"]) == 0
    assert cli.main(["install-hook"]) == 0  # second time = no-op

    data = json.loads(fake_settings.read_text())
    session_end = data["hooks"]["SessionEnd"]
    monkai_entries = [
        h
        for h in session_end
        if any(i.get("command") == cli.HOOK_COMMAND for i in h.get("hooks", []))
    ]
    assert len(monkai_entries) == 1


def test_install_hook_preserves_existing_hooks(fake_settings):
    fake_settings.write_text(
        json.dumps(
            {"hooks": {"SessionEnd": [{"hooks": [{"type": "command", "command": "other"}]}]}}
        )
    )
    assert cli.main(["install-hook"]) == 0

    session_end = json.loads(fake_settings.read_text())["hooks"]["SessionEnd"]
    commands = [i["command"] for h in session_end for i in h["hooks"]]
    assert "other" in commands
    assert cli.HOOK_COMMAND in commands


def test_uninstall_hook_removes_only_monkai(fake_settings):
    cli.main(["install-hook"])
    assert cli.main(["uninstall-hook"]) == 0
    data = json.loads(fake_settings.read_text())
    assert "SessionEnd" not in data.get("hooks", {})


def test_uninstall_hook_no_settings(fake_settings):
    assert not fake_settings.exists()
    assert cli.main(["uninstall-hook"]) == 0
