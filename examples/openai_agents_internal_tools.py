#!/usr/bin/env python3
"""
Example: OpenAI Agents with Internal Tools (web_search, file_search, code_interpreter)

This example demonstrates how MonkAI automatically captures OpenAI's built-in
internal tools that don't trigger regular on_tool_start/on_tool_end hooks.

⚠️ IMPORTANT - SDK v0.2.4+ BREAKING CHANGE:
    run_with_tracking() is now REQUIRED and ASYNC to capture internal tools.
    
    Using Runner.run() directly will NOT capture internal tools because
    the on_agent_end hook only receives final_output (a string), NOT the
    complete RunResult containing new_items/raw_responses where internal
    tools are stored.

✅ FIXED in v0.2.10 - INTERNAL TOOLS NOW WORK WITH batch_size=1:
    v0.2.9 had a bug where on_agent_end flushed BEFORE internal tools were captured.
    
    v0.2.10 fixes this with:
    - _skip_auto_flush flag to prevent premature flush
    - _serialize_to_dict() to handle Pydantic objects (ActionSearchSource, etc.)
    - Proper execution order: capture → flush

✅ FIXED in v0.2.7 - SOURCES CAPTURED VIA RunConfig:
    RunConfig(
        model_settings=ModelSettings(
            response_include=["web_search_call.action.sources", "file_search_call.results"]
        )
    )

⚠️ NOTE: v0.2.5-v0.2.9 have various issues. Use v0.2.10+.

Supported internal tools:
- web_search_call: Web search queries and results (sources from action.sources)
- file_search_call: File/document search (results via include param)
- code_interpreter_call: Code execution
- computer_call: Computer use actions

Requirements:
    pip install monkai-trace>=0.2.10 openai-agents-python

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
    print("MonkAI Internal Tools Capture Demo (SDK v0.2.10+)")
    print("=" * 60)
    
    # ==========================================================
    # FIXED in v0.2.10: batch_size=1 now works correctly
    # ==========================================================
    print("\n📍 FIXED: Internal Tools with batch_size=1 (v0.2.10+)")
    print("-" * 40)
    print("""
v0.2.9 had a bug where on_agent_end would flush BEFORE internal tools
were captured when using batch_size=1.

v0.2.10 fixes this with:
1. _skip_auto_flush flag prevents premature flush in run_with_tracking()
2. _serialize_to_dict() handles Pydantic objects (ActionSearchSource)
3. Correct order: capture internal tools → then flush

batch_size=1 is now RECOMMENDED for real-time monitoring!

Sources are captured via RunConfig.model_settings.response_include
(automatically handled by run_with_tracking()).

⚠️ Note: v0.2.5-v0.2.9 have various issues. Use v0.2.10+.
""")
    
    # ==========================================================
    # CRITICAL: Why run_with_tracking() is REQUIRED (v0.2.4+)
    # ==========================================================
    print("\n📋 Why run_with_tracking() is required")
    print("-" * 40)
    print("""
Internal tools (web_search, file_search, etc.) are ONLY available
in the complete RunResult object returned by Runner.run().

The on_agent_end hook only receives the final_output (a string),
NOT the full RunResult with new_items/raw_responses.

Therefore, run_with_tracking() is REQUIRED to capture internal tools.
It runs the agent and then extracts tools from the complete result.

❌ DON'T do this (internal tools will NOT be captured):
   result = await Runner.run(agent, "query", hooks=hooks)

✅ DO this instead (internal tools WILL be captured):
   result = await MonkAIRunHooks.run_with_tracking(agent, "query", hooks)
""")
    
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
        # ✅ CORRECT: Use run_with_tracking to capture web_search_call
        # This is REQUIRED for internal tools - Runner.run() won't work!
        result = await MonkAIRunHooks.run_with_tracking(
            web_search_agent,
            "What are the latest developments in AI agents as of today?",
            hooks
        )
        print(f"✅ Response: {str(result.final_output)[:200]}...")
        print("   Check debug output above for '_capture_internal_tools_from_result' messages")
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
        # ✅ CORRECT: Use run_with_tracking to capture code_interpreter_call
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
        # ✅ CORRECT: Use run_with_tracking to capture file_search_call
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
        # ✅ CORRECT: Use run_with_tracking to capture ALL internal tools
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
    print("📊 MonkAI Tracking Summary (SDK v0.2.10+)")
    print("=" * 60)
    print(f"""
BREAKING CHANGE in v0.2.4:
• run_with_tracking() is now ASYNC (must use await)
• run_with_tracking() is REQUIRED for internal tools capture

FIXED in v0.2.10:
• batch_size=1 now works correctly (recommended for real-time)
• Internal tools captured BEFORE flush via _skip_auto_flush flag
• Sources properly serialized via _serialize_to_dict()
• Fixed: "Object of type ActionSearchSource is not JSON serializable"

FIXED in v0.2.7:
• Include params passed via RunConfig.model_settings.response_include
• Sources captured from action.sources

Technical reason:
• on_agent_end hook only receives final_output (string)
• Internal tools are in RunResult.new_items and raw_responses
• run_with_tracking() captures the complete RunResult

Internal tools captured by MonkAI:
• web_search_call  → Query, sources (with URLs/titles), results
• file_search_call → Query, file IDs, matches
• code_interpreter_call → Code, language, output
• computer_call → Action type, output

Dashboard: https://monkai.com.br/dashboard/monitoring
Namespace: {namespace}
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Demo: OpenAI Agents with Internal Tools + MonkAI Tracking (v0.2.10+)"
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
