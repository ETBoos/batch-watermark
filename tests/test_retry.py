"""Unit tests for retry policy."""

from __future__ import annotations

import pytest

from batch_watermark.core.retry import RetryPolicy, run_with_retries


def test_delay_exponential():
    policy = RetryPolicy(max_retries=3, base_delay_sec=1.0, max_delay_sec=100, jitter=False)
    assert policy.delay_for_attempt(0) == 1.0
    assert policy.delay_for_attempt(1) == 2.0
    assert policy.delay_for_attempt(2) == 4.0


def test_should_retry_bounds():
    policy = RetryPolicy(max_retries=3)
    assert policy.should_retry(1) is True
    assert policy.should_retry(3) is True
    assert policy.should_retry(4) is False


def test_run_with_retries_success_after_failures(monkeypatch):
    policy = RetryPolicy(max_retries=3, base_delay_sec=0.01, jitter=False)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("fail")
        return "ok"

    monkeypatch.setattr("batch_watermark.core.retry.time.sleep", lambda _s: None)
    assert run_with_retries(flaky, policy) == "ok"
    assert calls["n"] == 3


def test_run_with_retries_exhausted(monkeypatch):
    policy = RetryPolicy(max_retries=2, base_delay_sec=0.01, jitter=False)
    monkeypatch.setattr("batch_watermark.core.retry.time.sleep", lambda _s: None)

    def always_fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        run_with_retries(always_fail, policy)


def test_cancel_raises():
    policy = RetryPolicy(max_retries=5, base_delay_sec=0.01, jitter=False)

    def fail():
        raise ValueError("x")

    with pytest.raises(InterruptedError):
        run_with_retries(fail, policy, should_cancel=lambda: True)
