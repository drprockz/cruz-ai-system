# SP1 Voice-over-Cellular Test

**Date:** 2026-04-26
**Carrier / network:** cellular (5G+ per Telegram alert screenshot, WiFi off)
**PWA URL:** `https://cruz.simpleinc.cloud`
**Routing:** Cloudflare Tunnel `cruz` → `localhost:3000` (FastAPI now mounts the
SPA at root via `StaticFiles(html=True)`; see Charter Override #2 in commit
log). Single ingress rule serves both UI and API.
**Spoken command:** "What can you help me with?" (or equivalent ad-hoc test phrase)
**Response observed:** PWA loaded, microphone permission granted, streamed
response from CRUZ rendered token-by-token — confirmed by the user as "working
same as desktop" from the phone over cellular.

**Gate met:** yes — voice command from phone over public cellular produced a
streamed response end-to-end. Charter SP1 gate criterion #2 satisfied.

**Path proven**
1. Phone DNS → Cloudflare nameservers → A records `104.21.66.102 / 172.67.159.7`
2. TLS handshake to Cloudflare edge (Mumbai PoP)
3. Cloudflare Tunnel (4 connections registered) → cloudflared system daemon
4. cloudflared → `http://localhost:3000` (FastAPI on the Mac)
5. FastAPI serves SPA HTML at `/`; SPA's voice flow calls `/voice/transcribe`,
   `/command`, `/voice/speak` on same origin (relative URLs from `VITE_API_BASE=""`)

**Gotchas captured for the readiness checklist / SP2 hand-off**
- Pre-SP1 dist build had `VITE_API_BASE=localhost:3000` baked in, which
  works on the Mac but fails on any other device. Fix: production builds
  must use `VITE_API_BASE=""` (the relative-URL path). See
  `frontend/.env.production`.
- The `cruz-ui` PM2 app (`npx serve -s frontend/dist -l 5173`) is now
  redundant with the FastAPI mount but kept running for local dev
  ergonomics. SP2 may drop it.
