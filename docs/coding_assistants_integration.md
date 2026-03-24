# Coding Assistants Integration

MonkAI Trace can parse and upload usage data from popular coding assistants, enabling you to track developer productivity, token consumption, and tool usage across your team.

## Supported Tools

| Tool | Class | Data Source | Token Tracking |
|------|-------|-------------|----------------|
| **Claude Code** | `ClaudeCodeTracer` | JSONL session logs (`~/.claude/`) | Exact (Anthropic API usage) |
| **Cline / OpenClaw** | `ClineTracer` | Task history (VS Code extension storage) | Estimated (~4 chars/token) |
| **GitHub Copilot** | `CopilotTracer` | Chat history + GitHub API + CSV | Estimated / API metrics |

> **Note:** Cline was formerly known as "Claude Dev" and "OpenClaw". The `ClineTracer` handles all variants and auto-detects VS Code, Cursor, and Windsurf installations.

---

## Claude Code

### Overview

[Claude Code](https://claude.com/claude-code) is Anthropic's CLI for Claude. It stores conversation sessions as JSONL files:

```
~/.claude/projects/{encoded_path}/{session_uuid}.jsonl
```

Each line is a JSON object with types: `user`, `assistant`, `progress`, `system`, `file-history-snapshot`.

### Usage

```python
from monkai_trace import ClaudeCodeTracer

tracer = ClaudeCodeTracer(
    tracer_token="tk_your_token",
    namespace="dev-productivity"
)

# Upload all projects
result = tracer.upload_all_projects()
print(f"Uploaded {result['total_inserted']} records")

# Or upload a specific project
tracer.upload_project("~/.claude/projects/-Users-me-myproject/")

# Or a single session
tracer.upload_session("~/.claude/projects/-Users-me/abc123.jsonl")

# List available projects
for p in tracer.list_projects():
    print(f"{p['decoded_path']} — {p['session_count']} sessions")
```

### What Gets Tracked

- **Messages**: User prompts and Claude responses
- **Tool calls**: Read, Edit, Write, Bash, Glob, Grep, Agent, etc.
- **Tokens**: Exact input/output from Anthropic API usage, cache creation/read as process/memory
- **Sessions**: Each JSONL file = one session, grouped into conversation turns

### Path Encoding

Claude Code encodes project paths by replacing `/` with `-`:
- `/Users/me/project` → `-Users-me-project`

The tracer handles encoding/decoding automatically.

---

## Cline (OpenClaw)

### Overview

[Cline](https://github.com/cline/cline) (formerly Claude Dev / OpenClaw) is a VS Code extension for AI-assisted coding. It stores task history in the extension's global storage:

```
~/Library/Application Support/Code/User/globalStorage/
    saoudrizwan.claude-dev/tasks/{task_id}/
        api_conversation_history.json
        ui_messages.json
```

### Usage

```python
from monkai_trace import ClineTracer

tracer = ClineTracer(
    tracer_token="tk_your_token",
    namespace="dev-productivity"
)

# Auto-detects VS Code, Cursor, or Windsurf
result = tracer.upload_all_tasks()

# Or specify a custom path
tracer = ClineTracer(
    tracer_token="tk_your_token",
    namespace="dev-productivity",
    storage_dir="~/Library/Application Support/Cursor/User/globalStorage/saoudrizwan.claude-dev/tasks/"
)

# Upload a specific task
tracer.upload_task("/path/to/tasks/1234567890/")

# List tasks
for t in tracer.list_tasks():
    print(f"{t['task_id']} — {t.get('message_count', 0)} messages")
```

### Auto-Detection

The tracer searches these locations automatically:

| Editor | macOS Path |
|--------|-----------|
| VS Code | `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/tasks/` |
| Cursor | `~/Library/Application Support/Cursor/User/globalStorage/saoudrizwan.claude-dev/tasks/` |
| Windsurf | `~/Library/Application Support/Windsurf/User/globalStorage/saoudrizwan.claude-dev/tasks/` |

On Linux, paths use `~/.config/` instead of `~/Library/Application Support/`.

### What Gets Tracked

- **Messages**: User requests and assistant responses
- **Tool calls**: `execute_command`, `read_file`, `write_to_file`, `replace_in_file`, `search_files`, `browser_action`, etc.
- **Tool results**: Command output, file contents (truncated to 500 chars)
- **Tokens**: Estimated from content length (~4 chars per token)

---

## GitHub Copilot

### Overview

GitHub Copilot tracking supports three data sources:

1. **Local Chat History** — VS Code Copilot Chat conversations
2. **GitHub API** — Org-level usage metrics (Business/Enterprise)
3. **CSV Export** — Admin dashboard exports

### Usage

#### Local Chat History

```python
from monkai_trace import CopilotTracer

tracer = CopilotTracer(
    tracer_token="tk_your_token",
    namespace="dev-productivity"
)

result = tracer.upload_chat_history()
```

#### GitHub Org Usage API

Requires a GitHub PAT with `manage_billing:copilot` or `org:read` scope and Copilot Business/Enterprise.

```python
result = tracer.upload_org_usage(
    github_token="ghp_your_token",
    org="BeMonkAI",
    since="2026-03-01",
    until="2026-03-24"
)
```

This uploads daily usage logs with:
- Total suggestions shown/accepted
- Lines suggested/accepted
- Active users
- Acceptance rate
- Per-language and per-editor breakdown

#### CSV Import

Export from the [GitHub admin dashboard](https://github.com/organizations/YOUR_ORG/settings/copilot) and import:

```python
result = tracer.upload_from_csv("copilot_usage_export.csv")
```

Expected CSV columns:
```
date, user, editor, language, suggestions_shown, suggestions_accepted, lines_suggested, lines_accepted
```

### What Gets Tracked

| Source | Data Type | Granularity |
|--------|-----------|-------------|
| Chat History | `ConversationRecord` | Per conversation |
| Org API | `LogEntry` | Per day (org aggregate) |
| CSV Export | `LogEntry` | Per day per user |

---

## Common Patterns

### Upload All Coding Assistant Data

```python
from monkai_trace import ClaudeCodeTracer, ClineTracer, CopilotTracer

token = "tk_your_token"
ns = "dev-productivity"

# Claude Code
claude = ClaudeCodeTracer(tracer_token=token, namespace=ns)
claude.upload_all_projects()

# Cline
cline = ClineTracer(tracer_token=token, namespace=ns)
cline.upload_all_tasks()

# Copilot
copilot = CopilotTracer(tracer_token=token, namespace=ns)
copilot.upload_chat_history()
```

### Filter by Source in Queries

All records include a `source` field (`claude-code`, `cline`, or `copilot`) so you can filter in the dashboard or via API:

```python
from monkai_trace import MonkAIClient

client = MonkAIClient(tracer_token="tk_your_token")

# Query only Claude Code sessions
records = client.query_records(
    namespace="dev-productivity",
    agent="claude-code"
)
```

### Scheduled Uploads

Use a cron job or scheduled task to upload new data periodically:

```bash
# crontab -e
0 */6 * * * python /path/to/upload_all.py
```

---

## Examples

- [`examples/claude_code_example.py`](../examples/claude_code_example.py) — Parse and upload Claude Code sessions
- [`examples/cline_example.py`](../examples/cline_example.py) — Parse and upload Cline tasks
- [`examples/copilot_example.py`](../examples/copilot_example.py) — Upload Copilot data from chat/API/CSV
