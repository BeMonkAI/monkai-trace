"""
Example: MonkAI logging integration for long-running services

This example demonstrates best practices for using MonkAILogHandler
in services, daemons, or any long-running application.

Key differences from scripts:
- Reduced batch_size for faster upload
- Periodic flush to avoid log accumulation
- Signal handling for graceful shutdown
- Ensures all logs are sent even with low volume

This solves the common problem where logs don't appear when running
as a service because the batch_size (default 50) is never reached.
"""

import logging
import time
import threading
import signal
import sys
import atexit
from monkai_trace.integrations.logging import MonkAILogHandler


class ServiceLogger:
    """
    Wrapper for configuring logging in long-running services.
    
    Handles three critical aspects:
    1. Reduced batch_size for services with low log volume
    2. Periodic flush to ensure logs are sent regularly
    3. Graceful shutdown to ensure no logs are lost
    """
    
    def __init__(self, tracer_token: str, namespace: str, agent: str = "service"):
        """
        Initialize service logger with optimal settings.
        
        Args:
            tracer_token: Your MonkAI tracer token
            namespace: Namespace for organizing logs
            agent: Agent identifier (default: "service")
        """
        # Configure handler with reduced batch_size for services
        self.handler = MonkAILogHandler(
            tracer_token=tracer_token,
            namespace=namespace,
            agent=agent,
            auto_upload=True,
            batch_size=10,  # Smaller than default (50) for services
            include_metadata=True,
        )
        
        # Configure logger
        self.logger = logging.getLogger(agent)
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.DEBUG)
        
        # Add console handler for local debugging
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
        self.logger.addHandler(console_handler)
        
        # Thread control for periodic flush
        self.stop_event = threading.Event()
        self.flush_thread = None
    
    def start_periodic_flush(self, interval: int = 60):
        """
        Start background thread that flushes logs periodically.
        
        This ensures logs are uploaded even if batch_size isn't reached.
        Critical for services with low log volume.
        
        Args:
            interval: Seconds between flushes (default: 60)
        """
        def flush_loop():
            """Background thread function for periodic flushing"""
            while not self.stop_event.is_set():
                # Wait with ability to interrupt on shutdown
                if self.stop_event.wait(timeout=interval):
                    break
                
                # Flush buffered logs
                self.handler.flush()
                self.logger.debug("Periodic flush completed")
        
        # Start daemon thread
        self.flush_thread = threading.Thread(target=flush_loop, daemon=True)
        self.flush_thread.start()
        self.logger.info(f"Periodic flush started (every {interval}s)")
    
    def setup_shutdown_handlers(self):
        """
        Configure signal handlers for graceful shutdown.
        
        Ensures logs are flushed when service receives:
        - SIGTERM (systemd/docker stop)
        - SIGINT (Ctrl+C)
        """
        def shutdown_handler(signum, frame):
            """Handle shutdown signals"""
            self.logger.info(f"Received signal {signum}, shutting down gracefully...")
            self.shutdown()
            sys.exit(0)
        
        # Register signal handlers
        signal.signal(signal.SIGTERM, shutdown_handler)
        signal.signal(signal.SIGINT, shutdown_handler)
        
        # Backup: ensure flush on normal exit
        atexit.register(self.shutdown)
        
        self.logger.info("Shutdown handlers configured")
    
    def shutdown(self):
        """
        Gracefully shutdown the logger.
        
        Stops periodic flush thread and ensures all logs are uploaded.
        """
        # Stop periodic flush thread
        if self.flush_thread and self.flush_thread.is_alive():
            self.stop_event.set()
            self.flush_thread.join(timeout=5)
        
        # Final flush and close
        self.handler.flush()
        self.handler.close()
        self.logger.info("Logger shutdown complete")


def simulate_service_work(logger):
    """
    Simulate the work of a long-running service.
    
    This represents a typical service that:
    - Processes tasks periodically
    - Generates logs at varying intervals
    - May have low log volume between tasks
    """
    task_count = 0
    
    while True:
        task_count += 1
        
        logger.info(
            f"Processing task {task_count}",
            extra={
                "task_id": task_count,
                "status": "started",
                "timestamp": time.time()
            }
        )
        
        # Simulate task processing (5 seconds)
        time.sleep(5)
        
        # Occasional warnings
        if task_count % 10 == 0:
            logger.warning(
                "Milestone reached",
                extra={
                    "task_count": task_count,
                    "milestone": task_count // 10
                }
            )
        
        # Simulate occasional errors
        if task_count % 15 == 0:
            try:
                # Simulate an error condition
                raise ValueError(f"Simulated error at task {task_count}")
            except ValueError as e:
                logger.error(
                    "Task processing error",
                    exc_info=True,
                    extra={
                        "task_id": task_count,
                        "error_type": "ValueError"
                    }
                )
        else:
            logger.info(
                f"Task {task_count} completed successfully",
                extra={
                    "task_id": task_count,
                    "status": "completed",
                    "duration_seconds": 5
                }
            )
        
        # Add some debug info
        if task_count % 5 == 0:
            logger.debug(
                "Memory usage check",
                extra={
                    "task_count": task_count,
                    "memory_mb": 128  # Simulated
                }
            )


def main():
    """
    Main function demonstrating service logging setup.
    
    This is the recommended pattern for long-running services:
    1. Create ServiceLogger with optimal settings
    2. Start periodic flush
    3. Configure shutdown handlers
    4. Run service logic
    """
    print("=" * 60)
    print("MonkAI Service Logging Example")
    print("=" * 60)
    print("\nThis example demonstrates:")
    print("  ✓ Reduced batch_size (10 vs default 50)")
    print("  ✓ Periodic flush every 60 seconds")
    print("  ✓ Graceful shutdown on SIGTERM/SIGINT")
    print("\nPress Ctrl+C to stop the service gracefully")
    print("=" * 60)
    print()
    
    # Configure logger for service
    service_logger = ServiceLogger(
        tracer_token="tk_your_token_here",  # Replace with your token
        namespace="my-service",
        agent="background-worker"
    )
    
    # Start periodic flush (every 60 seconds)
    service_logger.start_periodic_flush(interval=60)
    
    # Configure graceful shutdown
    service_logger.setup_shutdown_handlers()
    
    logger = service_logger.logger
    logger.info("Service started successfully")
    
    try:
        # Run service work
        simulate_service_work(logger)
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.critical(
            "Fatal error in service",
            exc_info=True,
            extra={"error_type": type(e).__name__}
        )
    finally:
        # Graceful shutdown
        service_logger.shutdown()


if __name__ == "__main__":
    main()
