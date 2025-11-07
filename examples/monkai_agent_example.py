"""
Basic example of MonkAI Trace integration with MonkAI Agent
"""

from monkai_agent import Agent
from monkai_trace.integrations.monkai_agent import MonkAIAgentHooks


def main():
    # Create tracking hooks
    hooks = MonkAIAgentHooks(
        tracer_token="tk_your_token_here",  # Replace with your token
        namespace="customer-support",
        auto_upload=True
    )
    
    # Create agent with tracking
    agent = Agent(
        name="Support Bot",
        instructions="You are a helpful customer support agent. Be concise and friendly.",
        hooks=hooks
    )
    
    # Run conversation (automatically tracked)
    result = agent.run("I need help with my order #12345")
    
    print("\n" + "="*50)
    print("Agent Response:")
    print("="*50)
    print(result)
    print("\n✅ Conversation automatically tracked in MonkAI!")
    print("   View your data at: https://monkai.app/monitoring")


if __name__ == "__main__":
    main()
