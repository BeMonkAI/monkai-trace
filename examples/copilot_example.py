"""
Example: Track GitHub Copilot usage in MonkAI Trace.

Supports three data sources:
1. VS Code Copilot Chat conversations (local)
2. GitHub Copilot org usage API (requires Business/Enterprise)
3. CSV export from GitHub admin dashboard

This example shows how to:
1. Upload local Copilot Chat history
2. Fetch and upload org usage metrics
3. Import from CSV export

Usage:
    # Local chat history
    python examples/copilot_example.py --token tk_your_token --mode chat

    # GitHub API (org usage)
    python examples/copilot_example.py --token tk_your_token --mode api --github-token ghp_xxx --org BeMonkAI

    # CSV import
    python examples/copilot_example.py --token tk_your_token --mode csv --csv-file copilot_export.csv
"""

import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from monkai_trace.integrations.copilot import CopilotTracer


def main():
    parser = argparse.ArgumentParser(description="Upload Copilot data to MonkAI")
    parser.add_argument("--token", default="tk_test", help="MonkAI tracer token")
    parser.add_argument("--namespace", default="dev-productivity", help="Namespace")
    parser.add_argument(
        "--mode",
        choices=["chat", "api", "csv", "all"],
        default="chat",
        help="Data source mode",
    )
    parser.add_argument("--github-token", default=None, help="GitHub PAT for API mode")
    parser.add_argument("--org", default=None, help="GitHub org for API mode")
    parser.add_argument("--csv-file", default=None, help="CSV file for csv mode")
    args = parser.parse_args()

    tracer = CopilotTracer(
        tracer_token=args.token,
        namespace=args.namespace,
    )

    if args.mode in ("chat", "all"):
        print("\n=== Copilot Chat History ===")
        try:
            result = tracer.upload_chat_history()
            print(f"  Uploaded {result['total_inserted']} conversations")
        except FileNotFoundError as e:
            print(f"  {e}")

    if args.mode in ("api", "all"):
        print("\n=== Copilot Org Usage (API) ===")
        if not args.github_token or not args.org:
            print("  Requires --github-token and --org")
        else:
            try:
                result = tracer.upload_org_usage(
                    github_token=args.github_token,
                    org=args.org,
                )
                count = result.get("total_inserted", result.get("total_logs", 0))
                print(f"  Uploaded {count} usage entries for {args.org}")
            except ValueError as e:
                print(f"  Error: {e}")

    if args.mode in ("csv", "all"):
        print("\n=== Copilot CSV Import ===")
        if not args.csv_file:
            print("  Requires --csv-file")
            print("  Expected columns: date, user, editor, language,")
            print("    suggestions_shown, suggestions_accepted,")
            print("    lines_suggested, lines_accepted")
        else:
            result = tracer.upload_from_csv(args.csv_file)
            count = result.get("total_inserted", result.get("total_logs", 0))
            print(f"  Uploaded {count} entries from {args.csv_file}")


if __name__ == "__main__":
    main()
