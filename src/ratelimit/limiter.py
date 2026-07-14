"""Token-bucket rate limiting for outbound Telegram sends.

Telegram's documented limits: ~30 messages/sec globally, ~1 message/sec per
chat. python-telegram-bot does not enforce these for you - if you blast
messages faster than that you'll start getting 429s. Two independent
buckets (global + per-chat) enforce both ceilings.
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict


class TokenBucket:
    def __init__(self, rate_per_sec: float, burst: float) -> None:
        self._rate = rate_per_sec
        self._capacity = burst
        self._tokens = burst
        self._last_check = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last_check
                self._last_check = now
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await asyncio.sleep((1 - self._tokens) / self._rate)


class TelegramRateLimiter:
    """One global bucket (30/sec) + one bucket per chat_id (1/sec)."""

    def __init__(self, global_rate: float = 30.0, per_chat_rate: float = 1.0) -> None:
        self._global_bucket = TokenBucket(global_rate, burst=global_rate)
        self._per_chat_rate = per_chat_rate
        self._chat_buckets: dict[int, TokenBucket] = defaultdict(
            lambda: TokenBucket(per_chat_rate, burst=max(per_chat_rate, 1))
        )

    async def acquire(self, chat_id: int) -> None:
        await self._global_bucket.acquire()
        await self._chat_buckets[chat_id].acquire()
