# MonkAI Agent Integration Guide

Complete guide for integrating MonkAI Trace with the MonkAI Agent framework for automatic conversation tracking.

## Installation

```bash
pip install monkai-trace monkai-agent
```

## Quick Start

```python
from monkai_agent import Agent
from monkai_trace.integrations.monkai_agent import MonkAIAgentHooks

# Initialize tracking hooks
hooks = MonkAIAgentHooks(
    tracer_token="tk_your_token_here",
    namespace="my-namespace"
)

# Create agent with automatic tracking
agent = Agent(
    name="Support Bot",
    instructions="You are a helpful assistant",
    hooks=hooks
)

# Run conversation (automatically tracked)
result = agent.run("Hello, I need help!")
```

## Getting Your Tracer Token

1. Go to [MonkAI Dashboard](https://monkai.app/my-agents)
2. Click "Connect Agent" or "Add Agent"
3. Follow the wizard to register your namespace
4. Copy your tracer token (starts with `tk_`)

## What Gets Tracked

### 1. Token Segmentation

MonkAI automatically tracks four types of tokens:

- **Input tokens**: User messages and prompts
- **Output tokens**: Agent responses
- **Process tokens**: Tool executions and function calls
- **Memory tokens**: System prompts and agent instructions

```python
# Token tracking is automatic
hooks = MonkAIAgentHooks(
    tracer_token="tk_your_token",
    namespace="my-namespace",
    estimate_system_tokens=True  # Automatically estimate memory tokens
)
```

### 2. Multi-Agent Handoffs

When agents transfer conversations to other agents, MonkAI tracks:

- Source agent name
- Destination agent name
- Handoff timestamp
- Reason for transfer (if provided)

```python
# Create specialized agents
billing_agent = Agent(name="Billing Agent", hooks=hooks)
support_agent = Agent(name="Support Agent", hooks=hooks)

# Triage agent with handoff capability
triage = Agent(
    name="Triage Agent",
    handoffs=[billing_agent, support_agent],
    hooks=hooks
)

# Handoffs are automatically tracked
result = triage.run("I was charged twice")
```

### 3. Tool Calls

All tool executions are tracked with:

- Tool name
- Input parameters
- Output results
- Execution tokens

```python
# Tools are automatically tracked when used
agent = Agent(
    name="Assistant",
    tools=[search_web, calculate, send_email],
    hooks=hooks
)
```

### 4. Session Continuity

Conversations are grouped by session for multi-turn tracking:

```python
hooks = MonkAIAgentHooks(
    tracer_token="tk_your_token",
    namespace="my-namespace"
)

agent = Agent(name="Chatbot", hooks=hooks)

# Same session across multiple turns
agent.run("What's the weather?")
agent.run("And tomorrow?")
agent.run("Thanks!")

# Start new session
hooks.reset_session()
agent.run("New conversation")
```

## Advanced Configuration

### Batch Uploads

Control when data is uploaded to MonkAI:

```python
hooks = MonkAIAgentHooks(
    tracer_token="tk_your_token",
    namespace="my-namespace",
    auto_upload=True,      # Upload after each agent completion
    batch_size=10          # Upload after 10 conversations
)

# Manual flush
hooks.flush()  # Force upload of pending records
```

### Custom Metadata

Add custom metadata to tracked conversations:

```python
from monkai_trace.models import Message

# Custom message tracking
hooks.on_message(agent, {
    "role": "user",
    "content": "Hello",
    "sender": "custom-sender",
    "metadata": {"user_id": "12345"}
})
```

### Error Handling

```python
try:
    hooks = MonkAIAgentHooks(
        tracer_token="tk_your_token",
        namespace="my-namespace"
    )
    
    agent = Agent(name="Bot", hooks=hooks)
    result = agent.run("Test message")
    
except Exception as e:
    print(f"Error: {e}")
    # Fallback: agent still works without tracking
```

## API Reference

### MonkAIAgentHooks

```python
MonkAIAgentHooks(
    tracer_token: str,              # Required: Your MonkAI tracer token
    namespace: str,                  # Required: Namespace for organization
    auto_upload: bool = True,        # Auto-upload after completion
    estimate_system_tokens: bool = True,  # Estimate memory tokens
    batch_size: int = 10,           # Records per batch
    base_url: Optional[str] = None  # Custom API endpoint
)
```

### Lifecycle Hooks

The following hooks are called automatically by MonkAI Agent:

```python
# Called when agent starts
on_agent_start(agent, context)

# Called when agent completes
on_agent_end(agent, context, output)

# Called for each message
on_message(agent, message)

# Called on agent handoff
on_handoff(from_agent, to_agent, context, reason)

# Called when tool starts
on_tool_start(agent, tool_name, tool_input)

# Called when tool completes
on_tool_end(agent, tool_name, tool_output)
```

### Public Methods

```python
# Manually flush pending records
hooks.flush()

# Reset session ID for new conversation
hooks.reset_session()
```

## Viewing Results

### MonkAI Dashboard

1. Visit [https://monkai.app/monitoring](https://monkai.app/monitoring)
2. Select your namespace from the filter
3. View:
   - **Conversation History**: All tracked conversations
   - **Agent Flow**: Visual representation of agent handoffs
   - **Token Analytics**: Token usage breakdown
   - **Logs**: Detailed execution logs

### Filter by Namespace

```python
# Use descriptive namespace names
hooks = MonkAIAgentHooks(
    tracer_token="tk_your_token",
    namespace="production-support"  # Easy to find in dashboard
)
```

### Multi-Environment Setup

```python
import os

# Different namespaces for different environments
env = os.getenv("ENVIRONMENT", "development")

hooks = MonkAIAgentHooks(
    tracer_token="tk_your_token",
    namespace=f"customer-support-{env}"  # e.g., "customer-support-production"
)
```

## Best Practices

### 1. Namespace Naming

Use clear, hierarchical namespace names:

```python
# Good
"production-customer-support"
"staging-order-processing"
"dev-chatbot-testing"

# Avoid
"namespace1"
"test"
"my-agent"
```

### 2. Session Management

Reset sessions for new conversations:

```python
def handle_new_user(user_id):
    hooks.reset_session()
    agent = Agent(name="Support", hooks=hooks)
    return agent.run(f"New conversation with {user_id}")
```

### 3. Error Handling

Always handle potential upload failures:

```python
import logging

logging.basicConfig(level=logging.INFO)

hooks = MonkAIAgentHooks(
    tracer_token="tk_your_token",
    namespace="my-namespace",
    auto_upload=True
)

# MonkAI logs upload failures automatically
# Your agent continues working even if tracking fails
```

### 4. Performance

For high-throughput applications, use batching:

```python
hooks = MonkAIAgentHooks(
    tracer_token="tk_your_token",
    namespace="high-volume",
    batch_size=50,  # Larger batches for better performance
    auto_upload=True
)
```

## Troubleshooting

### "monkai_agent is not installed"

```bash
pip install monkai-agent
```

### "Invalid tracer token"

- Ensure token starts with `tk_`
- Verify token in [MonkAI Dashboard](https://monkai.app/my-agents)
- Check namespace is registered

### "No data appearing in dashboard"

1. Verify `auto_upload=True` or call `hooks.flush()`
2. Check namespace filter in dashboard
3. Ensure agent completed execution (`on_agent_end` was called)
4. Check logs for upload errors

### Token counts seem incorrect

```python
# Enable token estimation for better accuracy
hooks = MonkAIAgentHooks(
    tracer_token="tk_your_token",
    namespace="my-namespace",
    estimate_system_tokens=True  # Estimates memory tokens
)
```

### Debug logging

```python
import logging

# Enable debug logs
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("monkai_trace")
logger.setLevel(logging.DEBUG)
```

## Examples

### Basic Chatbot

```python
from monkai_agent import Agent
from monkai_trace.integrations.monkai_agent import MonkAIAgentHooks

hooks = MonkAIAgentHooks(
    tracer_token="tk_your_token",
    namespace="chatbot"
)

agent = Agent(
    name="Chatbot",
    instructions="You are a friendly chatbot",
    hooks=hooks
)

result = agent.run("Tell me a joke")
print(result)
```

### Multi-Agent System

```python
hooks = MonkAIAgentHooks(
    tracer_token="tk_your_token",
    namespace="multi-agent"
)

# Specialized agents
billing = Agent(name="Billing", hooks=hooks)
tech = Agent(name="Technical", hooks=hooks)

# Triage agent
triage = Agent(
    name="Triage",
    handoffs=[billing, tech],
    hooks=hooks
)

result = triage.run("My payment failed")
# Dashboard shows: Triage → Billing handoff
```

### Production Setup

```python
import os
import logging

# Environment-specific configuration
env = os.getenv("ENV", "dev")
token = os.getenv("MONKAI_TOKEN")

logging.basicConfig(level=logging.INFO)

hooks = MonkAIAgentHooks(
    tracer_token=token,
    namespace=f"production-support-{env}",
    auto_upload=True,
    batch_size=20
)

agent = Agent(
    name="ProductionBot",
    instructions="Professional customer support agent",
    hooks=hooks
)
```

## Support

- **Documentation**: [https://docs.monkai.app](https://docs.monkai.app)
- **Dashboard**: [https://monkai.app](https://monkai.app)
- **Issues**: [GitHub Issues](https://github.com/monkai/monkai-trace-python/issues)
- **Email**: support@monkai.app
