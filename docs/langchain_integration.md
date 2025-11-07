# LangChain Integration Guide

This guide shows you how to integrate MonkAI Trace with LangChain to automatically track your agent conversations, tool calls, and token usage.

## Overview

The `MonkAICallbackHandler` is a LangChain callback handler that automatically captures:
- 📊 **Token Usage**: Input, output, and process tokens with automatic breakdown
- 🔧 **Tool Calls**: Every tool execution is logged with inputs and outputs
- 💬 **Conversations**: Full conversation history with session tracking
- 🔄 **Agent Actions**: Decision-making process and reasoning steps

## Installation

```bash
pip install monkai-trace langchain
```

> **Note:** LangChain is an optional dependency. You can install `monkai-trace` without it, and the integration will only be available when LangChain is installed.

## Quick Start

### Basic Agent Tracking

```python
from langchain.agents import AgentType, initialize_agent, load_tools
from langchain.llms import OpenAI
from monkai_trace.integrations.langchain import MonkAICallbackHandler

# Create MonkAI callback handler
monkai_handler = MonkAICallbackHandler(
    tracer_token="tk_your_token_here",
    namespace="my-agents",
    agent_name="Research Assistant",
    auto_upload=True
)

# Initialize your LangChain agent
llm = OpenAI(temperature=0)
tools = load_tools(["serpapi", "llm-math"], llm=llm)

agent = initialize_agent(
    tools,
    llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    callbacks=[monkai_handler]  # Add MonkAI handler here
)

# Run agent - automatically tracked!
result = agent.run("What is the population of Tokyo?")

# Ensure all records are uploaded
monkai_handler.flush()
```

That's it! Every agent interaction is now tracked in MonkAI.

## Configuration Options

### Handler Parameters

```python
MonkAICallbackHandler(
    tracer_token: str,           # Your MonkAI tracer token (required)
    namespace: str,              # Namespace for organizing data (required)
    agent_name: str = "langchain-agent",  # Name for your agent
    auto_upload: bool = True,    # Auto-upload records when batch is full
    batch_size: int = 10,        # Number of records before auto-upload
    estimate_tokens: bool = True # Estimate tokens for tool calls
)
```

### Token Tracking

MonkAI automatically tracks four types of tokens:

- **Input Tokens**: Tokens from user prompts and system messages
- **Output Tokens**: Tokens from LLM responses
- **Process Tokens**: Tokens used in tool execution and processing
- **Total Tokens**: Sum of all token types

If your LLM provides actual token usage, MonkAI will use those values. Otherwise, it estimates tokens using the rule: ~4 characters = 1 token.

## Usage Examples

### Multi-Turn Conversations

Track conversations across multiple interactions with session continuity:

```python
from langchain.memory import ConversationBufferMemory
from monkai_trace.integrations.langchain import MonkAICallbackHandler

monkai_handler = MonkAICallbackHandler(
    tracer_token="tk_your_token_here",
    namespace="customer-support",
    agent_name="Support Bot"
)

# Create agent with memory
memory = ConversationBufferMemory(memory_key="chat_history")
agent = initialize_agent(
    tools,
    llm,
    agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
    memory=memory,
    callbacks=[monkai_handler]
)

# All interactions share the same session ID
agent.run("What's the weather in SF?")
agent.run("And what time is it there?")
agent.run("Thanks!")

# Start a new conversation with new session ID
monkai_handler.reset_session()
agent.run("Hello again!")
```

### Custom Tools

MonkAI tracks all tool calls, including custom tools:

```python
from langchain.tools import Tool

def custom_calculator(input_str: str) -> str:
    """Custom calculation logic"""
    return str(eval(input_str))

tools = [
    Tool(
        name="Calculator",
        func=custom_calculator,
        description="Performs calculations"
    )
]

agent = initialize_agent(
    tools,
    llm,
    callbacks=[monkai_handler]
)

# Tool calls are automatically logged
result = agent.run("What is 25 * 4 + 10?")
```

### Different LangChain Chains

MonkAI works with any LangChain component that supports callbacks:

```python
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate

# Simple LLM Chain
prompt = PromptTemplate(
    input_variables=["topic"],
    template="Write a short poem about {topic}"
)

chain = LLMChain(llm=llm, prompt=prompt)

# Track chain execution
result = chain.run(topic="AI", callbacks=[monkai_handler])
```

## Manual Record Management

### Flushing Records

If `auto_upload=False` or you want to ensure all records are uploaded:

```python
# Upload any buffered records
monkai_handler.flush()
```

### Session Management

Control session IDs for organizing conversations:

```python
# Get current session ID
session_id = monkai_handler._get_or_create_session_id()

# Start a new conversation with new session ID
monkai_handler.reset_session()

# Next interaction will have a different session ID
agent.run("Hello!")
```

## Viewing Your Data

After running your agents:

1. Go to [MonkAI Monitoring](https://app.monkai.ai/monitoring)
2. Select your namespace
3. View conversations, token usage, and tool calls

You'll see:
- 📊 Token breakdown (input/output/process/total)
- 🔧 Tool call logs with inputs and outputs
- 💬 Full conversation history
- 📈 Performance metrics over time

## Token Segmentation

MonkAI provides detailed token breakdown:

| Token Type | What It Tracks |
|------------|----------------|
| Input | User prompts, system messages, context |
| Output | LLM responses, agent outputs |
| Process | Tool execution, chain processing |
| Memory | *(Not used in LangChain integration)* |
| Total | Sum of all tokens |

## Best Practices

1. **Use Descriptive Agent Names**: Makes it easier to identify agents in MonkAI
   ```python
   agent_name="Customer-Support-Bot-v2"
   ```

2. **Organize with Namespaces**: Group related agents together
   ```python
   namespace="production-support"
   ```

3. **Reset Sessions Between Users**: Keep user conversations separate
   ```python
   # After each user session
   monkai_handler.reset_session()
   ```

4. **Flush Before Exit**: Ensure all data is uploaded
   ```python
   try:
       agent.run(user_input)
   finally:
       monkai_handler.flush()
   ```

5. **Monitor Auto-Upload**: For high-volume agents, adjust batch size
   ```python
   # Upload more frequently
   MonkAICallbackHandler(batch_size=5)
   ```

## Advanced Configuration

### Disable Token Estimation

If you only want actual token counts from the LLM:

```python
monkai_handler = MonkAICallbackHandler(
    tracer_token="tk_your_token_here",
    namespace="my-namespace",
    estimate_tokens=False  # Only use actual token counts
)
```

### Manual Upload Mode

For full control over when records are uploaded:

```python
monkai_handler = MonkAICallbackHandler(
    tracer_token="tk_your_token_here",
    namespace="my-namespace",
    auto_upload=False
)

# Records accumulate in memory
agent.run("Question 1")
agent.run("Question 2")

# Upload when ready
monkai_handler.flush()
```

## Troubleshooting

### No Data Appearing in MonkAI?

1. **Check your tracer token**: Ensure it starts with `tk_` and is valid
2. **Call flush()**: Records may be buffered
   ```python
   monkai_handler.flush()
   ```
3. **Verify namespace**: Make sure you're looking at the correct namespace in MonkAI

### Token Counts Seem Off?

- LangChain doesn't always provide token usage in `llm_output`
- MonkAI falls back to estimation (~4 chars = 1 token)
- For accurate counts, use LLMs that report token usage (like OpenAI)

### Tool Calls Not Showing?

- Ensure you're using LangChain agents (not just chains)
- Tool calls are tracked via `on_agent_action` and `on_tool_start/end`

## Integration with Other MonkAI Features

### Combine with Python Logging

Track both agent activity and application logs:

```python
import logging
from monkai_trace.integrations.langchain import MonkAICallbackHandler
from monkai_trace.integrations.logging import MonkAILogHandler

# Set up logging
logger = logging.getLogger(__name__)
logger.addHandler(MonkAILogHandler(
    tracer_token="tk_your_token_here",
    namespace="my-namespace"
))

# Set up agent tracking
monkai_handler = MonkAICallbackHandler(
    tracer_token="tk_your_token_here",
    namespace="my-namespace"
)

# Both logs and agent data go to same namespace
logger.info("Starting agent execution")
result = agent.run("Question", callbacks=[monkai_handler])
logger.info(f"Agent completed: {result}")
```

## Next Steps

- [View API Reference](api_reference.md)
- [Learn about OpenAI Agents Integration](openai_agents_integration.md)
- [Explore Python Logging Integration](logging_integration.md)

## Support

Need help?
- 📧 Email: support@monkai.ai
- 💬 Discord: [Join our community](#)
- 📖 Docs: [Full documentation](https://docs.monkai.ai)
