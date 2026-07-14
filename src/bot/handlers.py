"""All Telegram update handlers: commands, callback (button) queries, and
free-text messages. This is where the state machine, database, and LLM
provider actually get wired together.
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from ..db.database import Database
from ..llm.base import LLMProvider
from ..llm.prompts import build_messages
from .keyboards import confirm_keyboard, date_keyboard, service_keyboard, time_keyboard
from .safe_send import safe_send
from .state_machine import State, can_transition

logger = logging.getLogger("bot.handlers")

HELP_TEXT = (
    "I can help you book an appointment or answer questions about our services.\n\n"
    "/book - start a new booking\n"
    "/cancel - cancel the current booking in progress\n"
    "/help - show this message\n\n"
    "You can also just ask me anything about what we offer."
)

GREETING = "Hi! I'm the booking assistant. Ask me about our services, or use /book to schedule an appointment."


def _db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.bot_data["db"]


def _llm(context: ContextTypes.DEFAULT_TYPE) -> LLMProvider:
    return context.bot_data["llm"]


async def _log_inbound(update: Update, kind: str) -> None:
    user = update.effective_user
    chat = update.effective_chat
    logger.info(
        "update received",
        extra={
            "direction": "inbound",
            "kind": kind,
            "user_id": user.id if user else None,
            "chat_id": chat.id if chat else None,
        },
    )


# -- commands -----------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _log_inbound(update, "command:/start")
    user = update.effective_user
    db = _db(context)
    await db.upsert_user(user.id, user.username, user.first_name)
    await db.set_session(user.id, State.IDLE, {})
    await safe_send(context.bot, update.effective_chat.id, GREETING)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _log_inbound(update, "command:/help")
    await safe_send(context.bot, update.effective_chat.id, HELP_TEXT)


async def book_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _log_inbound(update, "command:/book")
    user = update.effective_user
    db = _db(context)
    await db.set_session(user.id, State.COLLECTING_SERVICE, {})
    await safe_send(
        context.bot,
        update.effective_chat.id,
        "What would you like to book?",
        reply_markup=service_keyboard(),
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _log_inbound(update, "command:/cancel")
    user = update.effective_user
    db = _db(context)
    await db.set_session(user.id, State.IDLE, {})
    await safe_send(context.bot, update.effective_chat.id, "Booking cancelled. Use /book to start again anytime.")


# -- callback (inline keyboard) queries -----------------------------------

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()  # stop the Telegram client's loading spinner promptly
    await _log_inbound(update, f"callback:{query.data}")

    user = update.effective_user
    db = _db(context)
    session = await db.get_session(user.id)
    data = query.data or ""

    if data.startswith("service:") and can_transition(session.state, State.COLLECTING_DATE):
        service = data.split(":", 1)[1]
        await db.set_session(user.id, State.COLLECTING_DATE, {**session.context, "service": service})
        await safe_send(context.bot, update.effective_chat.id, f"Great, a {service}. What day works?", reply_markup=date_keyboard())
        return

    if data.startswith("date:") and can_transition(session.state, State.COLLECTING_TIME):
        chosen_date = data.split(":", 1)[1]
        await db.set_session(user.id, State.COLLECTING_TIME, {**session.context, "date": chosen_date})
        await safe_send(context.bot, update.effective_chat.id, f"And what time on {chosen_date}?", reply_markup=time_keyboard())
        return

    if data.startswith("time:") and can_transition(session.state, State.CONFIRMING):
        chosen_time = data.split(":", 1)[1]
        ctx = {**session.context, "time": chosen_time}
        await db.set_session(user.id, State.CONFIRMING, ctx)
        summary = f"{ctx.get('service')} on {ctx.get('date')} at {chosen_time}. Confirm?"
        await safe_send(context.bot, update.effective_chat.id, summary, reply_markup=confirm_keyboard())
        return

    if data == "confirm:yes" and can_transition(session.state, State.BOOKED):
        ctx = session.context
        await db.create_booking(user.id, ctx.get("service", "unknown"), ctx.get("date", "unknown"), ctx.get("time", "unknown"))
        await db.set_session(user.id, State.BOOKED, {})
        await safe_send(context.bot, update.effective_chat.id, "Booked! See you then. Use /book anytime for another appointment.")
        return

    if data == "confirm:no":
        await db.set_session(user.id, State.IDLE, {})
        await safe_send(context.bot, update.effective_chat.id, "No problem, cancelled. Use /book to start over.")
        return

    if data == "nav:back_to_service":
        await db.set_session(user.id, State.COLLECTING_SERVICE, {})
        await safe_send(context.bot, update.effective_chat.id, "What would you like to book?", reply_markup=service_keyboard())
        return

    if data == "nav:back_to_date" and can_transition(session.state, State.COLLECTING_DATE):
        await db.set_session(user.id, State.COLLECTING_DATE, {k: v for k, v in session.context.items() if k != "time"})
        await safe_send(context.bot, update.effective_chat.id, "What day works?", reply_markup=date_keyboard())
        return

    # Anything else: a stale button press (e.g. after a restart changed
    # state) or an invalid transition. Never go silent - explain and
    # reset to a known-good state instead of just ignoring the tap.
    logger.warning("unhandled or invalid callback", extra={"callback_data": data, "state": session.state})
    await db.set_session(user.id, State.IDLE, {})
    await safe_send(
        context.bot,
        update.effective_chat.id,
        "That option isn't valid anymore (maybe the bot restarted). Let's start fresh - use /book.",
    )


# -- free text: FAQ / general chat, layered on top of the state machine ---

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _log_inbound(update, "message:text")
    user = update.effective_user
    chat_id = update.effective_chat.id
    user_text = update.message.text

    db = _db(context)
    llm = _llm(context)

    await db.upsert_user(user.id, user.username, user.first_name)
    await db.append_history(user.id, "user", user_text)

    history = await db.get_recent_history(user.id, limit=6)
    # get_recent_history includes the turn we just appended; drop it so we
    # don't send the new user message to the LLM twice.
    history = history[:-1] if history else history

    messages = build_messages(history, user_text)
    reply = await llm.generate(messages, user_id=user.id)

    await db.append_history(user.id, "assistant", reply)
    await safe_send(context.bot, chat_id, reply)


async def unrecognized_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catch-all for message types we don't explicitly handle (stickers,
    voice notes, etc). Requirement: never let the bot go silent."""
    await _log_inbound(update, "message:unrecognized")
    await safe_send(
        context.bot,
        update.effective_chat.id,
        "I can only read text messages right now - try typing your question, or use /book to schedule.",
    )
