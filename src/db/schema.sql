-- Users seen by the bot
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    created_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL
);

-- One row per user: current state-machine state + arbitrary JSON context
-- (e.g. the service/date/time picked so far while booking).
CREATE TABLE IF NOT EXISTS sessions (
    user_id INTEGER PRIMARY KEY REFERENCES users(user_id),
    state TEXT NOT NULL DEFAULT 'idle',
    context_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

-- Rolling conversation log, used to give the LLM 2-3 turns of context.
-- Pruned by age (see database.py:prune_old_history), not unbounded.
CREATE TABLE IF NOT EXISTS conversation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_user_time ON conversation_history(user_id, created_at);

-- Completed/confirmed bookings. This is the actual business record;
-- conversation_history is just chat context and can be pruned freely,
-- but bookings never are.
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    service TEXT NOT NULL,
    booking_date TEXT NOT NULL,
    booking_time TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    created_at TEXT NOT NULL
);
