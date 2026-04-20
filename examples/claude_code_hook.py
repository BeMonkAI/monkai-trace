#!/usr/bin/env python3
"""
Live Claude Code → MonkAI Trace via Stop hook.

Claude Code can run a shell command whenever a turn ends (the `Stop` hook).
The hook receives a JSON payload on stdin that includes `transcript_path`,
the `.jsonl` file for the current session. This script parses that file with
`ClaudeCodeTracer` and uploads every new message/tool call to MonkAI.

Pairs with the backfill example in `claude_code_example.py`:
    - claude_code_example.py  → one-off upload of historical sessions
    - claude_code_hook.py     → live, per-turn upload (this file)

-------------------------------------------------------------------------
SETUP
-------------------------------------------------------------------------

1. Install the SDK on the same interpreter Claude Code will invoke:

       pip install monkai-trace

2. Export your tracer token (e.g. in ~/.zshrc):

       export MONKAI_TRACER_TOKEN="tk_your_token"

   Optional overrides:

       export MONKAI_NAMESPACE="personal-agents"
       export MONKAI_AGENT="claude-$USER"

3. Copy this file somewhere stable (e.g. ~/.claude/monkai_trace_hook.py)
   and register the hook in ~/.claude/settings.json:

       {
         "hooks": {
           "Stop": [
             {
               "matcher": "",
               "hooks": [
                 {
                   "type": "command",
                   "command": "python3 ~/.claude/monkai_trace_hook.py"
                 }
               ]
             }
           ]
         }
       }

-------------------------------------------------------------------------
DESIGN NOTES
-------------------------------------------------------------------------

- The hook must never crash Claude Code. Any error exits 0 and logs to
  stderr — the user still sees Claude's response normally.
- Each run uploads the *full* session file. The API is idempotent on
  (session_id, message), so replaying the same transcript is safe.
- `agent_name` defaults to `claude-<user>` so every developer shows up as
  their own "personal agent" in the MonkAI dashboard. Override with
  MONKAI_AGENT for per-project agents (e.g. `claude-vivo-pricing`).
"""

import json
import os
import sys
from pathlib import Path


def _log(msg: str) -> None:
    print(f"[monkai-trace] {msg}", file=sys.stderr)


def main() -> int:
    token = os.environ.get("MONKAI_TRACER_TOKEN")
    if not token:
        _log("MONKAI_TRACER_TOKEN not set — skipping upload")
        return 0

    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        _log(f"invalid hook payload on stdin: {exc}")
        return 0

    transcript = payload.get("transcript_path")
    if not transcript:
        _log("hook payload missing transcript_path — skipping")
        return 0

    path = Path(transcript).expanduser()
    if not path.exists():
        _log(f"transcript file not found: {path}")
        return 0

    try:
        from monkai_trace.integrations.claude_code import ClaudeCodeTracer
    except ImportError:
        _log("monkai-trace not installed — run `pip install monkai-trace`")
        return 0

    user = os.environ.get("USER", "anon")
    namespace = os.environ.get("MONKAI_NAMESPACE", "personal-agents")
    agent_name = os.environ.get("MONKAI_AGENT", f"claude-{user}")

    try:
        tracer = ClaudeCodeTracer(
            tracer_token=token,
            namespace=namespace,
            agent_name=agent_name,
        )
        result = tracer.upload_session(str(path))
    except Exception as exc:
        _log(f"upload failed ({type(exc).__name__}): {exc}")
        return 0

    inserted = result.get("total_inserted", 0)
    _log(f"uploaded {inserted} records from {path.name} (agent={agent_name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
