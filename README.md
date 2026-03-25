# MonkAI Trace - Python SDK

Official Python client for [MonkAI](https://monkai.ai) - Monitor, analyze, and optimize your AI agents.

[![PyPI version](https://badge.fury.io/py/monkai-trace.svg)](https://pypi.org/project/monkai-trace/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## Features

- **Upload conversation records** with full token segmentation
- **Track 4 token types**: input, output, process, memory
- **Async support** via `AsyncMonkAIClient` (aiohttp-based)
- **Retry with exponential backoff** on transient failures
- **Batch processing** with automatic chunking
- **Upload from JSON files** (supports your existing data)
- **Session management** with automatic cleanup and configurable timeouts
- **Data export** - Query records/logs with filters, export to JSON or CSV
- **Structured logging** via Python `logging` module
- **HTTP REST API** - Language-agnostic tracing for any runtime
- **Framework Integrations**:
  - **MonkAI Agent** - Native framework with automatic tracking
  - **LangChain** - Full callback handler support (v0.2+)
  - **OpenAI Agents** - RunHooks integration
  - **Python Logging** - Standard logging handler with `custom_object` metadata
- **Coding Assistant Integrations**:
  - **Claude Code** - Parse CLI session logs from `~/.claude/`
  - **Cline** - Parse VS Code extension task history (also Cursor, Windsurf)
  - **OpenClaw** - Parse personal AI assistant session transcripts
  - **GitHub Copilot** - Chat history, org usage API, CSV imports

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

### Basic Usage

```python
from monkai_trace import MonkAIClient

client = MonkAIClient(tracer_token="tk_your_token")

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

### Async Client

```python
from monkai_trace import AsyncMonkAIClient

async def main():
    client = AsyncMonkAIClient(tracer_token="tk_your_token")
    await client.upload_record(
        namespace="my-agent",
        agent="assistant",
        messages=[{"role": "user", "content": "Hello"}],
        input_tokens=5,
        output_tokens=10
    )
    await client.close()
```

### OpenAI Agents Integration

```python
from agents import Agent, WebSearchTool
from monkai_trace.integrations.openai_agents import MonkAIRunHooks

hooks = MonkAIRunHooks(
    tracer_token="tk_your_token",
    namespace="my-agent",
    batch_size=1
)

agent = Agent(
    name="Assistant",
    instructions="You are helpful",
    tools=[WebSearchTool()]
)

hooks.set_user_id("user_abc123")
hooks.set_user_name("João Silva")
hooks.set_user_channel("whatsapp")

result = await MonkAIRunHooks.run_with_tracking(agent, "Hello!", hooks)
```

### LangChain Integration

```python
from langchain.agents import initialize_agent, load_tools
from langchain.llms import OpenAI
from monkai_trace.integrations.langchain import MonkAICallbackHandler

handler = MonkAICallbackHandler(
    tracer_token="tk_your_token",
    namespace="my-agents"
)

llm = OpenAI(temperature=0)
tools = load_tools(["serpapi"], llm=llm)
agent = initialize_agent(tools, llm, callbacks=[handler])
agent.run("What is the weather in Tokyo?")
```

### MonkAI Agent Framework

```python
from monkai_agent import Agent
from monkai_trace.integrations.monkai_agent import MonkAIAgentHooks

hooks = MonkAIAgentHooks(
    tracer_token="tk_your_token",
    namespace="my-namespace"
)

agent = Agent(
    name="Support Bot",
    instructions="You are a helpful assistant",
    hooks=hooks
)

result = agent.run("Help me with my order")
```

### Claude Code Integration

```python
from monkai_trace import ClaudeCodeTracer

tracer = ClaudeCodeTracer(tracer_token="tk_your_token", namespace="dev-productivity")

# Upload all Claude Code sessions
tracer.upload_all_projects()

# Or a specific project
tracer.upload_project("~/.claude/projects/-Users-me-myproject/")
```

### Cline Integration

```python
from monkai_trace import ClineTracer

tracer = ClineTracer(tracer_token="tk_your_token", namespace="dev-productivity")

# Auto-detects VS Code, Cursor, or Windsurf
tracer.upload_all_tasks()
```

### OpenClaw Integration

```python
from monkai_trace import OpenClawTracer

tracer = OpenClawTracer(tracer_token="tk_your_token", namespace="dev-productivity")

# Upload all sessions from ~/.openclaw/
tracer.upload_all_sessions()
```

### GitHub Copilot Integration

```python
from monkai_trace import CopilotTracer

tracer = CopilotTracer(tracer_token="tk_your_token", namespace="dev-productivity")

# Local chat history
tracer.upload_chat_history()

# Org usage API (Business/Enterprise)
tracer.upload_org_usage(github_token="ghp_xxx", org="MyOrg")

# CSV import
tracer.upload_from_csv("copilot_export.csv")
```

### Upload from JSON Files

```python
client.upload_records_from_json("records.json")
client.upload_logs_from_json("logs.json", namespace="my-agent")
```

### Query & Export Data

```python
result = client.query_records(
    namespace="customer-support",
    agent="Support Bot",
    start_date="2025-01-01",
    limit=50
)

client.export_records(
    namespace="customer-support",
    output_file="conversations.json"
)

client.export_logs(
    namespace="my-agent",
    level="error",
    format="csv",
    output_file="errors.csv"
)
```

### HTTP REST API (Language-Agnostic)

For non-Python runtimes or direct HTTP calls:

```python
import requests

MONKAI_API = "https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api"
TOKEN = "tk_your_token"

session = requests.post(
    f"{MONKAI_API}/sessions/create",
    headers={"tracer_token": TOKEN, "Content-Type": "application/json"},
    json={"namespace": "my-agent", "user_id": "user123"}
).json()

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

## Session Management

MonkAI automatically manages user sessions with configurable timeouts:

- **Default timeout**: 2 minutes of inactivity
- **Automatic cleanup**: Background thread removes expired sessions
- **Multi-user support**: Each user gets isolated sessions
- **Persistent sessions**: Optional file-backed session storage with LRU caching

```python
hooks = MonkAIRunHooks(
    tracer_token="tk_your_token",
    namespace="support",
    inactivity_timeout=120
)
hooks.set_user_id("customer-12345")
```

See [Session Management Guide](docs/session_management.md) for details.

## Token Segmentation

Track 4 token types to understand LLM costs:

| Type | Description |
|------|-------------|
| **Input** | User queries and prompts |
| **Output** | Agent responses and completions |
| **Process** | System prompts, instructions, tool definitions |
| **Memory** | Conversation history and context |

```python
client.upload_record(
    namespace="analytics",
    agent="data-agent",
    messages={"role": "user", "content": "Analyze this"},
    input_tokens=15,
    output_tokens=200,
    process_tokens=500,
    memory_tokens=100
)
```

## Examples

See the [`examples/`](examples/) directory:

| Example | Description |
|---------|-------------|
| `openai_agents_example.py` | OpenAI Agents basic integration |
| `openai_agents_multi_agent.py` | Multi-agent handoff patterns |
| `monkai_agent_example.py` | MonkAI Agent framework |
| `langchain_example.py` | LangChain integration |
| `langchain_conversational.py` | LangChain with memory |
| `logging_example.py` | Python logging (scripts) |
| `service_logging_example.py` | Python logging (long-running services) |
| `session_management_basic.py` | Automatic session creation |
| `session_management_multi_user.py` | WhatsApp bot with concurrent users |
| `session_management_custom_timeout.py` | Custom timeout configuration |
| `http_rest_basic.py` | HTTP REST API basic usage |
| `http_rest_async.py` | Async HTTP REST client |
| `http_rest_openai.py` | OpenAI + HTTP REST tracing |
| `export_data.py` | Query and export data to JSON/CSV |
| `send_json_files.py` | Upload from JSON files |
| `claude_code_example.py` | Parse Claude Code session logs |
| `cline_example.py` | Parse Cline/OpenClaw task history |
| `openclaw_example.py` | Parse OpenClaw session transcripts |
| `copilot_example.py` | Track GitHub Copilot usage |

See [examples/README.md](examples/README.md) for the full guide.

## Documentation

- [Quick Start Guide](docs/quickstart.md)
- [HTTP REST API Guide](docs/http_rest_api.md)
- [Data Export Guide](docs/data_export.md)
- [Session Management Guide](docs/session_management.md)
- [Coding Assistants Integration](docs/coding_assistants_integration.md) ⭐ NEW
- [MonkAI Agent Integration](docs/monkai_agent_integration.md)
- [LangChain Integration](docs/langchain_integration.md)
- [OpenAI Agents Integration](docs/openai_agents_integration.md)
- [Logging Integration](docs/logging_integration.md)
- [JSON Upload Guide](docs/json_upload_guide.md)
- [API Reference](docs/api_reference.md)

## Development

```bash
git clone https://github.com/BeMonkAI/monkai-trace.git
cd monkai-trace

pip install -e ".[dev]"

pytest tests/ -x -q
```

## Requirements

- Python 3.8+
- `requests` >= 2.32.2
- `pydantic` >= 2.0.0
- `aiohttp` (optional, for `AsyncMonkAIClient`)
- `monkai-agent` (optional, for MonkAI Agent integration)
- `langchain` (optional, for LangChain integration)
- `openai-agents-python` (optional, for OpenAI Agents integration)

## Changelog

### v0.2.18

- Updated README and project URLs
- Synchronized repository metadata

### v0.2.17

- **Security**: Patched `requests` dependency (CVE fix, now >= 2.32.2)
- **Security**: Added `.env` files to `.gitignore`
- **Security**: Replaced bare `except:` with specific exception handling
- **Reliability**: Added retry with exponential backoff on all HTTP requests
- **Reliability**: Added CI test gate before PyPI publish
- **Usability**: Unified async client (base URL, auth headers, endpoints)
- **Usability**: Exported `AsyncMonkAIClient` from package `__init__`
- **Usability**: Fixed `TokenUsage.total_tokens` auto-calculation
- **Scalability**: Automatic session cleanup via background thread
- **Scalability**: Microsecond-precision session IDs to prevent collisions
- **Quality**: Migrated all `print()` calls to `logging` module

## License

MIT License - see [LICENSE](LICENSE) file.

## Support

- [Documentation](https://docs.monkai.ai)
- [GitHub Issues](https://github.com/BeMonkAI/monkai-trace/issues)

## Contributing

Contributions welcome! Please read our [Contributing Guide](CONTRIBUTING.md) first.
