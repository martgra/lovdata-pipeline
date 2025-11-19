"""Retry utilities for handling transient errors.

This module provides reusable retry configuration using the tenacity library
for handling transient errors in the pipeline.
"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TransientError(Exception):
    """Exception indicating a transient error that should be retried."""

    pass


class PermanentError(Exception):
    """Exception indicating a permanent error that should not be retried."""

    pass


# Common transient exceptions that warrant retry
TRANSIENT_EXCEPTIONS = (ConnectionError, TimeoutError, OSError)

# Common permanent exceptions that should not be retried
PERMANENT_EXCEPTIONS = (FileNotFoundError, ValueError, TypeError)


def create_retry_decorator(
    max_attempts: int = 3,
    min_wait: int = 1,
    max_wait: int = 10,
    transient_exceptions: tuple[type[Exception], ...] = TRANSIENT_EXCEPTIONS,
):
    """Create a tenacity retry decorator with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        min_wait: Minimum wait time in seconds
        max_wait: Maximum wait time in seconds
        transient_exceptions: Tuple of exception types to retry

    Returns:
        Tenacity retry decorator

    Example:
        >>> retry_decorator = create_retry_decorator(max_attempts=3)
        >>> @retry_decorator
        ... def fetch_data():
        ...     # May raise ConnectionError
        ...     return data
    """
    return retry(
        retry=retry_if_exception_type(transient_exceptions),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        reraise=True,
    )


def retry_with_exponential_backoff(
    func: Callable[..., T],
    *args: Any,
    max_retries: int = 3,
    transient_exceptions: tuple[type[Exception], ...] = TRANSIENT_EXCEPTIONS,
    permanent_exceptions: tuple[type[Exception], ...] = PERMANENT_EXCEPTIONS,
    **kwargs: Any,
) -> T:
    """Execute a function with exponential backoff retry logic using tenacity.

    Args:
        func: Function to execute
        *args: Positional arguments to pass to func
        max_retries: Maximum number of retry attempts (default: 3)
        transient_exceptions: Tuple of exception types to retry
        permanent_exceptions: Tuple of exception types that should not retry
        **kwargs: Keyword arguments to pass to func

    Returns:
        Result of the function call

    Raises:
        PermanentError: If a permanent error occurs
        Exception: If max retries exceeded for transient errors

    Example:
        >>> def fetch_data():
        ...     # May raise ConnectionError
        ...     return data
        >>> result = retry_with_exponential_backoff(fetch_data)
    """
    # Create retry decorator for this specific call
    retry_decorator = retry(
        retry=retry_if_exception_type(transient_exceptions),
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )

    # Wrap the function call
    @retry_decorator
    def _wrapped_call():
        try:
            return func(*args, **kwargs)
        except permanent_exceptions as e:
            # Convert permanent exceptions to PermanentError to avoid retry
            logger.error(f"Permanent error in {func.__name__}: {e}")
            raise PermanentError(f"Permanent error: {e}") from e

    try:
        return _wrapped_call()
    except Exception as e:
        # Log final failure
        logger.error(f"Failed to execute {func.__name__} after {max_retries} attempts: {e}")
        raise


def process_with_retry(
    items: list[Any],
    process_func: Callable[[Any], T],
    max_retries: int = 3,
    on_success: Callable[[Any, T], None] | None = None,
    on_failure: Callable[[Any, Exception], None] | None = None,
) -> tuple[list[T], list[tuple[Any, Exception]]]:
    """Process a list of items with retry logic using tenacity.

    Args:
        items: List of items to process
        process_func: Function to process each item
        max_retries: Maximum retry attempts per item
        on_success: Optional callback on successful processing
        on_failure: Optional callback on permanent failure

    Returns:
        Tuple of (successful_results, failed_items_with_errors)

    Example:
        >>> def process_file(file_path):
        ...     # Process file
        ...     return result
        >>> results, failures = process_with_retry(
        ...     file_paths,
        ...     process_file,
        ...     on_success=lambda path, result: logger.info(f"Processed {path}")
        ... )
    """
    successful_results = []
    failed_items = []

    for item in items:
        try:
            result = retry_with_exponential_backoff(process_func, item, max_retries=max_retries)
            successful_results.append(result)

            if on_success:
                on_success(item, result)

        except Exception as e:
            failed_items.append((item, e))

            if on_failure:
                on_failure(item, e)

    return successful_results, failed_items
