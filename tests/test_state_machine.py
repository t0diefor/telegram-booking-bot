"""Unit tests for the booking state machine's transition rules.

These don't touch Telegram, the database, or the LLM - just the pure logic
in src/bot/state_machine.py. Run with: pytest tests/
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bot.state_machine import State, can_transition  # noqa: E402


def test_idle_can_start_booking():
    assert can_transition(State.IDLE, State.COLLECTING_SERVICE) is True


def test_idle_cannot_skip_to_confirming():
    assert can_transition(State.IDLE, State.CONFIRMING) is False


def test_full_happy_path_is_valid():
    path = [
        (State.IDLE, State.COLLECTING_SERVICE),
        (State.COLLECTING_SERVICE, State.COLLECTING_DATE),
        (State.COLLECTING_DATE, State.COLLECTING_TIME),
        (State.COLLECTING_TIME, State.CONFIRMING),
        (State.CONFIRMING, State.BOOKED),
        (State.BOOKED, State.IDLE),
    ]
    for current, target in path:
        assert can_transition(current, target) is True, f"{current} -> {target} should be valid"


def test_cannot_go_backwards_from_booked_to_confirming():
    assert can_transition(State.BOOKED, State.CONFIRMING) is False


def test_back_navigation_is_valid():
    assert can_transition(State.COLLECTING_DATE, State.COLLECTING_SERVICE) is True
    assert can_transition(State.COLLECTING_TIME, State.COLLECTING_DATE) is True
    assert can_transition(State.CONFIRMING, State.COLLECTING_TIME) is True


def test_any_non_idle_state_can_cancel_to_idle():
    for state in State:
        if state is State.IDLE:
            continue  # already idle - not a meaningful transition
        assert can_transition(state, State.IDLE) is True, f"{state} should be able to cancel to idle"


def test_unknown_current_state_string_is_rejected():
    assert can_transition("not_a_real_state", State.COLLECTING_SERVICE) is False


def test_confirming_cannot_jump_to_collecting_service():
    assert can_transition(State.CONFIRMING, State.COLLECTING_SERVICE) is False
