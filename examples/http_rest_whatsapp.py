"""
MonkAI Trace - WhatsApp Integration Example

This example demonstrates how to properly integrate MonkAI Trace with
WhatsApp-based AI agents using the HTTP REST API.

Key features:
- User identification with phone number, name, and channel
- Session management for conversation grouping
- Complete trace of LLM calls, tool usage, and handoffs

The tracked data will appear in the MonkAI dashboard with:
- Green badge: User ID (phone number)
- Blue badge: User name
- Channel icon: WhatsApp
"""

import requests
from typing import Optional


# Configuration - Replace with your values
MONKAI_API = "https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api"
TRACER_TOKEN = "tk_your_token_here"  # Your MonkAI tracer token
NAMESPACE = "trackfuel"  # Your workspace/namespace


class WhatsAppTracer:
    """
    MonkAI tracer specifically designed for WhatsApp integrations.
    
    Automatically handles user identification from WhatsApp metadata.
    """
    
    def __init__(
        self,
        tracer_token: str,
        namespace: str,
        base_url: str = MONKAI_API
    ):
        self.token = tracer_token
        self.namespace = namespace
        self.base_url = base_url
        self.headers = {
            "tracer_token": self.token,
            "Content-Type": "application/json"
        }
    
    def create_session(
        self,
        phone_number: str,
        inactivity_timeout: int = 300  # 5 minutes default for WhatsApp
    ) -> str:
        """
        Create a new session for a WhatsApp conversation.
        
        Args:
            phone_number: User's WhatsApp number (e.g., "5521997772643")
            inactivity_timeout: Seconds before session expires (default: 300)
        
        Returns:
            Session ID for use in subsequent traces
        """
        response = requests.post(
            f"{self.base_url}/sessions/create",
            headers=self.headers,
            json={
                "namespace": self.namespace,
                "user_id": phone_number,
                "inactivity_timeout": inactivity_timeout,
                "metadata": {"platform": "whatsapp"}
            }
        )
        response.raise_for_status()
        return response.json()["session_id"]
    
    def trace_message(
        self,
        session_id: str,
        user_message: str,
        bot_response: str,
        phone_number: str,
        user_name: str,
        model: str = "gpt-4",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: int = None
    ):
        """
        Trace a WhatsApp message exchange (user message + bot response).
        
        This is the main method to call for each conversation turn.
        
        Args:
            session_id: Session ID from create_session()
            user_message: The message sent by the user
            bot_response: The response from your AI agent
            phone_number: User's WhatsApp number
            user_name: User's display name (from WhatsApp profile or extracted)
            model: LLM model used
            prompt_tokens: Input tokens consumed
            completion_tokens: Output tokens generated
            latency_ms: Response time in milliseconds
        """
        response = requests.post(
            f"{self.base_url}/traces/llm",
            headers=self.headers,
            json={
                "session_id": session_id,
                "model": model,
                "input": {
                    "messages": [{"role": "user", "content": user_message}]
                },
                "output": {
                    "content": bot_response,
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens
                    }
                },
                "latency_ms": latency_ms,
                # CRITICAL: User identification fields
                "external_user_id": phone_number,
                "external_user_name": user_name,
                "external_user_channel": "whatsapp"
            }
        )
        response.raise_for_status()
    
    def trace_tool_call(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict,
        result: any,
        phone_number: str,
        user_name: str,
        latency_ms: int = None,
        agent: str = None
    ):
        """
        Trace a tool/function call during conversation.
        
        Args:
            session_id: Session ID
            tool_name: Name of the tool (e.g., "get_fuel_price")
            arguments: Tool input arguments
            result: Tool execution result
            phone_number: User's WhatsApp number
            user_name: User's display name
            latency_ms: Execution time
            agent: Agent that called the tool
        """
        response = requests.post(
            f"{self.base_url}/traces/tool",
            headers=self.headers,
            json={
                "session_id": session_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "result": result,
                "latency_ms": latency_ms,
                "agent": agent,
                "external_user_id": phone_number,
                "external_user_name": user_name,
                "external_user_channel": "whatsapp"
            }
        )
        response.raise_for_status()
    
    def trace_handoff(
        self,
        session_id: str,
        from_agent: str,
        to_agent: str,
        reason: str,
        phone_number: str,
        user_name: str
    ):
        """
        Trace an agent-to-agent handoff.
        
        Args:
            session_id: Session ID
            from_agent: Source agent name
            to_agent: Target agent name
            reason: Reason for handoff
            phone_number: User's WhatsApp number
            user_name: User's display name
        """
        response = requests.post(
            f"{self.base_url}/traces/handoff",
            headers=self.headers,
            json={
                "session_id": session_id,
                "from_agent": from_agent,
                "to_agent": to_agent,
                "reason": reason,
                "external_user_id": phone_number,
                "external_user_name": user_name,
                "external_user_channel": "whatsapp"
            }
        )
        response.raise_for_status()
    
    def trace_log(
        self,
        session_id: str,
        message: str,
        level: str = "info",
        metadata: dict = None
    ):
        """
        Log an event or status message.
        
        Args:
            session_id: Session ID
            message: Log message
            level: Log level (info, warn, error, debug)
            metadata: Additional data
        """
        response = requests.post(
            f"{self.base_url}/traces/log",
            headers=self.headers,
            json={
                "session_id": session_id,
                "level": level,
                "message": message,
                "metadata": metadata
            }
        )
        response.raise_for_status()


def process_whatsapp_webhook(webhook_data: dict, tracer: WhatsAppTracer):
    """
    Example function to process a WhatsApp webhook and trace the interaction.
    
    This simulates how you would integrate MonkAI Trace into your
    WhatsApp webhook handler.
    """
    # Extract data from webhook (structure depends on your WhatsApp provider)
    phone_number = webhook_data.get("from")  # e.g., "5521997772643"
    user_name = webhook_data.get("pushName", "Unknown")  # e.g., "Italo"
    user_message = webhook_data.get("message", "")
    
    # Create or get existing session for this user
    session_id = tracer.create_session(
        phone_number=phone_number,
        inactivity_timeout=300  # 5 minutes
    )
    
    # Your AI agent processes the message and generates a response
    # (This is where your actual AI logic would go)
    bot_response = f"Resposta para: {user_message}"
    
    # Trace the conversation turn
    tracer.trace_message(
        session_id=session_id,
        user_message=user_message,
        bot_response=bot_response,
        phone_number=phone_number,
        user_name=user_name,
        model="gpt-4",
        prompt_tokens=50,
        completion_tokens=30,
        latency_ms=450
    )
    
    print(f"✓ Traced message from {user_name} ({phone_number})")
    return bot_response


def main():
    """
    Complete example demonstrating WhatsApp integration with MonkAI Trace.
    """
    print("MonkAI Trace - WhatsApp Integration Example")
    print("=" * 55)
    
    # Initialize tracer
    tracer = WhatsAppTracer(
        tracer_token=TRACER_TOKEN,
        namespace=NAMESPACE
    )
    
    # Simulated user data (would come from WhatsApp webhook in production)
    phone = "5521997772643"
    name = "Italo"
    
    # 1. Create session
    print("\n1. Creating WhatsApp session...")
    session_id = tracer.create_session(phone_number=phone)
    print(f"   Session ID: {session_id}")
    
    # 2. Trace first message
    print("\n2. Tracing first message...")
    tracer.trace_message(
        session_id=session_id,
        user_message="Qual o preço da gasolina hoje?",
        bot_response="Vou verificar o preço atual para você.",
        phone_number=phone,
        user_name=name,
        model="gpt-4",
        prompt_tokens=12,
        completion_tokens=10,
        latency_ms=320
    )
    print("   ✓ First message traced")
    
    # 3. Trace tool call
    print("\n3. Tracing tool call...")
    tracer.trace_tool_call(
        session_id=session_id,
        tool_name="get_fuel_price",
        arguments={"fuel_type": "gasoline", "city": "São Paulo"},
        result={"price": 5.89, "currency": "BRL", "unit": "liter"},
        phone_number=phone,
        user_name=name,
        latency_ms=85,
        agent="fuel-assistant"
    )
    print("   ✓ Tool call traced")
    
    # 4. Trace follow-up message with result
    print("\n4. Tracing follow-up message...")
    tracer.trace_message(
        session_id=session_id,
        user_message="Qual o preço da gasolina hoje?",
        bot_response="O preço atual da gasolina em São Paulo é R$ 5,89 por litro.",
        phone_number=phone,
        user_name=name,
        model="gpt-4",
        prompt_tokens=45,
        completion_tokens=18,
        latency_ms=280
    )
    print("   ✓ Follow-up message traced")
    
    # 5. Trace completion log
    print("\n5. Logging conversation completion...")
    tracer.trace_log(
        session_id=session_id,
        message="WhatsApp conversation completed successfully",
        level="info",
        metadata={
            "total_turns": 2,
            "tools_used": ["get_fuel_price"],
            "user_name": name,
            "phone": phone
        }
    )
    print("   ✓ Log entry created")
    
    # Summary
    print("\n" + "=" * 55)
    print("✅ All traces sent to MonkAI!")
    print("\n📊 Dashboard will show:")
    print(f"   • User ID (green badge): {phone}")
    print(f"   • User Name (blue badge): {name}")
    print(f"   • Channel: WhatsApp")
    print("\n🔗 View at: https://monkai.app/monitoring")


if __name__ == "__main__":
    main()
