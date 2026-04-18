#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# stop-cruz.sh — gracefully stop all CRUZ services
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

CRUZ_ROOT="/Users/drprockz/Projects/cruz-ai-system"
cd "$CRUZ_ROOT"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[CRUZ]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }

info "Stopping all CRUZ services…"
pm2 delete ecosystem.config.js 2>/dev/null || warn "No CRUZ apps were running in PM2"

# ── Confirm ports are free ────────────────────────────────────────────────────
sleep 1

for port in 3000 5173; do
  if lsof -ti tcp:"$port" > /dev/null 2>&1; then
    warn "Port $port is still in use after stopping PM2:"
    lsof -ti tcp:"$port" | xargs ps -p 2>/dev/null || true
    warn "  Run:  lsof -ti tcp:$port | xargs kill -9   to force-free it"
  else
    info "Port $port is free"
  fi
done

info "CRUZ stopped."
