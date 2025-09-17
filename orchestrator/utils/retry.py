"""Retry logic and decorators for AtlasAgents."""

import time
import random
import functools
from typing import Type, Tuple, Union, Optional, Callable, Any
from orchestrator.utils.logging import get_logger
from orchestrator.utils.exceptions import RetryableError, AtlasError


logger = get_logger(__name__)


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: Tuple[Type[Exception], ...] = (RetryableError,)
    ):
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt number."""
        delay = min(
            self.initial_delay * (self.exponential_base ** (attempt - 1)),
            self.max_delay
        )

        if self.jitter:
            # Add random jitter up to 25% of the delay
            jitter_amount = delay * 0.25 * random.random()
            delay = delay + jitter_amount

        return delay


class RetryManager:
    """Manages retry logic for operations."""

    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()

    def execute_with_retry(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute a function with retry logic.

        Args:
            func: Function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the function

        Raises:
            The last exception if all retries fail
        """
        last_exception = None

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                logger.debug(
                    f"Attempt {attempt}/{self.config.max_attempts} for {func.__name__}",
                    attempt=attempt,
                    max_attempts=self.config.max_attempts,
                    function=func.__name__
                )

                result = func(*args, **kwargs)

                if attempt > 1:
                    logger.info(
                        f"Succeeded on attempt {attempt} for {func.__name__}",
                        attempt=attempt,
                        function=func.__name__
                    )

                return result

            except self.config.retryable_exceptions as e:
                last_exception = e

                if attempt == self.config.max_attempts:
                    logger.error(
                        f"Max retries exceeded for {func.__name__}",
                        attempt=attempt,
                        max_attempts=self.config.max_attempts,
                        function=func.__name__,
                        error=str(e)
                    )
                    raise

                delay = self.config.get_delay(attempt)
                logger.warning(
                    f"Retryable error on attempt {attempt}, retrying in {delay:.1f}s",
                    attempt=attempt,
                    delay=delay,
                    function=func.__name__,
                    error=str(e)
                )

                time.sleep(delay)

            except Exception as e:
                # Non-retryable exception
                logger.error(
                    f"Non-retryable error in {func.__name__}",
                    function=func.__name__,
                    error=str(e),
                    exc_info=True
                )
                raise

        # Should never reach here, but just in case
        if last_exception:
            raise last_exception


def retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (RetryableError,)
):
    """
    Decorator for adding retry logic to functions.

    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff
        jitter: Whether to add random jitter to delays
        retryable_exceptions: Tuple of exception types to retry on

    Example:
        @retry(max_attempts=5, initial_delay=2.0)
        def flaky_operation():
            # Some operation that might fail
            pass
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        initial_delay=initial_delay,
        max_delay=max_delay,
        exponential_base=exponential_base,
        jitter=jitter,
        retryable_exceptions=retryable_exceptions
    )

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            manager = RetryManager(config)
            return manager.execute_with_retry(func, *args, **kwargs)
        return wrapper

    return decorator


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for preventing cascading failures.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "closed"  # closed, open, half-open

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Call a function through the circuit breaker.

        Args:
            func: Function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result of the function

        Raises:
            Exception: If circuit is open or function fails
        """
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half-open"
                logger.info(f"Circuit breaker entering half-open state for {func.__name__}")
            else:
                raise AtlasError(f"Circuit breaker is open for {func.__name__}")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result

        except self.expected_exception as e:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        return (
            self.last_failure_time and
            time.time() - self.last_failure_time >= self.recovery_timeout
        )

    def _on_success(self):
        """Handle successful call."""
        if self.state == "half-open":
            logger.info("Circuit breaker reset to closed state")
            self.state = "closed"

        self.failure_count = 0

    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures",
                failure_count=self.failure_count,
                threshold=self.failure_threshold
            )


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    expected_exception: Type[Exception] = Exception
):
    """
    Decorator for adding circuit breaker pattern to functions.

    Args:
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds to wait before attempting reset
        expected_exception: Exception type to track for failures

    Example:
        @circuit_breaker(failure_threshold=3, recovery_timeout=30)
        def external_api_call():
            # Call to external service
            pass
    """
    breaker = CircuitBreaker(failure_threshold, recovery_timeout, expected_exception)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)
        return wrapper

    return decorator