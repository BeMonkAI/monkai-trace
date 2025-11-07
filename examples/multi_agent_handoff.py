"""
Example of tracking multi-agent handoffs with MonkAI Agent
"""

from monkai_agent import Agent
from monkai_trace.integrations.monkai_agent import MonkAIAgentHooks


def main():
    # Shared hooks for all agents
    hooks = MonkAIAgentHooks(
        tracer_token="tk_your_token_here",  # Replace with your token
        namespace="support-triage"
    )
    
    # Create specialized agents
    billing_agent = Agent(
        name="Billing Agent",
        instructions="You help with billing and payment questions.",
        hooks=hooks
    )
    
    technical_agent = Agent(
        name="Technical Agent",
        instructions="You provide technical support.",
        hooks=hooks
    )
    
    # Triage agent with handoff capability
    triage_agent = Agent(
        name="Triage Agent",
        instructions="Route users to the right specialist agent.",
        handoffs=[billing_agent, technical_agent],
        hooks=hooks
    )
    
    # Run with automatic handoff tracking
    result = triage_agent.run("I was charged twice for my subscription")
    
    print("\n" + "="*50)
    print("Agent Response:")
    print("="*50)
    print(result)
    print("\n✅ MonkAI dashboard will show:")
    print("   - Triage Agent → Billing Agent handoff")
    print("   - Token usage per agent")
    print("   - Full conversation flow")
    print("   View at: https://monkai.app/monitoring")


if __name__ == "__main__":
    main()
