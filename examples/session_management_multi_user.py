"""
Multi-User Session Management Example
Simulates multiple users interacting with the same agent simultaneously
"""

import asyncio
from agents import Agent, Runner
from monkai_trace.integrations.openai_agents import MonkAIRunHooks


class CustomerSupportBot:
    """Simulates a customer support bot handling multiple users"""
    
    def __init__(self, tracer_token: str):
        self.hooks = MonkAIRunHooks(
            tracer_token=tracer_token,
            namespace="customer-support",
            inactivity_timeout=120  # 2 minutes
        )
        
        self.agent = Agent(
            name="Support Bot",
            instructions="You are a customer support agent. Be helpful and concise."
        )
    
    async def handle_message(self, user_id: str, message: str):
        """Handle message from a specific user"""
        # Set user ID to ensure session isolation
        self.hooks.set_user_id(user_id)
        
        # Get session info
        session_info = self.hooks.session_manager.get_session_info(user_id)
        
        print(f"\n{'='*60}")
        print(f"👤 User: {user_id}")
        print(f"💬 Message: {message}")
        
        if session_info:
            print(f"📋 Session: {session_info['session_id']}")
            print(f"⏱️  Duration: {int(session_info['duration'])}s")
            print(f"💤 Inactive: {int(session_info['inactive_for'])}s")
        
        # Process message
        result = await MonkAIRunHooks.run_with_tracking(
            self.agent,
            message,
            self.hooks
        )
        
        print(f"🤖 Response: {result.final_output[:80]}...")
        print(f"{'='*60}")


async def simulate_whatsapp_scenario():
    """Simulates WhatsApp bot with multiple concurrent users"""
    print("\n🚀 Simulating WhatsApp Bot with Multiple Users\n")
    
    bot = CustomerSupportBot(tracer_token="tk_demo")
    
    # Simulate interleaved messages from different users
    print("⏰ T=0s: User A starts conversation")
    await bot.handle_message("whatsapp-5511999999999", "Hi, I need help")
    
    await asyncio.sleep(2)
    
    print("\n⏰ T=2s: User B starts (different session)")
    await bot.handle_message("whatsapp-5511888888888", "Hello there")
    
    await asyncio.sleep(3)
    
    print("\n⏰ T=5s: User A continues (same session)")
    await bot.handle_message("whatsapp-5511999999999", "What's the status of order #123?")
    
    await asyncio.sleep(2)
    
    print("\n⏰ T=7s: User C joins (new session)")
    await bot.handle_message("whatsapp-5511777777777", "I have a question")
    
    await asyncio.sleep(3)
    
    print("\n⏰ T=10s: User B continues (same session)")
    await bot.handle_message("whatsapp-5511888888888", "Can you help me with a refund?")
    
    print("\n✅ Result: 3 users, 3 separate sessions, 5 messages total")


async def simulate_session_handoff():
    """Simulates session persistence across agent restarts"""
    print("\n🚀 Simulating Session Persistence\n")
    
    # Create bot instance
    bot1 = CustomerSupportBot(tracer_token="tk_demo")
    
    print("📝 User sends first message:")
    await bot1.handle_message("user-persistence-test", "I need help with billing")
    
    await asyncio.sleep(5)
    
    print("\n🔄 Bot restarts (new instance, same user):")
    bot2 = CustomerSupportBot(tracer_token="tk_demo")  # New instance
    
    print("\n📝 User continues conversation:")
    await bot2.handle_message("user-persistence-test", "What's my current balance?")
    
    print("\n✅ Session persists across bot restarts (within timeout)")


async def main():
    print("\n" + "="*70)
    print("MULTI-USER SESSION MANAGEMENT EXAMPLES")
    print("="*70)
    
    await simulate_whatsapp_scenario()
    
    print("\n" + "="*70)
    
    await simulate_session_handoff()
    
    print("\n" + "="*70)
    print("✅ All multi-user scenarios completed!")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
