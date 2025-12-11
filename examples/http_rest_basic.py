"""
Basic example of MonkAI Trace using HTTP REST API

This example shows how to use the HTTP REST API directly without
any SDK dependencies - useful for any language or runtime.
"""

import requests
from datetime import datetime


# Configuration
MONKAI_API = "https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api"
TRACER_TOKEN = "tk_your_token_here"  # Replace with your token
NAMESPACE = "my-agent"


def create_session(user_id: str, metadata: dict = None) -> str:
    """Create a new tracking session."""
    response = requests.post(
        f"{MONKAI_API}/sessions/create",
        headers={
            "tracer_token": TRACER_TOKEN,
            "Content-Type": "application/json"
        },
        json={
            "namespace": NAMESPACE,
            "user_id": user_id,
            "inactivity_timeout": 120,
            "metadata": metadata or {}
        }
    )
    response.raise_for_status()
    return response.json()["session_id"]


def trace_llm_call(
    session_id: str,
    model: str,
    input_messages: list,
    output_content: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int = None
):
    """Record an LLM call trace."""
    requests.post(
        f"{MONKAI_API}/traces/llm",
        headers={
            "tracer_token": TRACER_TOKEN,
            "Content-Type": "application/json"
        },
        json={
            "session_id": session_id,
            "model": model,
            "input": {"messages": input_messages},
            "output": {
                "content": output_content,
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens
                }
            },
            "latency_ms": latency_ms
        }
    )


def trace_tool_call(
    session_id: str,
    tool_name: str,
    arguments: dict = None,
    result: any = None,
    latency_ms: int = None,
    agent: str = None
):
    """Record a tool call trace."""
    requests.post(
        f"{MONKAI_API}/traces/tool",
        headers={
            "tracer_token": TRACER_TOKEN,
            "Content-Type": "application/json"
        },
        json={
            "session_id": session_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result,
            "latency_ms": latency_ms,
            "agent": agent
        }
    )


def trace_handoff(
    session_id: str,
    from_agent: str,
    to_agent: str,
    reason: str = None
):
    """Record an agent handoff trace."""
    requests.post(
        f"{MONKAI_API}/traces/handoff",
        headers={
            "tracer_token": TRACER_TOKEN,
            "Content-Type": "application/json"
        },
        json={
            "session_id": session_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "reason": reason
        }
    )


def trace_log(
    session_id: str,
    message: str,
    level: str = "info",
    metadata: dict = None
):
    """Record a log entry trace."""
    requests.post(
        f"{MONKAI_API}/traces/log",
        headers={
            "tracer_token": TRACER_TOKEN,
            "Content-Type": "application/json"
        },
        json={
            "session_id": session_id,
            "level": level,
            "message": message,
            "metadata": metadata
        }
    )


def main():
    print("MonkAI Trace HTTP REST API Example")
    print("=" * 50)
    
    # 1. Create a session
    print("\n1. Creating session...")
    session_id = create_session(
        user_id="user123",
        metadata={"platform": "web", "version": "1.0"}
    )
    print(f"   Session ID: {session_id}")
    
    # 2. Trace an LLM call
    print("\n2. Tracing LLM call...")
    trace_llm_call(
        session_id=session_id,
        model="gpt-4",
        input_messages=[
            {"role": "user", "content": "What's the weather like in São Paulo?"}
        ],
        output_content="I'll check the weather for you.",
        prompt_tokens=15,
        completion_tokens=8,
        latency_ms=450
    )
    print("   ✓ LLM call traced")
    
    # 3. Trace a tool call
    print("\n3. Tracing tool call...")
    trace_tool_call(
        session_id=session_id,
        tool_name="get_weather",
        arguments={"city": "São Paulo", "units": "celsius"},
        result={"temperature": 25, "condition": "sunny", "humidity": 60},
        latency_ms=120,
        agent="weather-assistant"
    )
    print("   ✓ Tool call traced")
    
    # 4. Trace another LLM call with tool result
    print("\n4. Tracing follow-up LLM call...")
    trace_llm_call(
        session_id=session_id,
        model="gpt-4",
        input_messages=[
            {"role": "user", "content": "What's the weather like in São Paulo?"},
            {"role": "assistant", "content": "I'll check the weather for you."},
            {"role": "tool", "content": '{"temperature": 25, "condition": "sunny"}'}
        ],
        output_content="The weather in São Paulo is sunny with 25°C and 60% humidity.",
        prompt_tokens=45,
        completion_tokens=18,
        latency_ms=380
    )
    print("   ✓ Follow-up LLM call traced")
    
    # 5. Trace a handoff
    print("\n5. Tracing agent handoff...")
    trace_handoff(
        session_id=session_id,
        from_agent="weather-assistant",
        to_agent="general-assistant",
        reason="Weather query completed, returning to general assistant"
    )
    print("   ✓ Handoff traced")
    
    # 6. Trace a log entry
    print("\n6. Tracing log entry...")
    trace_log(
        session_id=session_id,
        message="Conversation completed successfully",
        level="info",
        metadata={"total_turns": 2, "tools_used": ["get_weather"]}
    )
    print("   ✓ Log entry traced")
    
    print("\n" + "=" * 50)
    print("✅ All traces sent to MonkAI!")
    print("   View your data at: https://monkai.app/monitoring")


if __name__ == "__main__":
    main()
