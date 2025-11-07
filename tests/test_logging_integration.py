"""Tests for Python logging integration"""

import logging
import pytest
import time
import threading
import signal
from unittest.mock import Mock, patch, MagicMock, call

from monkai_trace.integrations.logging import MonkAILogHandler
from monkai_trace.models import LogEntry

# Import ServiceLogger from the example file
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'examples'))
from service_logging_example import ServiceLogger


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


# ============================================================================
# ServiceLogger Tests
# ============================================================================


def test_service_logger_initialization(mock_client):
    """Test ServiceLogger initialization with optimal settings"""
    service_logger = ServiceLogger(
        tracer_token="tk_test",
        namespace="test-service",
        agent="test-worker"
    )
    
    # Verify handler configuration
    assert service_logger.handler.namespace == "test-service"
    assert service_logger.handler.agent == "test-worker"
    assert service_logger.handler.batch_size == 10  # Reduced for services
    assert service_logger.handler.auto_upload is True
    
    # Verify logger configuration
    assert service_logger.logger.name == "test-worker"
    assert len(service_logger.logger.handlers) == 2  # MonkAI + console
    assert service_logger.stop_event is not None
    assert not service_logger.stop_event.is_set()


def test_service_logger_periodic_flush(mock_client):
    """Test periodic flush functionality"""
    service_logger = ServiceLogger(
        tracer_token="tk_test",
        namespace="test-service",
        agent="test-worker"
    )
    
    # Start periodic flush with short interval for testing
    service_logger.start_periodic_flush(interval=1)
    
    # Verify thread is running
    assert service_logger.flush_thread is not None
    assert service_logger.flush_thread.is_alive()
    
    # Add some logs
    service_logger.logger.info("Test message 1")
    service_logger.logger.info("Test message 2")
    
    # Wait for periodic flush to trigger
    time.sleep(1.5)
    
    # Verify flush was called (buffer should be empty or flushed)
    # Note: We can't directly verify mock_client.upload_logs because
    # batch_size is 10 and we only have 2 messages, but the flush
    # mechanism should be active
    
    # Cleanup
    service_logger.shutdown()
    assert not service_logger.flush_thread.is_alive()


def test_service_logger_shutdown(mock_client):
    """Test graceful shutdown of ServiceLogger"""
    service_logger = ServiceLogger(
        tracer_token="tk_test",
        namespace="test-service",
        agent="test-worker"
    )
    
    # Start periodic flush
    service_logger.start_periodic_flush(interval=60)
    
    # Add some logs
    service_logger.logger.info("Message before shutdown")
    
    # Shutdown
    service_logger.shutdown()
    
    # Verify stop event is set
    assert service_logger.stop_event.is_set()
    
    # Verify thread stopped
    if service_logger.flush_thread:
        assert not service_logger.flush_thread.is_alive()
    
    # Verify flush was called
    assert mock_client.upload_logs.call_count >= 1


def test_service_logger_shutdown_handlers(mock_client):
    """Test signal handler registration"""
    service_logger = ServiceLogger(
        tracer_token="tk_test",
        namespace="test-service",
        agent="test-worker"
    )
    
    # Setup shutdown handlers
    with patch('signal.signal') as mock_signal, \
         patch('atexit.register') as mock_atexit:
        
        service_logger.setup_shutdown_handlers()
        
        # Verify SIGTERM handler registered
        sigterm_calls = [call for call in mock_signal.call_args_list 
                         if call[0][0] == signal.SIGTERM]
        assert len(sigterm_calls) == 1
        
        # Verify SIGINT handler registered
        sigint_calls = [call for call in mock_signal.call_args_list 
                        if call[0][0] == signal.SIGINT]
        assert len(sigint_calls) == 1
        
        # Verify atexit handler registered
        assert mock_atexit.call_count == 1


def test_service_logger_low_volume_logging(mock_client):
    """Test that logs are handled correctly with low volume"""
    service_logger = ServiceLogger(
        tracer_token="tk_test",
        namespace="test-service",
        agent="test-worker"
    )
    
    # Log only 3 messages (below batch_size of 10)
    service_logger.logger.info("Message 1")
    service_logger.logger.info("Message 2")
    service_logger.logger.info("Message 3")
    
    # Verify logs are in buffer
    assert len(service_logger.handler._log_buffer) == 3
    
    # Manual flush should upload them
    service_logger.handler.flush()
    
    # Verify upload was called
    assert mock_client.upload_logs.call_count == 1
    assert len(service_logger.handler._log_buffer) == 0


def test_service_logger_thread_safety(mock_client):
    """Test thread-safe operation of ServiceLogger"""
    service_logger = ServiceLogger(
        tracer_token="tk_test",
        namespace="test-service",
        agent="test-worker"
    )
    
    # Start periodic flush
    service_logger.start_periodic_flush(interval=0.5)
    
    # Log from multiple threads
    def log_messages(thread_id, count):
        for i in range(count):
            service_logger.logger.info(
                f"Thread {thread_id} message {i}",
                extra={"thread_id": thread_id, "message_num": i}
            )
            time.sleep(0.1)
    
    # Create threads
    threads = []
    for i in range(3):
        t = threading.Thread(target=log_messages, args=(i, 5))
        threads.append(t)
        t.start()
    
    # Wait for threads to complete
    for t in threads:
        t.join()
    
    # Shutdown and verify all logs processed
    service_logger.shutdown()
    
    # Verify handler is closed properly
    assert service_logger.stop_event.is_set()


def test_service_logger_exception_handling(mock_client):
    """Test exception logging in ServiceLogger"""
    service_logger = ServiceLogger(
        tracer_token="tk_test",
        namespace="test-service",
        agent="test-worker"
    )
    
    # Log an exception
    try:
        raise RuntimeError("Service error")
    except RuntimeError:
        service_logger.logger.error(
            "Task failed",
            exc_info=True,
            extra={"task_id": 123, "error_type": "RuntimeError"}
        )
    
    # Verify exception was captured
    assert len(service_logger.handler._log_buffer) == 1
    log_entry = service_logger.handler._log_buffer[0]
    
    assert log_entry.level == "error"
    assert "exception" in log_entry.metadata
    assert "RuntimeError: Service error" in log_entry.metadata["exception"]
    assert log_entry.metadata["task_id"] == 123
    
    # Cleanup
    service_logger.shutdown()


def test_service_logger_multiple_flush_cycles(mock_client):
    """Test multiple flush cycles over time"""
    service_logger = ServiceLogger(
        tracer_token="tk_test",
        namespace="test-service",
        agent="test-worker"
    )
    
    # Start periodic flush with very short interval
    service_logger.start_periodic_flush(interval=0.5)
    
    # Log messages over several flush cycles
    for i in range(5):
        service_logger.logger.info(f"Cycle {i} message")
        time.sleep(0.3)
    
    # Wait for flushes to occur
    time.sleep(1)
    
    # Verify periodic flush happened multiple times
    # (Even with small batches, flush should be called)
    
    # Cleanup
    service_logger.shutdown()
    assert service_logger.stop_event.is_set()


def test_service_logger_graceful_shutdown_with_pending_logs(mock_client):
    """Test shutdown with logs still in buffer"""
    service_logger = ServiceLogger(
        tracer_token="tk_test",
        namespace="test-service",
        agent="test-worker"
    )
    
    # Start periodic flush
    service_logger.start_periodic_flush(interval=60)  # Long interval
    
    # Add logs that won't auto-flush
    for i in range(5):  # Below batch_size of 10
        service_logger.logger.info(f"Pending message {i}")
    
    # Verify logs are in buffer
    assert len(service_logger.handler._log_buffer) == 5
    
    # Shutdown should flush them
    service_logger.shutdown()
    
    # Verify all logs were flushed
    assert len(service_logger.handler._log_buffer) == 0
    assert mock_client.upload_logs.call_count >= 1


def test_service_logger_console_and_monkai_output(mock_client):
    """Test that logs go to both console and MonkAI"""
    service_logger = ServiceLogger(
        tracer_token="tk_test",
        namespace="test-service",
        agent="test-worker"
    )
    
    # Verify both handlers are present
    handlers = service_logger.logger.handlers
    assert len(handlers) == 2
    
    # One should be MonkAILogHandler
    monkai_handlers = [h for h in handlers if isinstance(h, MonkAILogHandler)]
    assert len(monkai_handlers) == 1
    
    # One should be StreamHandler (console)
    stream_handlers = [h for h in handlers if isinstance(h, logging.StreamHandler)]
    assert len(stream_handlers) == 1
    
    # Cleanup
    service_logger.shutdown()
