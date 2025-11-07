"""
Example of using AsyncMonkAIClient for high-performance uploads
"""

import asyncio
from monkai_trace import AsyncMonkAIClient
from monkai_trace.models import ConversationRecord, Message


async def main():
    # Use async context manager
    async with AsyncMonkAIClient(tracer_token="tk_your_token_here") as client:
        
        # Single upload
        await client.upload_record(
            namespace="async-demo",
            agent="fast-bot",
            messages={"role": "assistant", "content": "Hello from async!"},
            input_tokens=5,
            output_tokens=10
        )
        print("✅ Single record uploaded")
        
        # Batch upload with parallel processing
        records = [
            ConversationRecord(
                namespace="async-demo",
                agent="fast-bot",
                session_id=f"session-{i}",
                msg=Message(role="assistant", content=f"Message {i}"),
                input_tokens=10,
                output_tokens=20
            )
            for i in range(100)
        ]
        
        result = await client.upload_records_batch(
            records,
            chunk_size=25,
            parallel=True  # Upload chunks in parallel for speed
        )
        
        print(f"✅ Uploaded {result['total_inserted']} records in parallel")
        print(f"   Total records: {result['total_records']}")
        
        # Upload from JSON file (async + parallel)
        result = await client.upload_records_from_json(
            "path/to/records.json",
            chunk_size=50,
            parallel=True
        )
        
        print(f"✅ JSON upload complete: {result['total_inserted']} records")


if __name__ == "__main__":
    asyncio.run(main())
