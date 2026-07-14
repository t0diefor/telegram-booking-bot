"""Rate-limited, retried wrapper around sending Telegram messages.

Every outbound send in the bot should go through here, not
`context.bot.send_message` directly, so rate limiting and retry/logging
are applied uniformly instead of being re-implemented per handler.
"""
from __future__ import annotations

import logging

from telegram import Bot, InlineKeyboardMarkup

from ..ratelimit.limiter import TelegramRateLimiter
from ..reliability.retry import telegram_retry

logger = logging.getLogger("bot.send")

_limiter = TelegramRateLimiter()


@telegram_retry
async def _send(bot: Bot, chat_id: int, text: str, reply_markup: InlineKeyboardMarkup | None) -> None:
    await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


async def safe_send(bot: Bot, chat_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    await _limiter.acquire(chat_id)
    try:
        await _send(bot, chat_id, text, reply_markup)
        logger.info("message sent", extra={"chat_id": chat_id, "direction": "outbound", "length": len(text)})
    except Exception:
        # Last-resort fallback: log it, don't let the caller crash the
        # update loop over a single failed send. If this send WAS itself
        # the fallback message, there's nothing more we can safely do.
        logger.exception("failed to send message after retries", extra={"chat_id": chat_id})
