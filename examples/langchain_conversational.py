"""
Example of tracking multi-turn conversations with LangChain
"""

from langchain.agents import AgentType, initialize_agent
from langchain.llms import OpenAI
from langchain.memory import ConversationBufferMemory
from langchain.tools import Tool
from monkai_trace.integrations.langchain import MonkAICallbackHandler


def get_weather(location: str) -> str:
    """Simulated weather tool."""
    return f"The weather in {location} is sunny and 72°F."


def get_time(location: str) -> str:
    """Simulated time tool."""
    return f"The current time in {location} is 3:45 PM."


def main():
    # Create MonkAI callback handler
    monkai_handler = MonkAICallbackHandler(
        tracer_token="tk_your_token_here",  # Replace with your token
        namespace="customer-support",
        agent_name="Support Bot",
        auto_upload=True
    )
    
    # Create tools
    tools = [
        Tool(
            name="Weather",
            func=get_weather,
            description="Get weather information for a location"
        ),
        Tool(
            name="Time",
            func=get_time,
            description="Get current time for a location"
        )
    ]
    
    # Create agent with memory
    llm = OpenAI(temperature=0)
    memory = ConversationBufferMemory(memory_key="chat_history")
    
    agent = initialize_agent(
        tools,
        llm,
        agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
        memory=memory,
        callbacks=[monkai_handler],
        verbose=True
    )
    
    # Multi-turn conversation
    print("="*50)
    print("Multi-turn Conversation")
    print("="*50)
    
    conversations = [
        "What's the weather in San Francisco?",
        "And what time is it there?",
        "Thanks! Is it usually this nice there?"
    ]
    
    for user_input in conversations:
        print(f"\n👤 User: {user_input}")
        response = agent.run(user_input)
        print(f"🤖 Agent: {response}")
    
    print("\n✅ All conversations tracked in MonkAI with:")
    print("   - Same session ID for conversation continuity")
    print("   - Tool calls logged")
    print("   - Token breakdown per interaction")
    
    # Flush and start new session
    monkai_handler.flush()
    monkai_handler.reset_session()  # New conversation will get new session ID


if __name__ == "__main__":
    main()
