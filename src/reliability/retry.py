"""Shared retry policies for anything that talks to a network.

Two presets: one for the LLM call (a few retries, moderate backoff - a slow
model response shouldn't be abandoned too eagerly), one for Telegram API
calls (fast retries - Telegram itself is usually either up or briefly
flaky, not slow). Both only retry on transient failure classes; anything
that looks like a permanent error (bad auth, malformed request) is not
retried, since retrying those just wastes time before failing anyway.
"""
from __future__ import annotations

import aiohttp
from telegram.error import NetworkError, RetryAfter, TimedOut
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

llm_retry = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((aiohttp.ClientError, TimeoutError)),
)

telegram_retry = retry(
    reraise=True,
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
    retry=retry_if_exception_type((NetworkError, TimedOut, RetryAfter)),
)
