"""
Advanced example: Multi-agent handoff with MonkAI tracking
"""

import asyncio
import argparse
import os
from agents import Agent, Runner, Handoff
from monkai_trace.integrations.openai_agents import MonkAIRunHooks


async def main(token=None, namespace=None, test_mode=False):
    # Use provided token/namespace or defaults
    tracer_token = token or os.getenv("MONKAI_TEST_TOKEN") or "tk_your_token_here"
    tracer_namespace = namespace or os.getenv("MONKAI_TEST_NAMESPACE") or "multi-agent-support"
    
    # Create MonkAI tracking hooks
    hooks = MonkAIRunHooks(
        tracer_token=tracer_token,
        namespace=tracer_namespace,
        auto_upload=True,
        batch_size=5  # Upload every 5 conversations
    )
    
    # Create specialized agents
    triage_agent = Agent(
        name="Triage Agent",
        instructions="""You are a triage agent. Analyze customer requests and route them:
        - Technical issues → transfer to tech_support
        - Billing questions → transfer to billing
        - General questions → answer directly"""
    )
    
    tech_support_agent = Agent(
        name="Tech Support",
        instructions="You are a technical support specialist. Help with technical issues."
    )
    
    billing_agent = Agent(
        name="Billing Support",
        instructions="You are a billing specialist. Handle payment and invoice questions."
    )
    
    # Define handoffs
    triage_agent.handoffs = [
        Handoff(agent=tech_support_agent, description="Transfer to technical support"),
        Handoff(agent=billing_agent, description="Transfer to billing support")
    ]
    
    # Test Scenario 1: Technical Issue
    print("="*60)
    print("SCENARIO 1: Technical Issue (expects handoff)")
    print("="*60)
    
    result1 = await MonkAIRunHooks.run_with_tracking(
        triage_agent,
        "My app keeps crashing when I try to upload files",
        hooks
    )
    print(f"\nFinal Response: {result1.final_output}")
    print(f"Agent that responded: {result1.agent.name}")
    
    # Test Scenario 2: Billing Question
    print("\n" + "="*60)
    print("SCENARIO 2: Billing Question (expects handoff)")
    print("="*60)
    
    result2 = await MonkAIRunHooks.run_with_tracking(
        triage_agent,
        "I was charged twice for my subscription this month",
        hooks
    )
    print(f"\nFinal Response: {result2.final_output}")
    print(f"Agent that responded: {result2.agent.name}")
    
    # Test Scenario 3: General Question
    print("\n" + "="*60)
    print("SCENARIO 3: General Question (no handoff expected)")
    print("="*60)
    
    result3 = await MonkAIRunHooks.run_with_tracking(
        triage_agent,
        "What are your business hours?",
        hooks
    )
    print(f"\nFinal Response: {result3.final_output}")
    print(f"Agent that responded: {result3.agent.name}")
    
    print("\n" + "="*60)
    print("✅ All conversations tracked in MonkAI!")
    print("="*60)
    print("\nWhat was tracked:")
    print("- All user messages")
    print("- Agent responses")
    print("- Agent handoffs (triage → specialist)")
    print("- Token usage per agent")
    print("- Complete conversation flows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MonkAI Multi-Agent Example")
    parser.add_argument("--token", help="MonkAI tracer token")
    parser.add_argument("--namespace", help="MonkAI namespace")
    parser.add_argument("--test-mode", action="store_true", 
                       help="Run in test mode (for deterministic E2E tests)")
    args = parser.parse_args()
    
    asyncio.run(main(token=args.token, namespace=args.namespace, test_mode=args.test_mode))
