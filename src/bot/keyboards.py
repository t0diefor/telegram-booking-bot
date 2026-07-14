"""Inline keyboard builders for the booking flow."""
from __future__ import annotations

from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .state_machine import SERVICES, TIME_SLOTS


def service_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(s, callback_data=f"service:{s}")] for s in SERVICES]
    return InlineKeyboardMarkup(rows)


def date_keyboard(days_ahead: int = 7) -> InlineKeyboardMarkup:
    today = datetime.now().date()
    rows = []
    for i in range(1, days_ahead + 1):
        day = today + timedelta(days=i)
        label = day.strftime("%a %b %d")
        rows.append([InlineKeyboardButton(label, callback_data=f"date:{day.isoformat()}")])
    rows.append([InlineKeyboardButton("<< Back", callback_data="nav:back_to_service")])
    return InlineKeyboardMarkup(rows)


def time_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(t, callback_data=f"time:{t}")] for t in TIME_SLOTS]
    rows.append([InlineKeyboardButton("<< Back", callback_data="nav:back_to_date")])
    return InlineKeyboardMarkup(rows)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirm booking", callback_data="confirm:yes"),
                InlineKeyboardButton("Cancel", callback_data="confirm:no"),
            ]
        ]
    )
