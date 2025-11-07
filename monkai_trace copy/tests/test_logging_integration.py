"""Tests for Python logging integration"""

import logging
import pytest
from unittest.mock import Mock, patch, MagicMock

from monkai_trace.integrations.logging import MonkAILogHandler
from monkai_trace.models import LogEntry


@pytest.fixture
def mock_client():
    """Create a mock MonkAI client"""
    with patch('monkai_trace.integrations.logging.MonkAIClient') as mock:
        client_instance = Mock()
        mock.return_value = client_instance
        yield client_instance


def test_handler_initialization(mock_client):
    """Test MonkAILogHandler initialization"""
    handler = MonkAILogHandler(
        tracer_token="tk_test",
        namespace="test-app",
        agent="test-logger",
        batch_size=20,
    )
    
    assert handler.namespace == "test-app"
    assert handler.agent == "test-logger"
    assert handler.batch_size == 20
    assert handler.auto_upload is True
    assert len(handler._log_buffer) == 0


def test_level_mapping(mock_client):
    """Test Python log level to MonkAI level mapping"""
    handler = MonkAILogHandler(
        tracer_token="tk_test",
        namespace="test-app",
        auto_upload=False,
    )
    
    logger = logging.getLogger("test_logger")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    
    # Test different log levels
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")
    
    assert len(handler._log_buffer) == 5
    assert handler._log_buffer[0].level == "debug"
    assert handler._log_buffer[1].level == "info"
    assert handler._log_buffer[2].level == "warn"
    assert handler._log_buffer[3].level == "error"
    assert handler._log_buffer[4].level == "error"  # critical maps to error


def test_metadata_inclusion(mock_client):
    """Test that metadata is correctly captured"""
    handler = MonkAILogHandler(
        tracer_token="tk_test",
        namespace="test-app",
        auto_upload=False,
        include_metadata=True,
    )
    
    logger = logging.getLogger("test.module")
    logger.addHandler(handler)
    
    # Log with extra metadata
    logger.info(
        "User action",
        extra={"user_id": "123", "action": "login", "count": 5}
    )
    
    assert len(handler._log_buffer) == 1
    log_entry = handler._log_buffer[0]
    
    assert log_entry.message == "User action"
    assert log_entry.metadata is not None
    assert log_entry.metadata["user_id"] == "123"
    assert log_entry.metadata["action"] == "login"
    assert log_entry.metadata["count"] == 5
    assert log_entry.metadata["logger"] == "test.module"


def test_exception_logging(mock_client):
    """Test that exceptions are captured in metadata"""
    handler = MonkAILogHandler(
        tracer_token="tk_test",
        namespace="test-app",
        auto_upload=False,
    )
    
    logger = logging.getLogger("test_logger")
    logger.addHandler(handler)
    handler.setFormatter(logging.Formatter('%(message)s'))
    
    try:
        raise ValueError("Test error")
    except ValueError:
        logger.error("An error occurred", exc_info=True)
    
    assert len(handler._log_buffer) == 1
    log_entry = handler._log_buffer[0]
    
    assert "exception" in log_entry.metadata
    assert "ValueError: Test error" in log_entry.metadata["exception"]


def test_auto_upload_threshold(mock_client):
    """Test automatic upload when batch size is reached"""
    handler = MonkAILogHandler(
        tracer_token="tk_test",
        namespace="test-app",
        auto_upload=True,
        batch_size=3,
    )
    
    logger = logging.getLogger("test_logger")
    logger.addHandler(handler)
    
    # Log messages below threshold
    logger.info("Message 1")
    logger.info("Message 2")
    assert mock_client.upload_logs.call_count == 0
    
    # This should trigger upload
    logger.info("Message 3")
    assert mock_client.upload_logs.call_count == 1
    assert len(handler._log_buffer) == 0  # Buffer cleared


def test_manual_flush(mock_client):
    """Test manual flushing of logs"""
    handler = MonkAILogHandler(
        tracer_token="tk_test",
        namespace="test-app",
        auto_upload=False,
    )
    
    logger = logging.getLogger("test_logger")
    logger.addHandler(handler)
    
    logger.info("Message 1")
    logger.info("Message 2")
    
    assert len(handler._log_buffer) == 2
    assert mock_client.upload_logs.call_count == 0
    
    # Manual flush
    handler.flush()
    
    assert len(handler._log_buffer) == 0
    assert mock_client.upload_logs.call_count == 1
    
    # Verify correct arguments
    call_args = mock_client.upload_logs.call_args
    assert call_args.kwargs["namespace"] == "test-app"
    assert call_args.kwargs["agent"] == "python-logger"
    assert len(call_args.kwargs["logs"]) == 2


def test_handler_close(mock_client):
    """Test that close() flushes remaining logs"""
    handler = MonkAILogHandler(
        tracer_token="tk_test",
        namespace="test-app",
        auto_upload=False,
    )
    
    logger = logging.getLogger("test_logger")
    logger.addHandler(handler)
    
    logger.info("Final message")
    
    assert len(handler._log_buffer) == 1
    
    handler.close()
    
    assert len(handler._log_buffer) == 0
    assert mock_client.upload_logs.call_count == 1


def test_no_metadata_mode(mock_client):
    """Test handler with metadata disabled"""
    handler = MonkAILogHandler(
        tracer_token="tk_test",
        namespace="test-app",
        auto_upload=False,
        include_metadata=False,
    )
    
    logger = logging.getLogger("test_logger")
    logger.addHandler(handler)
    
    logger.info("Simple message", extra={"user_id": "123"})
    
    assert len(handler._log_buffer) == 1
    log_entry = handler._log_buffer[0]
    
    # Metadata should be None when disabled
    assert log_entry.metadata is None or log_entry.metadata == {}
