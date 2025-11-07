# MonkAI Trace - Python SDK

Official Python client for [MonkAI](https://monkai.ai) - Monitor, analyze, and optimize your AI agents.

## Features

- 📤 **Upload conversation records** with full token segmentation
- 📊 **Track 4 token types**: input, output, process, memory
- 📁 **Upload from JSON files** (supports your existing data)
- 🔄 **Batch processing** with automatic chunking
- ✅ **OpenAI Agents integration** - Fully implemented with automatic tracking
- ✅ **Python logging.Handler** - Fully implemented with automatic log uploads
- 🚧 **Framework integrations**: LangChain (coming soon)

## Installation

```bash
pip install monkai-trace
```

For OpenAI Agents integration:
```bash
pip install monkai-trace openai-agents-python
```

## Quick Start

### Basic Usage

```python
from monkai_trace import MonkAIClient

# Initialize client
client = MonkAIClient(tracer_token="tk_your_token")

# Upload a conversation
client.upload_record(
    namespace="customer-support",
    agent="support-bot",
    messages=[
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi! How can I help?"}
    ],
    input_tokens=5,
    output_tokens=10,
    process_tokens=100,
    memory_tokens=20
)
```

### OpenAI Agents Integration

```python
from agents import Agent, Runner
from monkai_trace.integrations.openai_agents import MonkAIRunHooks

# Create tracking hooks
hooks = MonkAIRunHooks(
    tracer_token="tk_your_token",
    namespace="my-agent"
)

# Create agent
agent = Agent(
    name="Assistant",
    instructions="You are helpful"
)

# Run with automatic tracking
result = await Runner.run(agent, "Hello!", hooks=hooks)
# ✅ Conversation tracked automatically!
```

### Upload from JSON Files

```python
# Upload conversation records
client.upload_records_from_json("records.json")

# Upload logs
client.upload_logs_from_json("logs.json", namespace="my-agent")
```

## Token Segmentation

MonkAI helps you understand your LLM costs by tracking 4 token types:

- **Input**: User queries and prompts
- **Output**: Agent responses and completions
- **Process**: System prompts, instructions, tool definitions
- **Memory**: Conversation history and context

```python
client.upload_record(
    namespace="analytics",
    agent="data-agent",
    messages={"role": "user", "content": "Analyze this"},
    input_tokens=15,      # User query
    output_tokens=200,    # Agent response
    process_tokens=500,   # System prompt + tools
    memory_tokens=100     # Previous conversation
)
```

## Documentation

- [Quick Start Guide](docs/quickstart.md)
- [OpenAI Agents Integration](docs/openai_agents_integration.md)
- [JSON Upload Guide](docs/json_upload_guide.md)
- [API Reference](docs/api_reference.md)

## Examples

See the `examples/` directory for:
- `openai_agents_example.py` - Basic OpenAI Agents integration
- `multi_agent_handoff.py` - Multi-agent tracking
- `send_json_files.py` - Upload from JSON files

## Development

```bash
# Clone repository
git clone https://github.com/monkai/monkai-trace-python
cd monkai-trace-python

# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run type checking
mypy monkai_trace
```

## Requirements

- Python 3.8+
- `requests` >= 2.31.0
- `pydantic` >= 2.0.0
- `openai-agents-python` (optional, for OpenAI Agents integration)

## License

MIT License - see [LICENSE](LICENSE) file.

## Support

- [Documentation](https://docs.monkai.ai)
- [GitHub Issues](https://github.com/monkai/monkai-trace-python/issues)
- [Discord Community](https://discord.gg/monkai)

## Contributing

Contributions welcome! Please read our [Contributing Guide](CONTRIBUTING.md) first.
