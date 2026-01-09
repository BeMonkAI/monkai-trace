# MonkAI Trace - Python SDK

Official Python client for [MonkAI](https://monkai.ai) - Monitor, analyze, and optimize your AI agents.

## Features

- 📤 **Upload conversation records** with full token segmentation
- 📊 **Track 4 token types**: input, output, process, memory (always present in API)
- 📁 **Upload from JSON files** (supports your existing data)
- 🔄 **Batch processing** with automatic chunking and improved error handling
- 🛡️ **Graceful optional dependencies** - Import without dependencies, error only on use
- 🌐 **HTTP REST API** - Language-agnostic tracing for any runtime (Deno, Go, Node.js, etc.)
- 🔌 **Framework Integrations**:
  - ✅ **MonkAI Agent** - Native framework with automatic tracking
  - ✅ **LangChain** - Full callback handler support (v0.2+)
  - ✅ **OpenAI Agents** - RunHooks integration (updated for latest API)
  - ✅ **Python Logging** - Standard logging handler with `custom_object` metadata

## Installation

```bash
pip install monkai-trace
```

For framework integrations:
```bash
# MonkAI Agent (Native Framework)
pip install monkai-trace monkai-agent

# LangChain
pip install monkai-trace langchain

# OpenAI Agents
pip install monkai-trace openai-agents-python
```

## Quick Start

### LangChain Integration

Automatically track LangChain agents:

```python
from langchain.agents import initialize_agent, load_tools
from langchain.llms import OpenAI
from monkai_trace.integrations.langchain import MonkAICallbackHandler

# Create callback handler
handler = MonkAICallbackHandler(
    tracer_token="tk_your_token",
    namespace="my-agents"
)

# Add to your agent
llm = OpenAI(temperature=0)
tools = load_tools(["serpapi"], llm=llm)
agent = initialize_agent(tools, llm, callbacks=[handler])

# Automatically tracked!
agent.run("What is the weather in Tokyo?")
```

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

### MonkAI Agent Framework (Native)

```python
from monkai_agent import Agent
from monkai_trace.integrations.monkai_agent import MonkAIAgentHooks

# Create tracking hooks
hooks = MonkAIAgentHooks(
    tracer_token="tk_your_token",
    namespace="my-namespace"
)

# Create agent with automatic tracking
agent = Agent(
    name="Support Bot",
    instructions="You are a helpful assistant",
    hooks=hooks
)

# Run agent - automatically tracked!
result = agent.run("Help me with my order")
```

### OpenAI Agents Integration

```python
from agents import Agent, WebSearchTool
from monkai_trace.integrations.openai_agents import MonkAIRunHooks

# Create tracking hooks (batch_size=1 recommended for real-time monitoring)
hooks = MonkAIRunHooks(
    tracer_token="tk_your_token",
    namespace="my-agent",
    batch_size=1  # v0.2.10+: Upload immediately
)

# Create agent with web search
agent = Agent(
    name="Assistant",
    instructions="You are helpful",
    tools=[WebSearchTool()]
)

# Set user identification (v0.2.12+)
hooks.set_user_id("user_abc123")         # Unique ID for session tracking
hooks.set_user_name("João Silva")        # Display name in dashboard
hooks.set_user_channel("whatsapp")       # Communication channel

# ✅ RECOMMENDED: Use run_with_tracking() for internal tools capture
result = await MonkAIRunHooks.run_with_tracking(agent, "Hello!", hooks)
# Captures: user message, web_search_call with sources, assistant response

# Dashboard shows:
# - "👤 João Silva" instead of "👤 Usuário" in messages
# - Filter by user name in monitoring panel
```

### HTTP REST API (Language-Agnostic)

For non-Python runtimes or when you prefer direct HTTP calls:

```python
import requests

MONKAI_API = "https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api"
TOKEN = "tk_your_token"

# Create session
session = requests.post(
    f"{MONKAI_API}/sessions/create",
    headers={"tracer_token": TOKEN, "Content-Type": "application/json"},
    json={"namespace": "my-agent", "user_id": "user123"}
).json()

# Trace LLM call
requests.post(
    f"{MONKAI_API}/traces/llm",
    headers={"tracer_token": TOKEN, "Content-Type": "application/json"},
    json={
        "session_id": session["session_id"],
        "model": "gpt-4",
        "input": {"messages": [{"role": "user", "content": "Hello"}]},
        "output": {"content": "Hi!", "usage": {"prompt_tokens": 5, "completion_tokens": 3}}
    }
)
```

See [HTTP REST API Guide](docs/http_rest_api.md) for complete documentation.

### Upload from JSON Files

```python
# Upload conversation records
client.upload_records_from_json("records.json")

# Upload logs
client.upload_logs_from_json("logs.json", namespace="my-agent")
```

## 📚 Practical Examples

Learn by example! Check out our comprehensive examples:

### Session Management
- **[Basic Sessions](examples/session_management_basic.py)** - Automatic session creation and timeout
- **[Multi-User](examples/session_management_multi_user.py)** - WhatsApp bot with concurrent users
- **[Custom Timeouts](examples/session_management_custom_timeout.py)** - Configure for your use case

### OpenAI Agents
- **[Basic Integration](examples/openai_agents_example.py)** - Get started quickly
- **[Multi-Agent](examples/openai_agents_multi_agent.py)** - Advanced handoff patterns

### HTTP REST API
- **[Basic Usage](examples/http_rest_basic.py)** - Direct API calls without SDK
- **[Async Client](examples/http_rest_async.py)** - High-performance async tracing
- **[OpenAI + HTTP](examples/http_rest_openai.py)** - Trace OpenAI calls via REST

**Run any example:**
```bash
python examples/session_management_basic.py
```

See [examples/README.md](examples/README.md) for full list and use case guide.

---

## Session Management

MonkAI automatically manages user sessions with configurable timeouts:

- **Default timeout**: 2 minutes of inactivity
- **Automatic session renewal**: Active conversations continue in same session
- **Multi-user support**: Each user gets isolated sessions
- **WhatsApp integration**: Use `user_whatsapp` or `user_id` for user identification

```python
hooks = MonkAIRunHooks(
    tracer_token="tk_your_token",
    namespace="support",
    inactivity_timeout=120  # 2 minutos
)
hooks.set_user_id("customer-12345")
```

See [Session Management Guide](docs/session_management.md) for details.

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
- [HTTP REST API Guide](docs/http_rest_api.md) ⭐ **NEW**
- [Session Management Guide](docs/session_management.md)
- [MonkAI Agent Integration](docs/monkai_agent_integration.md)
- [LangChain Integration](docs/langchain_integration.md)
- [OpenAI Agents Integration](docs/openai_agents_integration.md)
- [Logging Integration](docs/logging_integration.md)
- [JSON Upload Guide](docs/json_upload_guide.md)
- [API Reference](docs/api_reference.md)

## Examples

See the `examples/` directory for:
- `monkai_agent_example.py` - MonkAI Agent framework integration
- `langchain_example.py` - LangChain integration
- `langchain_conversational.py` - LangChain with memory
- `openai_agents_example.py` - OpenAI Agents integration
- `multi_agent_handoff.py` - Multi-agent tracking
- `logging_example.py` - Python logging integration (scripts)
- `service_logging_example.py` - Python logging for long-running services
- `send_json_files.py` - Upload from JSON files
- `http_rest_basic.py` - HTTP REST API basic usage ⭐ **NEW**
- `http_rest_async.py` - Async HTTP REST client ⭐ **NEW**
- `http_rest_openai.py` - OpenAI + HTTP REST tracing ⭐ **NEW**

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
- `monkai-agent` (optional, for MonkAI Agent integration)
- `langchain` (optional, for LangChain integration)
- `openai-agents-python` (optional, for OpenAI Agents integration)

## License

MIT License - see [LICENSE](LICENSE) file.

## Support

- [Documentation](https://docs.monkai.ai)
- [GitHub Issues](https://github.com/monkai/monkai-trace-python/issues)
- [Discord Community](https://discord.gg/monkai)

## Contributing

Contributions welcome! Please read our [Contributing Guide](CONTRIBUTING.md) first.
