"""Tests for LangChain integration"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from monkai_trace.integrations.langchain import MonkAICallbackHandler


@pytest.fixture
def mock_langchain_deps():
    """Mock LangChain dependencies"""
    with patch('monkai_trace.integrations.langchain.BaseCallbackHandler'):
        yield


@pytest.fixture
def handler(mock_client):
    """Create a MonkAICallbackHandler for testing"""
    with patch('monkai_trace.integrations.langchain.MonkAIClient', return_value=mock_client):
        return MonkAICallbackHandler(
            tracer_token="tk_test_token",
            namespace="test-namespace",
            agent_name="Test Agent",
            auto_upload=False
        )


def test_handler_initialization(handler):
    """Test handler initialization"""
    assert handler.namespace == "test-namespace"
    assert handler.agent_name == "Test Agent"
    assert handler.auto_upload is False
    assert handler.batch_size == 10
    assert handler.estimate_tokens is True
    assert handler.session_id is None
    assert len(handler.conversation_buffer) == 0


def test_session_id_generation(handler):
    """Test session ID generation"""
    session_id = handler._get_or_create_session_id()
    assert session_id is not None
    assert len(session_id) > 0
    
    # Should return same session ID on subsequent calls
    session_id2 = handler._get_or_create_session_id()
    assert session_id == session_id2


def test_token_estimation(handler):
    """Test token estimation"""
    # Roughly 4 characters per token
    text = "Hello world"  # 11 chars = ~2-3 tokens
    tokens = handler._estimate_tokens(text)
    assert tokens >= 2
    assert tokens <= 3
    
    # Longer text
    long_text = "a" * 100  # 100 chars = ~25 tokens
    tokens = handler._estimate_tokens(long_text)
    assert tokens == 25


def test_token_estimation_disabled(mock_client):
    """Test token estimation when disabled"""
    with patch('monkai_trace.integrations.langchain.MonkAIClient', return_value=mock_client):
        handler = MonkAICallbackHandler(
            tracer_token="tk_test_token",
            namespace="test-namespace",
            estimate_tokens=False
        )
        
        tokens = handler._estimate_tokens("Hello world")
        assert tokens == 0


def test_on_llm_start(handler):
    """Test LLM start callback"""
    prompts = ["What is the weather?", "Tell me more"]
    handler.on_llm_start({}, prompts)
    
    # Should accumulate input tokens from prompts
    assert handler.input_tokens > 0


def test_on_llm_end_with_usage(handler):
    """Test LLM end callback with actual token usage"""
    mock_response = Mock()
    mock_response.llm_output = {
        "token_usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30
        }
    }
    
    handler.on_llm_end(mock_response)
    
    assert handler.input_tokens == 10
    assert handler.output_tokens == 20


def test_on_llm_end_without_usage(handler):
    """Test LLM end callback without token usage (estimation fallback)"""
    mock_generation = Mock()
    mock_generation.text = "This is a response"
    
    mock_response = Mock()
    mock_response.llm_output = None
    mock_response.generations = [[mock_generation]]
    
    initial_output_tokens = handler.output_tokens
    handler.on_llm_end(mock_response)
    
    # Should have estimated tokens from the text
    assert handler.output_tokens > initial_output_tokens


def test_on_chain_start(handler):
    """Test chain start callback"""
    inputs = {"input": "What's the weather in Tokyo?"}
    handler.on_chain_start({}, inputs)
    
    assert handler.current_input == "What's the weather in Tokyo?"
    
    # Also test with 'question' key
    handler.current_input = None
    inputs = {"question": "How are you?"}
    handler.on_chain_start({}, inputs)
    
    assert handler.current_input == "How are you?"


def test_on_chain_end(handler):
    """Test chain end callback"""
    handler.input_tokens = 10
    handler.output_tokens = 20
    handler.process_tokens = 5
    
    outputs = {"output": "The weather is sunny"}
    handler.on_chain_end(outputs)
    
    # Should create a conversation record
    assert len(handler.conversation_buffer) == 1
    
    record = handler.conversation_buffer[0]
    assert record.namespace == "test-namespace"
    assert record.agent == "Test Agent"
    assert record.msg.content == "The weather is sunny"
    assert record.input_tokens == 10
    assert record.output_tokens == 20
    assert record.process_tokens == 5
    assert record.total_tokens == 35
    
    # Tokens should be reset
    assert handler.input_tokens == 0
    assert handler.output_tokens == 0
    assert handler.process_tokens == 0


def test_on_agent_action(handler):
    """Test agent action callback (tool call)"""
    mock_action = Mock()
    mock_action.tool = "Calculator"
    mock_action.tool_input = "2 + 2"
    
    handler.on_agent_action(mock_action)
    
    # Should track process tokens
    assert handler.process_tokens > 0
    
    # Should create a tool call record
    assert len(handler.conversation_buffer) == 1
    record = handler.conversation_buffer[0]
    assert record.msg.role == "tool"
    assert "Calculator" in record.msg.content
    assert "2 + 2" in record.msg.content


def test_on_tool_start_and_end(handler):
    """Test tool start and end callbacks"""
    initial_process_tokens = handler.process_tokens
    
    handler.on_tool_start({}, "search for weather")
    assert handler.process_tokens > initial_process_tokens
    
    tokens_after_start = handler.process_tokens
    handler.on_tool_end("sunny, 72°F")
    assert handler.process_tokens > tokens_after_start


def test_auto_upload_threshold(mock_client):
    """Test automatic upload when batch size is reached"""
    with patch('monkai_trace.integrations.langchain.MonkAIClient', return_value=mock_client):
        handler = MonkAICallbackHandler(
            tracer_token="tk_test_token",
            namespace="test-namespace",
            auto_upload=True,
            batch_size=2
        )
        
        # Add records until batch size is reached
        for i in range(2):
            handler.on_chain_end({"output": f"Response {i}"})
        
        # Should have triggered upload
        assert mock_client.upload_records_batch.called
        assert len(handler.conversation_buffer) == 0


def test_manual_flush(handler, mock_client):
    """Test manual flush of buffered records"""
    # Add some records
    handler.on_chain_end({"output": "Response 1"})
    handler.on_chain_end({"output": "Response 2"})
    
    assert len(handler.conversation_buffer) == 2
    
    # Manual flush
    handler.flush()
    
    assert mock_client.upload_records_batch.called
    assert len(handler.conversation_buffer) == 0


def test_reset_session(handler):
    """Test session reset"""
    # Create a session
    session_id1 = handler._get_or_create_session_id()
    assert handler.session_id is not None
    
    # Reset session
    handler.reset_session()
    assert handler.session_id is None
    
    # New session should have different ID
    session_id2 = handler._get_or_create_session_id()
    assert session_id2 != session_id1


def test_handler_cleanup(mock_client):
    """Test that handler flushes on cleanup"""
    with patch('monkai_trace.integrations.langchain.MonkAIClient', return_value=mock_client):
        handler = MonkAICallbackHandler(
            tracer_token="tk_test_token",
            namespace="test-namespace",
            auto_upload=False
        )
        
        handler.on_chain_end({"output": "Final response"})
        assert len(handler.conversation_buffer) == 1
        
        # Trigger cleanup
        handler.__del__()
        
        assert mock_client.upload_records_batch.called
