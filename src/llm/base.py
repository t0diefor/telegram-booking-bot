"""LLM provider abstraction.

Everything downstream (handlers.py) talks to this interface only. Swapping
the actual backend - OpenClaw today, direct Anthropic/OpenAI later - means
writing one new class here and changing one line in main.py's wiring.
Nothing else in the codebase needs to know which provider is active.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, messages: list[dict[str, str]], *, user_id: int) -> str:
        """messages: OpenAI-shape list of {"role": "system"|"user"|"assistant", "content": str}.

        Returns the assistant's reply text. Implementations are responsible
        for their own retry/timeout behavior (see reliability/retry.py) -
        callers should be able to treat this as "either a string comes back,
        or an exception is raised after retries are exhausted."
        """
        raise NotImplementedError
