// CRUZ AI System — PM2 process manager config.
//
// Runs the FastAPI server and the ARQ background worker under PM2 so the
// system auto-restarts on crash and on boot. Assumes the venv lives at
// ./venv/ (see SETUP.md). Uses the venv python directly to avoid needing
// `source venv/bin/activate` at launch.
//
// Usage:
//   pm2 start ecosystem.config.js
//   pm2 logs                      # follow combined logs
//   pm2 status                    # check both processes
//   pm2 save                      # persist current process list
//   pm2 startup                   # register auto-start on boot (follow its output)
//   pm2 stop ecosystem.config.js
//   pm2 reload ecosystem.config.js --update-env  # after .env change

const path = require("path");

const ROOT = __dirname;
const VENV_PY = path.join(ROOT, "venv/bin/python");
const LOGS_DIR = path.join(ROOT, "logs");

module.exports = {
  apps: [
    {
      name: "cruz-api",
      script: VENV_PY,
      args: "backend/api/main.py",
      cwd: ROOT,
      interpreter: "none", // we already point script at venv python
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
      },
      out_file: path.join(LOGS_DIR, "cruz-api-out.log"),
      error_file: path.join(LOGS_DIR, "cruz-api-err.log"),
      merge_logs: true,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
    },
    {
      name: "cruz-worker",
      script: VENV_PY,
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
  ],
};
