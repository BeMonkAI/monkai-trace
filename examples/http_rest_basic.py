"""
Basic example of MonkAI Trace using HTTP REST API

This example shows how to use the HTTP REST API directly without
any SDK dependencies - useful for any language or runtime.

Supports user identification fields for tracking who interacts with your agent.
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
    latency_ms: int = None,
    external_user_id: str = None,
    external_user_name: str = None,
    external_user_channel: str = None
):
    """
    Record an LLM call trace.
    
    Args:
        session_id: Session ID from create_session()
        model: Model name (e.g., "gpt-4")
        input_messages: List of input messages
        output_content: The LLM response content
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        latency_ms: Call latency in milliseconds
        external_user_id: External user identifier (phone, email, etc.)
        external_user_name: Human-readable user name
        external_user_channel: Origin channel (whatsapp, web, telegram, etc.)
    """
    payload = {
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
    
    # Add user identification fields if provided
    if external_user_id:
        payload["external_user_id"] = external_user_id
    if external_user_name:
        payload["external_user_name"] = external_user_name
    if external_user_channel:
        payload["external_user_channel"] = external_user_channel
    
    requests.post(
        f"{MONKAI_API}/traces/llm",
        headers={
            "tracer_token": TRACER_TOKEN,
            "Content-Type": "application/json"
        },
        json=payload
    )


def trace_tool_call(
    session_id: str,
    tool_name: str,
    arguments: dict = None,
    result: any = None,
    latency_ms: int = None,
    agent: str = None,
    external_user_id: str = None,
    external_user_name: str = None,
    external_user_channel: str = None
):
    """
    Record a tool call trace.
    
    Args:
        session_id: Session ID
        tool_name: Name of the tool being called
        arguments: Tool arguments
        result: Tool execution result
        latency_ms: Execution time in milliseconds
        agent: Agent that called the tool
        external_user_id: External user identifier
        external_user_name: User display name
        external_user_channel: Origin channel
    """
    payload = {
        "session_id": session_id,
        "tool_name": tool_name,
        "arguments": arguments,
        "result": result,
        "latency_ms": latency_ms,
        "agent": agent
    }
    
    # Add user identification fields if provided
    if external_user_id:
        payload["external_user_id"] = external_user_id
    if external_user_name:
        payload["external_user_name"] = external_user_name
    if external_user_channel:
        payload["external_user_channel"] = external_user_channel
    
    requests.post(
        f"{MONKAI_API}/traces/tool",
        headers={
            "tracer_token": TRACER_TOKEN,
            "Content-Type": "application/json"
        },
        json=payload
    )


def trace_handoff(
    session_id: str,
    from_agent: str,
    to_agent: str,
    reason: str = None,
    external_user_id: str = None,
    external_user_name: str = None,
    external_user_channel: str = None
):
    """
    Record an agent handoff trace.
    
    Args:
        session_id: Session ID
        from_agent: Source agent name
        to_agent: Target agent name
        reason: Reason for the handoff
        external_user_id: External user identifier
        external_user_name: User display name
        external_user_channel: Origin channel
    """
    payload = {
        "session_id": session_id,
        "from_agent": from_agent,
        "to_agent": to_agent,
        "reason": reason
    }
    
    # Add user identification fields if provided
    if external_user_id:
        payload["external_user_id"] = external_user_id
    if external_user_name:
        payload["external_user_name"] = external_user_name
    if external_user_channel:
        payload["external_user_channel"] = external_user_channel
    
    requests.post(
        f"{MONKAI_API}/traces/handoff",
        headers={
            "tracer_token": TRACER_TOKEN,
            "Content-Type": "application/json"
        },
        json=payload
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
    
    # Example user data (e.g., from WhatsApp)
    user_phone = "5521997772643"
    user_name = "Italo"
    user_channel = "whatsapp"
    
    # 1. Create a session
    print("\n1. Creating session...")
    session_id = create_session(
        user_id=user_phone,
        metadata={"platform": user_channel, "version": "1.0"}
    )
    print(f"   Session ID: {session_id}")
    
    # 2. Trace an LLM call with user identification
    print("\n2. Tracing LLM call with user identification...")
    trace_llm_call(
        session_id=session_id,
        model="gpt-4",
        input_messages=[
            {"role": "user", "content": "Qual o preço do combustível em São Paulo?"}
        ],
        output_content="Vou verificar o preço para você.",
        prompt_tokens=15,
        completion_tokens=8,
        latency_ms=450,
        external_user_id=user_phone,      # Important!
        external_user_name=user_name,     # Important!
        external_user_channel=user_channel # Important!
    )
    print("   ✓ LLM call traced with user identification")
    
    # 3. Trace a tool call with user identification
    print("\n3. Tracing tool call...")
    trace_tool_call(
        session_id=session_id,
        tool_name="get_fuel_price",
        arguments={"city": "São Paulo", "fuel_type": "gasoline"},
        result={"price": 5.89, "currency": "BRL", "unit": "liter"},
        latency_ms=120,
        agent="fuel-assistant",
        external_user_id=user_phone,
        external_user_name=user_name,
        external_user_channel=user_channel
    )
    print("   ✓ Tool call traced")
    
    # 4. Trace another LLM call with tool result
    print("\n4. Tracing follow-up LLM call...")
    trace_llm_call(
        session_id=session_id,
        model="gpt-4",
        input_messages=[
            {"role": "user", "content": "Qual o preço do combustível em São Paulo?"},
            {"role": "assistant", "content": "Vou verificar o preço para você."},
            {"role": "tool", "content": '{"price": 5.89, "currency": "BRL"}'}
        ],
        output_content="O preço atual da gasolina em São Paulo é R$ 5,89/L.",
        prompt_tokens=45,
        completion_tokens=18,
        latency_ms=380,
        external_user_id=user_phone,
        external_user_name=user_name,
        external_user_channel=user_channel
    )
    print("   ✓ Follow-up LLM call traced")
    
    # 5. Trace a handoff with user identification
    print("\n5. Tracing agent handoff...")
    trace_handoff(
        session_id=session_id,
        from_agent="fuel-assistant",
        to_agent="general-assistant",
        reason="Fuel query completed, returning to general assistant",
        external_user_id=user_phone,
        external_user_name=user_name,
        external_user_channel=user_channel
    )
    print("   ✓ Handoff traced")
    
    # 6. Trace a log entry
    print("\n6. Tracing log entry...")
    trace_log(
        session_id=session_id,
        message="Conversation completed successfully",
        level="info",
        metadata={"total_turns": 2, "tools_used": ["get_fuel_price"]}
    )
    print("   ✓ Log entry traced")
    
    print("\n" + "=" * 50)
    print("✅ All traces sent to MonkAI!")
    print(f"   User: {user_name} ({user_phone}) via {user_channel}")
    print("   View your data at: https://monkai.app/monitoring")


if __name__ == "__main__":
    main()
