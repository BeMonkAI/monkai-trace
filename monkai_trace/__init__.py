"""
MonkAI Trace - Python SDK for AI Agent Monitoring

Official Python client for MonkAI. Track and analyze your AI agent conversations.
"""

from .client import MonkAIClient
from .models import (
    ConversationRecord,
    LogEntry,
    Message,
    Transfer,
    TokenUsage
)
from .session_manager import SessionManager, PersistentSessionManager

try:
    from .async_client import AsyncMonkAIClient
except ImportError:
    AsyncMonkAIClient = None

# Coding assistant integrations (lazy imports — no extra deps required)
try:
    from .integrations.claude_code import ClaudeCodeTracer
except ImportError:
    ClaudeCodeTracer = None

try:
    from .integrations.cline import ClineTracer
except ImportError:
    ClineTracer = None

try:
    from .integrations.copilot import CopilotTracer
except ImportError:
    CopilotTracer = None

__version__ = "0.2.18"
__all__ = [
    "MonkAIClient",
    "AsyncMonkAIClient",
    "ConversationRecord",
    "LogEntry",
    "Message",
    "Transfer",
    "TokenUsage",
    "SessionManager",
    "PersistentSessionManager",
    "ClaudeCodeTracer",
    "ClineTracer",
    "CopilotTracer",
]
