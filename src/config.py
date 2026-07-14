"""Central configuration, loaded once from environment / .env.

Fail fast: if a required setting is missing, raise at startup rather than
limping along and failing confusingly later.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    # Telegram
    telegram_bot_token: str
    telegram_webhook_secret: str
    bot_mode: str  # "polling" | "webhook"
    webhook_url: str
    webhook_listen_host: str
    webhook_listen_port: int

    # OpenClaw Gateway / LLM
    openclaw_gateway_url: str
    openclaw_gateway_token: str
    openclaw_agent_model: str

    # Database
    db_path: Path
    conversation_history_max_age_days: int

    # Logging
    log_path: Path
    log_level: str

    @staticmethod
    def load() -> "Config":
        bot_mode = os.environ.get("BOT_MODE", "polling").strip().lower()
        if bot_mode not in ("polling", "webhook"):
            raise RuntimeError(f"BOT_MODE must be 'polling' or 'webhook', got {bot_mode!r}")

        cfg = Config(
            telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
            telegram_webhook_secret=_require("TELEGRAM_WEBHOOK_SECRET"),
            bot_mode=bot_mode,
            webhook_url=os.environ.get("WEBHOOK_URL", ""),
            webhook_listen_host=os.environ.get("WEBHOOK_LISTEN_HOST", "0.0.0.0"),
            webhook_listen_port=int(os.environ.get("WEBHOOK_LISTEN_PORT", "8443")),
            openclaw_gateway_url=_require("OPENCLAW_GATEWAY_URL").rstrip("/"),
            openclaw_gateway_token=_require("OPENCLAW_GATEWAY_TOKEN"),
            openclaw_agent_model=os.environ.get("OPENCLAW_AGENT_MODEL", "openclaw/default"),
            db_path=Path(os.environ.get("DB_PATH", "./data/bot.db")),
            conversation_history_max_age_days=int(
                os.environ.get("CONVERSATION_HISTORY_MAX_AGE_DAYS", "30")
            ),
            log_path=Path(os.environ.get("LOG_PATH", "./logs/bot.log")),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )

        if cfg.bot_mode == "webhook" and not cfg.webhook_url:
            raise RuntimeError("BOT_MODE=webhook requires WEBHOOK_URL to be set")

        cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.log_path.parent.mkdir(parents=True, exist_ok=True)
        return cfg


config = Config.load()
