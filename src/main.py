"""Entrypoint: wires config, database, LLM provider, and handlers together,
then runs the bot in polling or webhook mode.
"""
from __future__ import annotations

import logging

from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from .bot import handlers
from .config import config
from .db.database import Database
from .llm.openclaw_provider import OpenClawProvider
from .reliability.logging_config import configure_logging

logger = logging.getLogger("bot.main")

PRUNE_INTERVAL_SECONDS = 24 * 60 * 60  # once a day


async def _prune_job(context) -> None:
    db: Database = context.application.bot_data["db"]
    await db.prune_old_history(config.conversation_history_max_age_days)


async def _post_init(application: Application) -> None:
    db = Database(config.db_path)
    await db.connect()
    application.bot_data["db"] = db
    application.bot_data["llm"] = OpenClawProvider(
        gateway_url=config.openclaw_gateway_url,
        gateway_token=config.openclaw_gateway_token,
        model=config.openclaw_agent_model,
    )
    application.job_queue.run_repeating(_prune_job, interval=PRUNE_INTERVAL_SECONDS, first=60)
    logger.info("bot initialized: mode=%s db=%s model=%s", config.bot_mode, config.db_path, config.openclaw_agent_model)


async def _post_shutdown(application: Application) -> None:
    db: Database = application.bot_data.get("db")
    if db is not None:
        await db.close()
    logger.info("bot shut down cleanly")


def build_application() -> Application:
    application = (
        ApplicationBuilder()
        .token(config.telegram_bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", handlers.start_command))
    application.add_handler(CommandHandler("help", handlers.help_command))
    application.add_handler(CommandHandler("book", handlers.book_command))
    application.add_handler(CommandHandler("cancel", handlers.cancel_command))
    application.add_handler(CallbackQueryHandler(handlers.callback_query_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.text_handler))
    # Catch-all for anything else (stickers, photos, voice, etc) - requirement
    # is the bot must never go silent on an update it doesn't recognize.
    application.add_handler(MessageHandler(filters.ALL, handlers.unrecognized_handler))

    return application


def main() -> None:
    configure_logging(config.log_path, config.log_level)
    application = build_application()

    if config.bot_mode == "polling":
        logger.info("starting in polling mode")
        application.run_polling(allowed_updates=["message", "callback_query"])
    else:
        logger.info("starting in webhook mode: listening on %s:%s", config.webhook_listen_host, config.webhook_listen_port)
        application.run_webhook(
            listen=config.webhook_listen_host,
            port=config.webhook_listen_port,
            secret_token=config.telegram_webhook_secret,
            webhook_url=config.webhook_url,
            allowed_updates=["message", "callback_query"],
        )


if __name__ == "__main__":
    main()
