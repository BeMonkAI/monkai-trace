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

__version__ = "0.2.15"
__all__ = [
    "MonkAIClient",
    "ConversationRecord",
    "LogEntry",
    "Message",
    "Transfer",
    "TokenUsage",
    "SessionManager",
    "PersistentSessionManager",
]
