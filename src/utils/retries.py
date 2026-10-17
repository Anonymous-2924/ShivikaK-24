"""Retry helpers with exponential backoff and jitter.

Uses ``tenacity`` when available, with a small dependency-free fallback so the
core remains importable in minimal environments.
"""
from __future__ import annotations

import random
import time
from typing import Callable, Iterable, Type, TypeVar

T = TypeVar("T")

try:  # pragma: no cover - exercised indirectly
    from tenacity import (
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential_jitter,
    )

    _HAS_TENACITY = True
except Exception:  # pragma: no cover
    _HAS_TENACITY = False


def retry_call(
    func: Callable[[], T],
    *,
    retry_on: Iterable[Type[BaseException]],
    max_attempts: int = 4,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
) -> T:
    """Call ``func`` with retries on the given exception types.

    Backoff is exponential (base_delay * 2**n) capped at ``max_delay`` with
    random jitter. Re-raises the last exception when attempts are exhausted.
    """
    exc_types = tuple(retry_on)
    attempt = 0
    while True:
        try:
            return func()
        except exc_types as exc:  # type: ignore[misc]
            attempt += 1
            if attempt >= max_attempts:
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay += random.uniform(0, delay * 0.25)  # jitter
            time.sleep(delay)
        except Exception:
            raise  # non-retryable


def tenacity_retry(retry_on: Iterable[Type[BaseException]], max_attempts: int = 4):
    """Decorator form backed by tenacity when present, else :func:`retry_call`."""
    exc_types = tuple(retry_on)
    if _HAS_TENACITY:
        return retry(
            reraise=True,
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential_jitter(initial=2, max=30),
            retry=retry_if_exception_type(exc_types),
        )

    def decorator(fn):
        def wrapper(*args, **kwargs):
            return retry_call(
                lambda: fn(*args, **kwargs),
                retry_on=exc_types,
                max_attempts=max_attempts,
            )

        return wrapper

    return decorator
