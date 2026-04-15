# Voice Phase 1 — Runbook

## Start dev stack

    brew services start postgresql@16 redis
    docker compose up -d qdrant
    # apply voice schema additions
    psql "$DATABASE_URL" -f backend/models/schema.sql

## Env vars (add to `.env`)

    DEEPGRAM_API_KEY=...
    DEEPGRAM_TTS_MODEL=aura-2-orion-en
    LIVEKIT_API_KEY=...
    LIVEKIT_API_SECRET=...
    LIVEKIT_WS_URL=wss://your-project.livekit.cloud

## Run backend + worker + daemon (3 terminals)

    # terminal 1 — API
    source venv/bin/activate
    python backend/api/main.py

    # terminal 2 — LiveKit voice agent worker
    # Requires Python 3.10+ for livekit-agents 1.3+; on 3.9 upgrade first.
    source venv/bin/activate
    python -m workers.voice_agent.worker dev

    # terminal 3 — Mac mic daemon
    source venv/bin/activate
    python scripts/voice/livekit_client.py

## Verify

- Say "Hey Jarvis, what time is it" — Orion voice should respond in <2s
- Speak over CRUZ mid-reply — TTS should cut within ~300ms (barge-in)
- Kill Deepgram API key mid-session — reply should still complete via Inworld fallback
- `SELECT * FROM voice_sessions ORDER BY started_at DESC LIMIT 5;` — new row with turns>=1

## Verify fallback still works

- Stop the LiveKit worker; HTTP `/voice/transcribe` + `/voice/speak` + `/command`
  via `scripts/voice/listen.py` still function as before.

## Troubleshooting

- No Orion voice: check `DEEPGRAM_API_KEY` and `DEEPGRAM_TTS_MODEL=aura-2-orion-en`
- Wake word doesn't trigger: `openwakeword.utils.download_models()` may need first-run
- Agent worker won't connect: verify `LIVEKIT_WS_URL` matches the URL returned by `/voice/token`
- `livekit-agents` import error on Python 3.9: upgrade venv to 3.11 (CLAUDE.md target)

## Run integration tests

Only when you have API keys set:

    pytest tests/integration/ -v -m voice
