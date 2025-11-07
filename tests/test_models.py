"""Tests for Pydantic models"""

import pytest
from monkai_trace.models import (
    Message,
    Transfer,
    TokenUsage,
    ConversationRecord,
    LogEntry
)


def test_message_creation():
    """Test Message model creation"""
    msg = Message(
        role="user",
        content="Hello world",
        sender="test-user"
    )
    assert msg.role == "user"
    assert msg.content == "Hello world"
    assert msg.sender == "test-user"


def test_transfer_creation():
    """Test Transfer model creation"""
    transfer = Transfer(
        from_agent="agent-a",
        to_agent="agent-b",
        reason="User requested specialist help"
    )
    assert transfer.from_agent == "agent-a"
    assert transfer.to_agent == "agent-b"
    assert transfer.reason == "User requested specialist help"


def test_token_usage_from_openai_agents(sample_token_usage):
    """Test TokenUsage.from_openai_agents_usage"""
    token_usage = TokenUsage.from_openai_agents_usage(
        sample_token_usage,
        system_prompt_tokens=5,
        context_tokens=15
    )
    
    assert token_usage.input_tokens == 10
    assert token_usage.output_tokens == 20
    assert token_usage.process_tokens == 5
    assert token_usage.memory_tokens == 15
    assert token_usage.total_tokens == 50
    assert token_usage.requests == 1


def test_token_usage_auto_total():
    """Test TokenUsage auto-calculates total"""
    token_usage = TokenUsage(
        input_tokens=10,
        output_tokens=20,
        process_tokens=5,
        memory_tokens=15
    )
    assert token_usage.total_tokens == 50


def test_conversation_record_with_single_message():
    """Test ConversationRecord with single message"""
    record = ConversationRecord(
        namespace="test",
        agent="test-agent",
        msg=Message(role="assistant", content="Hello"),
        input_tokens=5,
        output_tokens=10
    )
    assert record.namespace == "test"
    assert record.agent == "test-agent"
    assert isinstance(record.msg, Message)


def test_conversation_record_with_multiple_messages():
    """Test ConversationRecord with message list"""
    messages = [
        Message(role="user", content="Hi"),
        Message(role="assistant", content="Hello")
    ]
    record = ConversationRecord(
        namespace="test",
        agent="test-agent",
        msg=messages
    )
    assert len(record.msg) == 2


def test_log_entry_creation():
    """Test LogEntry model creation"""
    log = LogEntry(
        namespace="test",
        level="info",
        message="Test log message",
        agent="test-agent"
    )
    assert log.namespace == "test"
    assert log.level == "info"
    assert log.message == "Test log message"
    assert log.agent == "test-agent"
