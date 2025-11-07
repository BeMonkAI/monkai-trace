"""
Basic example of MonkAI integration with OpenAI Agents
"""

import asyncio
from agents import Agent, Runner
from monkai_trace.integrations.openai_agents import MonkAIRunHooks


async def main():
    # Create MonkAI tracking hooks
    hooks = MonkAIRunHooks(
        tracer_token="tk_your_token_here",  # Replace with your token
        namespace="customer-support",
        auto_upload=True
    )
    
    # Create your agent
    agent = Agent(
        name="Support Bot",
        instructions="You are a helpful customer support agent. Be concise and friendly."
    )
    
    # Run conversation with automatic MonkAI tracking
    result = await Runner.run(
        agent,
        "I need help with my order",
        hooks=hooks
    )
    
    print("\n" + "="*50)
    print("Agent Response:")
    print("="*50)
    print(result.final_output)
    print("\n✅ Conversation automatically tracked in MonkAI with full token breakdown!")


if __name__ == "__main__":
    asyncio.run(main())
