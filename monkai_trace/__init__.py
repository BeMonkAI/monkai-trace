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

__version__ = "0.2.17"
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
]
