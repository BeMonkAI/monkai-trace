# MonkAI + OpenAI Agents Integration

This guide shows how to integrate MonkAI tracking into OpenAI Agents applications.

## Installation

```bash
pip install monkai-trace
pip install openai-agents-python
```

> **Compatibility:** This integration is compatible with the latest version of `openai-agents-python` and uses the updated `agents.run_context` module for run context management.

## Quick Start

⚠️ **IMPORTANT:** To ensure the initial user message is captured, use one of the following methods:

### Method 1: Wrapper Convenience (Recommended)

```python
import asyncio
from agents import Agent
from monkai_trace.integrations.openai_agents import MonkAIRunHooks


async def main():
    # 1. Create tracking hooks
    hooks = MonkAIRunHooks(
        tracer_token="tk_your_token",
        namespace="my-agent"
    )

    # 2. Create your agent
    agent = Agent(
        name="Assistant",
        instructions="You are a helpful assistant."
    )

    # 3. ✅ Recommended: Use run_with_tracking() wrapper
    result = await MonkAIRunHooks.run_with_tracking(
        agent,
        "Hello, how can you help?",
        hooks
    )
    
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
```

### Method 2: Explicit Capture

```python
async def main():
    hooks = MonkAIRunHooks(
        tracer_token="tk_your_token",
        namespace="my-agent"
    )
    
    agent = Agent(
        name="Assistant",
        instructions="You are a helpful assistant."
    )
    
    # ✅ Alternative: Set user input explicitly
    user_message = "Hello, how can you help?"
    hooks.set_user_input(user_message)
    
    result = await Runner.run(agent, user_message, hooks=hooks)
    print(result.final_output)
```

### Method 3: Automatic Capture (Experimental)

```python
async def main():
    hooks = MonkAIRunHooks(
        tracer_token="tk_your_token",
        namespace="my-agent"
    )
    
    agent = Agent(
        name="Assistant",
        instructions="You are a helpful assistant."
    )
    
    # ⚠️ Experimental: SDK will try to extract from context.input or context.messages
    # This depends on internal OpenAI Agents framework structure and may not work in all versions
    result = await Runner.run(
        agent,
        "Hello!",
        hooks=hooks
    )
    
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
```

**Note:** Method 3 relies on the internal structure of the OpenAI Agents framework and may fail silently. If you see a warning `"⚠️ WARNING: No user message captured"`, use Method 1 or 2 instead.

That's it! Your conversations are now tracked in MonkAI, including user messages.

## What Gets Tracked

### User Messages
User messages are automatically captured through multiple methods:
- **Automatic capture**: Via `on_llm_start` hook (direct access to input_data)
- **Explicit capture**: Via `set_user_input()` method
- **Fallback capture**: From context.input, context.messages, or nested context
- **Final guarantee**: Verified and added in `on_agent_end` if missing

### Token Segmentation
MonkAI provides detailed token breakdown:
- **Input Tokens**: User queries/prompts
- **Output Tokens**: Agent responses
- **Process Tokens**: System prompts, instructions, tool definitions
- **Memory Tokens**: Conversation history, context window

### Multi-Agent Handoffs

When agents hand off to each other, MonkAI tracks:
- Source agent name
- Target agent name
- Handoff timestamp
- Token usage per agent
- **🆕 Handoff reason** (when provided)

**New in v0.2.0**: Handoffs are now also recorded as `tool` type messages with `tool_name="transfer_to_agent"`. This allows the frontend to display handoffs inline with other tool calls, providing a complete visualization of the agent flow.

Example handoff message structure:
```python
Message(
    role="tool",
    content="Transferindo conversa para Billing Agent",
    sender="Triage Agent",
    tool_name="transfer_to_agent",
    tool_calls=[{
        "name": "transfer_to_agent",
        "arguments": {
            "from_agent": "Triage Agent",
            "to_agent": "Billing Agent",
            "timestamp": "2024-12-09T15:30:00.000Z"
        }
    }]
)
```

### Tool Calls
All tool invocations are tracked with:
- Tool name
- Input parameters
- Output results
- Execution time

### Internal OpenAI Tools (New in v0.2.1)

MonkAI automatically captures OpenAI's built-in internal tools that don't trigger regular `on_tool_start`/`on_tool_end` hooks. These tools are identified from the response's `raw_items`:

| Tool | Type ID | What's Captured |
|------|---------|-----------------|
| **Web Search** | `web_search_call` | Query, sources, search results |
| **File Search** | `file_search_call` | Query, file IDs, matched results |
| **Code Interpreter** | `code_interpreter_call` | Code, language, execution output |
| **Computer Use** | `computer_call` | Action type, output |

Example internal tool message structure:
```python
Message(
    role="tool",
    content="Internal tool: web_search",
    sender="Research Agent",
    tool_name="web_search",
    is_internal_tool=True,
    internal_tool_type="web_search_call",
    tool_calls=[{
        "name": "web_search",
        "type": "web_search_call",
        "id": "ws_abc123...",
        "status": "completed",
        "arguments": {"query": "latest AI news", "sources": [...]},
        "result": {"content": "..."}
    }]
)
```

These internal tools appear alongside your custom tools in the MonkAI Conversations panel, providing complete visibility into all tool usage during agent execution.

### Example: Agent with Web Search

```python
import asyncio
from agents import Agent, Runner, WebSearchTool
from monkai_trace.integrations.openai_agents import MonkAIRunHooks


async def main():
    # Create hooks for tracking
    hooks = MonkAIRunHooks(
        tracer_token="tk_your_token",
        namespace="research-agent"
    )
    
    # Create agent with web search capability
    agent = Agent(
        name="Research Assistant",
        instructions="You are a research assistant. Use web search to find current information.",
        tools=[WebSearchTool()]  # Enable web search
    )
    
    # Run with tracking
    user_message = "What are the latest developments in AI agents?"
    result = await MonkAIRunHooks.run_with_tracking(
        agent,
        user_message,
        hooks
    )
    
    print(result.final_output)
    
    # MonkAI automatically captures:
    # 1. User message: "What are the latest developments in AI agents?"
    # 2. Web search tool call with query, sources, and results
    # 3. Assistant response using the search results
    # 4. Token usage breakdown


if __name__ == "__main__":
    asyncio.run(main())
```

**What gets captured from web_search:**
- **Query**: The search query sent to the web search tool
- **Sources**: URLs and domains searched
- **Results**: The content returned from the search
- **Status**: Whether the search completed successfully

In the MonkAI dashboard, web search calls appear with:
- **Blue "Web Search" badge**
- **Query visualization** showing what was searched
- **Expandable results** showing sources and content
- **Position** in the conversation timeline

## Advanced Features

### Batch Upload
Control when data is sent:

```python
hooks = MonkAIRunHooks(
    tracer_token="tk_your_token",
    namespace="my-agent",
    batch_size=50  # Upload every 50 conversations
)
```

### Custom Metadata
Extend the hooks to add custom tracking:

```python
class MyHooks(MonkAIRunHooks):
    async def on_agent_end(self, context, agent, output):
        # Add your custom logic
        self._messages.append(Message(
            role="system",
            content=f"Custom metric: {your_metric}"
        ))
        await super().on_agent_end(context, agent, output)
```

### Session Management
Link multiple conversations:

```python
hooks._current_session = "user-session-123"
result = await Runner.run(agent, "First question", hooks=hooks)
result = await Runner.run(agent, "Follow-up question", hooks=hooks)
# Both tracked under same session
```

## Viewing Results

After running your agent with MonkAI hooks:

1. Go to your MonkAI dashboard
2. Navigate to the **Monitoring** tab
3. Filter by your `namespace`
4. See:
   - Conversation history
   - Token usage breakdown
   - Agent handoff flows
   - Tool call analytics

## Best Practices

1. **Use meaningful namespaces**: Group related agents together
2. **Enable batch upload** for high-throughput systems
3. **Track sessions** for multi-turn conversations
4. **Monitor token usage** to optimize costs
5. **Review handoff patterns** to improve agent routing

## Example: Multi-Agent System with Handoffs

```python
from agents import Agent, Runner
from monkai_trace.integrations.openai_agents import MonkAIRunHooks

async def main():
    hooks = MonkAIRunHooks(
        tracer_token="tk_your_token",
        namespace="support-system"
    )
    
    # Specialized agents
    billing_agent = Agent(
        name="Billing Agent",
        instructions="Handle billing questions"
    )
    
    tech_agent = Agent(
        name="Tech Agent",
        instructions="Handle technical issues"
    )
    
    # Triage agent with handoff capability
    triage_agent = Agent(
        name="Triage",
        instructions="Route to specialist based on user needs",
        handoffs=[billing_agent, tech_agent]
    )
    
    # Run with tracking (capture user message explicitly)
    user_message = "I was charged twice for my subscription"
    hooks.set_user_input(user_message)
    result = await Runner.run(
        triage_agent,
        user_message,
        hooks=hooks
    )
    
    # MonkAI tracks:
    # 1. User message: "I was charged twice..."
    # 2. Triage agent response
    # 3. Handoff tool message: transfer_to_agent (Triage → Billing Agent)
    # 4. Billing Agent response
    # 5. Token usage for each agent
```

### What Gets Recorded

When a handoff occurs, MonkAI automatically creates:

1. **Transfer Record** - For analytics and flow visualization:
   ```python
   Transfer(
       from_agent="Triage",
       to_agent="Billing Agent",
       timestamp="2024-12-09T15:30:00.000Z"
   )
   ```

2. **Tool Message** - For inline display with other messages:
   ```python
   Message(
       role="tool",
       content="Transferindo conversa para Billing Agent",
       tool_name="transfer_to_agent",
       tool_calls=[{
           "name": "transfer_to_agent",
           "arguments": {
               "from_agent": "Triage",
               "to_agent": "Billing Agent",
               "timestamp": "2024-12-09T15:30:00.000Z"
           }
       }]
   )
   ```

### Viewing Handoffs in the Dashboard

In the MonkAI dashboard, handoffs are displayed with:
- **Amber-colored badge** indicating "Transferência de Agente"
- **Arrow visualization** showing `Agent A → Agent B`
- **Reason** (if provided during handoff)
- **Position** in the conversation timeline alongside other messages
```

## Troubleshooting

### "openai-agents-python is required"
Install the OpenAI Agents framework:
```bash
pip install openai-agents-python
```

### User Messages Not Appearing

**Fixed in latest version!** The integration now has multiple capture methods with automatic fallbacks:

**Automatic capture (no setup required):**
The integration automatically captures user messages via the `on_llm_start` hook, which has direct access to the user's input data. This works automatically without any additional setup.

**Recommended approaches (for maximum reliability):**

1. **Use the wrapper (easiest):**
   ```python
   # ✅ Recommended approach
   result = await MonkAIRunHooks.run_with_tracking(agent, "Your message", hooks)
   ```

2. **Explicit capture (also reliable):**
   ```python
   # ✅ Also reliable
   hooks.set_user_input("Your message here")
   result = await Runner.run(agent, "Your message here", hooks=hooks)
   ```

**Capture methods (in order of priority):**
1. **`on_llm_start` hook**: Direct access to `input_data` parameter (automatic)
2. `_pending_user_input` (set via `set_user_input()`)
3. `context.input` (if available)
4. `context.messages` (searches for role='user')
5. `context.context` (nested context fallback)

**Final guarantee in `on_agent_end`:**
Even if all capture methods fail, the integration verifies at the end of agent execution and adds the user message if it was captured but not yet added to the messages list.

If you're still not seeing user messages, verify the logs show:
```
[MonkAI] Captured user message: Hello...
```
or
```
[MonkAI] Captured user message from on_llm_start: Hello...
```
or
```
[MonkAI] Added user message from backup: Hello...
```

### No data appearing in MonkAI
- Verify your tracer token is correct
- Check that `auto_upload=True` (default)
- Ensure your agent completes (on_agent_end fires)
- Check network connectivity
- Review the console logs for upload confirmations:
  ```
  [MonkAI] Uploaded X records
  ```

### Conversations showing as "incomplete"
This is expected if:
- Only assistant messages are captured (older SDK versions)
- Only tool calls are captured (no user/assistant dialogue)

**Solution**: The latest `monkai-trace` version now includes:
- Automatic user message capture via `on_llm_start` hook
- Multiple fallback methods for message capture
- Final guarantee in `on_agent_end` that ensures user messages are included

If you still see incomplete conversations, check the logs for:
- `[MonkAI] Captured user message: ...`
- `[MonkAI] Captured user message from on_llm_start: ...`
- `[MonkAI] Added user message from backup: ...`

### Token counts seem off
- Process tokens are estimated from system prompts (~4 chars per token)
- For exact counts, use OpenAI's token counter
- Memory tokens require explicit tracking of context

## API Reference

### MonkAIRunHooks

```python
MonkAIRunHooks(
    tracer_token: str,           # Required: Your MonkAI token
    namespace: str,              # Required: Namespace for tracking
    auto_upload: bool = True,    # Auto-upload on agent_end
    estimate_system_tokens: bool = True,  # Estimate process tokens
    batch_size: int = 10         # Records before upload
)
```

### Lifecycle Hooks

- `on_agent_start(context, agent)` - Agent begins (captures user message from context)
- `on_llm_start(context, agent, instructions, input_data)` - LLM called (captures user message from input_data - **automatic**)
- `on_agent_end(context, agent, output)` - Agent completes (uploads, guarantees user message is included)
- `on_handoff(context, from_agent, to_agent)` - Agent transfers
- `on_tool_start(context, agent, tool)` - Tool begins
- `on_tool_end(context, agent, tool, result)` - Tool completes

### Public Methods

- `set_user_input(user_input: str)` - Set user input before running (explicit control)
- `run_with_tracking(agent, user_input, hooks, **kwargs)` - Static convenience wrapper

## Next Steps

- [View full API reference](api_reference.md)
- [Learn about JSON uploads](json_upload_guide.md)
- [Explore other integrations](integrations.md)
