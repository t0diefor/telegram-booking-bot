# Telegram Booking Bot

A production-minded Telegram bot for appointment booking, with a general-purpose
FAQ/chat assistant layered on top, powered by an OpenClaw Gateway agent as the
LLM backend. Built with `python-telegram-bot` (async), SQLite, and a small
number of dependency-free reliability primitives (retry, rate limiting,
structured logging).

## What it does

- **Booking flow** (`/book`): a strict, auditable state machine
  (`idle -> collecting_service -> collecting_date -> collecting_time ->
  confirming -> booked`) driven entirely by inline keyboard buttons, so a
  booking can never end up in a state the code doesn't recognize. State is
  persisted to SQLite after every step, so a bot restart mid-booking does not
  lose the user's place.
- **General chat/FAQ**: any free-text message outside the booking flow is
  routed to an LLM (via OpenClaw's Gateway) with a small system prompt
  scoping it to business-relevant answers and instructing it to hand off to
  `/book` rather than try to collect booking details itself.
- **Never goes silent**: unrecognized message types (stickers, photos,
  voice notes) get an explicit "I can't handle that" reply instead of no
  response at all; invalid/stale button taps get reset to a known-good state
  with an explanation instead of being silently ignored.
- **Reliability**: outbound Telegram sends and LLM calls both go through
  retry policies tuned to their respective failure modes (see
  `src/reliability/retry.py`), and outbound sends are token-bucket rate
  limited against Telegram's documented per-chat and global limits (see
  `src/ratelimit/limiter.py`).
- **Structured logging**: every inbound update and outbound send is logged
  as JSON to `logs/bot.log` (see `src/reliability/logging_config.py`), so
  production issues are `grep`/`jq`-able rather than hidden in prose logs.

## Project layout

```
src/
  config.py              # loads and validates all settings from .env, fails fast
  main.py                # entrypoint: wires everything together, runs polling/webhook
  bot/
    handlers.py           # command / callback / text handlers
    state_machine.py       # booking state machine + transition table
    keyboards.py            # inline keyboard builders
    safe_send.py             # rate-limited, retried message sending
  db/
    schema.sql            # SQLite schema (users, sessions, history, bookings)
    database.py             # async data access layer
  llm/
    base.py                # LLMProvider interface
    openclaw_provider.py     # concrete implementation calling OpenClaw's Gateway
    prompts.py                # system prompt + message assembly
  reliability/
    retry.py               # tenacity retry policies (LLM vs Telegram)
    logging_config.py        # JSON logging setup
  ratelimit/
    limiter.py              # token-bucket rate limiter
tests/
  test_state_machine.py    # unit tests for the transition table
Dockerfile
docker-compose.yml
```

## Prerequisites

- Python 3.10+ (Docker image uses 3.12)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- An OpenClaw Gateway reachable from wherever the bot runs, with its
  OpenAI-compatible endpoint turned on (see below)

## OpenClaw Gateway setup

The bot talks to OpenClaw over its OpenAI-compatible endpoint, which is
**disabled by default**. On the machine running OpenClaw:

```bash
openclaw config set gateway.http.endpoints.chatCompletions.enabled true
```

Then restart the Gateway service so the change takes effect:

```bash
systemctl --user restart openclaw-gateway.service
```

`OPENCLAW_AGENT_MODEL` in `.env` is an *agent target*, not a raw model ID -
use `openclaw/default` to hit the default agent, or `openclaw/<agentId>` to
route to a specific one. `OPENCLAW_GATEWAY_TOKEN` is the same Bearer token
used for the Gateway's other HTTP APIs.

## Local setup (polling mode - easiest for development)

```bash
cp .env.example .env
# edit .env: fill in TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET (any random
# string is fine in polling mode, it's unused), OPENCLAW_GATEWAY_URL,
# OPENCLAW_GATEWAY_TOKEN

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m src.main
```

The bot will start polling Telegram for updates. Message it on Telegram to
test: `/start`, `/book`, or just ask it a question.

## Running the tests

```bash
pip install pytest
pytest tests/
```

## Docker deployment

```bash
cp .env.example .env    # fill in real values as above
docker compose up -d --build
docker compose logs -f  # tail the JSON logs
```

Data (`bot.db`) and logs persist in named Docker volumes across container
recreation. For production, set `BOT_MODE=webhook` in `.env` and put the bot
behind a reverse proxy that terminates TLS and forwards to port 8443 - the
`ports` mapping in `docker-compose.yml` is only needed for webhook mode and
can be removed if you're staying with polling.

## Swapping the LLM backend

`src/llm/base.py` defines a one-method interface (`LLMProvider.generate`).
`OpenClawProvider` is the only implementation today, but switching to
OpenAI or Anthropic directly means writing one more class with the same
interface and changing one line in `src/main.py`'s `_post_init` - nothing
in `handlers.py` or `prompts.py` needs to change.

## Known limitations / next steps

- Booking slots (dates/times) are a fixed set defined in
  `state_machine.py`, not checked against real calendar availability or
  double-booking. Wiring in a real calendar backend (or at least a
  `bookings` table uniqueness check on `(booking_date, booking_time)`)
  is the natural next step before this handles real traffic.
- No admin/staff-facing view of bookings yet - they're only queryable
  directly from `bookings.db`. A `/mybookings` command for users, plus a
  simple admin export, would be a reasonable Phase 10.
- Webhook mode's `run_webhook` uses PTB's built-in web server, which is
  fine for moderate traffic but doesn't give you a shared ASGI app for
  health checks etc. If you need that, PTB supports mounting into
  FastAPI/Starlette manually - not done here to keep the entrypoint simple.
