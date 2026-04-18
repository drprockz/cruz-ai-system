#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start-cruz.sh — one-command launcher for all CRUZ services
#
# What it does (in order):
#   1. Loads .env into the shell so PM2 inherits LiveKit/Deepgram/etc.
#   2. Ensures PostgreSQL + Redis are running (brew services start)
#   3. Builds the frontend if dist/ is missing or stale
#   4. Installs pm2 globally if not present
#   5. Kills any prior PM2 instance of this ecosystem file
#   6. Starts all 5 apps: cruz-api, cruz-worker, cruz-voice-worker,
#      cruz-daemon, cruz-ui
#   7. Saves the process list (so `pm2 resurrect` works after reboot)
#   8. Prints status and opens the UI in the browser
#
# Usage:
#   ./scripts/start-cruz.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

CRUZ_ROOT="/Users/drprockz/Projects/cruz-ai-system"
cd "$CRUZ_ROOT"

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[CRUZ]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

info "Starting CRUZ AI system from $CRUZ_ROOT"

# ── 1. Defensive: unset empty ANTHROPIC_API_KEY (user shell exports blank str) ─
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  unset ANTHROPIC_API_KEY 2>/dev/null || true
fi

# ── 2. Load .env so PM2 inherits every key ────────────────────────────────────
if [[ -f "$CRUZ_ROOT/.env" ]]; then
  info "Loading .env"
  set -a
  # shellcheck source=/dev/null
  source "$CRUZ_ROOT/.env"
  set +a
else
  warn ".env not found — services that need API keys may fail to start"
fi

# ── 3. Unset empty ANTHROPIC_API_KEY again (might have come in as blank from .env) ─
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  unset ANTHROPIC_API_KEY 2>/dev/null || true
fi

# ── 4. Ensure PostgreSQL + Redis are running ──────────────────────────────────
# We don't care which PG version owns port 5432 — only that ONE is reachable.
# This machine has both 15 and 16 installed; the app's data lives on the one
# that currently owns 5432 (whichever started first wins — usually 15).
info "Checking PostgreSQL on port 5432…"
if nc -z 127.0.0.1 5432 2>/dev/null; then
  info "  PostgreSQL is already reachable on :5432"
else
  info "  Nothing on :5432 — trying to start postgresql@15…"
  if ! brew services start postgresql@15 2>&1 | tail -2; then
    warn "  postgresql@15 failed — trying postgresql@16…"
    brew services start postgresql@16 2>&1 | tail -2 || true
  fi
  # Wait up to 10s for it to come up
  for i in $(seq 1 10); do
    if nc -z 127.0.0.1 5432 2>/dev/null; then
      info "  PostgreSQL reachable after ${i}s"
      break
    fi
    sleep 1
  done
  if ! nc -z 127.0.0.1 5432 2>/dev/null; then
    error "Postgres did not come up on :5432. Start manually then rerun."
    exit 1
  fi
fi

info "Checking Redis…"
if brew services list | grep -q "redis.*started"; then
  info "  Redis already running"
else
  info "  Starting Redis…"
  brew services start redis
fi

# ── 5. Ensure logs/ directory exists ─────────────────────────────────────────
mkdir -p "$CRUZ_ROOT/logs"
info "Log directory: $CRUZ_ROOT/logs"

# ── 6. Build frontend (only if dist/ is missing or stale) ────────────────────
FRONTEND_DIR="$CRUZ_ROOT/frontend"
DIST_DIR="$FRONTEND_DIR/dist"

needs_build=false
if [[ ! -d "$DIST_DIR" ]]; then
  needs_build=true
  info "frontend/dist not found — building…"
elif [[ "$FRONTEND_DIR/src" -nt "$DIST_DIR" ]] || [[ "$FRONTEND_DIR/package.json" -nt "$DIST_DIR" ]]; then
  needs_build=true
  info "frontend source is newer than dist/ — rebuilding…"
else
  info "frontend/dist is up to date — skipping build"
fi

if $needs_build; then
  pushd "$FRONTEND_DIR" > /dev/null
  if [[ ! -d node_modules ]]; then
    info "  Installing frontend node_modules…"
    npm install --silent
  fi
  info "  Running npm run build…"
  npm run build
  info "  Frontend build complete"
  popd > /dev/null
fi

# ── 7. Install pm2 globally if missing ───────────────────────────────────────
if ! command -v pm2 > /dev/null 2>&1; then
  info "pm2 not found — installing globally…"
  npm install -g pm2
fi

# ── 8. Stop any existing CRUZ pm2 apps (ignore errors if none running) ───────
info "Stopping any existing CRUZ pm2 apps…"
pm2 delete ecosystem.config.js 2>/dev/null || true

# ── 9. Start all 5 apps ───────────────────────────────────────────────────────
info "Starting CRUZ services via PM2…"
pm2 start ecosystem.config.js

# ── 10. Persist process list so pm2 resurrect / startup works ────────────────
pm2 save
info "PM2 process list saved"

# ── 11. Wait briefly for apps to settle, then print status ───────────────────
sleep 3
echo ""
pm2 status
echo ""

# ── 12. Open the UI ──────────────────────────────────────────────────────────
info "Opening http://localhost:5173 in the browser…"
open "http://localhost:5173" 2>/dev/null || true

# ── 13. Summary ───────────────────────────────────────────────────────────────
echo ""
info "─────────────────────────────────────────────────────────"
info "  CRUZ is running.  Useful commands:"
info ""
info "  pm2 logs                    # tail all logs"
info "  pm2 logs cruz-voice-worker  # voice worker only"
info "  pm2 logs cruz-daemon        # wake-word daemon only"
info "  pm2 status                  # process health"
info "  pm2 reload ecosystem.config.js --update-env  # after .env change"
info "  ./scripts/stop-cruz.sh      # stop everything"
info "─────────────────────────────────────────────────────────"
