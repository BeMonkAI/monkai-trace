"""Pytest configuration and fixtures"""

import pytest
from unittest.mock import Mock, AsyncMock
from monkai_trace import MonkAIClient
from monkai_trace.models import ConversationRecord, Message, TokenUsage


@pytest.fixture
def mock_client():
    """Mock MonkAI client for testing"""
    client = Mock(spec=MonkAIClient)
    client.upload_record = Mock(return_value={"success": True})
    client.upload_records_batch = Mock(return_value={"total_inserted": 1, "failures": []})
    return client


@pytest.fixture
def sample_conversation_record():
    """Sample conversation record for testing"""
    return ConversationRecord(
        namespace="test-namespace",
        agent="test-agent",
        session_id="test-session-123",
        msg=Message(
            role="assistant",
            content="Hello, how can I help you?",
            sender="test-agent"
        ),
        input_tokens=10,
        output_tokens=20,
        process_tokens=5,
        memory_tokens=15,
        total_tokens=50
    )


@pytest.fixture
def sample_token_usage():
    """Sample token usage for testing"""
    mock_usage = Mock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 20
    mock_usage.total_tokens = 30
    mock_usage.requests = 1
    return mock_usage


@pytest.fixture
def mock_agent():
    """Mock OpenAI Agent"""
    agent = Mock()
    agent.name = "Test Agent"
    agent.instructions = "You are a helpful assistant for testing purposes."
    return agent


@pytest.fixture
def mock_context():
    """Mock RunContextWrapper"""
    context = Mock()
    usage = Mock()
    usage.input_tokens = 10
    usage.output_tokens = 20
    usage.total_tokens = 30
    usage.requests = 1
    context.usage = usage
    return context


# E2E test fixtures
@pytest.fixture
def monkai_credentials():
    """Get MonkAI test credentials from environment for E2E tests."""
    import os
    token = os.getenv("MONKAI_TEST_TOKEN")
    if not token:
        pytest.skip("MONKAI_TEST_TOKEN environment variable not set")
    
    return {
        "token": token,
        "namespace": os.getenv("MONKAI_TEST_NAMESPACE", "e2e-test-service")
    }


@pytest.fixture
def monkai_client(monkai_credentials):
    """Create a real MonkAI client for E2E verification."""
    return MonkAIClient(tracer_token=monkai_credentials["token"])

