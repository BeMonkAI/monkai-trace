"""
Async example of MonkAI Trace using HTTP REST API with aiohttp

This example shows how to use the HTTP REST API with async/await
for high-performance applications.
"""

import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, Any


# Configuration
MONKAI_API = "https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api"
TRACER_TOKEN = "tk_your_token_here"  # Replace with your token
NAMESPACE = "my-agent"


class MonkAITraceClient:
    """Async client for MonkAI Trace HTTP REST API."""
    
    def __init__(
        self,
        token: str,
        namespace: str,
        base_url: str = MONKAI_API
    ):
        self.token = token
        self.namespace = namespace
        self.base_url = base_url
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            headers={
                "tracer_token": self.token,
                "Content-Type": "application/json"
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
    
    async def create_session(
        self,
        user_id: str,
        inactivity_timeout: int = 120,
        metadata: dict = None
    ) -> str:
        """Create a new tracking session."""
        async with self._session.post(
            f"{self.base_url}/sessions/create",
            json={
                "namespace": self.namespace,
                "user_id": user_id,
                "inactivity_timeout": inactivity_timeout,
                "metadata": metadata or {}
            }
        ) as response:
            response.raise_for_status()
            data = await response.json()
            return data["session_id"]
    
    async def trace_llm(
        self,
        session_id: str,
        model: str,
        input_messages: list,
        output_content: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: int = None,
        provider: str = None,
        metadata: dict = None
    ):
        """Record an LLM call trace."""
        async with self._session.post(
            f"{self.base_url}/traces/llm",
            json={
                "session_id": session_id,
                "model": model,
                "provider": provider,
                "input": {"messages": input_messages},
                "output": {
                    "content": output_content,
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens
                    }
                },
                "latency_ms": latency_ms,
                "metadata": metadata
            }
        ) as response:
            response.raise_for_status()
    
    async def trace_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict = None,
        result: Any = None,
        latency_ms: int = None,
        agent: str = None,
        metadata: dict = None
    ):
        """Record a tool call trace."""
        async with self._session.post(
            f"{self.base_url}/traces/tool",
            json={
                "session_id": session_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "result": result,
                "latency_ms": latency_ms,
                "agent": agent,
                "metadata": metadata
            }
        ) as response:
            response.raise_for_status()
    
    async def trace_handoff(
        self,
        session_id: str,
        from_agent: str,
        to_agent: str,
        reason: str = None,
        metadata: dict = None
    ):
        """Record an agent handoff trace."""
        async with self._session.post(
            f"{self.base_url}/traces/handoff",
            json={
                "session_id": session_id,
                "from_agent": from_agent,
                "to_agent": to_agent,
                "reason": reason,
                "metadata": metadata
            }
        ) as response:
            response.raise_for_status()
    
    async def trace_log(
        self,
        message: str,
        level: str = "info",
        session_id: str = None,
        resource_id: str = None,
        metadata: dict = None
    ):
        """Record a log entry trace."""
        payload = {
            "level": level,
            "message": message,
            "metadata": metadata
        }
        
        if session_id:
            payload["session_id"] = session_id
        else:
            payload["namespace"] = self.namespace
        
        if resource_id:
            payload["resource_id"] = resource_id
        
        async with self._session.post(
            f"{self.base_url}/traces/log",
            json=payload
        ) as response:
            response.raise_for_status()


async def simulate_conversation(client: MonkAITraceClient, user_id: str):
    """Simulate a conversation with multiple turns."""
    # Create session
    session_id = await client.create_session(
        user_id=user_id,
        metadata={"platform": "api", "simulation": True}
    )
    print(f"  Session: {session_id}")
    
    # Simulate conversation turns
    turns = [
        ("What's 2 + 2?", "2 + 2 equals 4."),
        ("And if I multiply by 3?", "4 multiplied by 3 equals 12."),
        ("Thanks!", "You're welcome! Let me know if you have more questions."),
    ]
    
    for i, (user_msg, assistant_msg) in enumerate(turns, 1):
        await client.trace_llm(
            session_id=session_id,
            model="gpt-4",
            input_messages=[{"role": "user", "content": user_msg}],
            output_content=assistant_msg,
            prompt_tokens=len(user_msg.split()) * 2,
            completion_tokens=len(assistant_msg.split()) * 2,
            latency_ms=200 + i * 50
        )
        print(f"    Turn {i}: {user_msg[:30]}...")
    
    await client.trace_log(
        message=f"Conversation completed with {len(turns)} turns",
        level="info",
        session_id=session_id,
        metadata={"turns": len(turns)}
    )
    
    return session_id


async def main():
    print("MonkAI Trace Async HTTP REST API Example")
    print("=" * 50)
    
    async with MonkAITraceClient(
        token=TRACER_TOKEN,
        namespace=NAMESPACE
    ) as client:
        # Simulate multiple concurrent conversations
        print("\nSimulating 3 concurrent conversations...")
        
        tasks = [
            simulate_conversation(client, f"user_{i}")
            for i in range(1, 4)
        ]
        
        session_ids = await asyncio.gather(*tasks)
        
        print(f"\n✅ Completed {len(session_ids)} conversations")
        print("   View your data at: https://monkai.app/monitoring")


if __name__ == "__main__":
    asyncio.run(main())
