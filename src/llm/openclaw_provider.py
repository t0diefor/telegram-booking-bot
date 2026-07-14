"""LLM provider backed by OpenClaw's Gateway OpenAI-compatible endpoint.

Requires the Gateway to have `gateway.http.endpoints.chatCompletions.enabled`
set to true (it's off by default) - see README "OpenClaw Gateway setup".

Because this speaks plain OpenAI chat-completions shape, swapping to real
OpenAI or Anthropic later is a matter of writing one more class that hits
a different base URL with a different auth header - see
llm/anthropic_provider.py.example in the README for the shape.
"""
from __future__ import annotations

import logging

import aiohttp

from ..reliability.retry import llm_retry
from .base import LLMProvider

logger = logging.getLogger("bot.llm.openclaw")

FALLBACK_REPLY = (
    "Sorry, I'm having trouble thinking right now. Please try again in a "
    "moment, or use /book to go straight to booking."
)


class OpenClawProvider(LLMProvider):
    def __init__(self, gateway_url: str, gateway_token: str, model: str, timeout_seconds: float = 30.0) -> None:
        self._url = f"{gateway_url}/v1/chat/completions"
        self._headers = {
            "Authorization": f"Bearer {gateway_token}",
            "Content-Type": "application/json",
        }
        self._model = model
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    @llm_retry
    async def _call(self, payload: dict) -> dict:
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            async with session.post(self._url, headers=self._headers, json=payload) as resp:
                if resp.status >= 500:
                    # Treat 5xx as transient - let tenacity retry.
                    text = await resp.text()
                    raise aiohttp.ClientError(f"OpenClaw gateway {resp.status}: {text[:300]}")
                if resp.status >= 400:
                    # 4xx is a real problem (bad token, bad request) - don't retry, just raise.
                    text = await resp.text()
                    raise RuntimeError(f"OpenClaw gateway rejected request ({resp.status}): {text[:300]}")
                return await resp.json()

    async def generate(self, messages: list[dict[str, str]], *, user_id: int) -> str:
        payload = {
            "model": self._model,
            "messages": messages,
            # Stable per-user session key server-side, so the agent's own
            # session continuity lines up with our own conversation_history.
            "user": str(user_id),
        }
        try:
            data = await self._call(payload)
            return data["choices"][0]["message"]["content"]
        except Exception:
            logger.exception("LLM call failed for user_id=%s", user_id)
            return FALLBACK_REPLY
