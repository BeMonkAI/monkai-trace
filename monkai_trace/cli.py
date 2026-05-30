"""Command-line interface for MonkAI Trace.

Exposes the ``monkai-trace`` console entrypoint. The primary use case is the
Claude Code hook, which auto-uploads conversation transcripts to MonkAI Trace
so they appear in the MonkAI Hub.

Subcommands:
    monkai-trace claude-hook        Read a Claude Code hook payload from stdin
                                    and incrementally upload the session.
    monkai-trace install-hook       Register the hook in ~/.claude/settings.json
                                    (idempotent; resolves an absolute command).
    monkai-trace uninstall-hook     Remove the hook from ~/.claude/settings.json.
    monkai-trace watch <dir>        Poll a project dir and upload incrementally.
    monkai-trace upload-session ... Manually upload a single session JSONL.
    monkai-trace upload-project ... Manually upload all sessions in a project dir.
"""

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
# Stable marker used to detect a MonkAI Trace hook regardless of how the
# command path is resolved (bare name, absolute path, or `python -m`).
HOOK_MARKER = "claude-hook"
DEFAULT_EVENT = "SessionEnd"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="monkai-trace",
        description="MonkAI Trace CLI — auto-trace Claude Code conversations.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "claude-hook",
        help="Read a Claude Code hook payload from stdin and upload the session.",
    )

    p_install = sub.add_parser(
        "install-hook",
        help="Register the Claude Code hook in ~/.claude/settings.json.",
    )
    p_install.add_argument(
        "--event",
        default=DEFAULT_EVENT,
        help=f"Hook event to register on (default: {DEFAULT_EVENT}). "
        "Use 'Stop' for near-realtime per-turn uploads.",
    )
    p_install.add_argument(
        "--token-file",
        default=None,
        help="Path to a file holding the tracer token (tk_...). Baked into the "
        "hook command via MONKAI_TRACE_TOKEN_FILE; default ~/.monkai_trace_token.",
    )

    sub.add_parser(
        "uninstall-hook",
        help="Remove the MonkAI Trace hook from ~/.claude/settings.json.",
    )

    p_watch = sub.add_parser(
        "watch", help="Poll a project directory and upload sessions incrementally."
    )
    p_watch.add_argument("path", help="Path to the project directory to watch.")
    p_watch.add_argument(
        "--interval", type=float, default=5.0, help="Seconds between scans (default 5)."
    )

    p_session = sub.add_parser("upload-session", help="Upload a single Claude Code session JSONL.")
    p_session.add_argument("path", help="Path to the .jsonl session file.")

    p_project = sub.add_parser("upload-project", help="Upload all sessions in a project directory.")
    p_project.add_argument("path", help="Path to the project directory.")

    return parser


def _require_token() -> Optional[str]:
    from .integrations.claude_code import resolve_token

    token = resolve_token()
    if not token:
        print(
            "error: no tracer token found. Set MONKAI_TRACE_TOKEN or put it in "
            "~/.monkai_trace_token (or MONKAI_TRACE_TOKEN_FILE).",
            file=sys.stderr,
        )
    return token


def _make_tracer(token: str):
    from .integrations.claude_code import DEFAULT_HOOK_BASE_URL, ClaudeCodeTracer

    return ClaudeCodeTracer(
        tracer_token=token,
        namespace=os.environ.get("MONKAI_TRACE_NAMESPACE", "claude-code"),
        base_url=os.environ.get("MONKAI_TRACE_BASE_URL", DEFAULT_HOOK_BASE_URL),
    )


def _resolve_hook_command(token_file: Optional[str]) -> str:
    """Build a hook command that resolves regardless of the hook runner's PATH.

    Prefers the absolute path of the installed ``monkai-trace`` binary; falls
    back to ``<python> -m monkai_trace.cli`` when the binary is not on PATH.
    When ``token_file`` is given, bakes ``MONKAI_TRACE_TOKEN_FILE`` into the
    command so the token does not depend on the shell profile being sourced.
    """
    binary = shutil.which("monkai-trace")
    if binary:
        cmd = f"{binary} {HOOK_MARKER}"
    else:
        cmd = f"{sys.executable} -m monkai_trace.cli {HOOK_MARKER}"
    if token_file:
        cmd = f'MONKAI_TRACE_TOKEN_FILE="{token_file}" {cmd}'
    return cmd


def _cmd_claude_hook() -> int:
    from .integrations.claude_code import run_hook

    return run_hook()


def _cmd_install_hook(event: str, token_file: Optional[str]) -> int:
    from .integrations.claude_code import resolve_token

    settings = _load_settings(CLAUDE_SETTINGS)
    hooks = settings.setdefault("hooks", {})
    event_hooks = hooks.setdefault(event, [])

    if _hook_present(event_hooks):
        print(f"MonkAI Trace hook already registered on {event}.")
        return 0

    command = _resolve_hook_command(token_file)
    event_hooks.append({"hooks": [{"type": "command", "command": command}]})
    _save_settings(CLAUDE_SETTINGS, settings)
    print(f"Registered MonkAI Trace hook on {event} in {CLAUDE_SETTINGS}.")
    print(f"  command: {command}")

    # Robustness: warn now if the hook would have no token at fire time.
    if token_file is None and not resolve_token():
        print(
            "warning: no tracer token found yet. Export MONKAI_TRACE_TOKEN in "
            "your shell profile, write it to ~/.monkai_trace_token, or re-run "
            "with --token-file <path>.",
            file=sys.stderr,
        )
    return 0


def _cmd_uninstall_hook() -> int:
    if not CLAUDE_SETTINGS.exists():
        print("No ~/.claude/settings.json found; nothing to remove.")
        return 0

    settings = _load_settings(CLAUDE_SETTINGS)
    hooks = settings.get("hooks", {})
    removed = False
    for event, event_hooks in list(hooks.items()):
        kept = [h for h in event_hooks if not _is_monkai_hook(h)]
        if len(kept) != len(event_hooks):
            removed = True
            if kept:
                hooks[event] = kept
            else:
                del hooks[event]

    if removed:
        _save_settings(CLAUDE_SETTINGS, settings)
        print("Removed MonkAI Trace hook from ~/.claude/settings.json.")
    else:
        print("MonkAI Trace hook was not registered; nothing to remove.")
    return 0


def _cmd_watch(path: str, interval: float) -> int:
    token = _require_token()
    if not token:
        return 1
    print(f"Watching {path} every {interval}s (Ctrl-C to stop)...")
    result = _make_tracer(token).watch(path, interval=interval)
    print(json.dumps(result, default=str))
    return 0


def _cmd_upload_session(path: str) -> int:
    token = _require_token()
    if not token:
        return 1
    result = _make_tracer(token).upload_session(path)
    print(json.dumps(result, default=str))
    return 0


def _cmd_upload_project(path: str) -> int:
    token = _require_token()
    if not token:
        return 1
    result = _make_tracer(token).upload_project(path)
    print(json.dumps(result, default=str))
    return 0


# --- settings.json helpers -------------------------------------------------


def _load_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: {path} is not valid JSON ({exc}); fix it before installing.")


def _save_settings(path: Path, settings: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def _is_monkai_hook(entry: dict) -> bool:
    inner = entry.get("hooks", []) if isinstance(entry, dict) else []
    return any(
        isinstance(h, dict) and isinstance(h.get("command"), str) and HOOK_MARKER in h["command"]
        for h in inner
    )


def _hook_present(event_hooks: List[dict]) -> bool:
    return any(_is_monkai_hook(h) for h in event_hooks)


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    args = _build_parser().parse_args(argv)

    if args.command == "claude-hook":
        return _cmd_claude_hook()
    if args.command == "install-hook":
        return _cmd_install_hook(args.event, args.token_file)
    if args.command == "uninstall-hook":
        return _cmd_uninstall_hook()
    if args.command == "watch":
        return _cmd_watch(args.path, args.interval)
    if args.command == "upload-session":
        return _cmd_upload_session(args.path)
    if args.command == "upload-project":
        return _cmd_upload_project(args.path)
    return 1


if __name__ == "__main__":
    sys.exit(main())
