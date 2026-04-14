# 72-Hour Uptime Test Procedure

**Goal:** demonstrate ≥ 99% green `/health` checks across 72 continuous hours on the Mac Mini M4 production host, under normal background load.

**Probe tool:** `scripts/uptime/check_stability.py` — polls `GET /health`, appends one JSON line per probe to `logs/uptime/stability.jsonl`.

## 1. Dry-run (one-shot sanity check)

```bash
source venv/bin/activate
python scripts/uptime/check_stability.py --once
# → prints a single JSON record; exit 0 if healthy, 2 otherwise
```

## 2. Start the 72h run

### Option A — launchd (recommended on macOS)

Create `~/Library/LaunchAgents/com.cruz.uptime.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.cruz.uptime</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/drprockz/Projects/cruz-ai-system/venv/bin/python</string>
    <string>/Users/drprockz/Projects/cruz-ai-system/scripts/uptime/check_stability.py</string>
    <string>--url</string><string>http://localhost:3000/health</string>
    <string>--interval</string><string>300</string>
    <string>--duration</string><string>259200</string>
    <string>--output</string><string>/Users/drprockz/Projects/cruz-ai-system/logs/uptime/stability.jsonl</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
  <key>StandardOutPath</key><string>/Users/drprockz/Projects/cruz-ai-system/logs/uptime/stdout.log</string>
  <key>StandardErrorPath</key><string>/Users/drprockz/Projects/cruz-ai-system/logs/uptime/stderr.log</string>
</dict></plist>
```

Activate:

```bash
launchctl load ~/Library/LaunchAgents/com.cruz.uptime.plist
launchctl list | grep com.cruz.uptime
```

Stop when finished:

```bash
launchctl unload ~/Library/LaunchAgents/com.cruz.uptime.plist
```

### Option B — plain cron (every 5 min)

```cron
*/5 * * * * cd /Users/drprockz/Projects/cruz-ai-system && \
  ./venv/bin/python scripts/uptime/check_stability.py --once \
  >> logs/uptime/stability.jsonl 2>> logs/uptime/stderr.log
```

### Option C — systemd-timer (Linux hosts)

```ini
# /etc/systemd/system/cruz-uptime.service
[Service]
Type=oneshot
WorkingDirectory=/opt/cruz
ExecStart=/opt/cruz/venv/bin/python scripts/uptime/check_stability.py --once

# /etc/systemd/system/cruz-uptime.timer
[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Unit=cruz-uptime.service
[Install]
WantedBy=timers.target
```

```bash
systemctl enable --now cruz-uptime.timer
```

## 3. Finalize the run

After 72h (or at the launchd `duration` end):

```bash
python scripts/uptime/check_stability.py --summary \
  --output logs/uptime/stability.jsonl
```

Target outcome:

```json
{ "total": 864, "ok": ≥856, "fail": ≤8, "pct_ok": ≥99.0 }
```

864 = 72h × 12 probes/hour at 5-min cadence.

## 4. Record the result

Append a row to `docs/perf/load_results.md` **Run log → Scenario 4** (or a new "Uptime" section) with:

- Start / end timestamps (UTC)
- Total probes / ok / fail
- pct_ok
- Any outage incidents (from `stderr.log` or agent_logs).
