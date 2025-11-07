"""
Example of tracking multi-agent handoffs with MonkAI
"""

import asyncio
from agents import Agent, Runner
from monkai_trace.integrations.openai_agents import MonkAIRunHooks


async def main():
    # MonkAI hooks will track all handoffs
    hooks = MonkAIRunHooks(
        tracer_token="tk_your_token_here",  # Replace with your token
        namespace="support-triage"
    )
    
    # Create specialized agents
    billing_agent = Agent(
        name="Billing Agent",
        handoff_description="Handles billing and payment questions",
        instructions="You help with billing issues. Be clear about payment terms."
    )
    
    technical_agent = Agent(
        name="Technical Agent",
        handoff_description="Handles technical support questions",
        instructions="You provide technical support. Debug issues step by step."
    )
    
    # Triage agent can hand off to specialists
    triage_agent = Agent(
        name="Triage Agent",
        instructions="Route users to the right specialist agent.",
        handoffs=[billing_agent, technical_agent]
    )
    
    # Run with tracking
    result = await Runner.run(
        triage_agent,
        "I was charged twice for my subscription",
        hooks=hooks
    )
    
    print("\n" + "="*50)
    print("Agent Response:")
    print("="*50)
    print(result.final_output)
    print("\n✅ MonkAI dashboard will show:")
    print("   - Triage Agent → Billing Agent handoff")
    print("   - Token usage per agent")
    print("   - Full conversation flow")


if __name__ == "__main__":
    asyncio.run(main())
