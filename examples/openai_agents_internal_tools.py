#!/usr/bin/env python3
"""
Example: OpenAI Agents with Internal Tools (web_search, file_search, code_interpreter)

This example demonstrates how MonkAI automatically captures OpenAI's built-in
internal tools that don't trigger regular on_tool_start/on_tool_end hooks.

Supported internal tools:
- web_search_call: Web search queries and results
- file_search_call: File/document search
- code_interpreter_call: Code execution
- computer_call: Computer use actions

Requirements:
    pip install monkai-trace openai-agents-python

Usage:
    python openai_agents_internal_tools.py --token tk_your_token --namespace my-agent
"""

import asyncio
import argparse
import os

from agents import Agent, Runner

from monkai_trace.integrations.openai_agents import MonkAIRunHooks


async def main(token: str, namespace: str):
    """Demonstrate internal tools capture with MonkAI tracking."""
    
    # Initialize MonkAI hooks
    hooks = MonkAIRunHooks(
        tracer_token=token,
        namespace=namespace,
        auto_upload=True,
        batch_size=1  # Upload immediately for demo
    )
    
    print("=" * 60)
    print("MonkAI Internal Tools Capture Demo")
    print("=" * 60)
    
    # ==========================================================
    # Example 1: Agent with Web Search
    # ==========================================================
    print("\n📍 Example 1: Web Search Agent")
    print("-" * 40)
    
    # Create an agent with web search enabled
    # Note: Requires OpenAI API key with web search access
    web_search_agent = Agent(
        name="Research Assistant",
        instructions="""You are a research assistant that helps users find 
        current information using web search. When asked about recent events,
        news, or current data, use your web search capability to find accurate,
        up-to-date information. Always cite your sources.""",
        # Web search is enabled via model capabilities or tools parameter
        # depending on your OpenAI API access
    )
    
    try:
        # Run with tracking - MonkAI will capture any web_search_call from raw_items
        result = await MonkAIRunHooks.run_with_tracking(
            web_search_agent,
            "What are the latest developments in AI agents as of today?",
            hooks
        )
        print(f"✅ Response: {str(result.final_output)[:200]}...")
    except Exception as e:
        print(f"⚠️ Web search example skipped: {e}")
        print("   (Web search requires specific OpenAI API access)")
    
    # ==========================================================
    # Example 2: Agent with Code Interpreter
    # ==========================================================
    print("\n📍 Example 2: Code Interpreter Agent")
    print("-" * 40)
    
    code_agent = Agent(
        name="Data Analyst",
        instructions="""You are a data analyst that can write and execute Python code
        to analyze data, create visualizations, and perform calculations.
        When asked to compute something, write the code and execute it.""",
        # Code interpreter is enabled via model capabilities
    )
    
    try:
        result = await MonkAIRunHooks.run_with_tracking(
            code_agent,
            "Calculate the first 10 Fibonacci numbers and show me the result",
            hooks
        )
        print(f"✅ Response: {str(result.final_output)[:200]}...")
    except Exception as e:
        print(f"⚠️ Code interpreter example skipped: {e}")
        print("   (Code interpreter requires specific OpenAI API access)")
    
    # ==========================================================
    # Example 3: Agent with File Search
    # ==========================================================
    print("\n📍 Example 3: File Search Agent")
    print("-" * 40)
    
    file_search_agent = Agent(
        name="Document Assistant",
        instructions="""You are a document assistant that can search through
        uploaded files and documents to find relevant information.
        When asked about document content, use file search to find answers.""",
        # File search requires vector store setup
    )
    
    try:
        result = await MonkAIRunHooks.run_with_tracking(
            file_search_agent,
            "Search my documents for information about project deadlines",
            hooks
        )
        print(f"✅ Response: {str(result.final_output)[:200]}...")
    except Exception as e:
        print(f"⚠️ File search example skipped: {e}")
        print("   (File search requires vector store configuration)")
    
    # ==========================================================
    # Example 4: Multi-tool Agent
    # ==========================================================
    print("\n📍 Example 4: Multi-tool Research Agent")
    print("-" * 40)
    
    multi_tool_agent = Agent(
        name="Research Analyst",
        instructions="""You are a research analyst with access to multiple tools:
        - Web search for current information
        - Code interpreter for data analysis
        - File search for document retrieval
        
        Use the appropriate tool(s) based on the user's request.
        Combine information from multiple sources when helpful.""",
    )
    
    try:
        result = await MonkAIRunHooks.run_with_tracking(
            multi_tool_agent,
            "What's the current stock price of NVIDIA and calculate its year-to-date percentage change?",
            hooks
        )
        print(f"✅ Response: {str(result.final_output)[:200]}...")
    except Exception as e:
        print(f"⚠️ Multi-tool example skipped: {e}")
    
    # ==========================================================
    # Summary
    # ==========================================================
    print("\n" + "=" * 60)
    print("📊 MonkAI Tracking Summary")
    print("=" * 60)
    print(f"""
Internal tools captured by MonkAI are automatically extracted from
the response's raw_items field. These include:

• web_search_call  → Query, sources, results
• file_search_call → Query, file IDs, matches  
• code_interpreter_call → Code, language, output
• computer_call → Action type, output

Check your MonkAI dashboard to see the captured internal tools
displayed alongside your custom tools in the Conversations panel.

Dashboard: https://monkai.com.br/dashboard/monitoring
Namespace: {namespace}
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Demo: OpenAI Agents with Internal Tools + MonkAI Tracking"
    )
    parser.add_argument(
        "--token",
        default=os.getenv("MONKAI_TOKEN", ""),
        help="MonkAI tracer token (or set MONKAI_TOKEN env var)"
    )
    parser.add_argument(
        "--namespace",
        default=os.getenv("MONKAI_NAMESPACE", "internal-tools-demo"),
        help="MonkAI namespace (or set MONKAI_NAMESPACE env var)"
    )
    
    args = parser.parse_args()
    
    if not args.token:
        print("❌ Error: MonkAI token required")
        print("   Use --token or set MONKAI_TOKEN environment variable")
        exit(1)
    
    asyncio.run(main(args.token, args.namespace))
