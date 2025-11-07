"""
Example of uploading conversation records and logs from JSON files
"""

from monkai_trace import MonkAIClient


def main():
    # Initialize client
    client = MonkAIClient(tracer_token="tk_your_token_here")
    
    # Example 1: Upload conversation records from JSON file
    print("Uploading conversation records...")
    records_result = client.upload_records_from_json(
        file_path="examples/sample_record_query.json",
        chunk_size=50  # Upload 50 records at a time
    )
    
    print(f"✅ Uploaded {records_result['total_inserted']} records")
    print(f"   Total in file: {records_result['total_records']}")
    if records_result['failures']:
        print(f"   ⚠️ {len(records_result['failures'])} chunks failed")
    
    # Example 2: Upload logs from JSON file
    print("\nUploading logs...")
    logs_result = client.upload_logs_from_json(
        file_path="examples/sample_logs.json",
        namespace="my-agent-namespace",  # Required for logs
        chunk_size=100
    )
    
    print(f"✅ Uploaded {logs_result['total_inserted']} logs")
    print(f"   Total in file: {logs_result['total_logs']}")
    if logs_result['failures']:
        print(f"   ⚠️ {len(logs_result['failures'])} chunks failed")


if __name__ == "__main__":
    main()
