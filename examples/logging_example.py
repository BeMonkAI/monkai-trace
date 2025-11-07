"""
Example: Python logging integration with MonkAI

This example shows how to automatically send Python logs to MonkAI
using the MonkAILogHandler.
"""

import logging
import time
from monkai_trace.integrations.logging import MonkAILogHandler


def main():
    # Configure MonkAI handler
    handler = MonkAILogHandler(
        tracer_token="tk_your_token_here",
        namespace="my-application",
        agent="python-logger",
        auto_upload=True,
        batch_size=10,
        include_metadata=True,
    )
    
    # Set up logger
    logger = logging.getLogger("my_app")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    
    # Optionally add console handler for local debugging
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    )
    logger.addHandler(console_handler)
    
    # Example logs
    logger.info("Application started")
    
    logger.debug("Debug message", extra={"debug_info": "additional context"})
    
    logger.info(
        "User logged in",
        extra={"user_id": "12345", "ip_address": "192.168.1.1"}
    )
    
    logger.warning(
        "High memory usage detected",
        extra={"memory_mb": 1024, "threshold_mb": 800}
    )
    
    try:
        # Simulate an error
        result = 10 / 0
    except ZeroDivisionError as e:
        logger.error(
            "Division by zero error",
            exc_info=True,
            extra={"operation": "divide", "numerator": 10}
        )
    
    logger.critical(
        "Database connection lost",
        extra={"host": "db.example.com", "port": 5432}
    )
    
    # Give time for batch to accumulate
    time.sleep(1)
    
    # Manually flush remaining logs
    handler.flush()
    
    logger.info("Application stopped")
    
    # Clean up (will auto-flush)
    handler.close()


if __name__ == "__main__":
    main()
