"""
Retry utilities with exponential backoff and jitter.

Why a decorator rather than inline try/except?
  Without a decorator, every retryable function looks like:
    for attempt in range(3):
        try:
            result = await do_thing()
            break
        except Exception as e:
            if attempt == 2: raise
            await asyncio.sleep(2 ** attempt)

  That's 8 lines of boilerplate per function. With @with_retry,
  it's one line. Same logic, zero repetition.

Why async specifically?
  Browser automation is async. A synchronous retry decorator would
  block the event loop during sleep — no other requests could be
  handled. asyncio.sleep() yields control back during the wait.

Exponential backoff formula:
  delay = min(base_delay * (2 ** attempt), max_delay) + jitter
  attempt 0: min(1.0 * 1,  10) + jitter  = ~1.0s
  attempt 1: min(1.0 * 2,  10) + jitter  = ~2.2s
  attempt 2: min(1.0 * 4,  10) + jitter  = ~4.3s
  attempt 3: min(1.0 * 8,  10) + jitter  = ~8.5s
  attempt 4: min(1.0 * 16, 10) + jitter  = ~10.6s  ← capped at max_delay
"""

import asyncio
import random
from functools import wraps
from typing import Callable, TypeVar, Any

T = TypeVar("T")


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    jitter: float = 0.5,
    exceptions: tuple = (Exception,),
):
    """
    Decorator: retry an async function with exponential backoff.

    Args:
        max_attempts: Total attempts (not retries — 3 means 1 try + 2 retries)
        base_delay:   Initial delay in seconds (doubles each attempt)
        max_delay:    Cap on delay — prevents waiting forever
        jitter:       Random ±N seconds added to each delay
        exceptions:   Only retry on these exception types (default: all)

    Usage:
        @with_retry(max_attempts=3, base_delay=1.0)
        async def fetch_page(url: str) -> str:
            ...

        # or for one-off use:
        result = await retry_async(my_fn, arg1, arg2, max_attempts=3)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_async(
                func, *args,
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                jitter=jitter,
                exceptions=exceptions,
                **kwargs,
            )
        return wrapper
    return decorator


async def retry_async(
    func: Callable,
    *args,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    jitter: float = 0.5,
    exceptions: tuple = (Exception,),
    **kwargs,
) -> Any:
    """
    Retry an async function with exponential backoff.
    Can be used without decorator for one-off retries.

    Example:
        result = await retry_async(navigate_to, page, url, max_attempts=3)
    """
    last_exception: Exception | None = None

    for attempt in range(max_attempts):
        try:
            return await func(*args, **kwargs)

        except exceptions as e:
            last_exception = e
            is_last = attempt == max_attempts - 1

            if is_last:
                break

            delay = min(base_delay * (2 ** attempt), max_delay)
            delay += random.uniform(-jitter, jitter)
            delay = max(0.1, delay)  # never wait less than 100ms

            print(
                f"[Retry] {func.__name__} attempt {attempt + 1}/{max_attempts} "
                f"failed: {type(e).__name__}: {str(e)[:80]}. "
                f"Retrying in {delay:.1f}s..."
            )
            await asyncio.sleep(delay)

    raise last_exception


def human_delay(min_ms: int = 80, max_ms: int = 350) -> float:
    """
    Return a random delay in seconds that mimics human reaction time.

    Why random?
    - Fixed 500ms delays are easily fingerprinted by anti-bot systems
    - Real humans take 80–400ms between UI interactions
    - Randomness prevents pattern detection

    Usage:
        await asyncio.sleep(human_delay())
        await asyncio.sleep(human_delay(min_ms=200, max_ms=600))  # slower, more careful
    """
    return random.randint(min_ms, max_ms) / 1000
