// CRUZ AI System — PM2 process manager config.
//
// All 5 CRUZ services under PM2: api, worker, voice-worker, daemon, ui.
// Start everything with a single command:
//
//   ./scripts/start-cruz.sh
//
// Or manually:
//   pm2 start ecosystem.config.js
//   pm2 logs                              # follow combined logs
//   pm2 status                            # check all processes
//   pm2 save                              # persist current process list
//   pm2 startup                           # register auto-start on boot
//   pm2 stop ecosystem.config.js
//   pm2 reload ecosystem.config.js --update-env   # after .env change
//
// IMPORTANT: PM2 does not auto-load .env.  Run start-cruz.sh which does
//   `set -a; source .env; set +a` before pm2 start so PM2 inherits env vars.

const path = require("path");

const ROOT = __dirname;
const VENV_PY311 = path.join(ROOT, "venv-py311/bin/python");
const LOGS_DIR = path.join(ROOT, "logs");

module.exports = {
  apps: [
    // ── 1. FastAPI backend ────────────────────────────────────────────────────
    {
      name: "cruz-api",
      script: VENV_PY311,
      args: "backend/api/main.py",
      cwd: ROOT,
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",
      min_uptime: "10s",
      max_restarts: 10,
      restart_delay: 2000,
      kill_timeout: 5000,
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONPATH: ROOT,
        PORT: "3000",
      },
      out_file: path.join(LOGS_DIR, "cruz-api-out.log"),
      error_file: path.join(LOGS_DIR, "cruz-api-err.log"),
      merge_logs: true,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
    },

    // ── 2. ARQ background task worker ────────────────────────────────────────
    {
      name: "cruz-worker",
      script: VENV_PY311,
      args: "-m arq workers.arq_worker.WorkerSettings",
      cwd: ROOT,
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",
      min_uptime: "10s",
      max_restarts: 10,
      restart_delay: 5000,
      kill_timeout: 10000,
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONPATH: ROOT,
      },
      out_file: path.join(LOGS_DIR, "cruz-worker-out.log"),
      error_file: path.join(LOGS_DIR, "cruz-worker-err.log"),
      merge_logs: true,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
    },

    // ── 3. LiveKit voice agent worker ─────────────────────────────────────────
    // Bridges Deepgram STT ↔ CRUZ ↔ Deepgram TTS inside LiveKit rooms.
    // Needs LiveKit + Deepgram + DB env vars — inherited from shell when
    // started via start-cruz.sh (which sources .env before pm2 start).
    {
      name: "cruz-voice-worker",
      script: VENV_PY311,
      args: "-u -m workers.voice_agent.worker dev",
      cwd: ROOT,
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",
      min_uptime: "10s",
      max_restarts: 10,
      restart_delay: 5000,
      kill_timeout: 15000,
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONPATH: ROOT,
      },
      out_file: path.join(LOGS_DIR, "cruz-voice-worker-out.log"),
      error_file: path.join(LOGS_DIR, "cruz-voice-worker-err.log"),
      merge_logs: true,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
    },

    // ── 4. Mac voice daemon (wake-word + mic/speaker) ─────────────────────────
    // Listens for "Hey Jarvis", joins the LiveKit room, streams mic audio.
    // Needs LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET / DEEPGRAM_API_KEY.
    // All inherited from shell environment — start via start-cruz.sh.
    {
      name: "cruz-daemon",
      script: VENV_PY311,
      args: "scripts/voice/livekit_client.py --host http://localhost:3000",
      cwd: ROOT,
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_memory_restart: "512M",
      min_uptime: "10s",
      max_restarts: 5,
      restart_delay: 3000,
      kill_timeout: 10000,
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONPATH: ROOT,
      },
      out_file: path.join(LOGS_DIR, "cruz-daemon-out.log"),
      error_file: path.join(LOGS_DIR, "cruz-daemon-err.log"),
      merge_logs: true,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
    },

    // ── 5. Frontend (pre-built static via `serve`) ────────────────────────────
    // start-cruz.sh runs `cd frontend && npm run build` before pm2 start,
    // so frontend/dist is always fresh.  `serve` is zero-config and stable.
    {
      name: "cruz-ui",
      script: "npx",
      args: "serve -s frontend/dist -l 5173",
      cwd: ROOT,
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_memory_restart: "256M",
      min_uptime: "5s",
      max_restarts: 10,
      restart_delay: 2000,
      kill_timeout: 5000,
      env: {
        NODE_ENV: "production",
      },
      out_file: path.join(LOGS_DIR, "cruz-ui-out.log"),
      error_file: path.join(LOGS_DIR, "cruz-ui-err.log"),
      merge_logs: true,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
    },
  ],
};
