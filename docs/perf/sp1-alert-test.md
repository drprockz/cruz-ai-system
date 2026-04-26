# SP1 Alert Test — Induced Outage

**Date:** 2026-04-26
**Stop time (UTC):** 2026-04-26T06:57:02Z (12:27:02 IST)
**Stop trigger:** `pm2 stop cruz-api`
**Alert received (IST):** 12:27 PM (same minute as stop)
**Observed latency (upper bound):** ≤ 58 seconds
**SP1 budget:** 120 s
**Kuma monitor:** CRUZ API — HTTP(s) probe at `http://host.docker.internal:3000/health`, interval 30 s
**Alert path:** Uptime Kuma → Telegram bot (chat_id 489534172, bot @CRUZBot)
**Alert content:** `[CRUZ API] [🔴 Down] connect ECONNREFUSED 192.168.65.254:3000`
  (192.168.65.254 = `host.docker.internal` resolved inside Kuma's container — confirms
  the monitor reached the host loopback as expected and observed CRUZ API down.)
**Recovery:** `pm2 start cruz-api` at 12:28 PM IST → up notification arrived same minute.

See [sp1-alert-test.png](sp1-alert-test.png) for the DM screenshot capturing the full
sequence (down at 12:27, up at 12:28).

**Gate met:** yes — DM arrived within the 120 s SP1 budget (worst-case ~58 s observed,
likely faster — Telegram timestamps are minute-precision in the chat view).
