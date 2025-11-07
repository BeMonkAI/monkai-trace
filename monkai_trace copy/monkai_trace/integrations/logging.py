"""Python logging integration for MonkAI"""

import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime

from ..client import MonkAIClient
from ..models import LogEntry


class MonkAILogHandler(logging.Handler):
    """
    A logging handler that sends Python logs to MonkAI.
    
    Maps Python log levels to MonkAI levels and supports batch uploads.
    
    Example:
        ```python
        import logging
        from monkai_trace.integrations.logging import MonkAILogHandler
        
        handler = MonkAILogHandler(
            tracer_token="tk_your_token",
            namespace="my-app"
        )
        logger = logging.getLogger("my_app")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        logger.info("User logged in", extra={"user_id": "123"})
        logger.error("Database error", extra={"query": "SELECT..."})
        ```
    """
    
    # Map Python logging levels to MonkAI levels
    LEVEL_MAPPING = {
        logging.DEBUG: "debug",
        logging.INFO: "info",
        logging.WARNING: "warn",
        logging.ERROR: "error",
        logging.CRITICAL: "error",
    }
    
    def __init__(
        self,
        tracer_token: str,
        namespace: str,
        agent: str = "python-logger",
        auto_upload: bool = True,
        batch_size: int = 50,
        include_metadata: bool = True,
    ):
        """
        Initialize the MonkAI logging handler.
        
        Args:
            tracer_token: MonkAI tracer token
            namespace: Namespace for the logs
            agent: Agent name (default: "python-logger")
            auto_upload: Automatically upload when batch size is reached
            batch_size: Number of logs to batch before uploading
            include_metadata: Include extra metadata from log records
        """
        super().__init__()
        self.client = MonkAIClient(tracer_token=tracer_token)
        self.namespace = namespace
        self.agent = agent
        self.auto_upload = auto_upload
        self.batch_size = batch_size
        self.include_metadata = include_metadata
        self._log_buffer: List[LogEntry] = []
    
    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record to MonkAI.
        
        Args:
            record: The logging record to emit
        """
        try:
            # Map Python log level to MonkAI level
            level = self.LEVEL_MAPPING.get(record.levelno, "info")
            
            # Format the message
            message = self.format(record)
            
            # Extract metadata
            metadata: Dict[str, Any] = {}
            if self.include_metadata:
                # Add standard fields
                metadata.update({
                    "logger": record.name,
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno,
                    "thread": record.thread,
                    "thread_name": record.threadName,
                })
                
                # Add exception info if present
                if record.exc_info:
                    metadata["exception"] = self.formatter.formatException(record.exc_info) if self.formatter else str(record.exc_info)
                
                # Add custom fields from extra
                for key, value in record.__dict__.items():
                    if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName', 
                                   'levelname', 'levelno', 'lineno', 'module', 'msecs', 
                                   'message', 'pathname', 'process', 'processName', 
                                   'relativeCreated', 'thread', 'threadName', 'exc_info', 
                                   'exc_text', 'stack_info', 'getMessage']:
                        try:
                            # Only include JSON-serializable values
                            import json
                            json.dumps(value)
                            metadata[key] = value
                        except (TypeError, ValueError):
                            metadata[key] = str(value)
            
            # Create log entry
            log_entry = LogEntry(
                timestamp=datetime.fromtimestamp(record.created).isoformat(),
                level=level,
                message=message,
                metadata=metadata if metadata else None,
            )
            
            # Add to buffer
            self._log_buffer.append(log_entry)
            
            # Auto-upload if threshold reached
            if self.auto_upload and len(self._log_buffer) >= self.batch_size:
                self.flush()
                
        except Exception:
            self.handleError(record)
    
    def flush(self) -> None:
        """Upload all buffered logs to MonkAI."""
        if not self._log_buffer:
            return
        
        try:
            self.client.upload_logs(
                namespace=self.namespace,
                agent=self.agent,
                logs=self._log_buffer,
            )
            self._log_buffer.clear()
        except Exception as e:
            # Use standard error handling
            self.handleError(logging.makeLogRecord({"msg": f"Failed to upload logs: {e}"}))
    
    def close(self) -> None:
        """Flush any remaining logs and close the handler."""
        self.flush()
        super().close()
    
    def __del__(self):
        """Ensure logs are flushed on deletion."""
        try:
            self.flush()
        except Exception:
            pass
