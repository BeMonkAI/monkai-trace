"""
Custom Timeout Configuration Examples
Shows how to configure different timeouts for different use cases
"""

import asyncio
from agents import Agent
from monkai_trace.integrations.openai_agents import MonkAIRunHooks


async def quick_support_chat():
    """Quick customer support - 1 minute timeout"""
    print("\n" + "="*70)
    print("USE CASE 1: Quick Support Chat (1 minute timeout)")
    print("="*70)
    
    hooks = MonkAIRunHooks(
        tracer_token="tk_demo",
        namespace="quick-support",
        inactivity_timeout=60  # 1 minute
    )
    
    agent = Agent(
        name="Quick Support",
        instructions="Provide quick answers."
    )
    
    hooks.set_user_id("user-quick")
    
    print("\n📝 Message 1:")
    await MonkAIRunHooks.run_with_tracking(agent, "Quick question", hooks)
    print(f"Session: {hooks._current_session}")
    
    print("\n⏳ Waiting 30 seconds...")
    await asyncio.sleep(30)
    
    print("\n📝 Message 2 (still within 1min):")
    await MonkAIRunHooks.run_with_tracking(agent, "Follow up", hooks)
    print(f"Session: {hooks._current_session}")
    print("✅ Same session (within 1 minute)")


async def long_running_analysis():
    """Long-running analysis - 10 minute timeout"""
    print("\n" + "="*70)
    print("USE CASE 2: Long-running Analysis (10 minute timeout)")
    print("="*70)
    
    hooks = MonkAIRunHooks(
        tracer_token="tk_demo",
        namespace="data-analysis",
        inactivity_timeout=600  # 10 minutes
    )
    
    agent = Agent(
        name="Data Analyst",
        instructions="Perform detailed analysis."
    )
    
    hooks.set_user_id("analyst-001")
    
    print("\n📝 Start analysis:")
    await MonkAIRunHooks.run_with_tracking(
        agent,
        "Analyze dataset X",
        hooks
    )
    print(f"Session: {hooks._current_session}")
    
    print("\n⏳ User reviews results for 5 minutes...")
    await asyncio.sleep(5)  # Simulate 5 min in demo
    
    print("\n📝 Request modifications:")
    await MonkAIRunHooks.run_with_tracking(
        agent,
        "Can you also show Y?",
        hooks
    )
    print(f"Session: {hooks._current_session}")
    print("✅ Same session (10min timeout allows long pauses)")


async def real_time_chat():
    """Real-time chat - 30 second timeout"""
    print("\n" + "="*70)
    print("USE CASE 3: Real-time Chat (30 second timeout)")
    print("="*70)
    
    hooks = MonkAIRunHooks(
        tracer_token="tk_demo",
        namespace="live-chat",
        inactivity_timeout=30  # 30 seconds
    )
    
    agent = Agent(
        name="Chat Bot",
        instructions="Engage in real-time conversation."
    )
    
    hooks.set_user_id("chat-user-123")
    
    messages = [
        "Hi!",
        "How's the weather?",
        "Tell me a joke",
        "Thanks!"
    ]
    
    for i, msg in enumerate(messages, 1):
        print(f"\n📝 Message {i}: {msg}")
        await MonkAIRunHooks.run_with_tracking(agent, msg, hooks)
        print(f"Session: {hooks._current_session}")
        
        if i < len(messages):
            await asyncio.sleep(5)  # Quick responses
    
    print("\n✅ All messages in same session (rapid-fire chat)")


async def main():
    print("\n🚀 Custom Timeout Configuration Examples")
    print("Different timeouts for different use cases\n")
    
    await quick_support_chat()
    await long_running_analysis()
    await real_time_chat()
    
    print("\n" + "="*70)
    print("✅ All timeout scenarios completed!")
    print("="*70)
    
    print("\n💡 Summary:")
    print("  - Quick support: 60s timeout")
    print("  - Long analysis: 600s timeout")
    print("  - Real-time chat: 30s timeout")
    print("  - Choose based on your use case!")


if __name__ == "__main__":
    asyncio.run(main())
