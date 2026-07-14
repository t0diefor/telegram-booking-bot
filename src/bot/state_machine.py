"""The booking flow's state machine.

idle -> collecting_service -> collecting_date -> collecting_time
     -> confirming -> booked (terminal, next /start or /book returns to idle)

Any state can fall back to FREEFORM handling (routed to the LLM) if the
user sends something that isn't a recognized button press - see
bot/handlers.py `handle_text`. The state machine governs *booking*
specifically; general chat/FAQ is always available on top of it.
"""
from __future__ import annotations

from enum import Enum


class State(str, Enum):
    IDLE = "idle"
    COLLECTING_SERVICE = "collecting_service"
    COLLECTING_DATE = "collecting_date"
    COLLECTING_TIME = "collecting_time"
    CONFIRMING = "confirming"
    BOOKED = "booked"


# Explicit, auditable transition table. Anything not listed here is invalid
# and handlers.py should refuse it rather than guess.
VALID_TRANSITIONS: dict[State, set[State]] = {
    State.IDLE: {State.COLLECTING_SERVICE},
    State.COLLECTING_SERVICE: {State.COLLECTING_DATE, State.IDLE},
    State.COLLECTING_DATE: {State.COLLECTING_TIME, State.COLLECTING_SERVICE, State.IDLE},
    State.COLLECTING_TIME: {State.CONFIRMING, State.COLLECTING_DATE, State.IDLE},
    State.CONFIRMING: {State.BOOKED, State.COLLECTING_TIME, State.IDLE},
    State.BOOKED: {State.IDLE},
}


def can_transition(current: str, target: State) -> bool:
    try:
        current_state = State(current)
    except ValueError:
        return False
    return target in VALID_TRANSITIONS.get(current_state, set())


SERVICES = ["Consultation", "Haircut", "Repair Estimate"]
TIME_SLOTS = ["09:00", "11:00", "13:00", "15:00", "17:00"]
