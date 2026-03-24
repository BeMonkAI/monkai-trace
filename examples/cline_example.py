"""
Example: Parse and upload Cline (formerly Claude Dev / OpenClaw) tasks to MonkAI Trace.

Cline stores task history in VS Code extension storage:
    ~/Library/Application Support/Code/User/globalStorage/
        saoudrizwan.claude-dev/tasks/{task_id}/api_conversation_history.json

Also works with Cursor and Windsurf (auto-detected).

This example shows how to:
1. List all Cline tasks
2. Upload a single task
3. Upload all tasks

Usage:
    python examples/cline_example.py --token tk_your_token --namespace dev-productivity
"""

import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from monkai_trace.integrations.cline import ClineTracer


def main():
    parser = argparse.ArgumentParser(description="Upload Cline tasks to MonkAI")
    parser.add_argument("--token", default="tk_test", help="MonkAI tracer token")
    parser.add_argument("--namespace", default="dev-productivity", help="Namespace")
    parser.add_argument("--storage-dir", default=None, help="Custom Cline tasks directory")
    args = parser.parse_args()

    tracer = ClineTracer(
        tracer_token=args.token,
        namespace=args.namespace,
        agent_name="cline",
        storage_dir=args.storage_dir,
    )

    # 1. List tasks
    print("\n=== Cline Tasks ===")
    tasks = tracer.list_tasks()
    if not tasks:
        print("  No tasks found. Is Cline installed in VS Code/Cursor/Windsurf?")
        print("  You can specify a custom path with --storage-dir")
        return

    for t in tasks[:10]:  # Show first 10
        status = "✅" if t["has_api_history"] else "❌"
        print(f"  {status} {t['task_id']} — {t.get('message_count', '?')} messages")

    print(f"  ... {len(tasks)} tasks total")

    # 2. Upload a specific task
    if tasks:
        print("\n=== Upload Single Task ===")
        first_task = tasks[0]
        result = tracer.upload_task(first_task["dir"])
        print(f"  Uploaded {result['total_inserted']} records from task {first_task['task_id']}")

    # 3. Upload all tasks
    print("\n=== Upload All Tasks ===")
    result = tracer.upload_all_tasks()
    print(f"  Total: {result['total_inserted']} records uploaded")
    if result.get("failures"):
        print(f"  Failures: {len(result['failures'])}")


if __name__ == "__main__":
    main()
