"""
Tests for MonkAI Agent integration
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from monkai_trace.integrations.monkai_agent import MonkAIAgentHooks
from monkai_trace.models import ConversationRecord, Message, Transfer


@pytest.fixture
def mock_agent():
    """Create a mock MonkAI Agent"""
    agent = Mock()
    agent.name = "Test Agent"
    agent.instructions = "You are a helpful test agent with clear instructions."
    return agent


@pytest.fixture
def mock_context():
    """Create a mock AgentContext"""
    context = Mock()
    usage = Mock()
    usage.input_tokens = 100
    usage.output_tokens = 150
    usage.process_tokens = 25
    context.usage = usage
    return context


@pytest.fixture
def hooks():
    """Create MonkAIAgentHooks instance for testing"""
    with patch('monkai_trace.integrations.monkai_agent.MonkAIClient'):
        return MonkAIAgentHooks(
            tracer_token="tk_test_token",
            namespace="test-namespace",
            auto_upload=False  # Disable auto-upload for testing
        )


class TestMonkAIAgentHooks:
    """Test suite for MonkAIAgentHooks"""
    
    def test_initialization(self):
        """Test hooks initialization with correct parameters"""
        with patch('monkai_trace.integrations.monkai_agent.MonkAIClient') as mock_client:
            hooks = MonkAIAgentHooks(
                tracer_token="tk_test",
                namespace="test-ns",
                auto_upload=True,
                batch_size=20
            )
            
            assert hooks.tracer_token == "tk_test"
            assert hooks.namespace == "test-ns"
            assert hooks.auto_upload is True
            assert hooks.batch_size == 20
            mock_client.assert_called_once()
    
    def test_initialization_defaults(self):
        """Test hooks initialization with default values"""
        with patch('monkai_trace.integrations.monkai_agent.MonkAIClient'):
            hooks = MonkAIAgentHooks(
                tracer_token="tk_test",
                namespace="test-ns"
            )
            
            assert hooks.auto_upload is True
            assert hooks.estimate_system_tokens is True
            assert hooks.batch_size == 10
    
    def test_on_agent_start(self, hooks, mock_agent):
        """Test on_agent_start generates session ID and estimates tokens"""
        hooks.on_agent_start(mock_agent)
        
        # Session ID should be generated
        assert hooks._session_id is not None
        assert len(hooks._session_id) == 36  # UUID format
        
        # Agent name should be tracked
        assert hooks._current_agent_name == "Test Agent"
        
        # State should be reset
        assert hooks._messages == []
        assert hooks._transfers == []
        
        # Memory tokens should be estimated from instructions
        assert hooks._token_counts["memory"] > 0
    
    def test_on_agent_start_no_token_estimation(self, mock_agent):
        """Test on_agent_start without token estimation"""
        with patch('monkai_trace.integrations.monkai_agent.MonkAIClient'):
            hooks = MonkAIAgentHooks(
                tracer_token="tk_test",
                namespace="test-ns",
                estimate_system_tokens=False
            )
            
            hooks.on_agent_start(mock_agent)
            assert hooks._token_counts["memory"] == 0
    
    def test_on_agent_end_creates_record(self, hooks, mock_agent, mock_context):
        """Test on_agent_end creates conversation record with correct data"""
        # Setup
        hooks.on_agent_start(mock_agent)
        hooks._messages = [
            Message(role="user", content="Hello", sender="User"),
            Message(role="assistant", content="Hi there!", sender="Test Agent")
        ]
        
        # Execute
        hooks.on_agent_end(mock_agent, mock_context, "Hi there!")
        
        # Verify record was created and batched
        assert len(hooks._batch_buffer) == 1
        record = hooks._batch_buffer[0]
        
        assert isinstance(record, ConversationRecord)
        assert record.namespace == "test-namespace"
        assert record.agent == "Test Agent"
        assert record.session_id == hooks._session_id
        assert len(record.msg) == 2
        assert record.input_tokens == 100
        assert record.output_tokens == 150
        assert record.process_tokens == 25
    
    def test_on_agent_end_with_auto_upload(self, mock_agent, mock_context):
        """Test on_agent_end triggers upload when batch size reached"""
        with patch('monkai_trace.integrations.monkai_agent.MonkAIClient') as mock_client:
            hooks = MonkAIAgentHooks(
                tracer_token="tk_test",
                namespace="test-ns",
                auto_upload=True,
                batch_size=2
            )
            
            # Run twice to reach batch size
            for _ in range(2):
                hooks.on_agent_start(mock_agent)
                hooks.on_agent_end(mock_agent, mock_context)
            
            # Verify upload was called
            hooks.client.upload_records_batch.assert_called_once()
    
    def test_on_message(self, hooks, mock_agent):
        """Test on_message tracks messages correctly"""
        message = {
            "role": "user",
            "content": "Hello, how are you?",
            "sender": "User"
        }
        
        hooks.on_message(mock_agent, message)
        
        assert len(hooks._messages) == 1
        msg = hooks._messages[0]
        assert msg.role == "user"
        assert msg.content == "Hello, how are you?"
        assert msg.sender == "User"
        assert msg.timestamp is not None
        
        # Input tokens should be updated
        assert hooks._token_counts["input"] > 0
    
    def test_on_message_assistant_response(self, hooks, mock_agent):
        """Test on_message tracks assistant messages"""
        message = {
            "role": "assistant",
            "content": "I'm doing great, thanks for asking!",
            "sender": "Test Agent"
        }
        
        hooks.on_message(mock_agent, message)
        
        assert len(hooks._messages) == 1
        assert hooks._messages[0].role == "assistant"
        
        # Output tokens should be updated
        assert hooks._token_counts["output"] > 0
    
    def test_on_handoff(self, hooks, mock_agent):
        """Test on_handoff tracks agent transfers"""
        from_agent = Mock(name="Triage Agent")
        from_agent.name = "Triage Agent"
        
        to_agent = Mock(name="Billing Agent")
        to_agent.name = "Billing Agent"
        
        hooks.on_handoff(
            from_agent=from_agent,
            to_agent=to_agent,
            reason="Billing inquiry detected"
        )
        
        assert len(hooks._transfers) == 1
        transfer = hooks._transfers[0]
        assert isinstance(transfer, Transfer)
        assert transfer.from_agent == "Triage Agent"
        assert transfer.to_agent == "Billing Agent"
        assert transfer.reason == "Billing inquiry detected"
        assert transfer.timestamp is not None
    
    def test_on_tool_start(self, hooks, mock_agent):
        """Test on_tool_start tracks tool execution"""
        tool_input = {"query": "weather in Paris", "units": "celsius"}
        
        hooks.on_tool_start(mock_agent, "search_weather", tool_input)
        
        assert len(hooks._messages) == 1
        msg = hooks._messages[0]
        assert msg.role == "tool"
        assert "search_weather" in msg.content
        assert msg.tool_calls is not None
        assert msg.tool_calls[0]["name"] == "search_weather"
        
        # Process tokens should be updated
        assert hooks._token_counts["process"] > 0
    
    def test_on_tool_end(self, hooks, mock_agent):
        """Test on_tool_end tracks tool results"""
        tool_output = {"temperature": 15, "condition": "cloudy"}
        
        hooks.on_tool_end(mock_agent, "search_weather", tool_output)
        
        assert len(hooks._messages) == 1
        msg = hooks._messages[0]
        assert msg.role == "tool"
        assert "Tool result" in msg.content
        
        # Process tokens should be updated
        assert hooks._token_counts["process"] > 0
    
    def test_flush_batch(self, hooks, mock_agent, mock_context):
        """Test manual flush uploads pending records"""
        # Create some records
        hooks.on_agent_start(mock_agent)
        hooks.on_agent_end(mock_agent, mock_context)
        
        assert len(hooks._batch_buffer) == 1
        
        # Flush
        hooks.flush()
        
        # Verify upload was called
        hooks.client.upload_records_batch.assert_called_once()
        assert len(hooks._batch_buffer) == 0
    
    def test_reset_session(self, hooks, mock_agent):
        """Test reset_session clears session ID"""
        hooks.on_agent_start(mock_agent)
        old_session = hooks._session_id
        
        hooks.reset_session()
        assert hooks._session_id is None
        
        # Next start should create new session
        hooks.on_agent_start(mock_agent)
        assert hooks._session_id != old_session
    
    def test_token_segmentation(self, hooks, mock_agent, mock_context):
        """Test all token types are tracked correctly"""
        hooks.on_agent_start(mock_agent)
        
        # User message (input tokens)
        hooks.on_message(mock_agent, {
            "role": "user",
            "content": "Test message"
        })
        
        # Tool execution (process tokens)
        hooks.on_tool_start(mock_agent, "test_tool", {"param": "value"})
        hooks.on_tool_end(mock_agent, "test_tool", {"result": "success"})
        
        # Assistant response (output tokens)
        hooks.on_message(mock_agent, {
            "role": "assistant",
            "content": "Response message"
        })
        
        hooks.on_agent_end(mock_agent, mock_context)
        
        record = hooks._batch_buffer[0]
        
        # All token types should have values
        assert record.input_tokens > 0
        assert record.output_tokens > 0
        assert record.process_tokens > 0
        assert record.memory_tokens > 0
        
        # Total should equal sum
        total = (record.input_tokens + record.output_tokens + 
                record.process_tokens + record.memory_tokens)
        assert record.total_tokens == total
    
    def test_session_continuity(self, hooks, mock_agent, mock_context):
        """Test session ID persists across multiple runs"""
        # First run
        hooks.on_agent_start(mock_agent)
        first_session = hooks._session_id
        hooks.on_agent_end(mock_agent, mock_context)
        
        # Second run (same session)
        hooks.on_agent_start(mock_agent)
        second_session = hooks._session_id
        hooks.on_agent_end(mock_agent, mock_context)
        
        # Session should persist
        assert first_session == second_session
        
        # Reset and third run (new session)
        hooks.reset_session()
        hooks.on_agent_start(mock_agent)
        third_session = hooks._session_id
        
        assert third_session != first_session


class TestMonkAIAgentHooksErrors:
    """Test error handling"""
    
    def test_missing_monkai_agent_import(self):
        """Test error when monkai_agent not installed"""
        with patch('monkai_trace.integrations.monkai_agent.MONKAI_AGENT_AVAILABLE', False):
            with pytest.raises(ImportError, match="monkai_agent is not installed"):
                MonkAIAgentHooks(
                    tracer_token="tk_test",
                    namespace="test"
                )
    
    def test_flush_upload_failure(self, hooks, mock_agent, mock_context):
        """Test graceful handling of upload failures"""
        hooks.client.upload_records_batch.side_effect = Exception("Network error")
        
        hooks.on_agent_start(mock_agent)
        hooks.on_agent_end(mock_agent, mock_context)
        
        # Should not raise exception
        hooks.flush()
        
        # Buffer should still contain record (not cleared on failure)
        assert len(hooks._batch_buffer) == 1
