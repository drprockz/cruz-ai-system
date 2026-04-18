# CRUZ — Command Centre Frontend

React 18 + TypeScript 5 + Vite 8 + Tailwind CSS 4 + shadcn/ui.
PWA-ready, LiveKit voice, 4 tabs: Conversation / Dashboard / Events / Approvals.

## Dev

```bash
cd frontend && npm install && npm run dev   # http://localhost:5173
```

Backend on `http://localhost:3000` is optional — UI loads gracefully without it.

## Build

```bash
npm run build      # TypeScript + Vite → dist/
npm run preview    # serve dist/ at http://localhost:4173
```

## Tests

```bash
npm test                          # Vitest unit tests
npx playwright install chromium   # one-time (~100 MB)
npx playwright test               # e2e smoke (starts Vite if not running)
npx playwright test --headed      # visual mode
npx playwright show-report        # last HTML report
```

## Prod (PM2)

```bash
# from repo root
cd frontend && npm run build && cd ..
pm2 start ecosystem.config.js   # starts cruz-api + cruz-worker + cruz-daemon
pm2 save && pm2 startup          # persist across reboots
pm2 logs                         # follow all logs
pm2 reload ecosystem.config.js --update-env   # after .env change
```

Serve `dist/` via nginx, caddy, or `npx serve dist` — Vite dev server
is not needed in production.

## Key files

| Path | Purpose |
|---|---|
| `src/components/Layout.tsx` | Responsive grid — rails on desktop, drawer on mobile |
| `src/components/NavDrawer.tsx` | Hamburger Sheet for phone/tablet |
| `src/components/Orb.tsx` | Animated voice state orb |
| `src/state/voiceStore.ts` | Zustand voice FSM |
| `src/hooks/useLiveKitRoom.ts` | LiveKit room connection |
| `src/lib/api.ts` | Typed fetch wrapper (proxied to `/api`) |
| `e2e/smoke.spec.ts` | Playwright smoke tests |
