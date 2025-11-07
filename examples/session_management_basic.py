"""
Basic Session Management Examples
Demonstrates automatic session creation and timeout behavior
"""

import asyncio
import time
from agents import Agent, Runner
from monkai_trace.integrations.openai_agents import MonkAIRunHooks


async def scenario_1_automatic_session():
    """Scenario 1: Automatic session creation (no user_id provided)"""
    print("\n" + "="*70)
    print("SCENARIO 1: Automatic Session Creation")
    print("="*70)
    
    hooks = MonkAIRunHooks(
        tracer_token="tk_demo",
        namespace="demo",
        inactivity_timeout=120  # 2 minutes
    )
    
    agent = Agent(
        name="Support Bot",
        instructions="You are helpful."
    )
    
    # First message - creates automatic session
    print("\n📝 First message (no user_id set):")
    result1 = await MonkAIRunHooks.run_with_tracking(agent, "Hello", hooks)
    print(f"Session ID: {hooks._current_session}")
    print(f"User ID: anonymous (default)")
    
    # Second message - reuses same session
    print("\n📝 Second message (within timeout):")
    result2 = await MonkAIRunHooks.run_with_tracking(agent, "How are you?", hooks)
    print(f"Session ID: {hooks._current_session}")
    print("✅ Same session reused!")


async def scenario_2_session_timeout():
    """Scenario 2: Session expires after timeout"""
    print("\n" + "="*70)
    print("SCENARIO 2: Session Timeout (1 second for demo)")
    print("="*70)
    
    hooks = MonkAIRunHooks(
        tracer_token="tk_demo",
        namespace="demo",
        inactivity_timeout=1  # 1 second for demo
    )
    
    agent = Agent(name="Support Bot", instructions="You are helpful.")
    
    hooks.set_user_id("user-123")
    
    # First message
    print("\n📝 First message:")
    await MonkAIRunHooks.run_with_tracking(agent, "Hello", hooks)
    session1 = hooks._current_session
    print(f"Session ID: {session1}")
    
    # Wait for timeout
    print("\n⏳ Waiting 2 seconds (timeout: 1 second)...")
    await asyncio.sleep(2)
    
    # Second message - new session created
    print("\n📝 Second message (after timeout):")
    await MonkAIRunHooks.run_with_tracking(agent, "Hello again", hooks)
    session2 = hooks._current_session
    print(f"Session ID: {session2}")
    
    if session1 != session2:
        print("✅ New session created after timeout!")
    else:
        print("❌ Error: Should have created new session")


async def scenario_3_continuous_conversation():
    """Scenario 3: Continuous conversation maintains session"""
    print("\n" + "="*70)
    print("SCENARIO 3: Continuous Conversation (Same Session)")
    print("="*70)
    
    hooks = MonkAIRunHooks(
        tracer_token="tk_demo",
        namespace="demo",
        inactivity_timeout=120  # 2 minutes
    )
    
    agent = Agent(name="Support Bot", instructions="You are helpful.")
    
    hooks.set_user_id("customer-456")
    
    print("\n📝 Message 1:")
    await MonkAIRunHooks.run_with_tracking(agent, "Hi", hooks)
    session = hooks._current_session
    print(f"Session: {session}")
    
    print("\n📝 Message 2 (10 seconds later):")
    await asyncio.sleep(10)
    await MonkAIRunHooks.run_with_tracking(agent, "What's the weather?", hooks)
    print(f"Session: {hooks._current_session}")
    
    print("\n📝 Message 3 (20 seconds later):")
    await asyncio.sleep(20)
    await MonkAIRunHooks.run_with_tracking(agent, "Thanks!", hooks)
    print(f"Session: {hooks._current_session}")
    
    print("\n✅ All messages in same session (within 2min timeout)")


async def main():
    print("\n🚀 MonkAI Session Management Examples")
    print("These examples demonstrate automatic session handling\n")
    
    await scenario_1_automatic_session()
    await scenario_2_session_timeout()
    await scenario_3_continuous_conversation()
    
    print("\n" + "="*70)
    print("✅ All scenarios completed!")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
