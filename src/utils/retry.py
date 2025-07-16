"""Retry logic and exponential backoff utilities."""

import time
import random
import logging
from functools import wraps
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)


def exponential_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """Calculate exponential backoff delay with jitter."""
    delay = min(base_delay * (2 ** attempt), max_delay)
    # Add jitter to prevent thundering herd
    jitter = random.uniform(0, delay * 0.1)
    return delay + jitter


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,)
):
    """Decorator for exponential backoff retry logic."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(f"Function {func.__name__} failed after {max_retries} retries: {e}")
                        raise e
                    
                    delay = exponential_backoff(attempt, base_delay, max_delay)
                    logger.warning(
                        f"Attempt {attempt + 1} of {func.__name__} failed: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    time.sleep(delay)
            
            # This should never be reached, but just in case
            raise last_exception
        
        return wrapper
    return decorator


class RetryableError(Exception):
    """Base class for errors that should trigger retries."""
    pass


class APIRateLimitError(RetryableError):
    """Raised when API rate limit is hit."""
    pass


class NetworkError(RetryableError):
    """Raised for network-related errors."""
    pass


class TemporaryServiceError(RetryableError):
    """Raised for temporary service unavailability."""
    pass


# Specific retry decorators for different use cases
def retry_api_call(max_retries: int = 5, base_delay: float = 2.0):
    """Retry decorator specifically for API calls with longer delays."""
    return retry_with_backoff(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=120.0,
        exceptions=(APIRateLimitError, NetworkError, TemporaryServiceError)
    )


def retry_file_operation(max_retries: int = 3, base_delay: float = 1.0):
    """Retry decorator for file operations with shorter delays."""
    return retry_with_backoff(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=10.0,
        exceptions=(OSError, IOError, PermissionError)
    )


def retry_download(max_retries: int = 3, base_delay: float = 2.0):
    """Retry decorator for download operations."""
    return retry_with_backoff(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=60.0,
        exceptions=(NetworkError, TemporaryServiceError, ConnectionError)
    )