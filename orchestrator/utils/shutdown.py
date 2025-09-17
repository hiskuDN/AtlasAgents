"""Graceful shutdown handling for AtlasAgents."""

import signal
import sys
import threading
import atexit
from typing import List, Callable, Optional
from contextlib import contextmanager
import time

from orchestrator.utils.logging import get_logger


logger = get_logger(__name__)


class ShutdownHandler:
    """Manages graceful shutdown of the application."""

    def __init__(self):
        self._shutdown_event = threading.Event()
        self._cleanup_handlers: List[Callable] = []
        self._is_shutting_down = False
        self._lock = threading.Lock()

        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Register atexit handler
        atexit.register(self._cleanup)

        logger.info("Shutdown handler initialized")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        signal_name = signal.Signals(signum).name
        logger.info(f"Received {signal_name} signal", signal=signal_name)
        self.initiate_shutdown(f"Received {signal_name}")

    def register_cleanup(self, handler: Callable, name: Optional[str] = None):
        """Register a cleanup handler to be called during shutdown."""
        with self._lock:
            self._cleanup_handlers.append(handler)
            handler_name = name or handler.__name__
            logger.debug(f"Registered cleanup handler: {handler_name}")

    def unregister_cleanup(self, handler: Callable):
        """Unregister a cleanup handler."""
        with self._lock:
            if handler in self._cleanup_handlers:
                self._cleanup_handlers.remove(handler)
                logger.debug(f"Unregistered cleanup handler: {handler.__name__}")

    def initiate_shutdown(self, reason: str = "Unknown"):
        """Initiate graceful shutdown."""
        with self._lock:
            if self._is_shutting_down:
                logger.warning("Shutdown already in progress")
                return

            self._is_shutting_down = True
            self._shutdown_event.set()

        logger.info(f"Initiating graceful shutdown: {reason}")
        self._cleanup()

    def _cleanup(self):
        """Execute all cleanup handlers."""
        if not self._is_shutting_down:
            return

        logger.info(f"Executing {len(self._cleanup_handlers)} cleanup handlers")

        for handler in reversed(self._cleanup_handlers):
            try:
                handler_name = getattr(handler, '__name__', str(handler))
                logger.debug(f"Executing cleanup handler: {handler_name}")
                handler()
            except Exception as e:
                logger.error(f"Error in cleanup handler: {e}", exc_info=True)

        logger.info("Cleanup completed")

    def is_shutting_down(self) -> bool:
        """Check if shutdown has been initiated."""
        return self._shutdown_event.is_set()

    def wait_for_shutdown(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for shutdown signal.

        Returns:
            True if shutdown was signaled, False if timeout occurred
        """
        return self._shutdown_event.wait(timeout)

    @contextmanager
    def graceful_exit(self):
        """Context manager for graceful exit handling."""
        try:
            yield self
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            self.initiate_shutdown("Keyboard interrupt")
        except Exception as e:
            logger.error(f"Unhandled exception: {e}", exc_info=True)
            self.initiate_shutdown(f"Unhandled exception: {e}")
            raise
        finally:
            if self._is_shutting_down:
                logger.info("Shutdown complete")


class ServiceLifecycle:
    """Manages lifecycle of long-running services."""

    def __init__(self, shutdown_handler: ShutdownHandler):
        self.shutdown_handler = shutdown_handler
        self.services: List[tuple[str, Callable, Callable]] = []
        self.service_threads: List[threading.Thread] = []

    def register_service(self, name: str, start_func: Callable, stop_func: Callable):
        """Register a service with start and stop functions."""
        self.services.append((name, start_func, stop_func))
        logger.info(f"Registered service: {name}")

    def start_all(self):
        """Start all registered services."""
        logger.info(f"Starting {len(self.services)} services")

        for name, start_func, stop_func in self.services:
            try:
                logger.debug(f"Starting service: {name}")
                thread = threading.Thread(target=start_func, name=f"service-{name}")
                thread.start()
                self.service_threads.append(thread)

                # Register cleanup handler
                self.shutdown_handler.register_cleanup(stop_func, name=f"stop-{name}")

            except Exception as e:
                logger.error(f"Failed to start service {name}: {e}")
                raise

        logger.info("All services started")

    def stop_all(self):
        """Stop all registered services."""
        logger.info(f"Stopping {len(self.services)} services")

        for name, _, stop_func in reversed(self.services):
            try:
                logger.debug(f"Stopping service: {name}")
                stop_func()
            except Exception as e:
                logger.error(f"Error stopping service {name}: {e}")

        # Wait for service threads to finish
        for thread in self.service_threads:
            thread.join(timeout=5)

        logger.info("All services stopped")

    def wait_for_shutdown(self):
        """Wait for shutdown signal and stop all services."""
        self.shutdown_handler.wait_for_shutdown()
        self.stop_all()


# Global shutdown handler instance
_shutdown_handler: Optional[ShutdownHandler] = None


def get_shutdown_handler() -> ShutdownHandler:
    """Get or create the global shutdown handler."""
    global _shutdown_handler
    if _shutdown_handler is None:
        _shutdown_handler = ShutdownHandler()
    return _shutdown_handler


def register_cleanup(handler: Callable, name: Optional[str] = None):
    """Register a cleanup handler with the global shutdown handler."""
    get_shutdown_handler().register_cleanup(handler, name)


def is_shutting_down() -> bool:
    """Check if the application is shutting down."""
    return get_shutdown_handler().is_shutting_down()