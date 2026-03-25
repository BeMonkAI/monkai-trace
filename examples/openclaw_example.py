"""
Example: Parse and upload OpenClaw session transcripts to MonkAI Trace.

OpenClaw (https://github.com/openclaw/openclaw) stores sessions as JSONL at:
    ~/.openclaw/agents/{agent_id}/sessions/{session_id}.jsonl

This example shows how to:
1. List all agents and sessions
2. Upload sessions from a specific agent
3. Upload all sessions

Usage:
    python examples/openclaw_example.py --token tk_your_token --namespace dev-productivity

    # Custom state directory
    python examples/openclaw_example.py --token tk_your_token --state-dir ~/.openclaw-dev
"""

import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from monkai_trace.integrations.openclaw import OpenClawTracer


def main():
    parser = argparse.ArgumentParser(description="Upload OpenClaw sessions to MonkAI")
    parser.add_argument("--token", default="tk_test", help="MonkAI tracer token")
    parser.add_argument("--namespace", default="dev-productivity", help="Namespace")
    parser.add_argument("--state-dir", default=None, help="Custom OpenClaw state dir")
    args = parser.parse_args()

    tracer = OpenClawTracer(
        tracer_token=args.token,
        namespace=args.namespace,
        state_dir=args.state_dir,
    )

    # 1. List agents
    print("\n=== OpenClaw Agents ===")
    agents = tracer.list_agents()
    if not agents:
        print("  No agents found. Is OpenClaw installed?")
        print(f"  Checked: {tracer.state_dir}")
        print("  Set --state-dir or OPENCLAW_STATE_DIR to specify location.")
        return

    for a in agents:
        print(f"  {a['agent_id']} — {a['session_count']} sessions")

    # 2. Upload from default agent
    print("\n=== Upload Default Agent Sessions ===")
    try:
        result = tracer.upload_agent_sessions("default")
        print(f"  Uploaded {result['total_inserted']} records")
    except FileNotFoundError as e:
        print(f"  {e}")

    # 3. Upload all agents
    print("\n=== Upload All Sessions ===")
    result = tracer.upload_all_sessions()
    print(f"  Total: {result['total_inserted']} records uploaded")


if __name__ == "__main__":
    main()
