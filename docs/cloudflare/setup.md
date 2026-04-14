# Cloudflare Tunnel — CRUZ public access + webhooks

CRUZ runs on a Mac Mini on your home LAN. Cloudflare Tunnel exposes it at
`https://cruz.simpleinc.cloud` without opening any router ports, so
external senders (GitHub, Vercel, Google Calendar) can POST webhooks to
CRUZ while it stays firewalled at home.

## 1. Install cloudflared

```bash
brew install cloudflared
cloudflared --version   # sanity check
```

## 2. Authenticate and create the tunnel

```bash
cloudflared tunnel login
# Browser opens → pick the simpleinc.cloud zone → allow.

cloudflared tunnel create cruz
# Prints:   Tunnel credentials written to ~/.cloudflared/<UUID>.json
#           Created tunnel cruz with id <UUID>
```

Copy `<UUID>` — you'll paste it into `config.yml` next.

## 3. DNS route

```bash
cloudflared tunnel route dns cruz cruz.simpleinc.cloud
```

This creates a **CNAME** record in Cloudflare DNS pointing
`cruz.simpleinc.cloud` → `<UUID>.cfargotunnel.com`. If you'd rather do it
in the Cloudflare dashboard:

| Type  | Name | Target                       | Proxy |
|-------|------|------------------------------|-------|
| CNAME | cruz | `<UUID>.cfargotunnel.com`    | ✅    |

## 4. Ingress rules

Copy `cloudflared/config.yml` from this repo to `~/.cloudflared/config.yml`,
replacing `<TUNNEL_UUID>` with the UUID from step 2.

Key ingress rules:

```yaml
ingress:
  - hostname: cruz.simpleinc.cloud
    service: http://localhost:3000      # FastAPI
  - hostname: cruz.simpleinc.cloud
    path: /webhooks/*                   # tighter timeouts
    service: http://localhost:3000
  - service: http_status:404            # mandatory catch-all
```

Validate:

```bash
cloudflared tunnel --config ~/.cloudflared/config.yml ingress validate
```

## 5. Run the tunnel

**Interactive (dev):**

```bash
cloudflared tunnel --config ~/.cloudflared/config.yml run cruz
```

**As a launchd service (production):**

```bash
sudo cloudflared service install
sudo launchctl list | grep cloudflared
```

Logs: `/var/log/cloudflared.log` (or `launchctl` output).

## 6. Verify

```bash
curl -s https://cruz.simpleinc.cloud/health | jq .
```

Should return the same body as `curl localhost:3000/health` from the Mac.

## 7. Register webhooks

### GitHub (per repository)

- **Settings → Webhooks → Add webhook**
- **Payload URL:** `https://cruz.simpleinc.cloud/webhooks/github`
- **Content type:** `application/json`
- **Secret:** same string you set as `GITHUB_WEBHOOK_SECRET` in `.env`
- **Events:** Pull requests + Pushes (or "Send me everything" for dev)

### Vercel (per project)

- **Project → Settings → Webhooks → Create Webhook**
- **Endpoint URL:** `https://cruz.simpleinc.cloud/webhooks/vercel`
- **Events:** `deployment.ready`, `deployment.error` (at minimum)
- **Secret:** store as `VERCEL_WEBHOOK_SECRET` (Vercel signs with HMAC-SHA1).

### Google Calendar (push notifications)

Calendar sends **watch** channels with an `X-Goog-Channel-Token` header you
control. Use the Google Calendar API `events.watch` to register:

```json
POST https://www.googleapis.com/calendar/v3/calendars/<calendarId>/events/watch
{
  "id":      "cruz-calendar-watch-1",
  "type":    "web_hook",
  "address": "https://cruz.simpleinc.cloud/webhooks/google-calendar",
  "token":   "<your GOOGLE_WEBHOOK_TOKEN>"
}
```

Watch channels expire every 7 days — refresh them nightly via ARQ cron or
manually through a small renewal task.

## 8. Env vars required

```
GITHUB_WEBHOOK_SECRET=<random 32-char string>
VERCEL_WEBHOOK_SECRET=<random 32-char string>
GOOGLE_WEBHOOK_TOKEN=<random 32-char string>
```

Generate with `openssl rand -hex 32` and store in Bitwarden.

## 9. What happens after a webhook arrives

1. Cloudflare Tunnel forwards `POST /webhooks/...` to `localhost:3000`.
2. FastAPI verifies the signature — failure returns **401** immediately.
3. On success, the payload is enqueued via ARQ (Redis) and the endpoint
   returns **200** in < 100 ms so senders don't time out.
4. The ARQ worker picks up the job and runs the corresponding handler in
   `workers/tasks/webhook_tasks.py`, where real routing into SENTINEL /
   TITAN / PULSE happens.

If any stage fails, `services/alerts.py` pushes a critical Telegram alert.
