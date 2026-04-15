-- CRUZ AI System — Database Schema
-- Source of truth: Alembic migrations in /migrations/versions/
-- This file documents the final schema state after all migrations.

-- Users table
CREATE TABLE users (
    id           SERIAL PRIMARY KEY,
    email        VARCHAR(255) UNIQUE NOT NULL,
    name         VARCHAR(255),
    preferences  JSONB,
    created_at   TIMESTAMP DEFAULT NOW()
);

-- Conversations (id is UUID string from API layer)
CREATE TABLE conversations (
    id          VARCHAR(36) PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id),
    device      VARCHAR(50),
    title       TEXT,
    context     JSONB,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

-- Messages
CREATE TABLE messages (
    id               SERIAL PRIMARY KEY,
    conversation_id  VARCHAR(36) REFERENCES conversations(id) NOT NULL,
    role             VARCHAR(20) NOT NULL,
    content          TEXT NOT NULL,
    metadata         JSONB,
    created_at       TIMESTAMP DEFAULT NOW()
);

-- Tasks
CREATE TABLE tasks (
    id           SERIAL PRIMARY KEY,
    agent        VARCHAR(50) NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT,
    status       VARCHAR(20) DEFAULT 'pending',
    priority     INTEGER DEFAULT 3,
    metadata     JSONB,
    created_at   TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- Agent logs (trace_id links all logs for one user request)
CREATE TABLE agent_logs (
    id           SERIAL PRIMARY KEY,
    trace_id     VARCHAR(64),
    agent        VARCHAR(50) NOT NULL,
    action       VARCHAR(100) NOT NULL,
    status       VARCHAR(20),
    input_data   JSONB,
    output_data  JSONB,
    tokens_used  INTEGER DEFAULT 0 NOT NULL,
    duration_ms  INTEGER,
    created_at   TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_tasks_agent            ON tasks(agent);
CREATE INDEX idx_tasks_status           ON tasks(status);
CREATE INDEX idx_agent_logs_agent       ON agent_logs(agent, created_at DESC);
CREATE INDEX idx_agent_logs_trace_id    ON agent_logs(trace_id);
CREATE INDEX idx_messages_conversation  ON messages(conversation_id);
CREATE INDEX idx_conversations_id       ON conversations(id);

-- ============================================================
-- Voice pipeline v2 (added 2026-04-15)
-- ============================================================

-- A single voice interaction session bound to a LiveKit room.
CREATE TABLE IF NOT EXISTS voice_sessions (
    id               VARCHAR(36) PRIMARY KEY,
    conversation_id  VARCHAR(36) REFERENCES conversations(id) NOT NULL,
    device_id        VARCHAR(100) NOT NULL,
    livekit_room     VARCHAR(200) NOT NULL,
    started_at       TIMESTAMP DEFAULT NOW(),
    ended_at         TIMESTAMP,
    deepgram_ws_ms   INTEGER DEFAULT 0,
    turns            INTEGER DEFAULT 0,
    barges           INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_voice_sessions_conv ON voice_sessions(conversation_id);

-- Approval request surfaced to the user via FCM + voice prompt.
CREATE TABLE IF NOT EXISTS approval_requests (
    id            VARCHAR(36) PRIMARY KEY,
    trace_id      VARCHAR(64) NOT NULL,
    agent         VARCHAR(50) NOT NULL,
    action        VARCHAR(100) NOT NULL,
    payload       JSONB NOT NULL,
    state         VARCHAR(20) DEFAULT 'pending',
    requested_at  TIMESTAMP DEFAULT NOW(),
    responded_at  TIMESTAMP,
    expires_at    TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_approval_requests_trace ON approval_requests(trace_id);
CREATE INDEX IF NOT EXISTS idx_approval_requests_state ON approval_requests(state, expires_at);

-- FCM device tokens for push-based approval notifications.
CREATE TABLE IF NOT EXISTS fcm_tokens (
    id         VARCHAR(36) PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id),
    device     VARCHAR(50) NOT NULL,
    token      TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, device)
);

-- messages: link a voice-originated turn to its session + audio length.
ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS voice_session_id VARCHAR(36) REFERENCES voice_sessions(id);
ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS audio_ms INTEGER;
