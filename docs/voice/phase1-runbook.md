# Voice Phase 1 — Runbook

## ONE COMMAND TO START EVERYTHING

```bash
./scripts/start-cruz.sh
```

That's it. The script handles PostgreSQL, Redis, frontend build, and all 5
PM2 services (api, worker, voice-worker, daemon, ui). See the script for
details; the rest of this file is reference only.

---

## What `start-cruz.sh` starts

| PM2 app | What it runs |
|---|---|
| `cruz-api` | FastAPI backend on port 3000 |
| `cruz-worker` | ARQ background task queue |
| `cruz-voice-worker` | LiveKit voice agent (Deepgram STT/TTS) |
| `cruz-daemon` | Mac wake-word listener + mic/speaker |
| `cruz-ui` | Vite-built frontend on port 5173 |

```bash
pm2 status          # check all 5 apps
pm2 logs            # tail all logs
pm2 logs cruz-daemon --lines 50   # wake-word diagnostics
```

To stop everything:

```bash
./scripts/stop-cruz.sh
```

---

## Env vars required in `.env`

```
DEEPGRAM_API_KEY=...
DEEPGRAM_TTS_MODEL=aura-2-orion-en
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
LIVEKIT_URL=wss://your-project.livekit.cloud
```

`start-cruz.sh` sources `.env` before calling `pm2 start`, so all services
inherit these values automatically.

---

## Wake word

Default threshold: **0.3** (lowered from 0.4 for AirPods).

Override per-session without changing code:

```bash
WAKE_WORD_THRESHOLD=0.25 ./scripts/start-cruz.sh   # noisier environment
WAKE_WORD_THRESHOLD=0.4  ./scripts/start-cruz.sh   # wired mic, quiet room
```

Enable verbose wake-score logging to tune the threshold:

```bash
# Add to .env:
DEBUG_VOICE=1
```

Then `pm2 logs cruz-daemon` will print every detection score above 0.05.

---

## Verify it works

After `./scripts/start-cruz.sh`:

1. Say **"Hey Jarvis, what time is it"** — Orion voice should respond in <4s
2. Speak over CRUZ mid-reply — TTS should cut within ~300ms (barge-in)
3. Kill Deepgram API key mid-session — reply should still complete via fallback
4. Check DB: `SELECT * FROM voice_sessions ORDER BY started_at DESC LIMIT 5;`

---

## Troubleshooting

- **No voice response**: check `pm2 logs cruz-voice-worker` — verify LIVEKIT_URL
- **Wake word not triggering**: `pm2 logs cruz-daemon` — look at `wake score=` lines.
  If scores are 0.10–0.25, try `WAKE_WORD_THRESHOLD=0.2`
- **Wake word fires constantly**: raise threshold to 0.4 or 0.5
- **Daemon crashes at startup**: `openwakeword.utils.download_models()` may need
  first-run in the venv-py311 environment
- **Agent worker won't connect**: verify `LIVEKIT_URL` in `.env` matches the URL
  returned by `GET /voice/token`

---

## Run integration tests (requires live API keys)

```bash
pytest tests/integration/ -v -m voice
```
