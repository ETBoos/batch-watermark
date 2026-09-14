"""Retry policy with exponential backoff."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay_sec: float = 0.5
    max_delay_sec: float = 30.0
    jitter: bool = True

    def delay_for_attempt(self, attempt: int) -> float:
        """attempt is 0-based failure count before this sleep."""
        delay = min(self.max_delay_sec, self.base_delay_sec * (2**attempt))
        if self.jitter:
            delay = delay * (0.5 + random.random())
        return delay

    def should_retry(self, attempt: int) -> bool:
        """attempt is 1-based completed tries."""
        return attempt <= self.max_retries


def run_with_retries(
    fn: Callable[[], T],
    policy: Optional[RetryPolicy] = None,
    *,
    on_retry: Optional[Callable[[int, BaseException, float], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> T:
    """
    Execute fn with retries. attempt counts completed failures.
    Raises last exception after exhausting retries.
    """
    policy = policy or RetryPolicy()
    last_exc: Optional[BaseException] = None
    # total tries = 1 + max_retries
    for attempt in range(1, policy.max_retries + 2):
        if should_cancel and should_cancel():
            raise InterruptedError("cancelled")
        try:
            return fn()
        except InterruptedError:
            raise
        except Exception as exc:  # noqa: BLE001 — job-level catch-all
            last_exc = exc
            if not policy.should_retry(attempt):
                break
            delay = policy.delay_for_attempt(attempt - 1)
            if on_retry:
                on_retry(attempt, exc, delay)
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc
