"""Tests for OpenAI Agents integration"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from monkai_trace.integrations.openai_agents import MonkAIRunHooks
from monkai_trace.models import Message, Transfer


@pytest.mark.asyncio
async def test_hooks_initialization():
    """Test MonkAIRunHooks initialization"""
    hooks = MonkAIRunHooks(
        tracer_token="tk_test",
        namespace="test-namespace",
        auto_upload=False
    )
    
    assert hooks.namespace == "test-namespace"
    assert hooks.auto_upload == False
    assert hooks.batch_size == 10


@pytest.mark.asyncio
async def test_on_agent_start(mock_context, mock_agent):
    """Test on_agent_start hook"""
    hooks = MonkAIRunHooks(
        tracer_token="tk_test",
        namespace="test",
        auto_upload=False,
        estimate_system_tokens=True
    )
    
    await hooks.on_agent_start(mock_context, mock_agent)
    
    # Should generate session ID
    assert hooks._current_session is not None
    
    # Should estimate system prompt tokens
    assert hooks._system_prompt_tokens > 0


@pytest.mark.asyncio
async def test_on_agent_end(mock_context, mock_agent):
    """Test on_agent_end hook"""
    hooks = MonkAIRunHooks(
        tracer_token="tk_test",
        namespace="test",
        auto_upload=False
    )
    
    # Mock the client upload
    hooks.client.upload_records_batch = Mock(return_value={"total_inserted": 1})
    
    # Start agent first
    await hooks.on_agent_start(mock_context, mock_agent)
    
    # End agent
    await hooks.on_agent_end(mock_context, mock_agent, "Test output")
    
    # Should create a batch buffer entry
    assert len(hooks._batch_buffer) == 1
    
    # Verify record structure
    record = hooks._batch_buffer[0]
    assert record.namespace == "test"
    assert record.agent == "Test Agent"
    assert record.input_tokens == 10
    assert record.output_tokens == 20


@pytest.mark.asyncio
async def test_on_handoff(mock_context):
    """Test on_handoff hook"""
    hooks = MonkAIRunHooks(
        tracer_token="tk_test",
        namespace="test",
        auto_upload=False
    )
    
    agent_a = Mock()
    agent_a.name = "Agent A"
    
    agent_b = Mock()
    agent_b.name = "Agent B"
    
    await hooks.on_handoff(mock_context, agent_a, agent_b)
    
    # Should track the transfer
    assert len(hooks._transfers) == 1
    assert hooks._transfers[0].from_agent == "Agent A"
    assert hooks._transfers[0].to_agent == "Agent B"
    
    # Should ALSO create a tool message for frontend visualization
    assert len(hooks._messages) == 1
    assert hooks._messages[0].role == "tool"
    assert hooks._messages[0].tool_name == "transfer_to_agent"
    assert "Agent B" in hooks._messages[0].content
    assert hooks._messages[0].tool_calls[0]["arguments"]["from_agent"] == "Agent A"
    assert hooks._messages[0].tool_calls[0]["arguments"]["to_agent"] == "Agent B"


@pytest.mark.asyncio
async def test_on_tool_start_and_end(mock_context, mock_agent):
    """Test on_tool_start and on_tool_end hooks"""
    hooks = MonkAIRunHooks(
        tracer_token="tk_test",
        namespace="test",
        auto_upload=False
    )
    
    tool = Mock()
    tool.name = "search_tool"
    
    # Start tool
    await hooks.on_tool_start(mock_context, mock_agent, tool)
    
    # Should add message
    assert len(hooks._messages) == 1
    assert hooks._messages[0].tool_name == "search_tool"
    
    # End tool
    await hooks.on_tool_end(mock_context, mock_agent, tool, "Search results")
    
    # Should add result message
    assert len(hooks._messages) == 2
    assert hooks._messages[1].content == "Search results"


@pytest.mark.asyncio
async def test_batch_upload_threshold(mock_context, mock_agent):
    """Test batch upload when threshold is reached"""
    hooks = MonkAIRunHooks(
        tracer_token="tk_test",
        namespace="test",
        auto_upload=True,
        batch_size=2
    )
    
    # Mock the client upload
    hooks.client.upload_records_batch = Mock(return_value={"total_inserted": 2})
    
    # Process first agent
    await hooks.on_agent_start(mock_context, mock_agent)
    await hooks.on_agent_end(mock_context, mock_agent, "Output 1")
    
    # Buffer should have 1 record
    assert len(hooks._batch_buffer) == 1
    
    # Process second agent
    await hooks.on_agent_start(mock_context, mock_agent)
    await hooks.on_agent_end(mock_context, mock_agent, "Output 2")
    
    # Should have triggered upload and cleared buffer
    hooks.client.upload_records_batch.assert_called_once()


@pytest.mark.asyncio
async def test_token_segmentation(mock_context, mock_agent):
    """Test that all 4 token types are captured"""
    hooks = MonkAIRunHooks(
        tracer_token="tk_test",
        namespace="test",
        auto_upload=False,
        estimate_system_tokens=True
    )
    
    await hooks.on_agent_start(mock_context, mock_agent)
    await hooks.on_agent_end(mock_context, mock_agent, "Test output")
    
    record = hooks._batch_buffer[0]
    
    # All 4 token types should be present
    assert record.input_tokens == 10  # From mock_context
    assert record.output_tokens == 20  # From mock_context
    assert record.process_tokens > 0  # Estimated from agent.instructions
    assert record.memory_tokens == 0  # Default for single-turn
    assert record.total_tokens > 0


@pytest.mark.asyncio
async def test_session_continuity(mock_context, mock_agent):
    """Test session ID remains consistent across multiple runs"""
    hooks = MonkAIRunHooks(
        tracer_token="tk_test",
        namespace="test",
        auto_upload=False
    )
    
    # First run
    await hooks.on_agent_start(mock_context, mock_agent)
    first_session = hooks._current_session
    await hooks.on_agent_end(mock_context, mock_agent, "Output 1")
    
    # Second run - session should be reset
    await hooks.on_agent_start(mock_context, mock_agent)
    second_session = hooks._current_session
    await hooks.on_agent_end(mock_context, mock_agent, "Output 2")
    
    # Sessions should be different for different runs
    assert first_session != second_session


@pytest.mark.asyncio
async def test_capture_user_message_from_context_input(mock_agent):
    """Test user message capture from context.input"""
    mock_context = Mock()
    mock_context.input = "Hello from context.input"
    usage = Mock()
    usage.input_tokens = 10
    usage.output_tokens = 20
    usage.total_tokens = 30
    usage.requests = 1
    mock_context.usage = usage
    
    hooks = MonkAIRunHooks(
        tracer_token="tk_test",
        namespace="test",
        auto_upload=False
    )
    await hooks.on_agent_start(mock_context, mock_agent)
    
    assert len(hooks._messages) == 1
    assert hooks._messages[0].role == "user"
    assert hooks._messages[0].content == "Hello from context.input"


@pytest.mark.asyncio
async def test_capture_user_message_from_context_messages(mock_agent):
    """Test user message capture from context.messages"""
    user_msg = Mock()
    user_msg.role = "user"
    user_msg.content = "Hello from context.messages"
    
    mock_context = Mock()
    mock_context.input = None  # Force fallback to messages
    mock_context.messages = [user_msg]
    usage = Mock()
    usage.input_tokens = 10
    usage.output_tokens = 20
    usage.total_tokens = 30
    usage.requests = 1
    mock_context.usage = usage
    
    hooks = MonkAIRunHooks(
        tracer_token="tk_test",
        namespace="test",
        auto_upload=False
    )
    await hooks.on_agent_start(mock_context, mock_agent)
    
    assert len(hooks._messages) == 1
    assert hooks._messages[0].role == "user"
    assert "Hello from context.messages" in hooks._messages[0].content


@pytest.mark.asyncio
async def test_set_user_input_priority(mock_agent):
    """Test that set_user_input() takes priority over context"""
    mock_context = Mock()
    mock_context.input = "From context"
    usage = Mock()
    usage.input_tokens = 10
    usage.output_tokens = 20
    usage.total_tokens = 30
    usage.requests = 1
    mock_context.usage = usage
    
    hooks = MonkAIRunHooks(
        tracer_token="tk_test",
        namespace="test",
        auto_upload=False
    )
    hooks.set_user_input("From set_user_input")
    await hooks.on_agent_start(mock_context, mock_agent)
    
    assert len(hooks._messages) == 1
    assert hooks._messages[0].content == "From set_user_input"


@pytest.mark.asyncio
async def test_warning_when_no_user_message(mock_agent, capsys):
    """Test warning is logged when no user message is captured"""
    mock_context = Mock()
    mock_context.input = None
    mock_context.messages = None
    usage = Mock()
    usage.input_tokens = 10
    usage.output_tokens = 20
    usage.total_tokens = 30
    usage.requests = 1
    mock_context.usage = usage
    
    hooks = MonkAIRunHooks(
        tracer_token="tk_test",
        namespace="test",
        auto_upload=False
    )
    await hooks.on_agent_start(mock_context, mock_agent)
    
    # No user message should be in the buffer
    assert len(hooks._messages) == 0
    
    # Check that warning was printed
    captured = capsys.readouterr()
    assert "WARNING: No user message captured" in captured.out


@pytest.mark.asyncio
async def test_session_timeout_creates_new_session(mock_context, mock_agent):
    """Test that inactive sessions get new session_id"""
    import time
    
    hooks = MonkAIRunHooks(
        tracer_token="tk_test",
        namespace="test",
        inactivity_timeout=1,  # 1 segundo
        auto_upload=False
    )
    hooks.set_user_id("user123")
    
    # Primera interação
    await hooks.on_agent_start(mock_context, mock_agent)
    session1 = hooks._current_session
    
    time.sleep(2)  # Esperar timeout
    
    # Segunda interação (nova sessão)
    await hooks.on_agent_start(mock_context, mock_agent)
    session2 = hooks._current_session
    
    assert session1 != session2
    assert "user123" in session1
    assert "user123" in session2


@pytest.mark.asyncio
async def test_session_continues_within_timeout(mock_context, mock_agent):
    """Test that sessions continue within timeout"""
    hooks = MonkAIRunHooks(
        tracer_token="tk_test",
        namespace="test",
        inactivity_timeout=60,  # 60 segundos
        auto_upload=False
    )
    hooks.set_user_id("user123")
    
    # Primera interação
    await hooks.on_agent_start(mock_context, mock_agent)
    session1 = hooks._current_session
    
    # Segunda interação (dentro do timeout)
    await hooks.on_agent_start(mock_context, mock_agent)
    session2 = hooks._current_session
    
    # Deve ser a mesma sessão
    assert session1 == session2


@pytest.mark.asyncio
async def test_multi_user_sessions(mock_context, mock_agent):
    """Test that different users get different sessions"""
    hooks = MonkAIRunHooks(
        tracer_token="tk_test",
        namespace="test",
        inactivity_timeout=60,
        auto_upload=False
    )
    
    # User 1
    hooks.set_user_id("user1")
    await hooks.on_agent_start(mock_context, mock_agent)
    session1 = hooks._current_session
    
    # User 2
    hooks.set_user_id("user2")
    await hooks.on_agent_start(mock_context, mock_agent)
    session2 = hooks._current_session
    
    # Sessões diferentes
    assert session1 != session2
    assert "user1" in session1
    assert "user2" in session2


@pytest.mark.asyncio
async def test_session_id_format(mock_context, mock_agent):
    """Test session ID format"""
    hooks = MonkAIRunHooks(
        tracer_token="tk_test",
        namespace="my-namespace",
        inactivity_timeout=60,
        auto_upload=False
    )
    hooks.set_user_id("user123")
    
    await hooks.on_agent_start(mock_context, mock_agent)
    session_id = hooks._current_session
    
    # Format: {namespace}-{user_id}-{timestamp}
    assert session_id.startswith("my-namespace-user123-")
    
    # Should have timestamp in format YYYYMMDD-HHMMSS
    parts = session_id.split("-")
    assert len(parts) >= 3
