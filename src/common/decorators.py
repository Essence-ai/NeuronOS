"""
Error Handling Decorators

Provides decorators for consistent error handling across NeuronOS.
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Type, Tuple, Callable, Any, Optional

logger = logging.getLogger(__name__)


def handle_errors(
    *exception_types: Type[Exception],
    default: Any = None,
    log_level: int = logging.ERROR,
    reraise: bool = False,
    message: Optional[str] = None,
):
    """
    Decorator to handle exceptions consistently.

    Args:
        exception_types: Exception types to catch (default: Exception)
        default: Value to return on error
        log_level: Logging level for errors
        reraise: Whether to re-raise after logging
        message: Custom error message prefix
    
    Example:
        @handle_errors(ValueError, TypeError, default=None)
        def parse_config(path):
            ...
    """
    if not exception_types:
        exception_types = (Exception,)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exception_types as e:
                prefix = message or f"{func.__name__} failed"
                logger.log(
                    log_level,
                    f"{prefix}: {e}",
                    exc_info=log_level >= logging.ERROR,
                )
                if reraise:
                    raise
                return default
        return wrapper
    return decorator


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
):
    """
    Decorator to retry failed operations with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for delay after each retry
        exceptions: Exception types to catch and retry
        on_retry: Callback called on each retry with (exception, attempt)
    
    Example:
        @retry(max_attempts=3, delay=0.5, exceptions=(ConnectionError,))
        def connect_to_server():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_attempts}): {e}"
                        )
                        if on_retry:
                            on_retry(e, attempt + 1)
                        time.sleep(current_delay)
                        current_delay *= backoff

            # All attempts exhausted
            logger.error(
                f"{func.__name__} failed after {max_attempts} attempts: {last_exception}"
            )
            raise last_exception

        return wrapper
    return decorator


def ensure_connected(connection_attr: str = "_connection"):
    """
    Decorator to ensure a connection is established before calling method.
    
    Args:
        connection_attr: Name of the connection attribute on self
    
    Example:
        @ensure_connected("_conn")
        def execute_query(self, sql):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            conn = getattr(self, connection_attr, None)
            if conn is None:
                raise RuntimeError(
                    f"Connection not established. Call connect() before {func.__name__}()"
                )
            return func(self, *args, **kwargs)
        return wrapper
    return decorator


def deprecated(message: str = "", version: str = ""):
    """
    Mark a function as deprecated.
    
    Args:
        message: Deprecation message
        version: Version when deprecated
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            import warnings
            warning_msg = f"{func.__name__} is deprecated"
            if version:
                warning_msg += f" since version {version}"
            if message:
                warning_msg += f": {message}"
            warnings.warn(warning_msg, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def require_root(func: Callable) -> Callable:
    """
    Decorator that requires root/sudo privileges.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        import os
        if os.geteuid() != 0:
            raise PermissionError(
                f"{func.__name__} requires root privileges. Run with sudo."
            )
        return func(*args, **kwargs)
    return wrapper


def timed(func: Callable) -> Callable:
    """
    Decorator to log function execution time.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            logger.debug(f"{func.__name__} completed in {elapsed:.3f}s")
    return wrapper
