"""
Example: Querying and Exporting Data from MonkAI Trace

This example demonstrates how to use the SDK to:
1. Query conversation records with filters
2. Query logs with filters
3. Export complete datasets to JSON or CSV files
"""

import os
from monkai_trace import MonkAIClient

# Initialize client
client = MonkAIClient(
    tracer_token=os.getenv("MONKAI_TRACER_TOKEN", "tk_your_token_here")
)

# ==================== QUERY RECORDS ====================

# Query recent records from a namespace
print("=== Querying Records ===")
result = client.query_records(
    namespace="customer-support",
    limit=10
)
print(f"Found {result['count']} records")
for record in result.get("records", []):
    print(f"  - Agent: {record['agent']}, Session: {record.get('session_id', 'N/A')}")

# Query records by agent and date range
print("\n=== Querying by Agent + Date ===")
result = client.query_records(
    namespace="customer-support",
    agent="Triage Agent",
    start_date="2025-01-01",
    end_date="2025-02-01",
    limit=50
)
print(f"Found {result['count']} records for Triage Agent in January 2025")

# Paginate through results
print("\n=== Paginating Records ===")
offset = 0
total = 0
while True:
    result = client.query_records(
        namespace="customer-support",
        limit=100,
        offset=offset
    )
    records = result.get("records", [])
    if not records:
        break
    total += len(records)
    offset += 100
    print(f"  Fetched {len(records)} records (total: {total})")

# ==================== QUERY LOGS ====================

print("\n=== Querying Logs ===")
result = client.query_logs(
    namespace="customer-support",
    level="error",
    limit=20
)
print(f"Found {result['count']} error logs")
for log in result.get("logs", []):
    print(f"  [{log.get('level')}] {log.get('message', '')[:80]}")

# ==================== EXPORT RECORDS ====================

# Export all records as JSON file
print("\n=== Exporting Records (JSON) ===")
records = client.export_records(
    namespace="customer-support",
    output_file="export_records.json"
)
print(f"Exported {len(records)} records to export_records.json")

# Export filtered records as CSV
print("\n=== Exporting Records (CSV) ===")
csv_data = client.export_records(
    namespace="customer-support",
    agent="Triage Agent",
    start_date="2025-01-01",
    end_date="2025-02-01",
    format="csv",
    output_file="triage_jan2025.csv"
)
print(f"Exported CSV ({len(csv_data)} bytes) to triage_jan2025.csv")

# ==================== EXPORT LOGS ====================

# Export error logs as JSON
print("\n=== Exporting Logs (JSON) ===")
logs = client.export_logs(
    namespace="customer-support",
    level="error",
    output_file="error_logs.json"
)
print(f"Exported {len(logs)} error logs to error_logs.json")

# Export all logs as CSV
print("\n=== Exporting Logs (CSV) ===")
csv_data = client.export_logs(
    namespace="customer-support",
    format="csv",
    output_file="all_logs.csv"
)
print(f"Exported CSV ({len(csv_data)} bytes) to all_logs.csv")

print("\n✅ All exports complete!")
