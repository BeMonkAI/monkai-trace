# Session Management Guide

## Overview
MonkAI automatically manages user sessions with configurable inactivity timeout to group related conversations and separate multiple users.

## Default Behavior
- **Inactivity Timeout**: 2 minutes (120 seconds)
- **Session ID Format**: `{namespace}-{user_id}-{timestamp}`
- **Automatic Renewal**: Sessions renew on activity
- **Multi-User Support**: Each user gets isolated sessions

## Why Session Management?

Without session management, every agent interaction creates a new session, making it difficult to:
- Track continuous conversations
- Separate multiple users interacting with the same agent
- Analyze conversation patterns over time

With session management:
- ✅ Continuous conversations maintain the same `session_id`
- ✅ Each user gets their own isolated sessions
- ✅ Inactive sessions automatically expire and create new ones
- ✅ Dashboard shows clear user separation

## Usage

### Basic Usage

```python
from monkai_trace.integrations.openai_agents import MonkAIRunHooks

hooks = MonkAIRunHooks(
    tracer_token="tk_your_token",
    namespace="customer-support",
    inactivity_timeout=120  # 2 minutos (default)
)

# Set user ID before running
hooks.set_user_id("user-12345")

result = await Runner.run(agent, "Hello", hooks=hooks)
```

### Custom Timeout

```python
# Sessões mais longas (5 minutos)
hooks = MonkAIRunHooks(
    tracer_token="tk_your_token",
    namespace="customer-support",
    inactivity_timeout=300  # 5 minutos
)

# Sessões mais curtas (30 segundos)
hooks = MonkAIRunHooks(
    tracer_token="tk_your_token",
    namespace="customer-support",
    inactivity_timeout=30  # 30 segundos
)
```

### Multi-User Support

```python
# User 1
hooks.set_user_id("user-001")
await Runner.run(agent, "Hi", hooks=hooks)

# User 2 (sessão separada automaticamente)
hooks.set_user_id("user-002")
await Runner.run(agent, "Hello", hooks=hooks)

# User 1 again (mesma sessão se dentro do timeout)
hooks.set_user_id("user-001")
await Runner.run(agent, "How are you?", hooks=hooks)
```

### WhatsApp Integration

For WhatsApp bots, use the WhatsApp user ID as the user identifier:

```python
# Extract WhatsApp user from incoming message
whatsapp_user_id = message['from']  # e.g., "5511999999999"

hooks.set_user_id(whatsapp_user_id)
await Runner.run(agent, message['text'], hooks=hooks)
```

### Custom Session Manager

You can provide your own `SessionManager` for advanced control:

```python
from monkai_trace.session_manager import SessionManager

# Create custom session manager
session_manager = SessionManager(inactivity_timeout=180)

hooks = MonkAIRunHooks(
    tracer_token="tk_your_token",
    namespace="customer-support",
    session_manager=session_manager  # Use custom manager
)
```

## How It Works

1. **First Interaction**: Creates a new session with format `{namespace}-{user_id}-{timestamp}`
2. **Subsequent Interactions**: 
   - If within timeout → Reuses same session
   - If after timeout → Creates new session
3. **Activity Tracking**: Each interaction updates the session's last activity timestamp
4. **Session Expiration**: Sessions expire after `inactivity_timeout` seconds of no activity

## Session Lifecycle Example

```python
hooks = MonkAIRunHooks(
    tracer_token="tk_your_token",
    namespace="support",
    inactivity_timeout=120  # 2 minutes
)

# 00:00 - User starts conversation
hooks.set_user_id("user-123")
await Runner.run(agent, "Hello", hooks=hooks)
# Session: support-user-123-20250107-120000

# 00:30 - User continues (within 2 min)
hooks.set_user_id("user-123")
await Runner.run(agent, "What's the weather?", hooks=hooks)
# Session: support-user-123-20250107-120000 (same)

# 03:00 - User returns (after 2 min timeout)
hooks.set_user_id("user-123")
await Runner.run(agent, "Hello again", hooks=hooks)
# Session: support-user-123-20250107-120300 (new)
```

## Dashboard Filtering

The MonkAI dashboard automatically groups conversations by `(session_id, user_id)` and provides:

- **User Filter**: Filter conversations by specific user
- **Session Status**: Visual indicators for active vs expired sessions
- **User Badges**: See which user each conversation belongs to

## Best Practices

### 1. Always Set User ID

```python
# ✅ GOOD: Explicit user ID
hooks.set_user_id("user-12345")
await Runner.run(agent, "Hello", hooks=hooks)

# ❌ BAD: No user ID (defaults to "anonymous")
await Runner.run(agent, "Hello", hooks=hooks)
```

### 2. Use Appropriate Timeouts

```python
# Customer support (quick interactions)
inactivity_timeout=120  # 2 minutes

# Long-running tasks (data analysis, etc.)
inactivity_timeout=600  # 10 minutes

# Real-time chat
inactivity_timeout=60  # 1 minute
```

### 3. WhatsApp/Messaging Apps

```python
# Use the platform's user ID directly
whatsapp_id = message['from']
hooks.set_user_id(whatsapp_id)
```

### 4. Force New Sessions

```python
# Start a completely new conversation
hooks.session_manager.close_session("user-123")
hooks.set_user_id("user-123")
await Runner.run(agent, "Start over", hooks=hooks)
```

## API Reference

### SessionManager

```python
class SessionManager:
    def __init__(self, inactivity_timeout: int = 120)
    
    def get_or_create_session(
        self,
        user_id: str,
        namespace: str,
        force_new: bool = False
    ) -> str
    
    def update_activity(self, user_id: str) -> None
    
    def close_session(self, user_id: str) -> None
    
    def cleanup_expired(self) -> int
    
    def get_session_info(self, user_id: str) -> Optional[Dict]
```

### MonkAIRunHooks

```python
class MonkAIRunHooks(RunHooks):
    def __init__(
        self,
        tracer_token: str,
        namespace: str,
        auto_upload: bool = True,
        estimate_system_tokens: bool = True,
        batch_size: int = 10,
        session_manager: Optional[SessionManager] = None,
        inactivity_timeout: int = 120
    )
    
    def set_user_id(self, user_id: str) -> None
```

## Troubleshooting

### Sessions Not Persisting

**Problem**: Each interaction creates a new session

**Solution**: Make sure you're setting the same `user_id`:

```python
# ✅ Correct
hooks.set_user_id("user-123")
await Runner.run(agent, "Message 1", hooks=hooks)
hooks.set_user_id("user-123")  # Same user
await Runner.run(agent, "Message 2", hooks=hooks)

# ❌ Wrong
hooks.set_user_id("user-123")
await Runner.run(agent, "Message 1", hooks=hooks)
hooks.set_user_id("user-456")  # Different user
await Runner.run(agent, "Message 2", hooks=hooks)
```

### Multiple Users Getting Same Session

**Problem**: Different users share sessions

**Solution**: Use unique user IDs for each user:

```python
# ✅ Correct
hooks.set_user_id(f"whatsapp-{phone_number}")

# ❌ Wrong
hooks.set_user_id("user")  # Same for everyone
```

### Sessions Expiring Too Quickly

**Problem**: Sessions expire before conversation ends

**Solution**: Increase the timeout:

```python
hooks = MonkAIRunHooks(
    tracer_token="tk_your_token",
    namespace="support",
    inactivity_timeout=600  # 10 minutes instead of 2
)
```

## Examples

See the `examples/` directory for practical, executable examples:

### Session Management Examples
- **[Basic Sessions](../examples/session_management_basic.py)** - Automatic session creation and timeout behavior
- **[Multi-User Scenarios](../examples/session_management_multi_user.py)** - WhatsApp bot simulation with concurrent users
- **[Custom Timeouts](../examples/session_management_custom_timeout.py)** - Configure timeouts for different use cases

### Integration Examples
- **[OpenAI Agents](../examples/openai_agents_example.py)** - Method 3 shows session management integration
- **[Multi-Agent Handoffs](../examples/openai_agents_multi_agent.py)** - Multi-user session handling

**Quick start:**
```bash
python examples/session_management_basic.py
```

See [examples/README.md](../examples/README.md) for complete guide and use case recommendations.
