# Python Logging Integration

MonkAI provides a `MonkAILogHandler` that integrates seamlessly with Python's built-in `logging` module, automatically sending your application logs to MonkAI for centralized monitoring.

## Installation

```bash
pip install monkai-trace
```

## Quick Start

```python
import logging
from monkai_trace.integrations.logging import MonkAILogHandler

# Configure MonkAI handler
handler = MonkAILogHandler(
    tracer_token="tk_your_token",
    namespace="my-application"
)

# Set up logger
logger = logging.getLogger("my_app")
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Now all logs are automatically sent to MonkAI
logger.info("User logged in", extra={"user_id": "123"})
logger.error("Database connection failed")
```

## What Gets Tracked

### Log Levels

Python log levels are automatically mapped to MonkAI levels:

| Python Level | MonkAI Level |
|--------------|--------------|
| DEBUG        | debug        |
| INFO         | info         |
| WARNING      | warn         |
| ERROR        | error        |
| CRITICAL     | error        |

### Metadata

The handler automatically captures:

- **Logger name** - The name of the logger that emitted the record
- **Module** - The module where the log was emitted
- **Function** - The function name
- **Line number** - Source code line number
- **Thread info** - Thread ID and name
- **Exception info** - Full traceback if logging an exception
- **Custom fields** - Any extra data passed via the `extra` parameter

## Configuration Options

```python
handler = MonkAILogHandler(
    tracer_token="tk_your_token",     # Required: Your MonkAI token
    namespace="my-app",                # Required: Namespace for logs
    agent="python-logger",             # Optional: Agent name (default: "python-logger")
    auto_upload=True,                  # Optional: Auto-upload when batch is full
    batch_size=50,                     # Optional: Logs to batch before upload
    include_metadata=True,             # Optional: Include extra metadata
)
```

### Parameters

- **tracer_token** (str, required): Your MonkAI tracer token
- **namespace** (str, required): Namespace to organize your logs
- **agent** (str, optional): Agent identifier (default: "python-logger")
- **auto_upload** (bool, optional): Automatically upload when batch size reached (default: True)
- **batch_size** (int, optional): Number of logs to batch before uploading (default: 50)
- **include_metadata** (bool, optional): Include contextual metadata (default: True)

## Advanced Usage

### Adding Custom Metadata

Use the `extra` parameter to attach custom fields to your logs:

```python
logger.info(
    "Payment processed",
    extra={
        "user_id": "user_123",
        "amount": 99.99,
        "currency": "USD",
        "payment_method": "credit_card"
    }
)
```

### Logging Exceptions

Capture full exception tracebacks:

```python
try:
    result = process_payment(user_id, amount)
except PaymentError as e:
    logger.error(
        "Payment processing failed",
        exc_info=True,  # Include full traceback
        extra={
            "user_id": user_id,
            "amount": amount,
            "error_code": e.code
        }
    )
```

### Multiple Handlers

Combine MonkAI handler with other handlers:

```python
import logging
from monkai_trace.integrations.logging import MonkAILogHandler

# MonkAI handler for cloud monitoring
monkai_handler = MonkAILogHandler(
    tracer_token="tk_your_token",
    namespace="my-app"
)

# Console handler for local debugging
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)

# Set up logger with both handlers
logger = logging.getLogger("my_app")
logger.addHandler(monkai_handler)
logger.addHandler(console_handler)
logger.setLevel(logging.DEBUG)
```

### Manual Flushing

Force upload of buffered logs:

```python
# Upload any pending logs immediately
handler.flush()

# Or close the handler (automatically flushes)
handler.close()
```

### Different Namespaces for Different Loggers

Organize logs by component:

```python
# Database logs
db_handler = MonkAILogHandler(
    tracer_token="tk_your_token",
    namespace="my-app-database"
)
db_logger = logging.getLogger("database")
db_logger.addHandler(db_handler)

# API logs
api_handler = MonkAILogHandler(
    tracer_token="tk_your_token",
    namespace="my-app-api"
)
api_logger = logging.getLogger("api")
api_logger.addHandler(api_handler)
```

## Best Practices

### 1. Use Appropriate Log Levels

```python
logger.debug("Detailed diagnostic info")    # Development debugging
logger.info("Normal operations")            # General information
logger.warning("Something unexpected")      # Warnings
logger.error("Error occurred")              # Errors
logger.critical("System failure")           # Critical failures
```

### 2. Add Context with Extra Fields

```python
# Good: Rich context
logger.info(
    "User action completed",
    extra={
        "user_id": user.id,
        "action": "purchase",
        "item_id": item.id,
        "duration_ms": duration
    }
)

# Avoid: No context
logger.info("Action completed")
```

### 3. Batch Size Configuration

```python
# High-volume applications: larger batch size
high_volume_handler = MonkAILogHandler(
    tracer_token="tk_your_token",
    namespace="high-traffic-api",
    batch_size=200  # Upload less frequently
)

# Low-volume applications: smaller batch size
low_volume_handler = MonkAILogHandler(
    tracer_token="tk_your_token",
    namespace="background-worker",
    batch_size=10  # Upload more frequently
)
```

### 4. Graceful Shutdown

Ensure logs are flushed on application exit:

```python
import atexit
import signal

# Register cleanup
atexit.register(handler.flush)

# Handle termination signals
def cleanup(signum, frame):
    handler.flush()
    exit(0)

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)
```

## Viewing Your Logs

Once configured, view your logs on the MonkAI dashboard:

1. Go to [monkai.ai](https://monkai.ai)
2. Navigate to **Monitoring** → **Logs**
3. Filter by namespace and time range
4. Search and analyze your application logs

## Complete Example

```python
import logging
import signal
import atexit
from monkai_trace.integrations.logging import MonkAILogHandler

# Configure handler
handler = MonkAILogHandler(
    tracer_token="tk_your_token",
    namespace="production-api",
    agent="web-server",
    batch_size=100,
)

# Set up logger
logger = logging.getLogger("api")
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Add console handler for local debugging
console = logging.StreamHandler()
console.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
logger.addHandler(console)

# Ensure logs are flushed on exit
atexit.register(handler.flush)
signal.signal(signal.SIGTERM, lambda s, f: handler.flush())

# Application code
def process_request(user_id, request_data):
    logger.info(
        "Processing request",
        extra={"user_id": user_id, "endpoint": "/api/process"}
    )
    
    try:
        result = perform_operation(request_data)
        logger.info(
            "Request completed",
            extra={"user_id": user_id, "status": "success"}
        )
        return result
    except Exception as e:
        logger.error(
            "Request failed",
            exc_info=True,
            extra={"user_id": user_id, "error_type": type(e).__name__}
        )
        raise

if __name__ == "__main__":
    logger.info("Application started")
    # Your application logic here
    logger.info("Application stopped")
```

## Troubleshooting

### Logs Not Appearing

1. **Check token validity**: Ensure your tracer token is valid
2. **Verify batch size**: Lower the batch size or manually call `handler.flush()`
3. **Check log level**: Ensure logger level is set appropriately
4. **Network issues**: Check firewall/proxy settings

### Performance Considerations

- **Batch size**: Larger batches = fewer network calls but higher memory usage
- **Auto-upload**: Set to `False` for fine-grained control over uploads
- **Metadata**: Disable with `include_metadata=False` to reduce payload size

### Error Handling

The handler uses Python's standard error handling mechanism:

```python
# Custom error handler
def handle_logging_errors(record):
    print(f"Failed to log: {record.getMessage()}")

handler.handleError = handle_logging_errors
```

## API Reference

See the [API Reference](api_reference.md#monkailoghandler) for detailed documentation.

## Next Steps

- [View examples](../examples/logging_example.py)
- [API Reference](api_reference.md)
- [Quick Start Guide](quickstart.md)

## Support

- [Documentation](https://docs.monkai.ai)
- [GitHub Issues](https://github.com/monkai/monkai-trace-python/issues)
- [Discord Community](https://discord.gg/monkai)
