"""
Example: Parse and upload Claude Code session logs to MonkAI Trace.

Claude Code stores conversation sessions as JSONL files in:
    ~/.claude/projects/{encoded_path}/{session_uuid}.jsonl

This example shows how to:
1. List all Claude Code projects
2. Upload a single session
3. Upload all sessions from a project
4. Upload everything

Usage:
    python examples/claude_code_example.py --token tk_your_token --namespace dev-productivity
"""

import argparse
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from monkai_trace.integrations.claude_code import ClaudeCodeTracer


def main():
    parser = argparse.ArgumentParser(description="Upload Claude Code sessions to MonkAI")
    parser.add_argument("--token", default="tk_test", help="MonkAI tracer token")
    parser.add_argument("--namespace", default="dev-productivity", help="Namespace")
    args = parser.parse_args()

    tracer = ClaudeCodeTracer(
        tracer_token=args.token,
        namespace=args.namespace,
        agent_name="claude-code",
    )

    # 1. List all Claude Code projects
    print("\n=== Claude Code Projects ===")
    projects = tracer.list_projects()
    for p in projects:
        print(f"  {p['decoded_path']} — {p['session_count']} sessions")

    if not projects:
        print("  No projects found. Is Claude Code installed?")
        return

    # 2. Upload a single session (first session of first project)
    print("\n=== Upload Single Session ===")
    from pathlib import Path

    first_project = Path(projects[0]["dir"])
    sessions = list(first_project.glob("*.jsonl"))
    if sessions:
        result = tracer.upload_session(str(sessions[0]))
        print(f"  Uploaded {result['total_inserted']} records from {sessions[0].name}")

    # 3. Upload all sessions from a project
    print("\n=== Upload Project ===")
    result = tracer.upload_project(projects[0]["dir"])
    print(f"  Uploaded {result['total_inserted']} records from {projects[0]['decoded_path']}")

    # 4. Upload everything (all projects)
    print("\n=== Upload All Projects ===")
    result = tracer.upload_all_projects()
    print(f"  Total: {result['total_inserted']} records uploaded")
    if result["failures"]:
        print(f"  Failures: {len(result['failures'])}")
        for f in result["failures"]:
            print(f"    - {f}")


if __name__ == "__main__":
    main()
