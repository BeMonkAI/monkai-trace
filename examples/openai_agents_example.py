"""
Basic example of MonkAI integration with OpenAI Agents

Recommended SDK version: monkai-trace>=0.2.6

v0.2.6+ Features:
- run_with_tracking() automatically injects include params for internal tools
- Web search sources captured from action.sources
- File search results captured automatically
- No manual configuration needed for source capture
"""

import asyncio
import argparse
import os
from agents import Agent, Runner
from monkai_trace.integrations.openai_agents import MonkAIRunHooks


async def main(token=None, namespace=None):
    # Use provided token/namespace or defaults
    tracer_token = token or os.getenv("MONKAI_TEST_TOKEN") or "tk_your_token_here"
    tracer_namespace = namespace or os.getenv("MONKAI_TEST_NAMESPACE") or "customer-support"
    
    # Create MonkAI tracking hooks
    hooks = MonkAIRunHooks(
        tracer_token=tracer_token,
        namespace=tracer_namespace,
        auto_upload=True
    )
    
    # Create your agent
    agent = Agent(
        name="Support Bot",
        instructions="You are a helpful customer support agent. Be concise and friendly."
    )
    
    # Method 1: Recommended - Using run_with_tracking() wrapper
    print("="*60)
    print("METHOD 1: Using run_with_tracking() - Recommended")
    print("="*60)
    result = await MonkAIRunHooks.run_with_tracking(
        agent,
        "I need help with my order",
        hooks
    )
    print("\nAgent Response:")
    print(result.final_output)
    print("\n✅ User message automatically captured!")
    
    # Method 2: Alternative - Using set_user_input() explicitly
    print("\n" + "="*60)
    print("METHOD 2: Using set_user_input() explicitly")
    print("="*60)
    user_message = "What's the status of my refund?"
    hooks.set_user_input(user_message)
    result2 = await Runner.run(agent, user_message, hooks=hooks)
    print("\nAgent Response:")
    print(result2.final_output)
    print("\n✅ Conversations tracked in MonkAI with full token breakdown!")
    
    # Method 3: Session Management with User ID
    print("\n" + "="*60)
    print("METHOD 3: Session Management with User ID")
    print("="*60)
    
    # Set user ID for session tracking
    hooks.set_user_id("customer-12345")
    
    print("\n📝 First message from user:")
    result3 = await MonkAIRunHooks.run_with_tracking(
        agent,
        "What are your business hours?",
        hooks
    )
    print(f"Session ID: {hooks._current_session}")
    
    print("\n📝 Follow-up message (same session):")
    result4 = await MonkAIRunHooks.run_with_tracking(
        agent,
        "And your address?",
        hooks
    )
    print(f"Session ID: {hooks._current_session}")
    print("\n✅ Both messages in same session!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MonkAI OpenAI Agents Example")
    parser.add_argument("--token", help="MonkAI tracer token")
    parser.add_argument("--namespace", help="MonkAI namespace")
    args = parser.parse_args()
    
    asyncio.run(main(token=args.token, namespace=args.namespace))
