# MonkAI Trace - Quick Start Guide

Get up and running with MonkAI in 5 minutes.

## Installation

```bash
pip install monkai-trace
```

For OpenAI Agents integration:
```bash
pip install monkai-trace[openai-agents]
```

## Get Your Tracer Token

1. Sign up at [monkai.ai](https://monkai.ai)
2. Navigate to **My Agents** → **Connect Agent**
3. Copy your tracer token (starts with `tk_`)

## Basic Usage

### Track a Simple Conversation

```python
from monkai_trace import MonkAIClient

# Initialize client
client = MonkAIClient(tracer_token="tk_your_token_here")

# Upload a conversation
client.upload_record(
    namespace="customer-support",
    agent="support-bot-v1",
    messages={
        "role": "assistant",
        "content": "How can I help you today?"
    },
    input_tokens=10,
    output_tokens=15,
    process_tokens=5,
    memory_tokens=0
)
```

### OpenAI Agents Integration (Recommended)

```python
import asyncio
from agents import Agent, Runner
from monkai_trace.integrations.openai_agents import MonkAIRunHooks

async def main():
    # 1. Create tracking hooks
    hooks = MonkAIRunHooks(
        tracer_token="tk_your_token_here",
        namespace="my-assistant"
    )
    
    # 2. Create your agent
    agent = Agent(
        name="Assistant",
        instructions="You are a helpful AI assistant."
    )
    
    # 3. Run with automatic tracking
    result = await Runner.run(
        agent,
        "What's the weather like?",
        hooks=hooks
    )
    
    print(result.final_output)
    # ✅ Automatically tracked in MonkAI!

if __name__ == "__main__":
    asyncio.run(main())
```

## What Gets Tracked

MonkAI provides detailed token segmentation:

- **Input Tokens**: User queries/prompts
- **Output Tokens**: Agent responses
- **Process Tokens**: System prompts, instructions, tool definitions
- **Memory Tokens**: Conversation history, context window

## Viewing Your Data

1. Go to [monkai.ai/monitoring](https://monkai.ai/monitoring)
2. Filter by your namespace
3. See:
   - Conversation history
   - Token usage breakdown
   - Agent performance metrics
   - Multi-agent flows

## Next Steps

- **Multi-Agent Systems**: [OpenAI Agents Integration Guide](./openai_agents_integration.md)
- **Bulk Upload**: [JSON Upload Guide](./json_upload_guide.md)
- **API Reference**: [Full API Documentation](./api_reference.md)

## Common Issues

### "Invalid tracer token"
- Ensure token starts with `tk_`
- Check you copied the entire token
- Verify token is active in your MonkAI dashboard

### "Connection timeout"
- Check your network connection
- Verify `base_url` is correct (default: `https://monkai.ai/api`)
- Try increasing timeout: `MonkAIClient(tracer_token="tk_xxx", timeout=60)`

### "No data showing in dashboard"
- Ensure `namespace` matches what you're filtering for
- Check `auto_upload=True` in hooks (default)
- Verify conversation completed (data uploads on agent_end)

## Need Help?

- 📚 [Full Documentation](https://docs.monkai.ai)
- 💬 [Discord Community](https://discord.gg/monkai)
- 📧 [Email Support](mailto:support@monkai.ai)
