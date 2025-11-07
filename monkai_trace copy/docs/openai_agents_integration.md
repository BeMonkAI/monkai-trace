# MonkAI + OpenAI Agents Integration

This guide shows how to integrate MonkAI tracking into OpenAI Agents applications.

## Installation

```bash
pip install monkai-trace
pip install openai-agents-python
```

## Quick Start

```python
from agents import Agent, Runner
from monkai_trace.integrations.openai_agents import MonkAIRunHooks

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

# 3. Run with tracking
result = await Runner.run(agent, "Hello!", hooks=hooks)
```

That's it! Your conversations are now tracked in MonkAI.

## What Gets Tracked

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

### Tool Calls
All tool invocations are tracked with:
- Tool name
- Input parameters
- Output results
- Execution time

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

## Example: Multi-Agent System

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
    
    # Triage agent
    triage_agent = Agent(
        name="Triage",
        instructions="Route to specialist",
        handoffs=[billing_agent, tech_agent]
    )
    
    # Run with tracking
    result = await Runner.run(
        triage_agent,
        "I was charged twice",
        hooks=hooks
    )
    
    # MonkAI tracks the handoff flow automatically
```

## Troubleshooting

### "openai-agents-python is required"
Install the OpenAI Agents framework:
```bash
pip install openai-agents-python
```

### No data appearing in MonkAI
- Verify your tracer token is correct
- Check that `auto_upload=True` (default)
- Ensure your agent completes (on_agent_end fires)
- Check network connectivity

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

- `on_agent_start(context, agent)` - Agent begins
- `on_agent_end(context, agent, output)` - Agent completes (uploads)
- `on_handoff(context, from_agent, to_agent)` - Agent transfers
- `on_tool_start(context, agent, tool)` - Tool begins
- `on_tool_end(context, agent, tool, result)` - Tool completes

## Next Steps

- [View full API reference](api_reference.md)
- [Learn about JSON uploads](json_upload_guide.md)
- [Explore other integrations](integrations.md)
