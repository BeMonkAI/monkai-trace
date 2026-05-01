# MonkAI Trace Examples

This directory contains practical, executable examples demonstrating MonkAI integration patterns.

## REST API (any language)

### 0. `monkai_trace.http` — request collection
A ready-to-run set of every REST endpoint, usable from VS Code REST Client or
JetBrains HTTP Client. Edit `@token` at the top, then click "Send Request"
above any block.

```
examples/monkai_trace.http
```

Pairs with `docs/openapi.yaml` (machine-readable contract) and the
"Integrate from Node.js" section in `docs/http_rest_api.md`.

---

## Session Management

### 1. Basic Session Management
**File**: `session_management_basic.py`

Learn the fundamentals of automatic session handling:
- ✅ Automatic session creation with default 2-minute timeout
- ✅ Session reuse within timeout period
- ✅ Session expiration and new session creation
- ✅ Anonymous vs explicit user IDs

**Run:**
```bash
python examples/session_management_basic.py
```

**What you'll see:**
- Session IDs automatically generated
- Sessions reused for continuous conversations
- New sessions created after timeouts

---

### 2. Multi-User Handling
**File**: `session_management_multi_user.py`

Real-world multi-user scenarios:
- ✅ Multiple users with same agent (WhatsApp bot simulation)
- ✅ Session isolation by user_id
- ✅ Concurrent conversations
- ✅ Session persistence across restarts

**Run:**
```bash
python examples/session_management_multi_user.py
```

**What you'll see:**
- 3 users with separate sessions
- Interleaved messages maintaining isolation
- Session duration and inactivity tracking

---

### 3. Custom Timeouts
**File**: `session_management_custom_timeout.py`

Configure timeouts for different use cases:
- ✅ Quick support: 1 minute timeout
- ✅ Long-running tasks: 10 minute timeout
- ✅ Real-time chat: 30 second timeout

**Run:**
```bash
python examples/session_management_custom_timeout.py
```

**What you'll see:**
- Different timeout configurations
- Use case-specific session behavior
- Best practices for timeout selection

---

## OpenAI Agents Integration

### 4. Basic Integration
**File**: `openai_agents_example.py`

Get started with OpenAI Agents tracking:
- ✅ Two integration methods
- ✅ Automatic user input capture
- ✅ Token usage tracking
- ✅ Session management

**Run:**
```bash
python examples/openai_agents_example.py --token tk_your_token --namespace your-namespace
```

---

### 5. Multi-Agent Handoffs
**File**: `openai_agents_multi_agent.py`

Advanced multi-agent patterns:
- ✅ Agent-to-agent transfers
- ✅ Specialized agent routing
- ✅ Handoff tracking
- ✅ Token breakdown per agent

**Run:**
```bash
python examples/openai_agents_multi_agent.py --token tk_your_token --namespace support
```

---

### 6. Internal Tools (Web Search, Code Interpreter) ⭐ FIXED v0.2.8
**File**: `openai_agents_internal_tools.py`

Capture OpenAI's built-in internal tools:
- ✅ Web search queries and **sources** (v0.2.7+: fixed via RunConfig)
- ✅ File search with document retrieval (via RunConfig.model_settings)
- ✅ Code interpreter execution
- ✅ Computer use actions
- ✅ Multi-tool agent patterns
- ✅ **v0.2.8:** Fixed record upload issues, added `flush()` method

**Run:**
```bash
pip install monkai-trace>=0.2.8  # Ensure latest version
python examples/openai_agents_internal_tools.py --token tk_your_token --namespace internal-tools-demo
```

**What you'll see:**
- Internal tools automatically captured from `response.raw_items`
- **Sources captured correctly** via RunConfig (v0.2.7+)
- **Records uploaded reliably** (v0.2.8+)
- Tools displayed alongside custom tools in MonkAI dashboard
- Query, arguments, and results tracked for each tool type

> ⚠️ **Note:** v0.2.5, v0.2.6, v0.2.7 had various issues. Use v0.2.8+.

---

## Data Export

### 7. Query & Export Data
**File**: `export_data.py`

Export your conversation records and logs programmatically:
- ✅ Query records with filters (namespace, agent, date range)
- ✅ Pagination for large datasets
- ✅ Export to JSON or CSV files
- ✅ Query and export logs by level
- ✅ Automatic server-side pagination for bulk exports

**Run:**
```bash
python examples/export_data.py
```

**What you'll see:**
- Records queried with various filters
- Paginated fetching for large datasets
- JSON and CSV files exported to disk
- Error logs filtered and exported

---

## Coding Assistant Integrations

### Claude Code
**File**: `claude_code_example.py`

Parse Claude Code CLI session logs and upload to MonkAI:
- ✅ List all projects and sessions
- ✅ Upload single session, project, or everything
- ✅ Exact token tracking from Anthropic API usage
- ✅ Tool call tracking (Read, Edit, Bash, Agent, etc.)

**Run:**
```bash
python examples/claude_code_example.py --token tk_your_token --namespace dev-productivity
```

#### Live tracking (Stop hook)
**File**: `claude_code_hook.py`

Envia a sessão automaticamente ao fim de cada turno do Claude Code:
- ✅ Hook `Stop` configurado em `~/.claude/settings.json`
- ✅ Padrão "agente pessoal": `namespace=personal-agents`, `agent=claude-<user>`
- ✅ Token via `MONKAI_TRACER_TOKEN`; nunca derruba o Claude Code em erro
- ✅ Complementa (não substitui) o backfill de `claude_code_example.py`

Ver docstring do arquivo para o setup completo (pip install, export do token e snippet do `settings.json`).

---

### Cline
**File**: `cline_example.py`

Parse Cline VS Code extension task history:
- ✅ Auto-detects VS Code, Cursor, and Windsurf
- ✅ Tracks tool usage (execute_command, read_file, write_to_file, etc.)
- ✅ Groups conversations by task
- ✅ Custom storage path support

**Run:**
```bash
python examples/cline_example.py --token tk_your_token --namespace dev-productivity
```

---

### OpenClaw
**File**: `openclaw_example.py`

Parse OpenClaw personal AI assistant session transcripts:
- ✅ Lists all agents and sessions
- ✅ JSONL transcript parsing from `~/.openclaw/`
- ✅ Multi-agent support
- ✅ Custom state directory (OPENCLAW_STATE_DIR)

**Run:**
```bash
python examples/openclaw_example.py --token tk_your_token --namespace dev-productivity
```

---

### GitHub Copilot
**File**: `copilot_example.py`

Track Copilot usage from multiple sources:
- ✅ Local Copilot Chat conversations
- ✅ GitHub org usage API (Business/Enterprise)
- ✅ CSV export from admin dashboard
- ✅ Acceptance rates, lines suggested/accepted

**Run:**
```bash
# Local chat history
python examples/copilot_example.py --token tk_your_token --mode chat

# GitHub API
python examples/copilot_example.py --token tk_your_token --mode api --github-token ghp_xxx --org MyOrg

# CSV import
python examples/copilot_example.py --token tk_your_token --mode csv --csv-file export.csv
```

---

## Other Integrations

### 8. LangChain
**File**: `langchain_example.py`
- Basic LangChain callback integration

### 7. Async Operations
**File**: `async_example.py`
- Async client usage patterns

### 8. Logging Integration
**File**: `logging_example.py`
- Service-level logging integration

### 9. JSON Upload
**File**: `send_json_files.py`
- Batch upload from JSON files

---

## Quick Start

### Install Dependencies
```bash
pip install monkai-trace>=0.2.7 openai-agents-python
```

### Set Environment Variables (Optional)
```bash
export MONKAI_TEST_TOKEN="tk_your_token_here"
export MONKAI_TEST_NAMESPACE="your-namespace"
export OPENAI_API_KEY="sk-your-openai-key"
```

### Run Examples
```bash
# Basic session management
python examples/session_management_basic.py

# Multi-user scenarios
python examples/session_management_multi_user.py

# Custom timeouts
python examples/session_management_custom_timeout.py

# OpenAI integration
python examples/openai_agents_example.py

# Multi-agent
python examples/openai_agents_multi_agent.py --token tk_your_token
```

---

## Use Case Guide

### I'm building a WhatsApp/Telegram bot
→ Start with: `session_management_multi_user.py`

### I need quick customer support (1-2 min sessions)
→ Start with: `session_management_custom_timeout.py` (quick support example)

### I'm doing long-running analysis (5-10 min thinking)
→ Start with: `session_management_custom_timeout.py` (analysis example)

### I want to track OpenAI Agents
→ Start with: `openai_agents_example.py`

### I have multiple specialized agents
→ Start with: `openai_agents_multi_agent.py`

### I'm using OpenAI's web search, code interpreter, or file search
→ Start with: `openai_agents_internal_tools.py`

### I want to track Claude Code usage
→ Start with: `claude_code_example.py`

### I want to track Cline usage
→ Start with: `cline_example.py`

### I want to track OpenClaw usage
→ Start with: `openclaw_example.py`

### I want to track GitHub Copilot usage
→ Start with: `copilot_example.py`

### I want to export my data for analysis
→ Start with: `export_data.py`
- 📋 Session IDs
- 👤 User IDs
- ⏱️ Session duration
- 💤 Inactivity time
- 🤖 Agent responses
- ✅ Success indicators

---

## Need Help?

- 📚 [Full Documentation](../docs/)
- 🔧 [API Reference](../docs/api_reference.md)
- 🎯 [Session Management Guide](../docs/session_management.md)
- 🤖 [OpenAI Agents Guide](../docs/openai_agents_integration.md)

---

## Contributing

Found a bug or have an example idea? Open an issue or PR!
