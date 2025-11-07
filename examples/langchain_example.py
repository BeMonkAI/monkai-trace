"""
Basic example of MonkAI integration with LangChain
"""

from langchain.agents import AgentType, initialize_agent, load_tools
from langchain.llms import OpenAI
from monkai_trace.integrations.langchain import MonkAICallbackHandler


def main():
    # Create MonkAI callback handler
    monkai_handler = MonkAICallbackHandler(
        tracer_token="tk_your_token_here",  # Replace with your token
        namespace="langchain-demo",
        agent_name="Research Assistant",
        auto_upload=True
    )
    
    # Initialize LangChain components
    llm = OpenAI(temperature=0)
    tools = load_tools(["serpapi", "llm-math"], llm=llm)
    
    # Create agent with MonkAI tracking
    agent = initialize_agent(
        tools,
        llm,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        callbacks=[monkai_handler],  # Add MonkAI handler
        verbose=True
    )
    
    # Run agent - automatically tracked in MonkAI
    result = agent.run(
        "What is the population of Tokyo and what is 20% of that number?"
    )
    
    print("\n" + "="*50)
    print("Agent Response:")
    print("="*50)
    print(result)
    print("\n✅ Conversation automatically tracked in MonkAI!")
    print("   - Token usage breakdown (input/output/process)")
    print("   - Tool calls logged")
    print("   - Full conversation flow")
    
    # Ensure all records are uploaded
    monkai_handler.flush()


if __name__ == "__main__":
    main()
