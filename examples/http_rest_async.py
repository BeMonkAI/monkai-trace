"""
Async example of MonkAI Trace using HTTP REST API with aiohttp

This example shows how to use the HTTP REST API with async/await
for high-performance applications with user identification support.
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
    """Async client for MonkAI Trace HTTP REST API with user identification support."""
    
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
        
        # User identification (can be set per-client)
        self._external_user_id: Optional[str] = None
        self._external_user_name: Optional[str] = None
        self._external_user_channel: Optional[str] = None
    
    def set_user(
        self,
        user_id: str = None,
        user_name: str = None,
        channel: str = None
    ):
        """
        Set user identification for all subsequent traces.
        
        Args:
            user_id: External user identifier (phone, email, etc.)
            user_name: Human-readable display name
            channel: Origin channel (whatsapp, web, telegram, etc.)
        """
        if user_id:
            self._external_user_id = user_id
        if user_name:
            self._external_user_name = user_name
        if channel:
            self._external_user_channel = channel
    
    def _add_user_fields(self, payload: dict) -> dict:
        """Add user identification fields to payload if set."""
        if self._external_user_id:
            payload["external_user_id"] = self._external_user_id
        if self._external_user_name:
            payload["external_user_name"] = self._external_user_name
        if self._external_user_channel:
            payload["external_user_channel"] = self._external_user_channel
        return payload
    
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
        metadata: dict = None,
        external_user_id: str = None,
        external_user_name: str = None,
        external_user_channel: str = None
    ):
        """
        Record an LLM call trace with optional user identification.
        
        If external_user_* parameters are not provided, uses the values
        set via set_user() method.
        """
        payload = {
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
        
        # Add user identification (parameter overrides client-level)
        if external_user_id:
            payload["external_user_id"] = external_user_id
        elif self._external_user_id:
            payload["external_user_id"] = self._external_user_id
            
        if external_user_name:
            payload["external_user_name"] = external_user_name
        elif self._external_user_name:
            payload["external_user_name"] = self._external_user_name
            
        if external_user_channel:
            payload["external_user_channel"] = external_user_channel
        elif self._external_user_channel:
            payload["external_user_channel"] = self._external_user_channel
        
        async with self._session.post(
            f"{self.base_url}/traces/llm",
            json=payload
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
        metadata: dict = None,
        external_user_id: str = None,
        external_user_name: str = None,
        external_user_channel: str = None
    ):
        """Record a tool call trace with optional user identification."""
        payload = {
            "session_id": session_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result,
            "latency_ms": latency_ms,
            "agent": agent,
            "metadata": metadata
        }
        
        # Add user identification
        if external_user_id:
            payload["external_user_id"] = external_user_id
        elif self._external_user_id:
            payload["external_user_id"] = self._external_user_id
            
        if external_user_name:
            payload["external_user_name"] = external_user_name
        elif self._external_user_name:
            payload["external_user_name"] = self._external_user_name
            
        if external_user_channel:
            payload["external_user_channel"] = external_user_channel
        elif self._external_user_channel:
            payload["external_user_channel"] = self._external_user_channel
        
        async with self._session.post(
            f"{self.base_url}/traces/tool",
            json=payload
        ) as response:
            response.raise_for_status()
    
    async def trace_handoff(
        self,
        session_id: str,
        from_agent: str,
        to_agent: str,
        reason: str = None,
        metadata: dict = None,
        external_user_id: str = None,
        external_user_name: str = None,
        external_user_channel: str = None
    ):
        """Record an agent handoff trace with optional user identification."""
        payload = {
            "session_id": session_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "reason": reason,
            "metadata": metadata
        }
        
        # Add user identification
        if external_user_id:
            payload["external_user_id"] = external_user_id
        elif self._external_user_id:
            payload["external_user_id"] = self._external_user_id
            
        if external_user_name:
            payload["external_user_name"] = external_user_name
        elif self._external_user_name:
            payload["external_user_name"] = self._external_user_name
            
        if external_user_channel:
            payload["external_user_channel"] = external_user_channel
        elif self._external_user_channel:
            payload["external_user_channel"] = self._external_user_channel
        
        async with self._session.post(
            f"{self.base_url}/traces/handoff",
            json=payload
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


async def simulate_whatsapp_conversation(
    client: MonkAITraceClient,
    phone: str,
    name: str
):
    """Simulate a WhatsApp conversation with user identification."""
    
    # Set user identification for this conversation
    client.set_user(
        user_id=phone,
        user_name=name,
        channel="whatsapp"
    )
    
    # Create session
    session_id = await client.create_session(
        user_id=phone,
        inactivity_timeout=300,  # 5 minutes for WhatsApp
        metadata={"platform": "whatsapp", "user_name": name}
    )
    print(f"  [{name}] Session: {session_id}")
    
    # Simulate conversation turns
    turns = [
        ("Qual o preço da gasolina?", "O preço atual é R$ 5,89/L."),
        ("E o etanol?", "O etanol está custando R$ 3,99/L."),
        ("Obrigado!", "Por nada! Precisando, estou à disposição."),
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
            # User identification is automatically added from set_user()
        )
        print(f"    [{name}] Turn {i}: {user_msg[:30]}...")
    
    await client.trace_log(
        message=f"Conversation completed with {len(turns)} turns",
        level="info",
        session_id=session_id,
        metadata={"turns": len(turns), "user_name": name}
    )
    
    return session_id


async def main():
    print("MonkAI Trace Async HTTP REST API Example")
    print("=" * 50)
    
    async with MonkAITraceClient(
        token=TRACER_TOKEN,
        namespace=NAMESPACE
    ) as client:
        # Simulate multiple concurrent WhatsApp conversations
        print("\nSimulating 3 concurrent WhatsApp conversations...")
        
        users = [
            ("5521997772643", "Italo"),
            ("5511988887777", "Maria"),
            ("5531999996666", "João"),
        ]
        
        tasks = [
            simulate_whatsapp_conversation(client, phone, name)
            for phone, name in users
        ]
        
        session_ids = await asyncio.gather(*tasks)
        
        print(f"\n✅ Completed {len(session_ids)} conversations with user identification")
        print("   View your data at: https://monkai.app/monitoring")


if __name__ == "__main__":
    asyncio.run(main())
