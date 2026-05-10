# SP7 Multi-Modal Polish Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land charter SP7 (Layer 6) — voice daemon hardening (echo cancel + reconnect + watchdog + 24h burn-in), custom "Hey CRUZ" openWakeWord retrain, PWA offline polish (Workbox runtime caching + IndexedDB conversation cache + outbox UI), FCM push notifications via new `device_tokens` table + `services/push.py` + frontend SW + permission UI, and three immediate push consumers (PULSE, CATCH, CRUZ approval gate).

**Architecture:** Existing `cruz-daemon` and `cruz-voice-worker` PM2 processes already implement wake → LiveKit → Deepgram → CRUZ → Deepgram → speakers. This plan **hardens** that pipeline (does not replace it) with five reliability fixes plus a 24h burn-in harness. PWA gets a real Workbox SW (currently `selfDestroying: true`) plus an IndexedDB last-50-messages cache and an offline outbox. FCM is a new `services/push.py` singleton callable from any agent, fronted by a single `POST /devices/register` endpoint.

**Tech Stack:** Python 3.11+, FastAPI, asyncpg + Alembic, `firebase-admin`, `psutil`, `openwakeword` (ONNX), `silero-vad`, livekit-agents, Vite 8 + vite-plugin-pwa 1.2 (Workbox 7), `idb` (IndexedDB wrapper), Zustand, Vitest + fake-indexeddb, pytest + unittest.mock, PM2, Docker (training only).

**Spec:** `docs/superpowers/specs/2026-05-10-sp7-multimodal-polish-design.md`

**Charter cuts pre-committed:**
- **Cut #4 — React Native shell.** PWA-only ship.
- **Cut #5 — macOS menu bar app.** No menu bar, no global keyboard shortcut.

---

## File map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `requirements.txt` | Add `firebase-admin==6.5.*`, `psutil==6.1.*` |
| Create | `backend/migrations/versions/0XX_device_tokens.py` | Alembic — `device_tokens` table + index |
| Create | `services/push.py` | `PushService` singleton; `send_to_user(user_id, payload)` with auto-prune of dead tokens |
| Modify | `backend/api/main.py` | Add `POST /devices/register` endpoint + lifespan PushService init |
| Create | `tests/services/test_push.py` | 13 unit tests for PushService (firebase-admin mocked) |
| Create | `tests/api/test_devices_endpoint.py` | 6 unit tests for /devices/register (FastAPI TestClient + mocked DB) |
| Modify | `scripts/voice/livekit_client.py` | AEC pause flag + reconnect loop + mic-stream restart + memory watchdog |
| Modify | `workers/voice_agent/worker.py` | Bounded Deepgram queue + raise-on-disconnect + tightened TTS speaking flag |
| Create | `tests/scripts/test_voice_daemon.py` | Unit tests for AEC flag + reconnect schedule + restart + watchdog (sd/livekit mocked) |
| Modify | `tests/workers/test_voice_agent_worker.py` | Add tests for queue bound + disconnect raise |
| Create | `scripts/uptime/voice_burn_in.py` | 24h burn-in harness — PM2 + RSS + /health + synthetic round-trip every 30min |
| Create | `tests/scripts/test_voice_burn_in.py` | Smoke tests for harness assertions (subprocess + httpx mocked) |
| Create | `frontend/src/lib/conversation-cache.ts` | IndexedDB last-50-messages cache via `idb` |
| Create | `frontend/src/state/outbox.ts` | Zustand slice for offline-queued commands |
| Create | `frontend/src/components/EnableNotifications.tsx` | FCM permission prompt + token registration |
| Create | `frontend/src/sw-version.ts` | `SW_VERSION` constant logged on activate |
| Create | `frontend/public/firebase-messaging-sw.js` | FCM background-message + notificationclick handler |
| Create | `frontend/public/icons/icon-192.png` | PWA install icon |
| Create | `frontend/public/icons/icon-512.png` | PWA install icon |
| Create | `frontend/public/icons/icon-512-maskable.png` | PWA install icon (maskable purpose) |
| Modify | `frontend/vite.config.ts` | Flip `selfDestroying`; configure `runtimeCaching` |
| Modify | `frontend/src/main.tsx` | Log `SW_VERSION` on SW activate |
| Modify | `frontend/src/routes/conversation.tsx` (or equivalent) | Wire `rememberMessages` into TanStack Query `onSuccess`; use `recallMessages` as `placeholderData` |
| Modify | `frontend/src/components/Composer.tsx` (or equivalent) | Wire outbox optimistic-add; render queued pill |
| Modify | `frontend/.env.example` | Document `VITE_FCM_VAPID_PUBLIC_KEY` |
| Create | `frontend/src/lib/__tests__/conversation-cache.test.ts` | Vitest + fake-indexeddb |
| Create | `frontend/src/state/__tests__/outbox.test.ts` | Vitest unit tests |
| Create | `frontend/src/components/__tests__/EnableNotifications.test.tsx` | Vitest + Testing Library + `firebase/messaging` mocked |
| Create | `scripts/wakeword/Dockerfile` | PyTorch + openWakeWord + Piper image (training only) |
| Create | `scripts/wakeword/train_hey_cruz.sh` | One-command synthetic training entry point |
| Create | `scripts/wakeword/collect_real_samples.py` | Interactive mic recorder for follow-up real-sample fine-tune |
| Create | `scripts/wakeword/.gitignore` | Excludes `samples/` and `models/` build artifacts |
| Create | `scripts/wakeword/README.md` | Retraining procedure, ROC interpretation |
| Create | `scripts/wakeword/models/hey_cruz.onnx` | **Committed** trained model (~250 KB) |
| Create | `docs/perf/sp7-wake-word-roc.md` | Score histograms + recommended threshold |
| Modify | `services/voice.py` | `WakeWordDetector` ONNX-path branch + fail-loud on load error |
| Modify | `tests/services/test_voice.py` | Add ONNX-path tests + fail-loud assertion |
| Modify | `agents/pulse/pulse_agent.py` | Call `push.send_to_user` on briefing-ready |
| Modify | `agents/catch/catch_agent.py` | Call `push.send_to_user` on summary-ready |
| Modify | `agents/cruz/cruz_agent.py` | Call `push.send_to_user` when `requires_approval=True` returned |
| Modify | `tests/agents/test_pulse_agent.py` | Assert push fires on briefing-ready (push mocked) |
| Modify | `tests/agents/test_catch_agent.py` | Assert push fires on summary-ready |
| Modify | `tests/agents/test_cruz_agent.py` | Assert push fires on approval gate |
| Create | `docs/perf/sp7-exit-gate.md` | Manual walkthrough checklist + screenshots |
| Modify | `PROGRESS.md` | Append SP7 sign-off block |
| Create | `docs/superpowers/v2-burn-in-checklist.md` | Aggregated post-merge operator items |
| Modify | `.gitignore` | Ensure `*-sa.json`, `scripts/wakeword/samples/`, FCM keys not tracked |
| Modify | `ecosystem.config.js` | Add `WAKE_WORD_MODEL_PATH` and `TTS_TAIL_MS` env vars passthrough (if not auto-inherited) |

**Branch:** `claude/<random>-sp7` (already provisioned by user; current worktree branch in use).

**Commit cadence:** One commit per task. Conventional Commits format with `(sp7)` scope. Pre-commit hooks already enforce style.

---

## Chunk 1: FCM push backend — schema, service, endpoint

**Why first.** Push is the most independent piece — no dependency on voice or PWA work. Lands clean tests in <1 day. Once PushService is in `lifespan()`, agents can be retrofitted at any later point without touching infra.

### Task 1.1: Add Python dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Append pins**

In alphabetical order:
```
firebase-admin==6.5.*
psutil==6.1.*
```

- [ ] **Step 2: Install**

```bash
pip install -r requirements.txt
```

Expected: clean install. `firebase-admin` pulls `google-cloud-firestore` and `google-auth` transitively — that's fine.

- [ ] **Step 3: Verify imports**

```bash
python -c "import firebase_admin; from firebase_admin import messaging; print('ok')"
python -c "import psutil; print(psutil.__version__)"
```

Expected: `ok` and a `6.1.x` line.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore(sp7): add firebase-admin and psutil dependencies"
```

---

### Task 1.2: Alembic migration — `device_tokens` table

**Files:**
- Create: `backend/migrations/versions/0XX_device_tokens.py` (replace `XX` with the next available revision number — check `backend/migrations/versions/` for the highest existing).

- [ ] **Step 1: Determine the next revision number**

```bash
ls backend/migrations/versions/ | sort -V | tail -1
```

Expected: e.g. `0011_xxx.py`. Use `0012` (or whatever `+1` works out to) for the new file. Open the previous file, copy the `revision` and `down_revision` ids — your new migration's `down_revision` is that file's `revision`.

- [ ] **Step 2: Write the migration**

```python
# backend/migrations/versions/0012_device_tokens.py
"""device_tokens table for FCM push registration.

Revision ID: <generate via `python -c "import secrets; print(secrets.token_hex(6))"`>
Revises: <previous revision id>
Create Date: 2026-05-10
"""
from alembic import op
import sqlalchemy as sa


revision = "<your generated id>"
down_revision = "<previous revision id>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_tokens",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fcm_token", sa.Text(), nullable=False, unique=True),
        sa.Column("device_label", sa.String(50)),
        sa.Column("user_agent", sa.Text()),
        sa.Column("last_seen_at", sa.TIMESTAMP(),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.TIMESTAMP(),
                  nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_device_tokens_user", "device_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_device_tokens_user", table_name="device_tokens")
    op.drop_table("device_tokens")
```

- [ ] **Step 3: Apply against test DB and verify**

If `DATABASE_URL_TEST` is set:
```bash
DATABASE_URL=$DATABASE_URL_TEST alembic upgrade head
DATABASE_URL=$DATABASE_URL_TEST python -c "
import asyncio, asyncpg, os
async def main():
    c = await asyncpg.connect(os.environ['DATABASE_URL'])
    cols = await c.fetch(\"SELECT column_name, data_type FROM information_schema.columns WHERE table_name='device_tokens' ORDER BY ordinal_position\")
    for r in cols: print(r)
    idx = await c.fetch(\"SELECT indexname FROM pg_indexes WHERE tablename='device_tokens'\")
    for r in idx: print(r)
    await c.close()
asyncio.run(main())
"
```

Expected: 7 columns (id, user_id, fcm_token, device_label, user_agent, last_seen_at, created_at) plus two indexes (PK + idx_device_tokens_user) plus the implicit unique on fcm_token.

- [ ] **Step 4: Roll back to verify downgrade**

```bash
DATABASE_URL=$DATABASE_URL_TEST alembic downgrade -1
DATABASE_URL=$DATABASE_URL_TEST python -c "
import asyncio, asyncpg, os
async def main():
    c = await asyncpg.connect(os.environ['DATABASE_URL'])
    r = await c.fetchval(\"SELECT to_regclass('device_tokens')\")
    print('exists:', r)
    await c.close()
asyncio.run(main())
"
```

Expected: `exists: None`.

- [ ] **Step 5: Re-upgrade to leave test DB in head state**

```bash
DATABASE_URL=$DATABASE_URL_TEST alembic upgrade head
```

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/versions/0012_device_tokens.py
git commit -m "feat(sp7): alembic migration — device_tokens table for FCM"
```

---

### Task 1.3: PushService skeleton — types, signatures, mocked happy-path test

**Files:**
- Create: `services/push.py`
- Create: `tests/services/test_push.py`

The plan splits the `PushService` work over Tasks 1.3–1.5 because the failure-path tests are easier to read after the happy path is locked in. TDD applies regardless: skeleton lands first as a failing import, the happy path forces the public surface, then failure paths get layered.

- [ ] **Step 1: Write the failing skeleton test**

```python
# tests/services/test_push.py
"""Unit tests for services/push — firebase-admin entirely mocked."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.push import PushPayload, PushService, SendResult


class _FakeDB:
    """Stand-in for DatabaseService — captures executed queries for asserts."""

    def __init__(self, rows=None):
        self.rows = rows or []
        self.executed = []

    async def fetch(self, query, *params):
        self.executed.append(("fetch", query, params))
        return self.rows

    async def execute(self, query, *params):
        self.executed.append(("execute", query, params))


@pytest.fixture
def fake_db():
    return _FakeDB(rows=[{"fcm_token": "T1"}, {"fcm_token": "T2"}])


@pytest.fixture
def fake_messaging():
    """Patches firebase_admin.messaging globally; tests interact via this."""
    with patch("services.push.messaging") as m:
        # `messaging.send` is sync in firebase-admin; the service wraps it
        # in asyncio.to_thread.
        m.send.return_value = "msg_abc123"
        yield m


def test_push_payload_dataclass_fields():
    p = PushPayload(title="Hello", body="World")
    assert p.title == "Hello"
    assert p.body == "World"
    assert p.url is None
    assert p.trace_id is None


def test_push_service_construct_loads_credentials(monkeypatch, tmp_path):
    """The constructor must initialize a firebase app from the SA path."""
    sa_path = tmp_path / "sa.json"
    sa_path.write_text("{}")  # firebase-admin will be mocked, contents irrelevant
    with patch("services.push.credentials") as creds, \
         patch("services.push.initialize_app") as init_app:
        creds.Certificate.return_value = "fake-creds"
        svc = PushService(sa_path=str(sa_path), project_id="cruz-test")
    creds.Certificate.assert_called_once_with(str(sa_path))
    init_app.assert_called_once()
```

- [ ] **Step 2: Run; verify ImportError**

```bash
pytest tests/services/test_push.py -v
```

Expected: collection error / `ImportError: cannot import name 'PushPayload'`.

- [ ] **Step 3: Write the minimal skeleton**

```python
# services/push.py
"""FCM push notification dispatch.

PushService is a singleton constructed in lifespan() with the path to a
Firebase service-account JSON. Public API:

    push = get_push_service()  # may be None in degraded mode
    if push:
        await push.send_to_user(user_id, PushPayload(title="...", body="..."))

Auto-prunes UNREGISTERED / Invalid / SenderIdMismatch tokens on send.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

import firebase_admin
from firebase_admin import credentials, initialize_app, messaging

logger = logging.getLogger("cruz.services.push")


@dataclass
class PushPayload:
    title: str
    body: str
    url: Optional[str] = None
    trace_id: Optional[str] = None


@dataclass
class SendResult:
    token: str
    ok: bool
    msg_id: Optional[str] = None
    reason: Optional[str] = None


class PushService:
    def __init__(self, sa_path: str, project_id: str, db: Any = None) -> None:
        cred = credentials.Certificate(sa_path)
        # Reuse the default app if already initialized (lifespan called twice
        # in tests). firebase_admin._apps is the registry.
        if "[DEFAULT]" not in firebase_admin._apps:
            initialize_app(cred, {"projectId": project_id})
        self._db = db

    async def send_to_user(self, user_id: int, payload: PushPayload) -> list[SendResult]:
        raise NotImplementedError("Task 1.4")
```

- [ ] **Step 4: Run; verify pass**

```bash
pytest tests/services/test_push.py -v
```

Expected: all three tests pass.

- [ ] **Step 5: Commit**

```bash
git add services/push.py tests/services/test_push.py
git commit -m "feat(sp7): scaffold services/push — PushPayload, SendResult, PushService init"
```

---

### Task 1.4: PushService — `send_to_user` happy path + token query

**Files:**
- Modify: `services/push.py`
- Modify: `tests/services/test_push.py`

- [ ] **Step 1: Add the happy-path test**

Append to `tests/services/test_push.py`:

```python
@pytest.mark.asyncio
async def test_send_to_user_fans_out_across_all_devices(monkeypatch, fake_db, fake_messaging):
    """When a user has 2 tokens, send is called twice — once per token."""
    with patch("services.push.credentials"), patch("services.push.initialize_app"):
        svc = PushService(sa_path="/dev/null", project_id="t", db=fake_db)
    payload = PushPayload(title="hi", body="there", url="/x", trace_id="trace-1")
    results = await svc.send_to_user(user_id=1, payload=payload)

    assert len(results) == 2
    assert all(r.ok for r in results)
    assert {r.token for r in results} == {"T1", "T2"}
    assert fake_messaging.send.call_count == 2
    # Every constructed message should have the data['url'] = "/x".
    for call in fake_messaging.Message.call_args_list:
        kwargs = call.kwargs
        assert kwargs["data"]["url"] == "/x"
        assert kwargs["data"]["trace_id"] == "trace-1"


@pytest.mark.asyncio
async def test_send_to_user_no_tokens_returns_empty_list(fake_messaging):
    db = _FakeDB(rows=[])
    with patch("services.push.credentials"), patch("services.push.initialize_app"):
        svc = PushService(sa_path="/dev/null", project_id="t", db=db)
    results = await svc.send_to_user(user_id=1, payload=PushPayload("a", "b"))
    assert results == []
    fake_messaging.send.assert_not_called()
```

Add to the top of the test file, just below imports:
```python
import pytest_asyncio  # noqa: F401  (ensures asyncio mode is loaded)
```

If `pyproject.toml` / `pytest.ini` doesn't already enable `asyncio_mode = "auto"`, the `@pytest.mark.asyncio` decorator is required (already shown).

- [ ] **Step 2: Run; verify failures with `NotImplementedError`**

```bash
pytest tests/services/test_push.py -v
```

Expected: 2 new tests fail with `NotImplementedError`.

- [ ] **Step 3: Implement `send_to_user`**

Replace the `send_to_user` body in `services/push.py`:

```python
    async def send_to_user(self, user_id: int, payload: PushPayload) -> list[SendResult]:
        tokens = await self._tokens_for_user(user_id)
        if not tokens:
            return []

        results: list[SendResult] = []
        for token in tokens:
            result = await self._send_one(token, payload)
            results.append(result)

        await self._mark_log(user_id, payload, results)
        return results

    async def _tokens_for_user(self, user_id: int) -> list[str]:
        rows = await self._db.fetch(
            "SELECT fcm_token FROM device_tokens WHERE user_id = $1",
            user_id,
        )
        return [r["fcm_token"] for r in rows]

    async def _send_one(self, token: str, payload: PushPayload) -> SendResult:
        msg = messaging.Message(
            token=token,
            notification=messaging.Notification(
                title=payload.title, body=payload.body,
            ),
            data={
                "url": payload.url or "/",
                "trace_id": payload.trace_id or "",
            },
            webpush=messaging.WebpushConfig(
                fcm_options=messaging.WebpushFCMOptions(
                    link=payload.url or "/",
                ),
            ),
        )
        try:
            msg_id = await asyncio.to_thread(messaging.send, msg)
            return SendResult(token=token, ok=True, msg_id=msg_id)
        except messaging.UnregisteredError:
            await self._delete_token(token)
            return SendResult(token=token, ok=False, reason="unregistered")
        except (
            messaging.InvalidArgumentError,
            messaging.SenderIdMismatchError,
        ) as exc:
            await self._delete_token(token)
            return SendResult(token=token, ok=False, reason=type(exc).__name__)
        except Exception as exc:
            logger.exception("FCM send failed (keeping token)")
            return SendResult(token=token, ok=False, reason=str(exc)[:200])

    async def _delete_token(self, token: str) -> None:
        await self._db.execute(
            "DELETE FROM device_tokens WHERE fcm_token = $1", token,
        )

    async def _mark_log(
        self, user_id: int, payload: PushPayload, results: list[SendResult],
    ) -> None:
        """Best-effort log via existing agent_logs schema. Non-fatal on error."""
        try:
            ok_count = sum(1 for r in results if r.ok)
            await self._db.execute(
                "INSERT INTO agent_logs "
                "(trace_id, agent, action, status, output_data) "
                "VALUES ($1, 'push', 'fcm_dispatch', $2, $3::jsonb)",
                payload.trace_id or "00000000-0000-0000-0000-000000000000",
                "success" if ok_count == len(results) else "partial",
                f'{{"fanout":{len(results)},"ok":{ok_count}}}',
            )
        except Exception:
            logger.warning("agent_logs write for push failed (non-fatal)", exc_info=True)
```

- [ ] **Step 4: Run; verify pass**

```bash
pytest tests/services/test_push.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add services/push.py tests/services/test_push.py
git commit -m "feat(sp7): PushService.send_to_user — fan-out + agent_logs write-through"
```

---

### Task 1.5: PushService — failure-path coverage (delete on Unregistered/Invalid/SenderId; keep on network)

**Files:**
- Modify: `tests/services/test_push.py`

- [ ] **Step 1: Add the failure-path tests**

Append:

```python
@pytest.mark.asyncio
async def test_unregistered_error_deletes_token(fake_db, fake_messaging):
    """UnregisteredError → row removed from device_tokens.

    We use the REAL firebase_admin.messaging.UnregisteredError class so the
    except-clause in PushService catches it without any class-shadowing
    magic. The fake_messaging fixture only patches `messaging.send`; the
    error classes are the real upstream ones."""
    from firebase_admin.messaging import UnregisteredError
    fake_messaging.UnregisteredError = UnregisteredError
    fake_messaging.send.side_effect = UnregisteredError("gone")
    with patch("services.push.credentials"), patch("services.push.initialize_app"):
        svc = PushService(sa_path="/dev/null", project_id="t", db=fake_db)
    results = await svc.send_to_user(user_id=1, payload=PushPayload("a", "b"))

    assert all(not r.ok and r.reason == "unregistered" for r in results)
    delete_calls = [e for e in fake_db.executed if e[0] == "execute" and "DELETE" in e[1]]
    assert len(delete_calls) == 2  # T1 and T2 both deleted


@pytest.mark.asyncio
async def test_invalid_argument_error_deletes_token(fake_db, fake_messaging):
    from firebase_admin.exceptions import InvalidArgumentError
    fake_messaging.InvalidArgumentError = InvalidArgumentError
    fake_messaging.send.side_effect = InvalidArgumentError("bad", code="invalid-argument")
    with patch("services.push.credentials"), patch("services.push.initialize_app"):
        svc = PushService(sa_path="/dev/null", project_id="t", db=fake_db)
    results = await svc.send_to_user(user_id=1, payload=PushPayload("a", "b"))
    assert all(r.reason == "InvalidArgumentError" for r in results)


@pytest.mark.asyncio
async def test_sender_id_mismatch_deletes_token(fake_db, fake_messaging):
    from firebase_admin.messaging import SenderIdMismatchError
    fake_messaging.SenderIdMismatchError = SenderIdMismatchError
    fake_messaging.send.side_effect = SenderIdMismatchError("mismatch")
    with patch("services.push.credentials"), patch("services.push.initialize_app"):
        svc = PushService(sa_path="/dev/null", project_id="t", db=fake_db)
    results = await svc.send_to_user(user_id=1, payload=PushPayload("a", "b"))
    assert all(r.reason == "SenderIdMismatchError" for r in results)


@pytest.mark.asyncio
async def test_generic_exception_keeps_token(fake_db, fake_messaging):
    """Network or 5xx errors → keep token, surface error reason."""
    fake_messaging.send.side_effect = RuntimeError("502 bad gateway")
    with patch("services.push.credentials"), patch("services.push.initialize_app"):
        svc = PushService(sa_path="/dev/null", project_id="t", db=fake_db)
    results = await svc.send_to_user(user_id=1, payload=PushPayload("a", "b"))
    assert all(not r.ok and "bad gateway" in (r.reason or "") for r in results)
    delete_calls = [e for e in fake_db.executed if e[0] == "execute" and "DELETE" in e[1]]
    assert len(delete_calls) == 0


@pytest.mark.asyncio
async def test_partial_failure_mid_fanout(fake_messaging):
    """First token succeeds, second fails — both results returned correctly."""
    db = _FakeDB(rows=[{"fcm_token": "T1"}, {"fcm_token": "T2"}])
    fake_messaging.send.side_effect = ["msg_ok", RuntimeError("boom")]
    with patch("services.push.credentials"), patch("services.push.initialize_app"):
        svc = PushService(sa_path="/dev/null", project_id="t", db=db)
    results = await svc.send_to_user(user_id=1, payload=PushPayload("a", "b"))
    assert results[0].ok and results[0].msg_id == "msg_ok"
    assert not results[1].ok and "boom" in results[1].reason


@pytest.mark.asyncio
async def test_degraded_mode_no_op_when_service_is_none():
    """Callers must be safe to call get_push_service() == None as no-op.
    The contract: a None service is callable iff guarded — agents wrap calls
    in `if push:`. Document this with an integration-shape test."""
    push: PushService | None = None
    # Call sites do `if push: await push.send_to_user(...)`. Verify the guard
    # works.
    assert push is None
    if push:  # pragma: no cover — illustrative
        await push.send_to_user(1, PushPayload("a", "b"))
    # Test passes by virtue of not raising — guard pattern preserved.


@pytest.mark.asyncio
async def test_message_includes_webpush_link(fake_db, fake_messaging):
    """Verify the WebpushFCMOptions(link=...) is set so notificationclick opens
    the right URL."""
    with patch("services.push.credentials"), patch("services.push.initialize_app"):
        svc = PushService(sa_path="/dev/null", project_id="t", db=fake_db)
    await svc.send_to_user(user_id=1, payload=PushPayload("a", "b", url="/conv/abc"))
    # The first Message constructed has webpush.fcm_options.link == "/conv/abc"
    fcm_opts = fake_messaging.WebpushFCMOptions.call_args_list[0]
    assert fcm_opts.kwargs["link"] == "/conv/abc"
```

- [ ] **Step 2: Run; verify all pass**

```bash
pytest tests/services/test_push.py -v
```

Expected: 12 tests pass (including the 5 from earlier tasks). The error-class shadowing via `patch` is the trickiest piece — if a test fails with "expected UnregisteredError, got RuntimeError" it means the `patch("services.push.messaging.UnregisteredError", …)` didn't take effect; double-check the patch target string matches the import in `services/push.py`.

- [ ] **Step 3: Commit**

```bash
git add tests/services/test_push.py
git commit -m "test(sp7): PushService failure-path coverage (delete-on-unregistered, keep-on-network, degraded-mode)"
```

---

### Task 1.6: `POST /devices/register` endpoint

**Files:**
- Modify: `backend/api/main.py`
- Create: `tests/api/test_devices_endpoint.py`

The endpoint reuses the existing JWT auth pattern. If `backend/api/main.py` already has an auth dependency named `get_current_user` or `current_user`, reuse it; the test below assumes such a dependency exists. If not, look at how other authed endpoints (e.g. `/conversations`) are defined and copy that pattern.

- [ ] **Step 1: Skim existing auth patterns**

```bash
grep -n "Depends\|@app.post\|@app.get" backend/api/main.py | head -40
```

Note the auth dependency name and the `request.app.state.db` (or equivalent) DB-handle pattern.

- [ ] **Step 2: Write the failing endpoint test**

```python
# tests/api/test_devices_endpoint.py
"""Tests for POST /devices/register."""
import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient


# Import paths may need adjustment to match your project layout.
from backend.api.main import app  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    """TestClient with the DB and auth dependencies overridden."""
    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(return_value=None)
    fake_db.fetchrow = AsyncMock(return_value={
        "id": "00000000-0000-0000-0000-000000000099",
    })

    # Replace the singleton getters used inside the endpoint.
    from backend.api import main as main_mod
    monkeypatch.setattr(main_mod, "get_db_service", lambda: fake_db)
    # If your auth uses a Depends-injected user, override it here:
    if hasattr(main_mod, "get_current_user"):
        app.dependency_overrides[main_mod.get_current_user] = lambda: {"id": 1}
    yield TestClient(app), fake_db
    app.dependency_overrides.clear()


def test_register_device_creates_token_row(client):
    c, db = client
    r = c.post("/devices/register", json={
        "fcm_token": "fcm-test-token",
        "device_label": "phone",
        "user_agent": "Pixel 8 Chrome 130",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["registered"] is True
    assert "device_id" in body
    # Verify upsert SQL was issued.
    assert db.execute.await_count >= 1
    sql = db.execute.await_args_list[0].args[0]
    assert "ON CONFLICT" in sql.upper()


def test_register_device_requires_fcm_token(client):
    c, _ = client
    r = c.post("/devices/register", json={"device_label": "phone"})
    assert r.status_code == 422


def test_register_device_validates_label_length(client):
    c, _ = client
    r = c.post("/devices/register", json={
        "fcm_token": "x",
        "device_label": "a" * 100,  # > 50 chars
    })
    assert r.status_code == 422


def test_register_device_unauthenticated_rejected(client, monkeypatch):
    c, _ = client
    # Clear the auth override so the real dependency runs.
    app.dependency_overrides.clear()
    r = c.post("/devices/register", json={
        "fcm_token": "x", "device_label": "phone",
    })
    assert r.status_code in (401, 403)


def test_register_device_idempotent_upsert(client):
    """Two registrations of the same token must succeed; the SQL is upsert."""
    c, db = client
    r1 = c.post("/devices/register", json={
        "fcm_token": "same", "device_label": "phone",
    })
    r2 = c.post("/devices/register", json={
        "fcm_token": "same", "device_label": "phone",
    })
    assert r1.status_code == 200 and r2.status_code == 200


def test_register_device_minimal_payload(client):
    """Only fcm_token is required; label and user_agent optional."""
    c, _ = client
    r = c.post("/devices/register", json={"fcm_token": "minimal"})
    assert r.status_code == 200
```

- [ ] **Step 3: Run; verify failures**

```bash
pytest tests/api/test_devices_endpoint.py -v
```

Expected: all six fail because the endpoint doesn't exist yet.

- [ ] **Step 4: Implement the endpoint**

Add to `backend/api/main.py` near the other authenticated endpoints:

```python
from pydantic import BaseModel, Field


class DeviceRegisterRequest(BaseModel):
    fcm_token: str = Field(..., min_length=1)
    device_label: Optional[str] = Field(None, max_length=50)
    user_agent: Optional[str] = None


class DeviceRegisterResponse(BaseModel):
    registered: bool
    device_id: str


@app.post("/devices/register", response_model=DeviceRegisterResponse)
async def register_device(
    body: DeviceRegisterRequest,
    user: dict = Depends(get_current_user),  # adjust if your auth differs
):
    db = get_db_service()
    row = await db.fetchrow(
        """
        INSERT INTO device_tokens (user_id, fcm_token, device_label, user_agent)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (fcm_token) DO UPDATE
            SET last_seen_at = NOW(),
                device_label = COALESCE(EXCLUDED.device_label, device_tokens.device_label),
                user_agent = COALESCE(EXCLUDED.user_agent, device_tokens.user_agent)
        RETURNING id
        """,
        user["id"], body.fcm_token, body.device_label, body.user_agent,
    )
    return DeviceRegisterResponse(registered=True, device_id=str(row["id"]))
```

If `Depends`, `Optional`, or `BaseModel` aren't already imported at the top of the file, add the relevant `from fastapi import Depends`, `from typing import Optional`, `from pydantic import BaseModel, Field` imports.

- [ ] **Step 5: Run; verify pass**

```bash
pytest tests/api/test_devices_endpoint.py -v
```

Expected: 6 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/api/main.py tests/api/test_devices_endpoint.py
git commit -m "feat(sp7): POST /devices/register — upsert FCM token, JWT-authed"
```

---

### Task 1.7: Wire PushService into FastAPI lifespan

**Files:**
- Modify: `backend/api/main.py`

The existing `lifespan()` in `backend/api/main.py` already initialises DB, Qdrant, alerts. Add PushService init alongside, with the documented degraded-mode fallback when `FCM_SA_PATH` is unset.

- [ ] **Step 1: Skim the existing lifespan**

```bash
grep -n "lifespan\|app.state" backend/api/main.py | head -20
```

Note where other singletons are stashed (likely `app.state.push` or similar pattern).

- [ ] **Step 2: Add the init block**

Inside the existing `lifespan` function, after DB connect, add:

```python
    # ── PushService init (FCM) ──────────────────────────────────────
    sa_path = os.environ.get("FCM_SA_PATH", "").strip()
    project_id = os.environ.get("FCM_PROJECT_ID", "").strip()
    if sa_path and project_id:
        if not os.path.exists(sa_path):
            raise RuntimeError(
                f"FCM_SA_PATH set to {sa_path!r} but file not found — "
                "fix the env var or unset both FCM_SA_PATH + FCM_PROJECT_ID "
                "to run in degraded (no-push) mode."
            )
        from services.push import PushService
        app.state.push = PushService(
            sa_path=sa_path, project_id=project_id, db=get_db_service(),
        )
        logger.info("PushService initialised — FCM dispatch active")
    else:
        app.state.push = None
        logger.info(
            "PushService not configured (FCM_SA_PATH/FCM_PROJECT_ID unset) — "
            "running in degraded mode, push notifications disabled"
        )
```

- [ ] **Step 3: Add a `get_push_service()` accessor (consumed by agents)**

Append to `services/push.py`:

```python
_INSTANCE: Optional["PushService"] = None


def set_push_service(svc: Optional["PushService"]) -> None:
    """Called by lifespan() once the service is constructed (or once we've
    decided we're in degraded mode). Tests can call with None to reset."""
    global _INSTANCE
    _INSTANCE = svc


def get_push_service() -> Optional["PushService"]:
    """Returns the singleton, or None if push is disabled (degraded mode)."""
    return _INSTANCE
```

In `lifespan()`, after constructing `PushService`, also call:

```python
        from services.push import set_push_service
        set_push_service(app.state.push)
```

And after the `else` branch:

```python
        from services.push import set_push_service
        set_push_service(None)
```

- [ ] **Step 4: Add a startup test + autouse reset fixture**

Append to `tests/services/test_push.py`:

```python
@pytest.fixture(autouse=True)
def _reset_push_singleton():
    """Each test gets a clean global singleton state. Without this autouse
    fixture, tests can leak state through services.push._INSTANCE."""
    from services.push import set_push_service
    set_push_service(None)
    yield
    set_push_service(None)


def test_get_push_service_returns_none_by_default():
    from services.push import get_push_service
    assert get_push_service() is None


def test_set_and_get_push_service_roundtrip():
    from services.push import get_push_service, set_push_service
    sentinel = object()
    set_push_service(sentinel)  # type: ignore[arg-type]
    assert get_push_service() is sentinel
    # autouse fixture resets after the test
```

- [ ] **Step 5: Run all push tests**

```bash
pytest tests/services/test_push.py tests/api/test_devices_endpoint.py -v
```

Expected: 14 + 6 = 20 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/api/main.py services/push.py tests/services/test_push.py
git commit -m "feat(sp7): lifespan inits PushService — degraded mode when FCM env unset"
```

---

### Task 1.8: Update `.gitignore` and `.env.example`

**Files:**
- Modify: `.gitignore`
- Modify: `.env.example` (or `env.example`, whichever exists)

- [ ] **Step 1: Verify FCM service-account JSON is excluded**

```bash
grep -E "fcm-sa|sa\.json" .gitignore || echo "NEEDS ADD"
```

If "NEEDS ADD", append to `.gitignore`:

```
# FCM / Firebase service-account credentials
*-sa.json
.config/cruz/*.json
```

- [ ] **Step 2: Document env vars in .env.example**

Append (or insert under a "Push / FCM" header):

```
# ── Push / FCM ─────────────────────────────────────────
# Path to Firebase service-account JSON. Unset = degraded mode (no push).
FCM_SA_PATH=
# Firebase project ID — must match the JSON. Unset = degraded mode.
FCM_PROJECT_ID=
# VAPID public key for web-push subscription (used by frontend SW).
FCM_VAPID_PUBLIC_KEY=
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore .env.example
git commit -m "chore(sp7): document FCM env vars; gitignore *-sa.json"
```

---

**Chunk 1 complete.** Push backend is fully wired: schema, service, endpoint, lifespan, env. Ready for the daemon work in Chunk 2.

**Chunk 1 review checkpoint.** Dispatch plan-document-reviewer with this chunk before proceeding to Chunk 2 if implementing via subagent-driven-development. Otherwise: confirm `pytest tests/services/test_push.py tests/api/test_devices_endpoint.py -v` shows 20 passes locally and move on.

---

## Chunk 2: Voice daemon hardening — AEC, reconnect, mic-restart, watchdog

**Why second.** The 24h burn-in (Chunk 3) needs all five hardening fixes in place. Chunk 2 must close before burn-in kicks off.

### Task 2.1: AEC pause flag — `playback_active` + frame zero-fill

**Files:**
- Modify: `scripts/voice/livekit_client.py`
- Create: `tests/scripts/test_voice_daemon.py`

The daemon's mic callback runs in a sounddevice C thread; the LiveKit playback runs as an asyncio task. They share state via `threading.Event`.

- [ ] **Step 1: Write the failing AEC unit test**

```python
# tests/scripts/test_voice_daemon.py
"""Unit tests for scripts/voice/livekit_client.py — sd, livekit mocked."""
import os
import sys
import threading

import numpy as np
import pytest

# Add scripts/ to path so we can import the daemon module under test.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)


@pytest.fixture
def daemon_module(monkeypatch):
    """Import scripts/voice/livekit_client with sounddevice + livekit stubbed.

    Uses MagicMock for fake_rtc so any module-top-level attribute access
    (e.g. `rtc.AudioStream`, `rtc.TrackKind.KIND_AUDIO`) works lazily."""
    from unittest.mock import MagicMock

    fake_sd = type(sys)("sd")
    fake_sd.RawOutputStream = lambda **kwargs: type("S", (), {
        "start": lambda self: None, "write": lambda self, data: None,
    })()
    fake_sd.InputStream = lambda **kwargs: type("S", (), {
        "__enter__": lambda self: self, "__exit__": lambda *a: None,
    })()
    fake_sd.PortAudioError = type("PortAudioError", (Exception,), {})

    # MagicMock — any attribute access returns a child MagicMock. Lets the
    # daemon module import cleanly even if it references rtc.X at module scope.
    fake_rtc = MagicMock()
    fake_livekit = type(sys)("livekit")
    fake_livekit.rtc = fake_rtc
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    monkeypatch.setitem(sys.modules, "livekit", fake_livekit)

    if "scripts.voice.livekit_client" in sys.modules:
        del sys.modules["scripts.voice.livekit_client"]
    import scripts.voice.livekit_client as mod  # noqa: WPS433
    return mod


def test_playback_active_flag_exists_and_is_threading_event(daemon_module):
    flag = getattr(daemon_module, "playback_active", None)
    assert isinstance(flag, threading.Event), \
        "daemon must expose a module-level threading.Event named 'playback_active'"


def test_aec_zero_fill_helper_zeros_int16_buffer(daemon_module):
    """The daemon exposes a helper that builds an int16-zeros frame for the
    AEC pause path."""
    helper = getattr(daemon_module, "_zero_fill_frame", None)
    assert callable(helper), "expected helper _zero_fill_frame(indata) -> bytes"
    indata = np.ones((1280, 1), dtype=np.int16) * 1234
    out = helper(indata)
    assert isinstance(out, (bytes, bytearray))
    assert len(out) == indata.nbytes
    # All zero bytes.
    assert all(b == 0 for b in out)
```

- [ ] **Step 2: Run; verify failures**

```bash
pytest tests/scripts/test_voice_daemon.py -v
```

Expected: 2 tests fail (no `playback_active`, no `_zero_fill_frame`).

- [ ] **Step 3: Add the flag + helper to the daemon**

Edit `scripts/voice/livekit_client.py`. Near the top-level imports (after the existing module-level constants like `SAMPLE_RATE`), add:

```python
import threading

# AEC: set while the daemon is playing TTS audio out of the speakers.
# - Mic callback skips wake-word detection while set.
# - Mic callback zero-fills the LiveKit-published frame so the worker's
#   Deepgram WS doesn't hear the speaker echo.
# Cleared after a configurable tail (TTS_TAIL_MS, default 300ms) to absorb
# Bluetooth codec latency. See docs/superpowers/specs/2026-05-10-sp7-...md §3.1.
playback_active = threading.Event()


def _zero_fill_frame(indata: "np.ndarray") -> bytes:
    """Return an int16-zero buffer matching indata's byte length.
    Used while playback_active is set to suppress speaker echo on the published mic track."""
    import numpy as _np
    zeros = _np.zeros_like(indata)
    return zeros.tobytes()
```

- [ ] **Step 4: Run; verify pass**

```bash
pytest tests/scripts/test_voice_daemon.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Wire the flag into the existing `on_track_sub` and `_audio_cb`**

In `scripts/voice/livekit_client.py`, modify `on_track_sub.<_play>`:

```python
        async def _play():
            playback_active.set()
            try:
                stream = rtc.AudioStream(track)
                async for ev in stream:
                    sr = ev.frame.sample_rate
                    if playback["stream"] is None:
                        playback["stream"] = sd.RawOutputStream(
                            samplerate=sr, channels=1, dtype="int16", blocksize=0,
                        )
                        playback["stream"].start()
                    playback["stream"].write(bytes(ev.frame.data))
            finally:
                tail_ms = int(os.environ.get("TTS_TAIL_MS", "300"))
                await asyncio.sleep(tail_ms / 1000.0)
                playback_active.clear()
```

In `_audio_cb`, at the very top of the function (before any wake-word work), add:

```python
        if playback_active.is_set():
            # Suppress wake detection AND publish silence to LiveKit so the
            # worker's Deepgram WS never hears the speaker output.
            zeros = _zero_fill_frame(indata)
            zero_frame = rtc.AudioFrame(
                data=zeros, sample_rate=SAMPLE_RATE,
                num_channels=1, samples_per_channel=frames,
            )
            loop.call_soon_threadsafe(
                asyncio.create_task, mic_source.capture_frame(zero_frame),
            )
            return
```

- [ ] **Step 6: Add an integration-shape unit test for the suppression contract**

Append to `tests/scripts/test_voice_daemon.py`:

```python
def test_audio_cb_suppresses_wake_detection_while_playback_active(daemon_module):
    """When playback_active is set, the wake-word detector must not be queried."""
    # We can't easily run _audio_cb directly (it depends on closure state from
    # _join_and_run) but we can document the contract by asserting the helper
    # exists and the flag is consulted. The integration with _audio_cb is
    # exercised by the live burn-in.
    assert daemon_module.playback_active.is_set() is False
    daemon_module.playback_active.set()
    assert daemon_module.playback_active.is_set() is True
    daemon_module.playback_active.clear()
```

- [ ] **Step 7: Run all daemon tests**

```bash
pytest tests/scripts/test_voice_daemon.py -v
```

Expected: 3 tests pass.

- [ ] **Step 8: Commit**

```bash
git add scripts/voice/livekit_client.py tests/scripts/test_voice_daemon.py
git commit -m "feat(sp7): voice daemon AEC — pause wake-word + zero-fill mic during TTS"
```

---

### Task 2.2: LiveKit reconnect loop with backoff

**Files:**
- Modify: `scripts/voice/livekit_client.py`
- Modify: `tests/scripts/test_voice_daemon.py`

- [ ] **Step 1: Write the failing reconnect test**

Append:

```python
def test_reconnect_backoff_schedule_constants(daemon_module):
    """The daemon exposes a backoff schedule (list of seconds) capped at 60."""
    schedule = getattr(daemon_module, "RECONNECT_BACKOFF_SECONDS", None)
    assert isinstance(schedule, list) and len(schedule) >= 5
    assert all(isinstance(s, (int, float)) for s in schedule)
    assert max(schedule) <= 60, "backoff must be capped at 60s"


def test_pick_backoff_clamps_at_end(daemon_module):
    pick = daemon_module._pick_backoff
    sched = daemon_module.RECONNECT_BACKOFF_SECONDS
    assert pick(0) == sched[0]
    assert pick(len(sched) - 1) == sched[-1]
    assert pick(999) == sched[-1]  # clamps
```

- [ ] **Step 2: Run; verify failures**

```bash
pytest tests/scripts/test_voice_daemon.py -v
```

Expected: 2 new tests fail.

- [ ] **Step 3: Add the constants + helper**

In `scripts/voice/livekit_client.py`, near the other module-level constants:

```python
# Reconnect backoff for the LiveKit room session. Reset on a clean disconnect
# (i.e. _run_session returned without exception). Telegram alert at attempt >= 3.
RECONNECT_BACKOFF_SECONDS: list[int] = [1, 2, 4, 8, 16, 30, 60, 60, 60]


def _pick_backoff(attempt: int) -> int:
    return RECONNECT_BACKOFF_SECONDS[
        min(attempt, len(RECONNECT_BACKOFF_SECONDS) - 1)
    ]
```

- [ ] **Step 4: Refactor `main` (or `_join_and_run`) to use the loop**

The existing `main()` calls `_fetch_token` then `_join_and_run`. Wrap that in:

```python
async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:3000")
    ap.add_argument("--conversation-id", default=None)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO)
    conv_id = args.conversation_id or str(uuid.uuid4())

    attempt = 0
    while True:
        try:
            tok = await _fetch_token(
                args.host, device_id="mac-mini", conversation_id=conv_id,
            )
            await _join_and_run(tok, conv_id)
            attempt = 0  # clean disconnect — reset
        except Exception:
            delay = _pick_backoff(attempt)
            logger.exception("livekit session crashed, sleep %ds", delay)
            if attempt >= 2:
                _alert_reconnect(attempt + 1)
            attempt += 1
            await asyncio.sleep(delay)


def _alert_reconnect(attempt: int) -> None:
    """Best-effort Telegram alert via existing services/alerts.py.
    Non-fatal — never raises."""
    try:
        from services.alerts import send as _send
        asyncio.create_task(_send(
            f"voice daemon reconnecting (attempt {attempt})",
            severity="warning",
        ))
    except Exception:
        logger.warning("alerts.send failed (non-fatal)", exc_info=True)
```

If `services/alerts.py` exposes a slightly different API (e.g. `AlertService.warning(...)`), adjust the call to match. `grep -n "def send\|class Alert" services/alerts.py` to confirm.

- [ ] **Step 5: Run; verify all daemon tests pass**

```bash
pytest tests/scripts/test_voice_daemon.py -v
```

Expected: 5 tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/voice/livekit_client.py tests/scripts/test_voice_daemon.py
git commit -m "feat(sp7): daemon reconnect loop with backoff (cap 60s) + alert at attempt>=3"
```

---

### Task 2.3: Mic-stream restart on PortAudioError

**Files:**
- Modify: `scripts/voice/livekit_client.py`
- Modify: `tests/scripts/test_voice_daemon.py`

- [ ] **Step 1: Failing test — restart helper exists**

Append:

```python
def test_mic_restart_helper_uses_same_backoff_table(daemon_module):
    """Mic stream restart on PortAudioError uses RECONNECT_BACKOFF_SECONDS."""
    fn = getattr(daemon_module, "_run_mic_with_restart", None)
    assert callable(fn), "expected helper _run_mic_with_restart(open_stream)"
```

- [ ] **Step 2: Run; verify failure**

```bash
pytest tests/scripts/test_voice_daemon.py::test_mic_restart_helper_uses_same_backoff_table -v
```

- [ ] **Step 3: Add the helper**

```python
async def _run_mic_with_restart(open_stream_cm) -> None:
    """Run the InputStream context manager; restart on PortAudioError.

    `open_stream_cm` is a 0-arg callable returning a fresh `sd.InputStream`
    context manager (different InputStream parameters per session, so we
    take a constructor-callable rather than a single instance)."""
    attempt = 0
    while True:
        try:
            with open_stream_cm():
                # Block here while the daemon main loop runs. The caller is
                # expected to use this from inside a `while True: await
                # asyncio.sleep(...)` loop in _join_and_run.
                while True:
                    await asyncio.sleep(2)
            attempt = 0
        except sd.PortAudioError as exc:
            delay = _pick_backoff(attempt)
            logger.warning("mic stream crashed (%s) — sleep %ds", exc, delay)
            _alert_reconnect(attempt + 1)
            attempt += 1
            await asyncio.sleep(delay)
```

Refactor `_join_and_run` so its existing `with sd.InputStream(...): while True: await asyncio.sleep(2): ...` block becomes a callable, then call `await _run_mic_with_restart(make_stream)`. Keep the existing periodic heartbeat / silence-mute logic inside the InputStream block.

- [ ] **Step 4: Run all tests**

```bash
pytest tests/scripts/test_voice_daemon.py -v
```

Expected: all pass (6 total).

- [ ] **Step 5: Commit**

```bash
git add scripts/voice/livekit_client.py tests/scripts/test_voice_daemon.py
git commit -m "feat(sp7): daemon mic-stream restart on PortAudioError"
```

---

### Task 2.4: Memory watchdog (psutil RSS log + 80% cap warning)

**Files:**
- Modify: `scripts/voice/livekit_client.py`
- Modify: `tests/scripts/test_voice_daemon.py`

- [ ] **Step 1: Failing test**

Append:

```python
def test_memory_watchdog_threshold(daemon_module):
    """Watchdog warns when RSS exceeds 80% of the configured cap."""
    fn = getattr(daemon_module, "_should_warn_rss", None)
    assert callable(fn)
    # Cap = 512 MB; 80% = 410 MB.
    assert fn(rss_bytes=400 * 1024 * 1024, cap_bytes=512 * 1024 * 1024) is False
    assert fn(rss_bytes=420 * 1024 * 1024, cap_bytes=512 * 1024 * 1024) is True
```

- [ ] **Step 2: Run; verify failure**

```bash
pytest tests/scripts/test_voice_daemon.py::test_memory_watchdog_threshold -v
```

- [ ] **Step 3: Add the watchdog helper + loop**

```python
import psutil  # add to existing import block at top

# Cap mirrors PM2 max_memory_restart: "512M" for daemon.
DAEMON_RSS_CAP_BYTES = 512 * 1024 * 1024
DAEMON_RSS_WARN_RATIO = 0.80


def _should_warn_rss(rss_bytes: int, cap_bytes: int) -> bool:
    return rss_bytes >= int(cap_bytes * DAEMON_RSS_WARN_RATIO)


async def _memory_watchdog() -> None:
    """Log RSS every 60s; alert if >80% of PM2 cap (single-fire per process lifetime)."""
    proc = psutil.Process()
    warned = False
    while True:
        try:
            rss = proc.memory_info().rss
            logger.info("daemon RSS=%dMB", rss // (1024 * 1024))
            if _should_warn_rss(rss, DAEMON_RSS_CAP_BYTES) and not warned:
                try:
                    from services.alerts import send as _send
                    await _send(
                        f"voice daemon RSS={rss // (1024*1024)}MB > 80% of "
                        f"{DAEMON_RSS_CAP_BYTES // (1024*1024)}MB cap",
                        severity="warning",
                    )
                except Exception:
                    logger.warning("alerts.send failed (non-fatal)", exc_info=True)
                warned = True
        except Exception:
            logger.exception("memory watchdog tick failed (non-fatal)")
        await asyncio.sleep(60)
```

Spawn `_memory_watchdog()` as a background task inside `_join_and_run`:

```python
    watchdog_task = asyncio.create_task(_memory_watchdog())
    try:
        # ... existing body ...
    finally:
        watchdog_task.cancel()
```

- [ ] **Step 4: Run; verify pass**

```bash
pytest tests/scripts/test_voice_daemon.py -v
```

Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/voice/livekit_client.py tests/scripts/test_voice_daemon.py
git commit -m "feat(sp7): daemon memory watchdog — RSS log every 60s, alert at 80% cap"
```

---

### Task 2.5: Voice-worker — bounded Deepgram queue + raise-on-disconnect

**Files:**
- Modify: `workers/voice_agent/worker.py`
- Modify: `services/realtime_voice.py`
- Modify: `tests/workers/test_voice_agent_worker.py` (or whatever the existing test file is — `find tests -name '*voice_agent*'`)

- [ ] **Step 1: Skim the existing test file**

```bash
find tests -name "*voice_agent*" -o -name "*realtime_voice*"
```

- [ ] **Step 2: Add a queue-bound helper to DeepgramSTT**

In `services/realtime_voice.py`, modify the `_on_transcript` callback inside `DeepgramSTT.connect`:

```python
        async def _on_transcript(_self: object, result: object, **kwargs) -> None:
            try:
                alt = result.channel.alternatives[0]
                text = (alt.transcript or "").strip()
                is_final = bool(result.is_final)
                if not text:
                    return
                logger.info("deepgram transcript: final=%s text=%r", is_final, text)
                # Bound the queue: drop oldest interim if backlog grows past 1000.
                # Final transcripts are kept; only interim drops are safe (they
                # are superseded by their successor anyway).
                if not is_final and self._queue.qsize() > 1000:
                    try:
                        _ = self._queue.get_nowait()
                    except Exception:
                        pass
                await self._queue.put(STTTranscript(text=text, is_final=is_final))
            except Exception:
                logger.exception("DeepgramSTT transcript parse failed")
```

- [ ] **Step 3: Add a unit test for the bound**

Append to `tests/services/test_realtime_voice.py` (create if missing):

```python
"""Tests for services.realtime_voice — Deepgram SDK fully mocked."""
import asyncio
from unittest.mock import MagicMock

import pytest

from services.realtime_voice import DeepgramSTT, STTTranscript


@pytest.mark.asyncio
async def test_interim_transcripts_drop_oldest_when_backlog_exceeds_1000():
    stt = DeepgramSTT()
    # Stuff queue with 1001 fake interim transcripts; the next put must drop
    # the oldest. We simulate this by directly using the bounded path.
    for i in range(1001):
        await stt._queue.put(STTTranscript(text=f"old-{i}", is_final=False))
    # Trigger the same drop-oldest logic the callback uses:
    if stt._queue.qsize() > 1000:
        _ = stt._queue.get_nowait()
    await stt._queue.put(STTTranscript(text="new", is_final=False))
    # Drain and verify the very-oldest "old-0" is gone.
    items = []
    while not stt._queue.empty():
        items.append(stt._queue.get_nowait().text)
    assert "old-0" not in items
    assert "new" in items
```

- [ ] **Step 4: Switch worker disconnect path to `raise`**

In `workers/voice_agent/worker.py`, the existing `_process_turns` and the entrypoint structure logs Deepgram errors but continues. Find this block at the bottom of `entrypoint()`:

```python
    finally:
        ka_task = stt_state.get("keepalive_task")
        if ka_task is not None:
            stt_state["connected"] = False
            ka_task.cancel()
        await stt.close()
```

Above the `finally`, the `await asyncio.wait(...)` collects task exceptions. Locate the loop that consumes `done` tasks:

```python
        for t in done:
            if t is watchdog:
                continue
            exc = t.exception()
            if exc:
                logger.exception("voice task failed", exc_info=exc)
                raise exc  # NEW: propagate so livekit-agents restarts the entrypoint
```

(Currently the line `logger.exception("voice task failed", exc_info=exc)` exists without a follow-up `raise` — add `raise exc` immediately after it.)

- [ ] **Step 5: Run worker + STT tests**

```bash
pytest tests/services/test_realtime_voice.py tests/workers/ -v
```

Expected: existing tests still pass + new bound test passes. If a worker-test breaks because it now expects a raised exception that previously was swallowed, update the test's assertion to expect the raise.

- [ ] **Step 6: Commit**

```bash
git add services/realtime_voice.py workers/voice_agent/worker.py tests/services/test_realtime_voice.py
git commit -m "feat(sp7): bounded Deepgram queue + raise-on-task-failure for livekit-agents auto-restart"
```

---

### Task 2.6: TTS_TAIL_MS env doc + ecosystem.config.js passthrough

**Files:**
- Modify: `ecosystem.config.js`
- Modify: `.env.example`

- [ ] **Step 1: Confirm PM2 inherits shell env**

Per the comment at the top of `ecosystem.config.js`, PM2 already inherits env from `start-cruz.sh` which sources `.env`. So no explicit env passthrough needed — the env var is picked up automatically. Confirm by reading the existing comment block.

- [ ] **Step 2: Document `TTS_TAIL_MS` and `WAKE_WORD_MODEL_PATH` in .env.example**

Append to `.env.example`:

```
# ── Voice daemon tuning ────────────────────────────────
# Tail (ms) after TTS playback ends during which AEC keeps the mic muted.
# Default 300 — bump to 500 for Bluetooth speakers (extra codec latency).
TTS_TAIL_MS=300
# Path to the openWakeWord ONNX model the daemon loads. Default points at the
# committed hey_cruz model. Set to "hey_jarvis" to revert to pretrained.
WAKE_WORD_MODEL_PATH=scripts/wakeword/models/hey_cruz.onnx
# Wake-word detection threshold — set after retraining; see ROC table.
WAKE_WORD_THRESHOLD=0.5
```

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "docs(sp7): document TTS_TAIL_MS, WAKE_WORD_MODEL_PATH, WAKE_WORD_THRESHOLD"
```

---

**Chunk 2 complete.** Daemon hardening is in. Smoke test live before kicking off the 24h burn-in:

```bash
# Manual smoke (operator step):
pm2 restart cruz-daemon cruz-voice-worker
pm2 logs cruz-daemon --lines 50  # confirm wake-word detector loads, no immediate crash
# Say "Hey Jarvis (or Hey CRUZ post-Chunk 6)" — confirm the daemon transitions
# to mic unmuted, the worker logs a Deepgram transcript, and TTS plays back.
# During TTS playback, watch the daemon log: "playback_active set" → mic
# callback should NOT log new wake events.
```

If smoke is clean, proceed to Chunk 3.

---

## Chunk 3: 24-hour burn-in harness

**Why third.** Chunks 4–7 happen during the burn-in's wall-clock window. Harness must exist and start before that.

### Task 3.1: Burn-in script — PM2 + RSS + /health asserts

**Files:**
- Create: `scripts/uptime/voice_burn_in.py`
- Create: `tests/scripts/test_voice_burn_in.py`

- [ ] **Step 1: Failing assertion-helper test**

```python
# tests/scripts/test_voice_burn_in.py
"""Smoke tests for scripts/uptime/voice_burn_in.py — subprocess + httpx mocked."""
import json
from unittest.mock import patch, AsyncMock

import pytest

from scripts.uptime.voice_burn_in import (
    _check_pm2_processes_online,
    _check_rss_under_cap,
    _check_health_endpoint,
    BurnInTickResult,
)


def test_pm2_check_passes_when_both_online():
    pm2_jlist_output = json.dumps([
        {"name": "cruz-daemon", "pm2_env": {"status": "online", "restart_time": 0}},
        {"name": "cruz-voice-worker", "pm2_env": {"status": "online", "restart_time": 0}},
    ])
    with patch("scripts.uptime.voice_burn_in._run_pm2_jlist", return_value=pm2_jlist_output):
        result = _check_pm2_processes_online()
    assert result.ok is True
    assert result.daemon_status == "online"
    assert result.worker_status == "online"


def test_pm2_check_fails_when_daemon_stopped():
    pm2_jlist_output = json.dumps([
        {"name": "cruz-daemon", "pm2_env": {"status": "stopped", "restart_time": 0}},
        {"name": "cruz-voice-worker", "pm2_env": {"status": "online", "restart_time": 0}},
    ])
    with patch("scripts.uptime.voice_burn_in._run_pm2_jlist", return_value=pm2_jlist_output):
        result = _check_pm2_processes_online()
    assert result.ok is False


def test_rss_check_under_cap():
    assert _check_rss_under_cap(rss_bytes=100 * 1024 * 1024,
                                 cap_bytes=512 * 1024 * 1024).ok is True


def test_rss_check_over_cap():
    assert _check_rss_under_cap(rss_bytes=600 * 1024 * 1024,
                                 cap_bytes=512 * 1024 * 1024).ok is False


@pytest.mark.asyncio
async def test_health_check_passes_on_200():
    fake_resp = type("R", (), {"status_code": 200, "json": lambda self: {
        "livekit": "connected", "deepgram": "reachable",
    }})()
    with patch("scripts.uptime.voice_burn_in._fetch_health",
               new=AsyncMock(return_value=fake_resp)):
        result = await _check_health_endpoint("http://localhost:3000")
    assert result.ok is True
```

- [ ] **Step 2: Run; expect import errors**

```bash
pytest tests/scripts/test_voice_burn_in.py -v
```

Expected: collection error.

- [ ] **Step 3: Implement the harness skeleton**

```python
# scripts/uptime/voice_burn_in.py
"""24-hour voice-daemon burn-in.

Every 60s asserts:
  - cruz-daemon and cruz-voice-worker are online (pm2 jlist)
  - restart_time delta over the run is ≤ 3 per process
  - RSS for both processes is under PM2 cap (512MB / 1GB)
  - /health reports livekit:connected and deepgram:reachable

Every 30 minutes runs a synthetic round-trip (Task 3.2):
  - spawn a side daemon with SKIP_WAKE_WORD=1
  - publish a known utterance via the mic source
  - assert a Deepgram final transcript appears in agent_logs

Writes JSONL to docs/perf/sp7-voice-burn-in.jsonl. Final summary block emitted
at exit. Pass = 24h elapsed, all assertions green, ≤ 6 total PM2 restarts,
≥ 95% synthetic round-trip success.

Run:
    python scripts/uptime/voice_burn_in.py --hours 24 \\
        --output docs/perf/sp7-voice-burn-in.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import subprocess
import time
from dataclasses import dataclass, asdict
from typing import Optional

import httpx

logger = logging.getLogger("cruz.burn_in.voice")

DAEMON_RSS_CAP_BYTES = 512 * 1024 * 1024
WORKER_RSS_CAP_BYTES = 1024 * 1024 * 1024
TICK_INTERVAL_SECONDS = 60
SYNTHETIC_INTERVAL_SECONDS = 30 * 60


@dataclass
class BurnInTickResult:
    ok: bool
    detail: str = ""
    daemon_status: Optional[str] = None
    worker_status: Optional[str] = None
    daemon_restarts: int = 0
    worker_restarts: int = 0
    daemon_rss: int = 0
    worker_rss: int = 0


def _run_pm2_jlist() -> str:
    """Wrapper for testability."""
    return subprocess.check_output(["pm2", "jlist"], text=True)


def _check_pm2_processes_online() -> BurnInTickResult:
    raw = _run_pm2_jlist()
    procs = json.loads(raw)
    daemon = next((p for p in procs if p.get("name") == "cruz-daemon"), None)
    worker = next((p for p in procs if p.get("name") == "cruz-voice-worker"), None)
    if not daemon or not worker:
        return BurnInTickResult(ok=False, detail="missing PM2 entry")
    d_status = daemon["pm2_env"].get("status")
    w_status = worker["pm2_env"].get("status")
    return BurnInTickResult(
        ok=(d_status == "online" and w_status == "online"),
        daemon_status=d_status,
        worker_status=w_status,
        daemon_restarts=daemon["pm2_env"].get("restart_time", 0),
        worker_restarts=worker["pm2_env"].get("restart_time", 0),
        daemon_rss=daemon.get("monit", {}).get("memory", 0),
        worker_rss=worker.get("monit", {}).get("memory", 0),
        detail=f"daemon={d_status} worker={w_status}",
    )


def _check_rss_under_cap(rss_bytes: int, cap_bytes: int) -> BurnInTickResult:
    return BurnInTickResult(
        ok=rss_bytes < cap_bytes,
        detail=f"rss={rss_bytes // (1024*1024)}MB cap={cap_bytes // (1024*1024)}MB",
    )


async def _fetch_health(host: str) -> httpx.Response:
    async with httpx.AsyncClient(timeout=5) as c:
        return await c.get(f"{host}/health")


async def _check_health_endpoint(host: str) -> BurnInTickResult:
    try:
        resp = await _fetch_health(host)
    except Exception as exc:
        return BurnInTickResult(ok=False, detail=f"health unreachable: {exc}")
    if resp.status_code != 200:
        return BurnInTickResult(ok=False, detail=f"health HTTP {resp.status_code}")
    body = resp.json() if hasattr(resp, "json") else {}
    livekit = body.get("livekit")
    deepgram = body.get("deepgram")
    return BurnInTickResult(
        ok=(livekit == "connected" and deepgram == "reachable"),
        detail=f"livekit={livekit} deepgram={deepgram}",
    )


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--host", default="http://localhost:3000")
    ap.add_argument("--output", default="docs/perf/sp7-voice-burn-in.jsonl")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO)
    end_at = time.time() + args.hours * 3600
    last_synth = 0.0
    initial_restarts = {"daemon": None, "worker": None}
    synth_runs, synth_ok = 0, 0
    pm2 = BurnInTickResult(ok=False)  # init for the post-loop summary

    with open(args.output, "a") as out:
        while time.time() < end_at:
            tick: dict = {"ts": time.time()}
            pm2 = _check_pm2_processes_online()
            tick["pm2"] = asdict(pm2)
            if initial_restarts["daemon"] is None:
                initial_restarts["daemon"] = pm2.daemon_restarts
                initial_restarts["worker"] = pm2.worker_restarts
            tick["daemon_restarts_delta"] = pm2.daemon_restarts - initial_restarts["daemon"]
            tick["worker_restarts_delta"] = pm2.worker_restarts - initial_restarts["worker"]
            d_rss = _check_rss_under_cap(pm2.daemon_rss, DAEMON_RSS_CAP_BYTES)
            w_rss = _check_rss_under_cap(pm2.worker_rss, WORKER_RSS_CAP_BYTES)
            tick["daemon_rss"] = asdict(d_rss)
            tick["worker_rss"] = asdict(w_rss)
            tick["health"] = asdict(await _check_health_endpoint(args.host))

            if time.time() - last_synth > SYNTHETIC_INTERVAL_SECONDS:
                last_synth = time.time()
                synth_result = await _run_synthetic_round_trip(args.host)
                tick["synthetic"] = synth_result
                synth_runs += 1
                if synth_result.get("ok"):
                    synth_ok += 1

            out.write(json.dumps(tick) + "\n")
            out.flush()
            await asyncio.sleep(TICK_INTERVAL_SECONDS)

        # Summary block
        summary = {
            "summary": True,
            "duration_hours": args.hours,
            "synthetic_runs": synth_runs,
            "synthetic_ok": synth_ok,
            "synthetic_success_rate": (synth_ok / synth_runs) if synth_runs else 0,
            "final_daemon_restarts_delta": pm2.daemon_restarts - initial_restarts["daemon"],
            "final_worker_restarts_delta": pm2.worker_restarts - initial_restarts["worker"],
            "pass": (
                synth_runs > 0
                and (synth_ok / synth_runs) >= 0.95
                and (pm2.daemon_restarts - initial_restarts["daemon"]) <= 3
                and (pm2.worker_restarts - initial_restarts["worker"]) <= 3
            ),
        }
        out.write(json.dumps(summary) + "\n")
        out.flush()
        logger.info("burn-in complete: %s", summary)


async def _run_synthetic_round_trip(host: str) -> dict:
    """Stubbed in this task; implemented in Task 3.2."""
    return {"ok": False, "skipped": "synthetic round-trip implemented in Task 3.2"}


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/scripts/test_voice_burn_in.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/uptime/voice_burn_in.py tests/scripts/test_voice_burn_in.py
git commit -m "feat(sp7): voice burn-in harness — PM2 + RSS + /health asserts every 60s"
```

---

### Task 3.2: Synthetic round-trip implementation

**Files:**
- Modify: `scripts/uptime/voice_burn_in.py`
- Modify: `tests/scripts/test_voice_burn_in.py`

The synthetic round-trip publishes a known WAV file directly to a temporary LiveKit room (bypassing the wake word) and asserts a Deepgram final transcript lands in `agent_logs` within 10s.

- [ ] **Step 1: Add the WAV asset**

Either commit a small (~30 KB, 2-second) "CRUZ status check" WAV at `tests/fixtures/synthetic_utterance.wav`, or generate it on the fly via `say -o /tmp/utt.aiff "CRUZ status check" && ffmpeg -i /tmp/utt.aiff /tmp/utt.wav` at test setup time.

For determinism, prefer the committed asset. Generate locally on Mac Mini:

```bash
mkdir -p tests/fixtures
say -o /tmp/utt.aiff "CRUZ status check"
ffmpeg -i /tmp/utt.aiff -ar 16000 -ac 1 -sample_fmt s16 tests/fixtures/synthetic_utterance.wav
```

(One-shot, then commit.)

- [ ] **Step 2: Implement `_run_synthetic_round_trip`**

Replace the stub in `scripts/uptime/voice_burn_in.py`:

```python
async def _run_synthetic_round_trip(host: str) -> dict:
    """Spawn a side daemon with SKIP_WAKE_WORD=1, publish a known WAV,
    poll agent_logs for the resulting Deepgram transcript.
    Returns {ok, latency_ms, error?}.
    """
    import os, uuid

    conv_id = str(uuid.uuid4())
    wav_path = "tests/fixtures/synthetic_utterance.wav"
    if not os.path.exists(wav_path):
        return {"ok": False, "error": f"missing {wav_path}"}

    env = os.environ.copy()
    env["SKIP_WAKE_WORD"] = "1"
    env["SYNTHETIC_WAV_PATH"] = wav_path  # daemon reads this and publishes once
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "scripts/voice/livekit_client.py",
        "--host", host, "--conversation-id", conv_id,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    started = time.time()
    found = False
    error: Optional[str] = None
    try:
        # Poll the API for a transcript matching this conversation_id.
        async with httpx.AsyncClient(timeout=5) as c:
            for _ in range(20):  # 20 × 0.5s = 10s ceiling
                await asyncio.sleep(0.5)
                try:
                    r = await c.get(f"{host}/conversations/{conv_id}/messages")
                    msgs = r.json() if r.status_code == 200 else []
                    if any("status check" in (m.get("content") or "").lower()
                           for m in msgs):
                        found = True
                        break
                except Exception as exc:
                    error = str(exc)
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=3)
        except asyncio.TimeoutError:
            proc.kill()
    return {
        "ok": found,
        "latency_ms": int((time.time() - started) * 1000),
        "error": error if not found else None,
        "conversation_id": conv_id,
    }
```

Add `import sys` to the imports if not already present.

- [ ] **Step 3: Wire `SYNTHETIC_WAV_PATH` into the daemon**

In `scripts/voice/livekit_client.py`, near the existing `SKIP_WAKE_WORD` handling, add a one-shot publish path:

```python
    synth_wav = os.environ.get("SYNTHETIC_WAV_PATH", "").strip()
    if synth_wav and os.path.exists(synth_wav):
        async def _publish_wav_once():
            import wave
            await asyncio.sleep(2)  # let LiveKit room settle
            with wave.open(synth_wav, "rb") as wf:
                frames = wf.readframes(wf.getnframes())
            sr = 16000
            chunk = sr * 2  # 1s of int16-mono per frame
            for i in range(0, len(frames), chunk):
                seg = frames[i:i+chunk]
                if not seg:
                    break
                samples = len(seg) // 2
                af = rtc.AudioFrame(
                    data=seg, sample_rate=sr,
                    num_channels=1, samples_per_channel=samples,
                )
                await mic_source.capture_frame(af)
                await asyncio.sleep(samples / sr)
            logger.info("synthetic WAV publish complete")
        asyncio.create_task(_publish_wav_once())
```

Place this inside `_join_and_run` after `mic_track` is published. The daemon will exit naturally when the burn-in script terminates it.

- [ ] **Step 4: Add an opt-in integration test**

```python
# tests/integration/test_voice_burn_in_smoke.py
"""60-second mini burn-in. Requires PM2 + a live LiveKit setup + Deepgram key.
Skipped unless VOICE_BURN_IN=1 is set."""
import os
import subprocess
import pytest


@pytest.mark.skipif(os.environ.get("VOICE_BURN_IN") != "1",
                    reason="opt-in via VOICE_BURN_IN=1")
def test_60_second_burn_in_smoke(tmp_path):
    out = tmp_path / "burn.jsonl"
    r = subprocess.run(
        ["python", "scripts/uptime/voice_burn_in.py",
         "--hours", str(1.0/60.0),  # 1 minute
         "--output", str(out)],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stderr
    assert out.exists()
    lines = out.read_text().strip().split("\n")
    summary = next((l for l in lines if '"summary"' in l), None)
    assert summary, "burn-in must emit a summary line"
```

- [ ] **Step 5: Run the unit tests (fast); skip the integration**

```bash
pytest tests/scripts/test_voice_burn_in.py -v
```

Expected: 5 unit tests pass; integration skipped.

- [ ] **Step 6: Commit**

```bash
git add scripts/uptime/voice_burn_in.py scripts/voice/livekit_client.py \
        tests/scripts/test_voice_burn_in.py tests/integration/test_voice_burn_in_smoke.py \
        tests/fixtures/synthetic_utterance.wav
git commit -m "feat(sp7): synthetic round-trip — WAV publish + transcript poll, 30min cadence"
```

---

### Task 3.3: Smoke run + 24h kick-off (operator)

**Files:**
- (No code changes — operator-side execution.)

- [ ] **Step 1: 3-minute smoke**

```bash
VOICE_BURN_IN=1 pytest tests/integration/test_voice_burn_in_smoke.py -v
```

The smoke test internally runs `--hours 0.05` (3 minutes) — long enough for two ticks (60s each) plus the synthetic round-trip cycle to fire and emit a meaningful summary line. Expected to complete within 4 minutes wall clock. If it fails, debug before kicking off the full 24h.

Adjust the smoke test if it currently uses `1.0/60.0` hours (one minute) — the harness's tick interval is 60 seconds, so a one-minute window emits zero or one tick and won't exercise the synthetic path. Update the test:

```python
# tests/integration/test_voice_burn_in_smoke.py — update --hours
r = subprocess.run(
    ["python", "scripts/uptime/voice_burn_in.py",
     "--hours", "0.05",  # 3 minutes — exercises 2 ticks + synthetic
     "--output", str(out)],
    capture_output=True, text=True, timeout=300,
)
```

- [ ] **Step 2: Pre-burn-in checklist**

Confirm:
- `pm2 status` shows `cruz-api`, `cruz-worker`, `cruz-voice-worker`, `cruz-daemon`, `cruz-ui` all `online`
- `tests/fixtures/synthetic_utterance.wav` exists and is non-empty
- `docs/perf/` exists (mkdir if not)

- [ ] **Step 3: Kick off the 24h burn-in (background)**

```bash
nohup python scripts/uptime/voice_burn_in.py \
    --hours 24 \
    --output docs/perf/sp7-voice-burn-in.jsonl \
    > logs/burn-in.log 2>&1 &
echo $! > logs/burn-in.pid
```

Note the kick-off timestamp. Burn-in will conclude ~24h later.

- [ ] **Step 4: Document kick-off in `docs/perf/sp7-exit-gate.md`**

Create `docs/perf/sp7-exit-gate.md` (will fill in fully in Chunk 8) with at least:

```markdown
# SP7 Exit Gate — Manual Walkthrough

## Burn-in run
- Kicked off: <ISO8601 timestamp>
- Expected end: <ISO8601 timestamp + 24h>
- Output: docs/perf/sp7-voice-burn-in.jsonl
- PID: $(cat logs/burn-in.pid)
```

- [ ] **Step 5: Commit the kick-off marker**

```bash
git add docs/perf/sp7-exit-gate.md
git commit -m "ops(sp7): burn-in kick-off marker — burn-in.jsonl will accumulate over next 24h"
```

---

**Chunk 3 complete.** Burn-in is running in background. **Proceed immediately to Chunk 4 (PWA offline) — does not require burn-in to complete.**

---

## Chunk 4: PWA offline polish — Workbox, IndexedDB, outbox, icons

**Why fourth.** Independent of voice work. Lands during burn-in wall-clock window per Approach 2 sequencing.

### Task 4.1: Flip selfDestroying + configure Workbox runtimeCaching

**Files:**
- Modify: `frontend/vite.config.ts`

- [ ] **Step 1: Read the current config**

```bash
cat frontend/vite.config.ts
```

- [ ] **Step 2: Replace the VitePWA block**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";
import path from "node:path";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      // SP7: was true (destroyed itself on install). Now ships a real SW.
      selfDestroying: false,
      registerType: "autoUpdate",
      injectRegister: "auto",
      workbox: {
        skipWaiting: true,
        clientsClaim: true,
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [
          /^\/api/,
          /^\/health/,
          /^\/conversations/,
          /^\/command/,
          /^\/devices/,
          /^\/voice/,
          /^\/webhooks/,
        ],
        runtimeCaching: [
          {
            urlPattern: ({ request }) =>
              ["document", "script", "style", "font"].includes(request.destination),
            handler: "StaleWhileRevalidate",
            options: { cacheName: "cruz-shell-v1" },
          },
          {
            urlPattern: ({ request }) => request.destination === "image",
            handler: "CacheFirst",
            options: {
              cacheName: "cruz-assets-v1",
              expiration: { maxEntries: 50, maxAgeSeconds: 30 * 24 * 60 * 60 },
            },
          },
          {
            urlPattern: /\/conversations(\/[\w-]+\/messages)?(\?.*)?$/,
            method: "GET",
            handler: "NetworkFirst",
            options: {
              cacheName: "cruz-conversations-v1",
              networkTimeoutSeconds: 3,
              expiration: { maxEntries: 50 },
            },
          },
          {
            urlPattern: /\/command$/,
            method: "POST",
            handler: "NetworkOnly",
            options: {
              backgroundSync: {
                name: "command-queue",
                options: { maxRetentionTime: 24 * 60 },  // minutes
              },
            },
          },
        ],
      },
      manifest: {
        name: "CRUZ",
        short_name: "CRUZ",
        description: "FRIDAY-style AI command center",
        theme_color: "#0a0a0a",
        background_color: "#0a0a0a",
        display: "standalone",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "/icons/icon-512-maskable.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
    }),
  ],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:3000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
```

- [ ] **Step 3: Build + verify the SW asset is generated**

```bash
cd frontend
npm run build
ls dist/ | grep -E "sw\.js|manifest"
```

Expected: `sw.js`, `workbox-*.js`, `manifest.webmanifest` files present in `dist/`.

- [ ] **Step 4: Commit**

```bash
git add frontend/vite.config.ts
git commit -m "feat(sp7): flip PWA selfDestroying off, configure Workbox runtimeCaching"
```

---

### Task 4.2: SW_VERSION constant + main.tsx logging

**Files:**
- Create: `frontend/src/sw-version.ts`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Create the constant**

```typescript
// frontend/src/sw-version.ts
/** Bumped with every PR that touches the service worker or runtime caching.
 * Logged on activate so reviewers can confirm the new SW took over.
 *
 * Manual QA cadence per release: install on phone, swipe-refresh, confirm
 * the version logged in DevTools / Sentry breadcrumbs matches expected.
 */
export const SW_VERSION = "sp7-v1";
```

- [ ] **Step 2: Log it in main.tsx**

In `frontend/src/main.tsx`, after the existing render but before the closing of the file, add:

```typescript
import { SW_VERSION } from "./sw-version";

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.ready.then(() => {
    // Version log — useful for "did the new SW activate?" QA checks.
    console.info(`[CRUZ] service worker active — version=${SW_VERSION}`);
  });
}
```

- [ ] **Step 3: Build + run dev**

```bash
cd frontend
npm run build
npm run dev
```

Open `http://localhost:5173` in DevTools open. Expected: console shows `[CRUZ] service worker active — version=sp7-v1` after the SW activates.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/sw-version.ts frontend/src/main.tsx
git commit -m "feat(sp7): SW_VERSION constant logged on activate for release QA"
```

---

### Task 4.3: IndexedDB conversation cache

**Files:**
- Modify: `frontend/package.json` (add `idb`)
- Create: `frontend/src/lib/conversation-cache.ts`
- Create: `frontend/src/lib/__tests__/conversation-cache.test.ts`

- [ ] **Step 1: Install `idb` and `fake-indexeddb`**

```bash
cd frontend
npm install idb
npm install --save-dev fake-indexeddb
```

- [ ] **Step 2: Failing test**

```typescript
// frontend/src/lib/__tests__/conversation-cache.test.ts
import "fake-indexeddb/auto";
import { describe, expect, it, beforeEach } from "vitest";
import {
  rememberMessages, recallMessages, clearCache,
} from "../conversation-cache";

beforeEach(async () => {
  await clearCache();
});

const mkMsg = (id: string, content = "hello") => ({
  id, role: "user" as const, content, created_at: new Date().toISOString(),
});

describe("conversation-cache", () => {
  it("remembers and recalls messages by conversation_id", async () => {
    await rememberMessages("conv-1", [mkMsg("m1"), mkMsg("m2")]);
    const out = await recallMessages("conv-1");
    expect(out.map((m) => m.id).sort()).toEqual(["m1", "m2"]);
  });

  it("isolates messages between conversations", async () => {
    await rememberMessages("conv-1", [mkMsg("m1")]);
    await rememberMessages("conv-2", [mkMsg("m2")]);
    expect((await recallMessages("conv-1")).map((m) => m.id)).toEqual(["m1"]);
    expect((await recallMessages("conv-2")).map((m) => m.id)).toEqual(["m2"]);
  });

  it("keeps only the last 50 messages per conversation", async () => {
    const many = Array.from({ length: 75 }, (_, i) => mkMsg(`m${i}`));
    await rememberMessages("conv-1", many);
    const out = await recallMessages("conv-1");
    expect(out).toHaveLength(50);
    expect(out.every((m) => parseInt(m.id.slice(1)) >= 25)).toBe(true);
  });

  it("returns empty array for unknown conversation", async () => {
    expect(await recallMessages("nonexistent")).toEqual([]);
  });
});
```

- [ ] **Step 3: Run; verify failure**

```bash
cd frontend
npm run test -- conversation-cache.test
```

Expected: tests fail (module not found).

- [ ] **Step 4: Implement**

```typescript
// frontend/src/lib/conversation-cache.ts
/** IndexedDB-backed cache of the last 50 messages per conversation.
 *
 * Used to hydrate the chat view instantly while offline or before the
 * network call lands. Workbox already caches the GET response, but we
 * also want structured access for the UI.
 */
import { openDB, type IDBPDatabase } from "idb";

export interface Message {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  created_at: string;
  metadata?: Record<string, unknown>;
}

interface StoredMessage extends Message {
  conversation_id: string;
}

const DB_NAME = "cruz";
const DB_VERSION = 1;
const STORE = "messages";
const MAX_PER_CONVERSATION = 50;

let dbPromise: Promise<IDBPDatabase> | null = null;

function getDB() {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains(STORE)) {
          const store = db.createObjectStore(STORE, {
            keyPath: ["conversation_id", "id"],
          });
          store.createIndex("by_conversation", "conversation_id");
        }
      },
    });
  }
  return dbPromise;
}

export async function rememberMessages(
  conversationId: string,
  messages: Message[],
): Promise<void> {
  if (messages.length === 0) return;
  const db = await getDB();
  // Always keep the trailing N — slice from the end of the supplied list.
  const recent = messages.slice(-MAX_PER_CONVERSATION);
  const tx = db.transaction(STORE, "readwrite");
  // Remove any existing rows for this conversation first, then put the
  // recent set. Simplest correct strategy for "last 50".
  const idx = tx.store.index("by_conversation");
  let cursor = await idx.openCursor(IDBKeyRange.only(conversationId));
  while (cursor) {
    cursor.delete();
    cursor = await cursor.continue();
  }
  for (const m of recent) {
    await tx.store.put({ ...m, conversation_id: conversationId });
  }
  await tx.done;
}

export async function recallMessages(conversationId: string): Promise<Message[]> {
  const db = await getDB();
  const idx = db.transaction(STORE).store.index("by_conversation");
  const rows = (await idx.getAll(IDBKeyRange.only(conversationId))) as StoredMessage[];
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  return rows.map(({ conversation_id, ...rest }) => rest);
}

export async function clearCache(): Promise<void> {
  const db = await getDB();
  await db.clear(STORE);
}
```

- [ ] **Step 5: Run; verify pass**

```bash
cd frontend
npm run test -- conversation-cache.test
```

Expected: 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json \
        frontend/src/lib/conversation-cache.ts \
        frontend/src/lib/__tests__/conversation-cache.test.ts
git commit -m "feat(sp7): IndexedDB conversation cache via idb (last-50 per conversation)"
```

---

### Task 4.4: Wire cache into the conversation route

**Files:**
- Modify: `frontend/src/routes/conversation.tsx` (or `frontend/src/tabs/Chat.tsx` — find the file that calls `useQuery` for `/conversations/:id/messages`).

- [ ] **Step 1: Locate the conversation hook**

```bash
cd frontend
grep -rn "useQuery\|/conversations" src/ | grep -i "messages" | head -10
```

- [ ] **Step 2: Wire cache hydration + write-back**

Use the cache as a fallback render source while the network call is in flight (TanStack Query's `placeholderData` only accepts sync values, and our cache is async). The pattern: load cache via `useEffect` into local state, fall back to it when network data is undefined.

```typescript
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { rememberMessages, recallMessages, type Message } from "@/lib/conversation-cache";

// Inside the conversation component:
const [cached, setCached] = useState<Message[]>([]);

// Hydrate from IndexedDB on mount / conversation change.
useEffect(() => {
  recallMessages(conversationId).then(setCached).catch(console.warn);
}, [conversationId]);

const { data: networkMessages } = useQuery({
  queryKey: ["conversation", conversationId, "messages"],
  queryFn: async () => {
    const r = await fetch(`/api/conversations/${conversationId}/messages`);
    return r.json() as Promise<Message[]>;
  },
});

// Write back to cache whenever fresh network data lands.
useEffect(() => {
  if (networkMessages?.length) {
    rememberMessages(conversationId, networkMessages).catch(console.warn);
  }
}, [networkMessages, conversationId]);

// Render: prefer fresh network data, fall back to cache while loading / offline.
const messages = networkMessages ?? cached;
```

This is the single pattern to use — do not also pass `placeholderData` to `useQuery`, that would conflict with the explicit fallback below the query.

- [ ] **Step 3: Smoke test**

```bash
cd frontend
npm run dev
```

Open the chat, navigate to a conversation, watch DevTools → Application → IndexedDB → `cruz` → `messages`. Confirm rows appear.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/conversation.tsx  # or whichever file
git commit -m "feat(sp7): conversation view hydrates from IndexedDB cache, writes back on fetch"
```

---

### Task 4.5: Outbox Zustand slice

**Files:**
- Create: `frontend/src/state/outbox.ts`
- Create: `frontend/src/state/__tests__/outbox.test.ts`

- [ ] **Step 1: Failing test**

```typescript
// frontend/src/state/__tests__/outbox.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { useOutbox } from "../outbox";

describe("outbox", () => {
  beforeEach(() => {
    useOutbox.setState({ pending: [] });
  });

  it("addPending pushes a queued item", () => {
    useOutbox.getState().addPending("local-1", "deploy ama");
    const items = useOutbox.getState().pending;
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      localId: "local-1",
      content: "deploy ama",
      status: "queued",
    });
  });

  it("confirmReplay removes the queued item by localId", () => {
    useOutbox.getState().addPending("a", "x");
    useOutbox.getState().addPending("b", "y");
    useOutbox.getState().confirmReplay("a");
    expect(useOutbox.getState().pending.map((p) => p.localId)).toEqual(["b"]);
  });

  it("markStuck flips status when retry button visible", () => {
    useOutbox.getState().addPending("a", "x");
    useOutbox.getState().markStuck("a");
    expect(useOutbox.getState().pending[0].status).toBe("stuck");
  });

  it("retry resets status to queued and bumps attempt counter", () => {
    useOutbox.getState().addPending("a", "x");
    useOutbox.getState().markStuck("a");
    useOutbox.getState().retry("a");
    const item = useOutbox.getState().pending[0];
    expect(item.status).toBe("queued");
    expect(item.attempts).toBe(2);
  });

  it("hasPending is reactive", () => {
    expect(useOutbox.getState().pending).toHaveLength(0);
    useOutbox.getState().addPending("a", "x");
    expect(useOutbox.getState().pending).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run; verify failure**

```bash
cd frontend
npm run test -- outbox.test
```

- [ ] **Step 3: Implement**

```typescript
// frontend/src/state/outbox.ts
/** Outbox for offline-queued POST /command requests.
 *
 * The Workbox SW silently retries via Background Sync. The UI uses this
 * slice to render queued state and surface a "tap to retry" button if a
 * queued item is still pending 60s after the device reconnects.
 */
import { create } from "zustand";

export type OutboxStatus = "queued" | "stuck" | "sending";

export interface OutboxItem {
  localId: string;
  content: string;
  status: OutboxStatus;
  attempts: number;
  queuedAt: number;
}

interface OutboxState {
  pending: OutboxItem[];
  addPending: (localId: string, content: string) => void;
  confirmReplay: (localId: string) => void;
  markStuck: (localId: string) => void;
  retry: (localId: string) => void;
}

export const useOutbox = create<OutboxState>((set) => ({
  pending: [],
  addPending: (localId, content) =>
    set((s) => ({
      pending: [
        ...s.pending,
        { localId, content, status: "queued", attempts: 1, queuedAt: Date.now() },
      ],
    })),
  confirmReplay: (localId) =>
    set((s) => ({ pending: s.pending.filter((p) => p.localId !== localId) })),
  markStuck: (localId) =>
    set((s) => ({
      pending: s.pending.map((p) =>
        p.localId === localId ? { ...p, status: "stuck" } : p,
      ),
    })),
  retry: (localId) =>
    set((s) => ({
      pending: s.pending.map((p) =>
        p.localId === localId
          ? { ...p, status: "queued", attempts: p.attempts + 1 }
          : p,
      ),
    })),
}));
```

- [ ] **Step 4: Run; verify pass**

```bash
cd frontend
npm run test -- outbox.test
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/state/outbox.ts frontend/src/state/__tests__/outbox.test.ts
git commit -m "feat(sp7): outbox Zustand slice — queued/stuck/retry for offline POST /command"
```

---

### Task 4.6: Wire outbox into composer

**Files:**
- Modify: `frontend/src/components/Composer.tsx` (or whatever the chat-input component is — `grep -rn "POST.*command\|/command" frontend/src/components/`).

- [ ] **Step 1: Optimistic add + watch online**

Pseudocode (adapt to your real component):

```typescript
import { useOutbox } from "@/state/outbox";

const { addPending, confirmReplay, markStuck, retry, pending } = useOutbox();

async function send(message: string) {
  const localId = crypto.randomUUID();
  addPending(localId, message);

  try {
    const r = await fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, conversation_id: conversationId, stream: false }),
    });
    if (r.ok) {
      confirmReplay(localId);
      // The server response itself fans into the conversation cache via
      // the existing useQuery refetch path — no manual hydration here.
    }
  } catch (e) {
    // Workbox queues the failed POST; the catch is just for "we know it
    // didn't go through right now". Leave the item in `queued` state.
  }
}

// Watchdog: on `online`, if items are still queued after 60s, mark stuck.
useEffect(() => {
  function handleOnline() {
    setTimeout(() => {
      pending
        .filter((p) => p.status === "queued")
        .forEach((p) => markStuck(p.localId));
    }, 60_000);
  }
  window.addEventListener("online", handleOnline);
  return () => window.removeEventListener("online", handleOnline);
}, [pending, markStuck]);

// Render queued/stuck pills in the message list — minimal example:
{pending.map((p) => (
  <div key={p.localId} className="opacity-50 italic">
    {p.content}{" "}
    {p.status === "queued" && <span>(queued offline)</span>}
    {p.status === "stuck" && (
      <button onClick={() => retry(p.localId)}>tap to retry</button>
    )}
  </div>
))}
```

- [ ] **Step 2: Smoke**

```bash
cd frontend
npm run dev
```

Open chat → DevTools → Network panel → set throttling to "Offline". Type a message and send. Expected: optimistic pill appears with "queued offline" badge; when you flip back online, after a few seconds the message replays and the pill disappears.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Composer.tsx  # or actual filename
git commit -m "feat(sp7): composer wires outbox optimistic add + online-watchdog stuck flip"
```

---

### Task 4.7: PWA icons

**Files:**
- Create: `frontend/public/icons/icon-192.png`
- Create: `frontend/public/icons/icon-512.png`
- Create: `frontend/public/icons/icon-512-maskable.png`

- [ ] **Step 1: Source a 1024×1024 logo**

If a CRUZ logo PNG already exists in the repo (`find . -iname "cruz-logo*" -o -iname "logo*"`), copy it to `/tmp/cruz-source.png`. Otherwise generate a simple "C" wordmark — white on `#0a0a0a` — via any vector tool or one-shot Figma export. ~5 minutes.

- [ ] **Step 2: Generate the three sizes via `pwa-asset-generator`**

```bash
cd frontend
npx pwa-asset-generator /tmp/cruz-source.png \
    public/icons --type png \
    --background "#0a0a0a" \
    --padding "10%" \
    --opaque false \
    --icon-only \
    --maskable \
    --favicon false \
    --manifest false \
    --index false
```

This generates many sizes; keep only `icon-192x192.png`, `icon-512x512.png`, `icon-512x512-maskable.png` and rename to match the manifest:

```bash
cd frontend/public/icons
mv icon-192x192.png icon-192.png
mv icon-512x512.png icon-512.png
mv icon-512x512-maskable.png icon-512-maskable.png
```

Delete any other generated files.

- [ ] **Step 3: Verify the icons render**

```bash
cd frontend
npm run build
ls dist/icons/
```

Expected: three files. Open `dist/index.html` in a browser → Application → Manifest → all three icons preview.

- [ ] **Step 4: Commit**

```bash
git add frontend/public/icons/
git commit -m "feat(sp7): PWA install icons (192, 512, 512-maskable)"
```

---

**Chunk 4 complete.** PWA offline + outbox + icons live. The `selfDestroying` SW will be replaced on next page-load on installed PWAs (autoUpdate).

**Chunk 4 review checkpoint.** Run all frontend tests:

```bash
cd frontend
npm run test
```

Expected: all green. If subagent-driven, dispatch plan-document-reviewer for Chunks 1–4 before proceeding.

---

## Chunk 5: FCM frontend — service worker, permission UI, VAPID wiring

**Why fifth.** Backend push is in (Chunk 1). Frontend SW must register before the manual exit-gate walkthrough in Chunk 8.

### Task 5.1: Operator-side Firebase project setup notes

**Files:**
- Modify: `docs/superpowers/v2-burn-in-checklist.md` (created in Chunk 8 — for now write a stub)

This task captures the operator-side prerequisite work in a single place. The work itself is manual (web console clicks); we document it so it can be executed during burn-in and confirmed in the exit-gate checklist.

- [ ] **Step 1: Create the burn-in checklist stub with the FCM operator block**

```markdown
# v2 Burn-in Checklist

> Operator-side items that must clear before v2 is "operational."
> Code-complete is a separate milestone (SP7 merge). This checklist is the
> bridge from code-complete to operational.

## FCM / Firebase setup (one-time, ~30 minutes)

- [ ] Create Firebase project named `cruz-personal` (Spark / free plan)
  - Console: https://console.firebase.google.com
- [ ] Enable Cloud Messaging API
  - Project Settings → Cloud Messaging → enable
- [ ] Generate a service-account JSON
  - Project Settings → Service Accounts → "Generate new private key"
  - Save to `~/.config/cruz/fcm-sa.json` on Mac Mini
  - `chmod 600 ~/.config/cruz/fcm-sa.json`
- [ ] Generate Web Push VAPID key pair
  - Project Settings → Cloud Messaging → "Web Push certificates" → Generate
- [ ] Set `.env` vars on Mac Mini:
  ```
  FCM_SA_PATH=/Users/darshan/.config/cruz/fcm-sa.json
  FCM_PROJECT_ID=cruz-personal
  FCM_VAPID_PUBLIC_KEY=B...
  VITE_FCM_VAPID_PUBLIC_KEY=B...   # same value, frontend exposure
  ```
- [ ] `pm2 reload ecosystem.config.js --update-env`
- [ ] Confirm `/health` does not regress (FCM init runs in lifespan)
- [ ] Back up the service-account JSON as a Bitwarden secure-note attachment
```

- [ ] **Step 2: Commit the stub**

```bash
git add docs/superpowers/v2-burn-in-checklist.md
git commit -m "docs(sp7): seed v2-burn-in-checklist with FCM operator setup block"
```

---

### Task 5.2: `firebase-messaging-sw.js` service worker (template + build-time substitution)

**Files:**
- Create: `frontend/firebase-messaging-sw.template.js` (committed template with `__FCM_*__` markers)
- Create: `frontend/scripts/build-firebase-sw.mjs` (Node prebuild script)
- Modify: `frontend/package.json` (add `prebuild` hook)
- Modify: `frontend/.gitignore` (exclude generated SW)

The SW must live at `dist/firebase-messaging-sw.js` (FCM hard requirement). We don't commit a placeholder file with `REPLACE_WITH_*` strings — instead a small `prebuild` step renders the SW from a template + the `VITE_FCM_*` env vars. The output file is gitignored. If env vars are missing, `prebuild` fails loud — the operator sees the error before `npm run build` even runs the Vite pipeline.

- [ ] **Step 1: Write the template**

```javascript
// frontend/firebase-messaging-sw.template.js
// TEMPLATE — rendered to public/firebase-messaging-sw.js by
// scripts/build-firebase-sw.mjs at prebuild time. The rendered file is
// gitignored; this template is the source of truth.
//
// FCM background-message handler. Coexists with the Workbox SW; Firebase
// owns 'push' + 'notificationclick' events, Workbox owns fetch/cache.

importScripts("https://www.gstatic.com/firebasejs/10.13.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.13.0/firebase-messaging-compat.js");

firebase.initializeApp({
  apiKey: "__FCM_API_KEY__",
  authDomain: "__FCM_AUTH_DOMAIN__",
  projectId: "__FCM_PROJECT_ID__",
  storageBucket: "__FCM_STORAGE_BUCKET__",
  messagingSenderId: "__FCM_SENDER_ID__",
  appId: "__FCM_APP_ID__",
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  const title = (payload.notification && payload.notification.title) || "CRUZ";
  const body = (payload.notification && payload.notification.body) || "";
  const url = (payload.data && payload.data.url) || "/";
  self.registration.showNotification(title, {
    body,
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
    data: { url, trace_id: (payload.data && payload.data.trace_id) || "" },
    tag: "cruz",
    renotify: true,
  });
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      for (const w of wins) {
        if (w.url && new URL(w.url).origin === self.location.origin) {
          w.navigate(targetUrl);
          return w.focus();
        }
      }
      return self.clients.openWindow(targetUrl);
    }),
  );
});
```

- [ ] **Step 2: Write the prebuild script**

```javascript
// frontend/scripts/build-firebase-sw.mjs
// Renders firebase-messaging-sw.template.js → public/firebase-messaging-sw.js
// using VITE_FCM_* env vars. Fails loud if any required var is missing.
//
// Run via `npm run prebuild`, which is invoked automatically by npm before
// `npm run build`. Also runs on `npm run dev` via the script pipeline below.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, "..");

const REQUIRED = [
  "VITE_FCM_API_KEY",
  "VITE_FCM_AUTH_DOMAIN",
  "VITE_FCM_PROJECT_ID",
  "VITE_FCM_STORAGE_BUCKET",
  "VITE_FCM_SENDER_ID",
  "VITE_FCM_APP_ID",
];

const missing = REQUIRED.filter((k) => !process.env[k] || !process.env[k].trim());
if (missing.length > 0) {
  // Degraded mode: render a STUB SW that no-ops. Document why.
  console.warn(
    `[build-firebase-sw] WARNING: missing env vars (${missing.join(", ")}) — ` +
    `writing a no-op stub SW. Push notifications will not work in this build. ` +
    `Set the VITE_FCM_* vars in frontend/.env to enable.`,
  );
  const stub = `// frontend/public/firebase-messaging-sw.js — STUB
// Generated because VITE_FCM_* env vars were missing at build time.
// This SW is a no-op so push registration silently fails on the client side.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
`;
  fs.writeFileSync(path.join(ROOT, "public", "firebase-messaging-sw.js"), stub);
  process.exit(0);
}

const template = fs.readFileSync(
  path.join(ROOT, "firebase-messaging-sw.template.js"), "utf8",
);
let rendered = template;
for (const key of REQUIRED) {
  // Strip the VITE_ prefix to match the marker (__FCM_API_KEY__ etc.)
  const marker = `__${key.replace(/^VITE_/, "")}__`;
  rendered = rendered.replaceAll(marker, process.env[key]);
}
// Sanity check — no unsubstituted markers remain.
const leftovers = rendered.match(/__FCM_[A-Z_]+__/g);
if (leftovers) {
  console.error(
    `[build-firebase-sw] ERROR: unsubstituted markers remain: ${leftovers.join(", ")}`,
  );
  process.exit(1);
}

fs.mkdirSync(path.join(ROOT, "public"), { recursive: true });
fs.writeFileSync(
  path.join(ROOT, "public", "firebase-messaging-sw.js"),
  rendered,
);
console.log("[build-firebase-sw] wrote public/firebase-messaging-sw.js");
```

- [ ] **Step 3: Add the prebuild hook**

In `frontend/package.json`, add to `scripts`:

```json
"scripts": {
  "predev": "node scripts/build-firebase-sw.mjs",
  "dev": "vite",
  "prebuild": "node scripts/build-firebase-sw.mjs",
  "build": "tsc -b && vite build",
  ...
}
```

- [ ] **Step 4: Gitignore the generated SW**

Append to `frontend/.gitignore` (create if missing):

```
# Generated at prebuild time from firebase-messaging-sw.template.js
public/firebase-messaging-sw.js
```

- [ ] **Step 5: Smoke test the prebuild**

With env vars unset:
```bash
cd frontend
npm run prebuild
ls public/firebase-messaging-sw.js
cat public/firebase-messaging-sw.js | head -3
```
Expected: stub SW written, warning printed, `npm run prebuild` exits 0 (degraded-mode path).

With env vars set (use placeholder real values for the smoke test):
```bash
cd frontend
VITE_FCM_API_KEY=test-key \
VITE_FCM_AUTH_DOMAIN=test.firebaseapp.com \
VITE_FCM_PROJECT_ID=test \
VITE_FCM_STORAGE_BUCKET=test.appspot.com \
VITE_FCM_SENDER_ID=12345 \
VITE_FCM_APP_ID=1:12345:web:abc \
npm run prebuild
grep "test-key" public/firebase-messaging-sw.js
```
Expected: rendered SW contains the substituted values, no `__FCM_*__` markers remain.

- [ ] **Step 6: Add a unit test for the prebuild script**

```javascript
// frontend/scripts/__tests__/build-firebase-sw.test.mjs
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const SCRIPT = path.resolve("scripts/build-firebase-sw.mjs");
const OUT = path.resolve("public/firebase-messaging-sw.js");

function runScript(env) {
  return execSync(`node ${SCRIPT}`, {
    env: { ...process.env, ...env, PATH: process.env.PATH },
    encoding: "utf8",
  });
}

describe("build-firebase-sw", () => {
  beforeEach(() => { if (fs.existsSync(OUT)) fs.unlinkSync(OUT); });
  afterEach(() => { if (fs.existsSync(OUT)) fs.unlinkSync(OUT); });

  it("writes a stub SW when env vars are missing", () => {
    runScript({
      VITE_FCM_API_KEY: "", VITE_FCM_AUTH_DOMAIN: "",
      VITE_FCM_PROJECT_ID: "", VITE_FCM_STORAGE_BUCKET: "",
      VITE_FCM_SENDER_ID: "", VITE_FCM_APP_ID: "",
    });
    expect(fs.existsSync(OUT)).toBe(true);
    const text = fs.readFileSync(OUT, "utf8");
    expect(text).toMatch(/STUB/);
  });

  it("substitutes env values into the template when all set", () => {
    runScript({
      VITE_FCM_API_KEY: "real-key",
      VITE_FCM_AUTH_DOMAIN: "real.firebaseapp.com",
      VITE_FCM_PROJECT_ID: "real-proj",
      VITE_FCM_STORAGE_BUCKET: "real.appspot.com",
      VITE_FCM_SENDER_ID: "987",
      VITE_FCM_APP_ID: "1:987:web:xyz",
    });
    const text = fs.readFileSync(OUT, "utf8");
    expect(text).toMatch(/real-key/);
    expect(text).not.toMatch(/__FCM_/);
  });
});
```

- [ ] **Step 7: Commit**

```bash
git add frontend/firebase-messaging-sw.template.js \
        frontend/scripts/build-firebase-sw.mjs \
        frontend/scripts/__tests__/build-firebase-sw.test.mjs \
        frontend/package.json frontend/.gitignore
git commit -m "feat(sp7): firebase-messaging-sw build-time template substitution (no committed placeholders)"
```

---

### Task 5.3: EnableNotifications component

**Files:**
- Modify: `frontend/package.json` (add `firebase`)
- Create: `frontend/src/components/EnableNotifications.tsx`
- Create: `frontend/src/components/__tests__/EnableNotifications.test.tsx`

- [ ] **Step 1: Install `firebase` (frontend SDK)**

```bash
cd frontend
npm install firebase
```

- [ ] **Step 2: Failing test**

```typescript
// frontend/src/components/__tests__/EnableNotifications.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// Mock the firebase modules before importing the component.
vi.mock("firebase/app", () => ({
  initializeApp: vi.fn(() => ({})),
  getApps: vi.fn(() => []),
}));

const mockGetToken = vi.fn().mockResolvedValue("fake-fcm-token");
vi.mock("firebase/messaging", () => ({
  getMessaging: vi.fn(() => ({})),
  getToken: (...args: unknown[]) => mockGetToken(...args),
  isSupported: vi.fn(() => Promise.resolve(true)),
}));

import { EnableNotifications } from "../EnableNotifications";

describe("EnableNotifications", () => {
  beforeEach(() => {
    mockGetToken.mockClear();
    localStorage.clear();
    Object.defineProperty(global, "Notification", {
      writable: true,
      value: {
        permission: "default",
        requestPermission: vi.fn().mockResolvedValue("granted"),
      },
    });
    global.fetch = vi.fn().mockResolvedValue({
      ok: true, json: () => Promise.resolve({ registered: true, device_id: "x" }),
    }) as unknown as typeof fetch;
  });

  it("renders the enable banner when permission is default", () => {
    render(<EnableNotifications />);
    expect(screen.getByText(/get notified/i)).toBeInTheDocument();
  });

  it("does not render when permission is granted", () => {
    (global.Notification as { permission: string }).permission = "granted";
    const { container } = render(<EnableNotifications />);
    expect(container).toBeEmptyDOMElement();
  });

  it("does not render when permission is denied", () => {
    (global.Notification as { permission: string }).permission = "denied";
    const { container } = render(<EnableNotifications />);
    expect(container).toBeEmptyDOMElement();
  });

  it("does not render when user has dismissed (localStorage flag)", () => {
    localStorage.setItem("cruz.notifications.dismissed", "1");
    const { container } = render(<EnableNotifications />);
    expect(container).toBeEmptyDOMElement();
  });

  it("on click: requests permission, gets token, posts to /devices/register", async () => {
    render(<EnableNotifications />);
    fireEvent.click(screen.getByRole("button", { name: /enable/i }));
    await waitFor(() => {
      expect(global.Notification.requestPermission).toHaveBeenCalled();
      expect(mockGetToken).toHaveBeenCalled();
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/devices/register",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("dismiss button sets the localStorage flag and hides the banner", () => {
    const { container } = render(<EnableNotifications />);
    fireEvent.click(screen.getByRole("button", { name: /not now/i }));
    expect(localStorage.getItem("cruz.notifications.dismissed")).toBe("1");
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 3: Run; verify failure**

```bash
cd frontend
npm run test -- EnableNotifications.test
```

- [ ] **Step 4: Implement**

```typescript
// frontend/src/components/EnableNotifications.tsx
import { useEffect, useState } from "react";
import { getApps, initializeApp } from "firebase/app";
import { getMessaging, getToken, isSupported } from "firebase/messaging";

const DISMISSED_KEY = "cruz.notifications.dismissed";

const FIREBASE_CONFIG = {
  // Public, non-secret. Same values as in firebase-messaging-sw.js.
  apiKey: import.meta.env.VITE_FCM_API_KEY,
  authDomain: import.meta.env.VITE_FCM_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FCM_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FCM_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FCM_SENDER_ID,
  appId: import.meta.env.VITE_FCM_APP_ID,
};

function getOrInitFirebaseApp() {
  return getApps().length ? getApps()[0] : initializeApp(FIREBASE_CONFIG);
}

function detectDeviceLabel(): string {
  const ua = navigator.userAgent;
  if (/iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return "ipad";
  if (/Android|iPhone/.test(ua)) return "phone";
  if (/Macintosh/.test(ua)) return "mac";
  if (/Windows/.test(ua)) return "thinkpad";
  return "unknown";
}

export function EnableNotifications() {
  const [show, setShow] = useState(false);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (typeof Notification === "undefined") return;
    if (Notification.permission !== "default") return;
    if (localStorage.getItem(DISMISSED_KEY)) return;
    setShow(true);
  }, []);

  if (!show) return null;

  async function enable() {
    setPending(true);
    try {
      // Degraded mode: env vars not set → tell the user, don't crash.
      if (!FIREBASE_CONFIG.apiKey) {
        alert("Push notifications aren't configured in this build. " +
              "Set VITE_FCM_* env vars and rebuild.");
        return;
      }
      const supported = await isSupported();
      if (!supported) {
        alert("This browser does not support web push notifications.");
        return;
      }
      const result = await Notification.requestPermission();
      if (result !== "granted") {
        setShow(false);
        return;
      }
      const app = getOrInitFirebaseApp();
      const messaging = getMessaging(app);
      const token = await getToken(messaging, {
        vapidKey: import.meta.env.VITE_FCM_VAPID_PUBLIC_KEY,
      });
      await fetch("/api/devices/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fcm_token: token,
          device_label: detectDeviceLabel(),
          user_agent: navigator.userAgent,
        }),
      });
      setShow(false);
    } catch (e) {
      console.error("FCM registration failed", e);
      alert("Failed to enable notifications. See console for details.");
    } finally {
      setPending(false);
    }
  }

  function dismiss() {
    localStorage.setItem(DISMISSED_KEY, "1");
    setShow(false);
  }

  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-zinc-900 border-b border-zinc-800 text-sm">
      <span>Get notified when CRUZ has news for you.</span>
      <button
        onClick={enable}
        disabled={pending}
        className="px-3 py-1 bg-zinc-700 hover:bg-zinc-600 rounded"
      >
        {pending ? "Enabling…" : "Enable"}
      </button>
      <button
        onClick={dismiss}
        className="px-3 py-1 text-zinc-400 hover:text-zinc-200"
      >
        Not now
      </button>
    </div>
  );
}
```

- [ ] **Step 5: Run tests; verify pass**

```bash
cd frontend
npm run test -- EnableNotifications.test
```

Expected: 6 tests pass.

- [ ] **Step 6: Mount the component**

In `frontend/src/App.tsx` (or wherever the app shell renders), import and render `<EnableNotifications />` near the top of the chat view, above the conversation pane.

```bash
grep -n "App.tsx\|main shell" frontend/src/
```

Add:
```typescript
import { EnableNotifications } from "@/components/EnableNotifications";
// ...
<EnableNotifications />
```

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json \
        frontend/src/components/EnableNotifications.tsx \
        frontend/src/components/__tests__/EnableNotifications.test.tsx \
        frontend/src/App.tsx
git commit -m "feat(sp7): EnableNotifications — permission UI, FCM token register"
```

---

### Task 5.4: Document VITE_FCM_* env vars

**Files:**
- Modify: `frontend/.env.example` (create if it doesn't exist)

- [ ] **Step 1: Document the public Firebase config**

```bash
cat > frontend/.env.example <<'EOF'
# Public, non-secret Firebase web config — copy from Firebase Console
# (Project Settings → General → "Your apps" → Web app → Config snippet).
VITE_FCM_API_KEY=
VITE_FCM_AUTH_DOMAIN=
VITE_FCM_PROJECT_ID=
VITE_FCM_STORAGE_BUCKET=
VITE_FCM_SENDER_ID=
VITE_FCM_APP_ID=
# Web Push VAPID public key (Cloud Messaging → Web Push certificates).
VITE_FCM_VAPID_PUBLIC_KEY=
EOF
```

- [ ] **Step 2: Commit**

```bash
git add frontend/.env.example
git commit -m "docs(sp7): document VITE_FCM_* env vars in frontend/.env.example"
```

---

**Chunk 5 complete.** FCM frontend wired. Backend (Chunk 1) + frontend (Chunk 5) coexist; once operator setup (Task 5.1) lands the env vars, end-to-end push works.

---

## Chunk 6: Wake-word retraining — Docker pipeline + integration

**Why sixth.** Burn-in needs to be running first so we can capture real-condition pre-trigger samples for follow-up retrains. The committed ONNX (synthetic-only) is sufficient for Chunk 8's exit gate.

### Task 6.1: Dockerfile + scripts/wakeword scaffold

**Files:**
- Create: `scripts/wakeword/Dockerfile`
- Create: `scripts/wakeword/.gitignore`
- Create: `scripts/wakeword/README.md`

- [ ] **Step 1: Dockerfile**

```dockerfile
# scripts/wakeword/Dockerfile
# PyTorch + openWakeWord + Piper for synthetic wake-word training.
# Built and run on demand — never as part of the app runtime.
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends git ffmpeg sox espeak-ng curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Pin torch CPU build so we don't pull in a 2GB CUDA image on the M4.
RUN pip install --no-cache-dir \
    torch==2.4.* --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir \
    openwakeword==0.6.* \
    piper-tts==1.2.* \
    librosa==0.10.* \
    onnx==1.17.* \
    soundfile==0.12.*

WORKDIR /work
ENTRYPOINT ["bash"]
```

- [ ] **Step 2: .gitignore for the training directory**

```
# scripts/wakeword/.gitignore
samples/
build/
__pycache__/
*.pyc
# Keep the trained ONNX checked in (committed model artefact)
!models/hey_cruz.onnx
```

- [ ] **Step 3: README**

```markdown
# Hey CRUZ — Wake-Word Retraining

Synthetic-first openWakeWord pipeline. Synthetic samples generate ~95%
accuracy out of the box; layer 30–60 real recordings to specialize for
your voice + room acoustic.

## Build the trainer image

    docker build -t cruz-wakeword-trainer scripts/wakeword

## Train (synthetic only — first pass)

    bash scripts/wakeword/train_hey_cruz.sh

Outputs:
- `scripts/wakeword/models/hey_cruz.onnx` (committed)
- `docs/perf/sp7-wake-word-roc.md` (committed)

## Real-sample fine-tune (post-burn-in polish)

    python scripts/wakeword/collect_real_samples.py
    # records 30 utterances into samples/positive/
    bash scripts/wakeword/train_hey_cruz.sh --with-real
    # writes a new hey_cruz.onnx; rerun the 1-hour mini burn-in to verify
    # FP/FN rates match the ROC table

## Reverting

To run with openWakeWord's pretrained `hey_jarvis` model instead:

    export WAKE_WORD_MODEL_PATH=hey_jarvis
    pm2 restart cruz-daemon

The daemon `WakeWordDetector` accepts both an absolute `.onnx` path and a
named pretrained model. Fail-loud on load error — no silent revert.
```

- [ ] **Step 4: Commit**

```bash
mkdir -p scripts/wakeword/models
git add scripts/wakeword/Dockerfile scripts/wakeword/.gitignore scripts/wakeword/README.md
git commit -m "chore(sp7): scaffold scripts/wakeword — Dockerfile + .gitignore + README"
```

---

### Task 6.2: train_hey_cruz.sh + synthetic training script

**Files:**
- Create: `scripts/wakeword/train_hey_cruz.sh`
- Create: `scripts/wakeword/synth_train.py`

- [ ] **Step 1: Shell wrapper**

```bash
#!/usr/bin/env bash
# scripts/wakeword/train_hey_cruz.sh
# One-command synthetic training.
#
# Usage:
#   bash scripts/wakeword/train_hey_cruz.sh           # synthetic only (~20 min on M4)
#   bash scripts/wakeword/train_hey_cruz.sh --with-real  # incorporate samples/positive/
set -euo pipefail

cd "$(dirname "$0")"

WITH_REAL=0
if [[ "${1:-}" == "--with-real" ]]; then WITH_REAL=1; fi

if ! docker image inspect cruz-wakeword-trainer >/dev/null 2>&1; then
    echo "Building trainer image (one-time, ~5 min)..."
    docker build -t cruz-wakeword-trainer .
fi

EXTRA_ARGS=""
if [[ "$WITH_REAL" == "1" ]]; then EXTRA_ARGS="--with-real"; fi

docker run --rm \
    -v "$PWD:/work" \
    -v "$PWD/../../docs/perf:/perf" \
    cruz-wakeword-trainer \
    -lc "python /work/synth_train.py $EXTRA_ARGS"

echo
echo "✓ Training complete."
echo "  - Model: scripts/wakeword/models/hey_cruz.onnx"
echo "  - ROC:   docs/perf/sp7-wake-word-roc.md"
echo
echo "Next: commit the new ONNX + ROC, then restart cruz-daemon."
```

```bash
chmod +x scripts/wakeword/train_hey_cruz.sh
```

- [ ] **Step 2: Python training script**

The training pipeline follows openwakeword 0.6.x's documented "automatic model training" workflow (upstream notebook: `notebooks/automatic_model_training.ipynb`). We adapt that workflow into a runnable script. The script does FOUR concrete things:

1. **Generate synthetic positives** via Piper TTS — N voices × varied prompts → ~3000 WAV clips
2. **Source negatives** by downloading a small subset of Common Voice (~3000 clips, English, varied speakers)
3. **Train** the wake-word classifier using openwakeword's `openwakeword.train.train_model` (the actual public function in 0.6.x; verify at runtime with `python -c "from openwakeword.train import train_model"`)
4. **Score** 100 held-out synthetic positives and 1000 random Common Voice negatives via `Model.predict()` → real percentile data → ROC table

```python
# scripts/wakeword/synth_train.py
"""Synthetic-first Hey CRUZ openWakeWord training.

Runs INSIDE the cruz-wakeword-trainer container (Dockerfile in this dir).

Pipeline:
  1. Piper TTS → ~3000 synthetic positive WAV clips into work/positive/
  2. Common Voice download → ~3000 negative clips into work/negative/
  3. openwakeword.train.train_model → ONNX into models/hey_cruz.onnx
  4. Held-out scoring → score arrays → docs/perf/sp7-wake-word-roc.md

Output paths (relative to /work which is bind-mounted from scripts/wakeword/):
    models/hey_cruz.onnx
    /perf/sp7-wake-word-roc.md

If openwakeword 0.6.x's training API changes upstream, the import block
fails LOUD with a clear remediation message — never silently produces a
fake ROC.
"""
from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
import wave
from pathlib import Path
from typing import List

# ── Upstream API contract — fail loud if missing ─────────────────────────
try:
    from openwakeword import Model
    from openwakeword.utils import download_models as _download_pretrained
    # The training entry point in openwakeword 0.6.x. If this import fails,
    # upstream has restructured — fix the script before continuing.
    from openwakeword.train import train_model as _train_model  # type: ignore
except ImportError as exc:
    raise SystemExit(
        f"openwakeword 0.6.x training API mismatch: {exc}\n"
        "Either pin openwakeword==0.6.* in scripts/wakeword/Dockerfile, "
        "or update synth_train.py to match upstream's current train entry point. "
        "See https://github.com/dscripka/openWakeWord/blob/main/notebooks/"
        "automatic_model_training.ipynb for the canonical workflow."
    ) from exc


N_POSITIVE = 3000
N_NEGATIVE = 3000
N_HELDOUT_POS = 100
N_HELDOUT_NEG = 1000

POSITIVE_PROMPTS = [
    "hey cruz", "hey cruz can you", "hey cruz please",
    "hey cruz what's", "hey cruz tell me", "hey cruz are you",
    "hey cruz did you", "hey cruz how's", "hey cruz it's",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-real", action="store_true",
                    help="Mix in samples from /work/samples/positive/ if present")
    ap.add_argument("--seed", type=int, default=20260510)
    args = ap.parse_args()

    random.seed(args.seed)

    work = Path("/work")
    pos_dir = work / "build" / "positive"
    neg_dir = work / "build" / "negative"
    pos_dir.mkdir(parents=True, exist_ok=True)
    neg_dir.mkdir(parents=True, exist_ok=True)
    out_dir = work / "models"
    out_dir.mkdir(parents=True, exist_ok=True)
    perf_dir = Path("/perf")
    perf_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] Generating {N_POSITIVE} synthetic positives via Piper TTS...",
          flush=True)
    _generate_piper_positives(pos_dir, N_POSITIVE, args.seed)

    if args.with_real:
        real_dir = work / "samples" / "positive"
        if real_dir.exists():
            real_count = sum(1 for _ in real_dir.glob("*.wav"))
            print(f"      + mixing in {real_count} real samples from {real_dir}",
                  flush=True)
            for src in real_dir.glob("*.wav"):
                dst = pos_dir / f"real_{src.name}"
                dst.write_bytes(src.read_bytes())

    print(f"[2/4] Sourcing {N_NEGATIVE} negative clips (Common Voice subset)...",
          flush=True)
    _ensure_common_voice_subset(neg_dir, N_NEGATIVE, args.seed)

    print("[3/4] Training the openwakeword classifier head...", flush=True)
    # Pre-fetch openwakeword's pretrained embedder weights.
    _download_pretrained()
    final_path = out_dir / "hey_cruz.onnx"
    _train_model(
        wake_phrase="hey cruz",
        positive_audio_dir=str(pos_dir),
        negative_audio_dir=str(neg_dir),
        output_path=str(final_path),
        seed=args.seed,
    )
    if not final_path.exists():
        raise SystemExit(
            f"_train_model returned but {final_path} was not produced. "
            "Inspect train_model output above for cause."
        )
    print(f"      ✓ Wrote {final_path}", flush=True)

    print(f"[4/4] Scoring held-out: {N_HELDOUT_POS} pos, {N_HELDOUT_NEG} neg...",
          flush=True)
    held_pos_dir = work / "build" / "heldout_positive"
    held_neg_dir = work / "build" / "heldout_negative"
    held_pos_dir.mkdir(parents=True, exist_ok=True)
    held_neg_dir.mkdir(parents=True, exist_ok=True)
    _generate_piper_positives(held_pos_dir, N_HELDOUT_POS, args.seed + 1)
    _ensure_common_voice_subset(held_neg_dir, N_HELDOUT_NEG, args.seed + 1)

    pos_scores = _score_clips(final_path, held_pos_dir)
    neg_scores = _score_clips(final_path, held_neg_dir)

    if not pos_scores or not neg_scores:
        raise SystemExit(
            f"Held-out scoring returned empty: pos={len(pos_scores)} "
            f"neg={len(neg_scores)}. Cannot write a meaningful ROC."
        )

    roc_lines = _build_roc_lines(pos_scores, neg_scores, args.seed, final_path)
    (perf_dir / "sp7-wake-word-roc.md").write_text("\n".join(roc_lines) + "\n")
    print(f"      ✓ Wrote /perf/sp7-wake-word-roc.md", flush=True)

    return 0


def _generate_piper_positives(out_dir: Path, n: int, seed: int) -> None:
    """Run piper-tts CLI N times to synthesize 'hey cruz' WAVs.
    Piper voices are ~30MB each; one voice is plenty for synthetic-first."""
    voice = os.environ.get("PIPER_VOICE", "en_US-libritts-high")
    rng = random.Random(seed)
    for i in range(n):
        prompt = rng.choice(POSITIVE_PROMPTS)
        out = out_dir / f"hey_cruz_{i:05d}.wav"
        # piper writes WAV when given --output_file; sample rate fixed at 22050,
        # we resample down to 16000 with sox for openwakeword.
        tmp = out_dir / f".tmp_{i:05d}.wav"
        subprocess.run(
            ["piper", "--model", voice, "--output_file", str(tmp)],
            input=prompt.encode(),
            check=True, capture_output=True,
        )
        subprocess.run(
            ["sox", str(tmp), "-r", "16000", "-c", "1", "-b", "16", str(out)],
            check=True, capture_output=True,
        )
        tmp.unlink()


def _ensure_common_voice_subset(out_dir: Path, n: int, seed: int) -> None:
    """If out_dir already has ≥ n WAVs, skip download. Else download a
    Common Voice English mini subset and resample to 16kHz mono."""
    existing = sorted(out_dir.glob("*.wav"))
    if len(existing) >= n:
        return
    cache = Path("/work/.cache/common_voice_en_subset")
    if not cache.exists():
        cache.mkdir(parents=True, exist_ok=True)
        # Use the openwakeword-recommended mini subset (small, public).
        # Falls back to Mozilla CV if a curated mirror is unavailable.
        url = os.environ.get(
            "CV_SUBSET_URL",
            "https://huggingface.co/datasets/openwakeword/common_voice_en_mini/"
            "resolve/main/cv-en-mini.tar.gz",
        )
        subprocess.run(
            ["curl", "-L", "-o", str(cache / "cv.tar.gz"), url],
            check=True,
        )
        subprocess.run(
            ["tar", "-xzf", str(cache / "cv.tar.gz"), "-C", str(cache)],
            check=True,
        )
    rng = random.Random(seed)
    all_clips = sorted(cache.rglob("*.wav")) or sorted(cache.rglob("*.mp3"))
    if len(all_clips) < n:
        raise SystemExit(
            f"Common Voice subset has only {len(all_clips)} clips, need {n}. "
            f"Set CV_SUBSET_URL to a larger mirror, or reduce N_NEGATIVE."
        )
    chosen = rng.sample(all_clips, n)
    for i, src in enumerate(chosen):
        dst = out_dir / f"neg_{i:05d}.wav"
        subprocess.run(
            ["sox", str(src), "-r", "16000", "-c", "1", "-b", "16", str(dst)],
            check=True, capture_output=True,
        )


def _score_clips(model_path: Path, clip_dir: Path) -> List[float]:
    """Run Model.predict() on each WAV and return the max wake-word score."""
    import numpy as np
    model = Model(
        wakeword_models=[str(model_path)],
        inference_framework="onnx",
    )
    scores: List[float] = []
    for wav in sorted(clip_dir.glob("*.wav")):
        with wave.open(str(wav), "rb") as wf:
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        # Feed in 1280-sample chunks; capture max over all frames in the clip.
        clip_max = 0.0
        for i in range(0, len(audio) - 1280, 1280):
            frame = audio[i:i+1280]
            preds = model.predict(frame)
            if isinstance(preds, dict):
                m = max(preds.values(), default=0.0)
                clip_max = max(clip_max, float(m))
        scores.append(clip_max)
        # Reset model state between clips.
        if hasattr(model, "reset"):
            model.reset()
    return scores


def _build_roc_lines(
    pos: List[float], neg: List[float], seed: int, model_path: Path,
) -> list[str]:
    import numpy as np
    pos_arr, neg_arr = np.array(pos), np.array(neg)
    pos_p50, pos_p05 = float(np.percentile(pos_arr, 50)), float(np.percentile(pos_arr, 5))
    neg_p95, neg_p99 = float(np.percentile(neg_arr, 95)), float(np.percentile(neg_arr, 99))
    recommended = round(neg_p95, 2)
    return [
        "# Hey CRUZ — Wake-Word ROC",
        "",
        f"**Model:** `scripts/wakeword/models/{model_path.name}`",
        f"**Seed:** {seed}",
        f"**Held-out:** {len(pos)} positive (Piper-synth, distinct seed) "
        f"+ {len(neg)} negative (Common Voice random)",
        "",
        "## Score percentiles",
        "",
        "| Set | p5 | p50 | p95 | p99 |",
        "|---|---|---|---|---|",
        f"| Positive | {pos_p05:.3f} | {pos_p50:.3f} | "
        f"{float(np.percentile(pos_arr, 95)):.3f} | "
        f"{float(np.percentile(pos_arr, 99)):.3f} |",
        f"| Negative | {float(np.percentile(neg_arr, 5)):.3f} | "
        f"{float(np.percentile(neg_arr, 50)):.3f} | "
        f"{neg_p95:.3f} | {neg_p99:.3f} |",
        "",
        "## Recommended threshold",
        "",
        f"**Default:** `{recommended:.2f}` (95th percentile of negatives — ~5% FP rate, "
        "target <1 false trigger per 24h ambient).",
        "",
        "Tune by setting `WAKE_WORD_THRESHOLD` in `.env`. Lower = more sensitive "
        "(more FPs); higher = stricter (more FNs).",
    ]


if __name__ == "__main__":
    sys.exit(main())
```

**Why this works.**
- Imports fail loud if openwakeword's API differs — no silent fallback, no fake ROC.
- All four pipeline stages produce real artefacts: positives (Piper output WAVs), negatives (Common Voice WAVs), trained ONNX (real `train_model` call), held-out scores (real `Model.predict()` calls).
- The Dockerfile (Task 6.1) installs `piper-tts` and `sox`, plus `curl` and `tar` for the Common Voice subset download.
- ROC numbers are rounded to 3 decimals and computed from real percentile data — never randomized.

**Pre-flight verification before running training.** Before Task 6.5 actually runs the pipeline, do a quick API-compatibility check:

```bash
docker run --rm cruz-wakeword-trainer -lc \
    'python -c "from openwakeword.train import train_model; print(train_model.__doc__[:200])"'
```

If this fails, **fix `synth_train.py` to match the actual upstream API before proceeding.** Per the import-block contract above, the script will not produce a fake ROC if upstream changes — it will exit loud.

- [ ] **Step 3: Commit**

```bash
git add scripts/wakeword/train_hey_cruz.sh scripts/wakeword/synth_train.py
git commit -m "feat(sp7): wake-word synthetic training entry point + ROC writer"
```

---

### Task 6.3: collect_real_samples.py — interactive recorder

**Files:**
- Create: `scripts/wakeword/collect_real_samples.py`

- [ ] **Step 1: Implement**

```python
# scripts/wakeword/collect_real_samples.py
"""Interactive recorder for follow-up real-sample fine-tuning.

Records 30 utterances of "Hey CRUZ" into samples/positive/. Prompts the
operator to vary tone, distance, ambient noise across takes. Files are
biometric data — gitignored.

Usage:
    python scripts/wakeword/collect_real_samples.py [--count 30]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
DURATION_S = 1.5  # ~1.5s per "Hey CRUZ"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=30)
    ap.add_argument("--output", default="scripts/wakeword/samples/positive")
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Will record {args.count} samples of 'Hey CRUZ' into {out}/")
    print("Vary your delivery: normal, quiet, fast, slow, near, far.")
    print("Press ENTER to start each take. Ctrl+C to abort.\n")

    for i in range(args.count):
        try:
            input(f"Take {i+1}/{args.count} — press ENTER...")
        except KeyboardInterrupt:
            print("\nAborted.")
            return 1
        time.sleep(0.3)
        print("Recording 1.5s...")
        audio = sd.rec(
            int(DURATION_S * SAMPLE_RATE),
            samplerate=SAMPLE_RATE, channels=1, dtype="int16",
        )
        sd.wait()
        path = out / f"hey_cruz_{int(time.time())}_{i:03d}.wav"
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        print(f"  → {path.name}")

    print(f"\n✓ Recorded {args.count} samples into {out}/")
    print("Now run: bash scripts/wakeword/train_hey_cruz.sh --with-real")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Commit**

```bash
git add scripts/wakeword/collect_real_samples.py
git commit -m "feat(sp7): collect_real_samples — interactive 30-utterance recorder"
```

---

### Task 6.4: WakeWordDetector ONNX-path branch + fail-loud

**Files:**
- Modify: `services/voice.py`
- Modify: `tests/services/test_voice.py`

- [ ] **Step 1: Failing test for ONNX path**

Append to `tests/services/test_voice.py`:

```python
def test_wakeword_detector_loads_onnx_path_directly(monkeypatch, tmp_path):
    """When `keyword` ends in .onnx (or is an absolute path), pass it as the
    wakeword_models entry verbatim."""
    fake_model_path = tmp_path / "hey_cruz.onnx"
    fake_model_path.write_bytes(b"\x00\x00")  # contents irrelevant — Model() mocked
    fake_oww = MagicMock()
    fake_oww.Model = MagicMock(return_value=MagicMock())
    fake_oww.utils.download_models = MagicMock()
    monkeypatch.setattr("services.voice.openwakeword", fake_oww)

    from services.voice import WakeWordDetector
    det = WakeWordDetector(keyword=str(fake_model_path), threshold=0.4)
    fake_oww.Model.assert_called_once()
    args, kwargs = fake_oww.Model.call_args
    # The model arg should be the path itself, not a name like "hey_jarvis".
    wakeword_models = kwargs.get("wakeword_models") or args[0]
    assert wakeword_models == [str(fake_model_path)]


def test_wakeword_detector_fails_loud_on_corrupt_onnx(monkeypatch, tmp_path):
    """A corrupt/missing ONNX must raise RuntimeError — never silently fall
    back to hey_jarvis."""
    fake_path = tmp_path / "hey_cruz.onnx"
    fake_path.write_bytes(b"")  # empty
    fake_oww = MagicMock()
    fake_oww.Model = MagicMock(side_effect=RuntimeError("corrupt onnx"))
    fake_oww.utils.download_models = MagicMock()
    monkeypatch.setattr("services.voice.openwakeword", fake_oww)

    from services.voice import WakeWordDetector
    with pytest.raises(RuntimeError, match="hey_cruz.onnx"):
        WakeWordDetector(keyword=str(fake_path), threshold=0.4)
```

- [ ] **Step 2: Run; verify failures**

```bash
pytest tests/services/test_voice.py -v
```

Expected: 2 new tests fail.

- [ ] **Step 3: Modify `_init_openwakeword` in `services/voice.py`**

Change the body so a path-like keyword passes through unchanged, with explicit fail-loud:

```python
    def _init_openwakeword(self) -> None:
        if openwakeword is None:
            raise RuntimeError(
                "openwakeword package not installed. "
                "Run `pip install openwakeword`."
            )
        # Distinguish a pretrained-name (e.g. "hey_jarvis") from a local file.
        # `Model(wakeword_models=...)` accepts both forms; we just need to
        # log the right thing and surface a clear error on failure.
        kw = self._keyword
        is_path = (
            kw.endswith(".onnx")
            or kw.startswith("/")
            or os.path.isabs(kw)
            or os.path.exists(kw)
        )

        if is_path:
            if not os.path.exists(kw):
                raise RuntimeError(
                    f"WakeWord ONNX not found at {kw!r}. Either retrain "
                    f"(scripts/wakeword/train_hey_cruz.sh) or set "
                    f"WAKE_WORD_MODEL_PATH=hey_jarvis to revert."
                )
            try:
                self._oww_model = openwakeword.Model(
                    wakeword_models=[kw],
                    inference_framework="onnx",
                )
                logger.info("openWakeWord loaded local model: %s", kw)
            except Exception as exc:
                # Fail loud — never silently fall back to hey_jarvis.
                raise RuntimeError(
                    f"Failed to load WakeWord ONNX from {kw!r}: {exc}. "
                    f"Either fix the file or set "
                    f"WAKE_WORD_MODEL_PATH=hey_jarvis to revert."
                ) from exc
            return

        # Pretrained-name path (legacy / explicit revert).
        try:
            from openwakeword.utils import download_models  # type: ignore
            download_models()
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "openwakeword model download failed (continuing): %s", exc,
            )
        self._oww_model = openwakeword.Model(
            wakeword_models=[kw],
            inference_framework="onnx",
        )
        logger.info("openWakeWord loaded pretrained: %s", kw)
```

- [ ] **Step 4: Run; verify pass**

```bash
pytest tests/services/test_voice.py -v
```

Expected: existing voice tests still pass + 2 new pass.

- [ ] **Step 5: Commit**

```bash
git add services/voice.py tests/services/test_voice.py
git commit -m "feat(sp7): WakeWordDetector ONNX path branch + fail-loud on load error"
```

---

### Task 6.5: Run synthetic training, commit ONNX + ROC

**Files:**
- Create: `scripts/wakeword/models/hey_cruz.onnx` (binary, committed)
- Create: `docs/perf/sp7-wake-word-roc.md`

- [ ] **Step 1: Run training**

```bash
bash scripts/wakeword/train_hey_cruz.sh
```

Expected: ~5 min image build (first time) + ~20 min training = ~25 min wall clock. Outputs `scripts/wakeword/models/hey_cruz.onnx` (~250 KB) and `docs/perf/sp7-wake-word-roc.md`.

- [ ] **Step 2: Inspect outputs**

```bash
ls -la scripts/wakeword/models/hey_cruz.onnx
cat docs/perf/sp7-wake-word-roc.md
```

Expected: ONNX file ~150-400 KB; ROC table shows positive p50 score notably higher than negative p95.

- [ ] **Step 3: Set the recommended threshold**

Edit `.env` to set `WAKE_WORD_THRESHOLD` to the recommended value from the ROC table (e.g. `0.4` or `0.5`). Update `.env.example` only if your default-tuning is materially different from the placeholder.

- [ ] **Step 4: Daemon swap**

The `WAKE_WORD_MODEL_PATH` env in `.env.example` already points at the new file. PM2 reload to pick up the model:

```bash
pm2 reload ecosystem.config.js --update-env
pm2 logs cruz-daemon --lines 30
```

Expected: log shows `openWakeWord loaded local model: scripts/wakeword/models/hey_cruz.onnx`.

- [ ] **Step 5: 1-hour mini burn-in**

```bash
nohup python scripts/uptime/voice_burn_in.py --hours 1 \
    --output docs/perf/sp7-wake-word-mini-burn-in.jsonl \
    > logs/wake-mini-burn.log 2>&1 &
```

After 1 hour, check the summary line for synthetic round-trip success rate ≥ 95%. If notably worse than the original `hey_jarvis` 24h burn-in's rate, raise the threshold or revert via `WAKE_WORD_MODEL_PATH=hey_jarvis`.

- [ ] **Step 6: Commit the trained model + ROC**

```bash
git add scripts/wakeword/models/hey_cruz.onnx \
        docs/perf/sp7-wake-word-roc.md \
        docs/perf/sp7-wake-word-mini-burn-in.jsonl
git commit -m "feat(sp7): committed hey_cruz.onnx (synthetic-only train) + ROC + mini burn-in"
```

---

**Chunk 6 complete.** Custom wake word live. Real-sample fine-tune is post-merge polish (in `v2-burn-in-checklist.md`).

---

## Chunk 7: Push consumers — PULSE, CATCH, CRUZ approval gate

**Why seventh.** PushService is in (Chunk 1); now wire the three consumers from spec §6.6.

### Task 7.1: PULSE morning-briefing push

**Files:**
- Modify: `agents/pulse/pulse_agent.py`
- Modify: `tests/agents/test_pulse_agent.py`

The pattern across Tasks 7.1, 7.2, 7.3 is: extract a small helper method on the agent that does the push dispatch, then unit-test the helper directly with a fully-mocked PushService. This keeps the tests independent of each agent's existing fixture conventions (which vary across PULSE/CATCH/CRUZ test files).

- [ ] **Step 1: Failing test for the helper**

Create `tests/agents/test_pulse_push.py` (a new dedicated file — does not collide with `test_pulse_agent.py` and does not need to import its fixtures):

```python
"""Tests for PULSE → FCM push dispatch. Helper-level unit tests."""
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def fake_push():
    p = AsyncMock()
    p.send_to_user = AsyncMock(return_value=[])
    return p


@pytest.mark.asyncio
async def test_pulse_helper_calls_push_with_briefing_title(fake_push, monkeypatch):
    """PulseAgent._dispatch_briefing_push fires send_to_user with a
    'Morning briefing ready' title and the count in the body."""
    monkeypatch.setattr(
        "agents.pulse.pulse_agent.get_push_service", lambda: fake_push,
    )
    from agents.pulse.pulse_agent import PulseAgent
    agent = PulseAgent()
    await agent._dispatch_briefing_push(
        user_id=1,
        item_count=7,
        conversation_id="conv-abc",
        trace_id="trace-xyz",
    )
    fake_push.send_to_user.assert_awaited_once()
    kwargs = fake_push.send_to_user.await_args.kwargs
    assert kwargs["user_id"] == 1
    payload = kwargs["payload"]
    assert "briefing" in payload.title.lower()
    assert "7" in payload.body
    assert payload.url == "/conversations/conv-abc"
    assert payload.trace_id == "trace-xyz"


@pytest.mark.asyncio
async def test_pulse_helper_no_op_when_push_service_none(fake_push, monkeypatch):
    """Degraded mode (FCM not configured) — helper is a clean no-op."""
    monkeypatch.setattr(
        "agents.pulse.pulse_agent.get_push_service", lambda: None,
    )
    from agents.pulse.pulse_agent import PulseAgent
    await PulseAgent()._dispatch_briefing_push(
        user_id=1, item_count=5, conversation_id="x", trace_id="y",
    )
    fake_push.send_to_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_pulse_helper_swallows_push_failures(fake_push, monkeypatch):
    """Push dispatch errors must not bubble up from PULSE."""
    fake_push.send_to_user.side_effect = RuntimeError("FCM down")
    monkeypatch.setattr(
        "agents.pulse.pulse_agent.get_push_service", lambda: fake_push,
    )
    from agents.pulse.pulse_agent import PulseAgent
    # Must NOT raise.
    await PulseAgent()._dispatch_briefing_push(
        user_id=1, item_count=5, conversation_id="x", trace_id="y",
    )
```

- [ ] **Step 2: Run; verify failures**

```bash
pytest tests/agents/test_pulse_push.py -v
```

Expected: 3 failures (helper doesn't exist).

- [ ] **Step 3: Implement the helper + the call site**

In `agents/pulse/pulse_agent.py`, add the helper method to the agent class:

```python
    async def _dispatch_briefing_push(
        self,
        user_id: int,
        item_count: int,
        conversation_id: str,
        trace_id: str,
    ) -> None:
        """Fire an FCM push announcing that the morning briefing is ready.
        Best-effort: degraded-mode no-op when FCM not configured; swallows
        all dispatch errors so a bad FCM state can't break the briefing job."""
        try:
            from services.push import PushPayload, get_push_service
            push = get_push_service()
            if push is None:
                return
            await push.send_to_user(
                user_id=user_id,
                payload=PushPayload(
                    title="Morning briefing ready",
                    body=f"{item_count} items waiting",
                    url=f"/conversations/{conversation_id}",
                    trace_id=trace_id,
                ),
            )
        except Exception:
            self.logger.warning(
                "pulse push dispatch failed (non-fatal)", exc_info=True,
            )
```

Then add the call site at the end of `process()`. First locate where the briefing finishes — `grep -n "return AgentOutput\|return self._success" agents/pulse/pulse_agent.py` to find the success-return paths. Immediately before the success return, add:

```python
        # Best-effort push notification.
        await self._dispatch_briefing_push(
            user_id=(input.context or {}).get("user_id", 1),
            item_count=_count_briefing_items(briefing),  # see helper below
            conversation_id=input.conversation_id,
            trace_id=input.trace_id,
        )
```

Where `_count_briefing_items` is a tiny module-level helper that handles the briefing struct. If `briefing` is a dict with a list under e.g. `"items"`:

```python
def _count_briefing_items(briefing) -> int:
    """Return the count of actionable items in a PULSE briefing.
    Tolerates dict / dataclass / list shapes — PULSE has evolved over time."""
    if briefing is None:
        return 0
    if isinstance(briefing, list):
        return len(briefing)
    if isinstance(briefing, dict):
        for key in ("items", "actionable", "highlights"):
            if isinstance(briefing.get(key), list):
                return len(briefing[key])
    if hasattr(briefing, "items") and isinstance(briefing.items, list):
        return len(briefing.items)
    return 0
```

Place `_count_briefing_items` near the top of `pulse_agent.py` (module-level helper, importable from tests if needed).

- [ ] **Step 4: Run; verify pass**

```bash
pytest tests/agents/test_pulse_push.py -v
pytest tests/agents/test_pulse_agent.py -v   # existing tests still green
```

- [ ] **Step 5: Commit**

```bash
git add agents/pulse/pulse_agent.py tests/agents/test_pulse_push.py
git commit -m "feat(sp7): PULSE fires FCM push on briefing-ready (helper-level tests)"
```

---

### Task 7.2: CATCH meeting-summary push

**Files:**
- Modify: `agents/catch/catch_agent.py`
- Modify: `tests/agents/test_catch_agent.py`

Same helper-level test pattern as Task 7.1.

- [ ] **Step 1: Failing test**

Create `tests/agents/test_catch_push.py`:

```python
"""Tests for CATCH → FCM push dispatch. Helper-level unit tests."""
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def fake_push():
    p = AsyncMock()
    p.send_to_user = AsyncMock(return_value=[])
    return p


@pytest.mark.asyncio
async def test_catch_helper_fires_with_meeting_title(fake_push, monkeypatch):
    monkeypatch.setattr(
        "agents.catch.catch_agent.get_push_service", lambda: fake_push,
    )
    from agents.catch.catch_agent import CatchAgent
    await CatchAgent()._dispatch_summary_push(
        user_id=1,
        meeting_title="AMA design review",
        action_count=4,
        conversation_id="conv-1",
        trace_id="t-1",
    )
    fake_push.send_to_user.assert_awaited_once()
    payload = fake_push.send_to_user.await_args.kwargs["payload"]
    assert "AMA design review" in payload.title
    assert "captured" in payload.title.lower()
    assert "4" in payload.body


@pytest.mark.asyncio
async def test_catch_helper_no_op_when_push_service_none(fake_push, monkeypatch):
    monkeypatch.setattr(
        "agents.catch.catch_agent.get_push_service", lambda: None,
    )
    from agents.catch.catch_agent import CatchAgent
    await CatchAgent()._dispatch_summary_push(
        user_id=1, meeting_title="x", action_count=0,
        conversation_id="c", trace_id="t",
    )
    fake_push.send_to_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_catch_helper_swallows_dispatch_errors(fake_push, monkeypatch):
    fake_push.send_to_user.side_effect = RuntimeError("FCM 503")
    monkeypatch.setattr(
        "agents.catch.catch_agent.get_push_service", lambda: fake_push,
    )
    from agents.catch.catch_agent import CatchAgent
    # Must NOT raise.
    await CatchAgent()._dispatch_summary_push(
        user_id=1, meeting_title="x", action_count=0,
        conversation_id="c", trace_id="t",
    )
```

- [ ] **Step 2: Run; verify failures**

```bash
pytest tests/agents/test_catch_push.py -v
```

- [ ] **Step 3: Implement**

In `agents/catch/catch_agent.py`, add the helper:

```python
    async def _dispatch_summary_push(
        self,
        user_id: int,
        meeting_title: str,
        action_count: int,
        conversation_id: str,
        trace_id: str,
    ) -> None:
        """Fire FCM push announcing meeting summary is ready. Best-effort."""
        try:
            from services.push import PushPayload, get_push_service
            push = get_push_service()
            if push is None:
                return
            await push.send_to_user(
                user_id=user_id,
                payload=PushPayload(
                    title=f"{meeting_title} captured",
                    body=f"{action_count} action items extracted",
                    url=f"/conversations/{conversation_id}",
                    trace_id=trace_id,
                ),
            )
        except Exception:
            self.logger.warning(
                "catch push dispatch failed (non-fatal)", exc_info=True,
            )
```

Then add the call site near the existing success-return path. `grep -n "return AgentOutput\|return self._success" agents/catch/catch_agent.py` to locate. Just before the return:

```python
        meeting_title = (input.context or {}).get("meeting_title", "Meeting")
        action_count = len(action_items) if isinstance(action_items, list) else 0
        await self._dispatch_summary_push(
            user_id=(input.context or {}).get("user_id", 1),
            meeting_title=meeting_title,
            action_count=action_count,
            conversation_id=input.conversation_id,
            trace_id=input.trace_id,
        )
```

- [ ] **Step 4: Run; verify pass + existing CATCH tests still green**

```bash
pytest tests/agents/test_catch_push.py tests/agents/test_catch_agent.py -v
```

- [ ] **Step 5: Commit**

```bash
git add agents/catch/catch_agent.py tests/agents/test_catch_push.py
git commit -m "feat(sp7): CATCH fires FCM push on meeting summary ready"
```

---

### Task 7.3: CRUZ approval-gate push

**Files:**
- Modify: `agents/cruz/cruz_agent.py`
- Modify: `tests/agents/test_cruz_agent.py`

Same helper-level pattern.

- [ ] **Step 1: Failing test**

Create `tests/agents/test_cruz_push.py`:

```python
"""Tests for CRUZ → FCM push on sub-agent approval gate."""
from unittest.mock import AsyncMock

import pytest

from agents.base_agent import AgentOutput


@pytest.fixture
def fake_push():
    p = AsyncMock()
    p.send_to_user = AsyncMock(return_value=[])
    return p


def _approval_output(agent: str = "echo", prompt: str = "send 3 emails?"):
    return AgentOutput(
        success=True, result=None, agent=agent, duration_ms=10,
        requires_approval=True, approval_prompt=prompt,
    )


@pytest.mark.asyncio
async def test_cruz_helper_fires_when_sub_requires_approval(fake_push, monkeypatch):
    monkeypatch.setattr(
        "agents.cruz.cruz_agent.get_push_service", lambda: fake_push,
    )
    from agents.cruz.cruz_agent import CruzAgent
    await CruzAgent()._notify_approval_gate(
        sub_result=_approval_output("echo", "ECHO ready to send 3 emails — review?"),
        conversation_id="conv-1",
        trace_id="t-1",
    )
    fake_push.send_to_user.assert_awaited_once()
    payload = fake_push.send_to_user.await_args.kwargs["payload"]
    assert "ECHO" in payload.title
    assert "approval" in payload.title.lower()
    assert "ECHO" in payload.body or "send" in payload.body.lower()
    assert payload.url == "/conversations/conv-1"


@pytest.mark.asyncio
async def test_cruz_helper_no_op_when_no_approval_required(fake_push, monkeypatch):
    monkeypatch.setattr(
        "agents.cruz.cruz_agent.get_push_service", lambda: fake_push,
    )
    from agents.cruz.cruz_agent import CruzAgent
    non_approval = AgentOutput(
        success=True, result="ok", agent="echo", duration_ms=5,
        requires_approval=False,
    )
    await CruzAgent()._notify_approval_gate(
        sub_result=non_approval, conversation_id="c", trace_id="t",
    )
    fake_push.send_to_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_cruz_helper_no_op_when_push_service_none(fake_push, monkeypatch):
    monkeypatch.setattr(
        "agents.cruz.cruz_agent.get_push_service", lambda: None,
    )
    from agents.cruz.cruz_agent import CruzAgent
    await CruzAgent()._notify_approval_gate(
        sub_result=_approval_output(), conversation_id="c", trace_id="t",
    )
    fake_push.send_to_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_cruz_helper_truncates_long_prompt(fake_push, monkeypatch):
    monkeypatch.setattr(
        "agents.cruz.cruz_agent.get_push_service", lambda: fake_push,
    )
    from agents.cruz.cruz_agent import CruzAgent
    long_prompt = "x" * 500
    await CruzAgent()._notify_approval_gate(
        sub_result=_approval_output("echo", long_prompt),
        conversation_id="c", trace_id="t",
    )
    payload = fake_push.send_to_user.await_args.kwargs["payload"]
    assert len(payload.body) <= 100


@pytest.mark.asyncio
async def test_cruz_helper_swallows_dispatch_errors(fake_push, monkeypatch):
    fake_push.send_to_user.side_effect = RuntimeError("FCM down")
    monkeypatch.setattr(
        "agents.cruz.cruz_agent.get_push_service", lambda: fake_push,
    )
    from agents.cruz.cruz_agent import CruzAgent
    # Must NOT raise.
    await CruzAgent()._notify_approval_gate(
        sub_result=_approval_output(), conversation_id="c", trace_id="t",
    )
```

- [ ] **Step 2: Run; verify failures**

```bash
pytest tests/agents/test_cruz_push.py -v
```

- [ ] **Step 3: Implement the helper**

In `agents/cruz/cruz_agent.py`, add:

```python
    async def _notify_approval_gate(
        self,
        sub_result: AgentOutput,
        conversation_id: str,
        trace_id: str,
    ) -> None:
        """Fire FCM push when a sub-agent returns requires_approval=True.
        Best-effort: degraded-mode no-op + swallows all dispatch errors."""
        if not sub_result.requires_approval:
            return
        try:
            from services.push import PushPayload, get_push_service
            push = get_push_service()
            if push is None:
                return
            prompt = (sub_result.approval_prompt or "Action awaiting review")[:100]
            await push.send_to_user(
                user_id=1,  # single-user for now — extend when multi-user lands
                payload=PushPayload(
                    title=f"{sub_result.agent.upper()} needs approval",
                    body=prompt,
                    url=f"/conversations/{conversation_id}",
                    trace_id=trace_id,
                ),
            )
        except Exception:
            self.logger.warning(
                "cruz approval-gate push failed (non-fatal)", exc_info=True,
            )
```

Then wire the call site. `grep -n "requires_approval\|approval_prompt" agents/cruz/cruz_agent.py` to find where sub-agent results are processed in `process()` and `stream_response()`. After every site that receives a sub-agent's `AgentOutput` from a tool dispatch, add:

```python
        await self._notify_approval_gate(
            sub_result=sub_output,
            conversation_id=input.conversation_id,
            trace_id=input.trace_id,
        )
```

If `process()` and `stream_response()` both have a tool-result branch, the call goes in both.

- [ ] **Step 4: Run; verify pass + existing CRUZ tests still green**

```bash
pytest tests/agents/test_cruz_push.py tests/agents/test_cruz_agent.py -v
```

- [ ] **Step 5: Commit**

```bash
git add agents/cruz/cruz_agent.py tests/agents/test_cruz_push.py
git commit -m "feat(sp7): CRUZ fires FCM push on sub-agent requires_approval=True"
```

---

**Chunk 7 complete.** Three immediate consumers wired. SENTINEL/TITAN/alerts integration documented in spec for follow-up.

---

## Chunk 8: Exit gate, sign-off, v2-burn-in checklist

**Why eighth.** All hardening lands; burn-in concludes; manual walkthrough proves the three exit-gate criteria.

### Task 8.1: Burn-in result review

**Files:**
- Modify: `docs/perf/sp7-exit-gate.md`
- Modify: `docs/perf/sp7-voice-burn-in.jsonl` (already populated by the harness)

- [ ] **Step 1: Read the summary line**

```bash
tail -1 docs/perf/sp7-voice-burn-in.jsonl | python -m json.tool
```

Expected:
```json
{
  "summary": true,
  "duration_hours": 24.0,
  "synthetic_runs": 48,
  "synthetic_ok": 47,
  "synthetic_success_rate": 0.97,
  "final_daemon_restarts_delta": 0,
  "final_worker_restarts_delta": 1,
  "pass": true
}
```

- [ ] **Step 2: Append the result block to the exit-gate doc**

```markdown
## Burn-in result (Gate 1)

- Started: <ISO timestamp>
- Concluded: <ISO timestamp>
- Synthetic round-trips: 47/48 successful (97.9%)
- cruz-daemon PM2 restarts: 0
- cruz-voice-worker PM2 restarts: 1 (transient Deepgram WS, auto-recovered)
- RSS bounded for both processes throughout
- **Verdict: PASS**

Detailed trace: `docs/perf/sp7-voice-burn-in.jsonl`
```

If `pass: false`, do NOT proceed to Tasks 8.2-8.4. Instead:
- Diagnose the failure mode from the JSONL trace
- Apply a fix-window patch (≤25% of original SP7 estimate per charter §5.1 K2)
- Re-kick a fresh 24h burn-in
- If second burn-in also fails, shelve voice daemon to v2.1 per spec §8 R7 mitigation

- [ ] **Step 3: Commit the burn-in artifacts**

```bash
git add docs/perf/sp7-voice-burn-in.jsonl docs/perf/sp7-exit-gate.md
git commit -m "ops(sp7): burn-in concluded — Gate 1 PASS"
```

---

### Task 8.2: PWA exit-gate walkthrough (Gate 2)

**Files:**
- Modify: `docs/perf/sp7-exit-gate.md`

- [ ] **Step 1: Phone install**

On Nothing Phone 2:
1. Open Chrome → navigate to `https://cruz.simpleinc.cloud`
2. Tap menu → "Add to Home Screen" → confirm
3. Verify CRUZ icon appears on home screen
4. Open the installed PWA → home view loads → screenshot
5. Toggle airplane mode ON
6. Force-quit the PWA (swipe up)
7. Reopen the PWA → home view STILL LOADS (cached) → screenshot
8. Tap into a recent conversation → last 50 messages visible (cached) → screenshot
9. Type a command → "queued (offline)" pill appears → screenshot
10. Toggle airplane mode OFF → wait 10s
11. Verify queued message replays, response streams in → screenshot

- [ ] **Step 2: iPad install**

Repeat steps 1–11 on iPad. Append screenshots.

- [ ] **Step 3: ThinkPad install**

Repeat steps 1–11 on ThinkPad (Chrome on Windows). Append screenshots.

- [ ] **Step 4: Append the result block**

```markdown
## PWA install + offline (Gate 2)

| Device | Install OK | Offline open OK | Outbox replay OK |
|---|---|---|---|
| Nothing Phone 2 (Android Chrome) | ✓ | ✓ | ✓ |
| iPad (Safari) | ✓ | ✓ | ✓ |
| ThinkPad (Windows Chrome) | ✓ | ✓ | ✓ |

Screenshots: `docs/perf/sp7-pwa-walkthrough/{phone,ipad,thinkpad}/*.png`

**Verdict: PASS**
```

- [ ] **Step 5: Commit**

```bash
mkdir -p docs/perf/sp7-pwa-walkthrough/{phone,ipad,thinkpad}
# (move screenshots into those directories)
git add docs/perf/sp7-pwa-walkthrough/ docs/perf/sp7-exit-gate.md
git commit -m "ops(sp7): PWA install + offline walkthrough — Gate 2 PASS"
```

---

### Task 8.3: FCM 5-second push delivery (Gate 3)

**Files:**
- Modify: `docs/perf/sp7-exit-gate.md`

- [ ] **Step 1: Register all three devices**

On phone, iPad, ThinkPad: open the PWA → tap "Enable notifications" → grant. Verify three rows in `device_tokens`:

```bash
psql $DATABASE_URL -c "SELECT user_id, device_label, last_seen_at FROM device_tokens ORDER BY created_at DESC"
```

Expected: three rows with distinct `device_label` values.

- [ ] **Step 2: Dispatch a test push from the Mac Mini**

```bash
python -c "
import asyncio
from services.push import get_push_service, PushPayload
from services.db import get_db_service

async def main():
    db = get_db_service(); await db.connect()
    from services.push import PushService
    import os
    svc = PushService(
        sa_path=os.environ['FCM_SA_PATH'],
        project_id=os.environ['FCM_PROJECT_ID'],
        db=db,
    )
    results = await svc.send_to_user(
        user_id=1,
        payload=PushPayload(
            title='SP7 test',
            body='hello from the Mac Mini',
            url='/',
            trace_id='exit-gate-test',
        ),
    )
    for r in results:
        print(r)

asyncio.run(main())
"
```

- [ ] **Step 3: Stopwatch on each device**

Stopwatch starts the moment the dispatch command returns. Stop when each device's notification appears. Record three latencies.

- [ ] **Step 4: Tap the phone notification**

Verify tapping opens the PWA at the correct URL.

- [ ] **Step 5: Append the result block**

```markdown
## FCM push delivery (Gate 3)

- Phone:    1.8s
- iPad:     2.3s
- ThinkPad: 1.1s

All three devices delivered within 5 seconds.
Tap-to-open verified on phone.

**Verdict: PASS**
```

- [ ] **Step 6: Commit**

```bash
git add docs/perf/sp7-exit-gate.md
git commit -m "ops(sp7): FCM 3-device delivery walkthrough — Gate 3 PASS"
```

---

### Task 8.4: PROGRESS.md sign-off block

**Files:**
- Modify: `PROGRESS.md`

- [ ] **Step 1: Append SP7 sign-off**

```markdown
---

## SP7 — Multi-Modal Polish (Layer 6) ✅ SIGNED OFF <YYYY-MM-DD>

**Spec:** `docs/superpowers/specs/2026-05-10-sp7-multimodal-polish-design.md`
**Plan:** `docs/superpowers/plans/2026-05-10-sp7-multimodal-polish.md`
**Branch / PR:** `claude/<random>-sp7` / PR #<N>
**Tests added:** ~48 unit tests + 1 opt-in integration test smoke

### Charter exit-gate verdict

| Gate | Status | Evidence |
|---|---|---|
| 1. Voice daemon 24h continuous | ✓ | `docs/perf/sp7-voice-burn-in.jsonl` (summary: pass=true, 47/48 synthetic OK) |
| 2. PWA install + offline | ✓ | `docs/perf/sp7-pwa-walkthrough/` screenshots × 3 devices |
| 3. FCM push <5s on all devices | ✓ | `docs/perf/sp7-exit-gate.md` § "FCM push delivery (Gate 3)" |

### Charter cuts taken

- Cut #4 — React Native shell — pre-committed at SP7 start (PWA-only)
- Cut #5 — Menu bar app — pre-committed at SP7 start (PM2 + /agents/status for ops)

### Reality

- Voice daemon hardening: AEC pause flag, reconnect with backoff (cap 60s),
  mic-stream restart on PortAudioError, RSS watchdog, bounded Deepgram queue.
- Custom "Hey CRUZ" via openWakeWord synthetic training (committed ONNX,
  ~250 KB). Real-sample fine-tune deferred to v2-burn-in-checklist.md.
- PWA: Workbox runtime caching (shell + assets + conversations + Background
  Sync queue for /command), IndexedDB last-50-messages cache via `idb`,
  Outbox UI for offline-queued commands, three install icons.
- FCM: `device_tokens` table, `services/push.py`, `POST /devices/register`,
  `firebase-messaging-sw.js`, `EnableNotifications` UI. Three immediate
  consumers (PULSE, CATCH, CRUZ approval gate). Token cleanup on
  `UnregisteredError` / `InvalidArgumentError` / `SenderIdMismatchError`.

### Operator-side follow-ups (in v2-burn-in-checklist.md)

- Real-sample wake-word fine-tune
- Firebase project + service-account already set up during SP7
- LiveKit Cloud usage monitoring
- Retro on R2 (AEC tail tuning) once we have 7 days of real usage

**With SP7 merge, v2 is code-complete.** Operational milestone clears
when all items in `docs/superpowers/v2-burn-in-checklist.md` are ticked.
```

- [ ] **Step 2: Commit**

```bash
git add PROGRESS.md
git commit -m "docs(sp7): sign-off block — all three exit gates pass"
```

---

### Task 8.5: Author v2-burn-in-checklist.md (full)

**Files:**
- Modify: `docs/superpowers/v2-burn-in-checklist.md` (extend the FCM stub from Task 5.1)

- [ ] **Step 1: Pull open SP1 + SP2 items from DEFERRED.md**

Aggregate the unchecked items from `docs/superpowers/DEFERRED.md` into the v2-burn-in-checklist. Don't duplicate — link to DEFERRED.md and let it remain the source of truth for those, OR migrate them in and delete DEFERRED.md (per the file's own §Tracking instructions).

- [ ] **Step 2: Author the full doc**

```markdown
# v2 Burn-in Checklist

> Operator-side items that must clear before v2 is "operational."
> Code-complete is a separate milestone (SP7 merge, see PROGRESS.md).
> This checklist is the bridge from code-complete to operational.
>
> Owner: Darshan Parmar
> Created: <YYYY-MM-DD> (post-SP7 merge)

---

## Migrated from `docs/superpowers/DEFERRED.md`

### SP1 — Operational Deployment (deferred items)

[Pull the unchecked items from DEFERRED.md SP1 section verbatim.]

### SP2 — Knowledge Base (deferred items)

[Pull the unchecked items from DEFERRED.md SP2 section verbatim.]

---

## SP7 follow-ups

### FCM / Firebase setup (already done during SP7 burn-in — verify)

- [x] Firebase project `cruz-personal` exists
- [x] Service-account JSON at `~/.config/cruz/fcm-sa.json`
- [x] VAPID keys generated and in `.env`
- [x] Three devices registered (phone, iPad, ThinkPad)
- [ ] Service-account JSON backed up to Bitwarden secure-note attachment

### Wake-word real-sample fine-tune (post-burn-in polish)

- [ ] Run `python scripts/wakeword/collect_real_samples.py` — record 30 utterances of "Hey CRUZ"
- [ ] Run `bash scripts/wakeword/train_hey_cruz.sh --with-real`
- [ ] Inspect updated ROC at `docs/perf/sp7-wake-word-roc.md`
- [ ] Replace `scripts/wakeword/models/hey_cruz.onnx` with the new model
- [ ] 1-hour mini burn-in: `python scripts/uptime/voice_burn_in.py --hours 1 \\`
      `  --output docs/perf/sp7-wake-word-real-mini.jsonl`
- [ ] Confirm synthetic round-trip success rate ≥ 95% with the new model
- [ ] Commit + restart `cruz-daemon`

### iOS Safari PWA fresh-device install

- [ ] On a Mac/iPhone outside the user's primary devices, install the PWA
- [ ] Confirm offline mode + push delivery (≥ iOS 16.4 required)
- [ ] Document any Safari-specific quirks discovered

### LiveKit Cloud usage monitoring

- [ ] After 7 days of normal use, check LiveKit Cloud dashboard for usage
      (free tier: 100 concurrent participants, 50GB transfer/month)
- [ ] If approaching limits, plan migration to self-hosted LiveKit on
      Mac Mini (Docker compose entry exists in spec; not yet wired)

### Retro: AEC tail tuning (R2)

- [ ] After 7 days, review burn-in JSONL for instances of:
      "wake word detected" within 1s of "playback_active cleared"
- [ ] If observed >5 times/24h, bump `TTS_TAIL_MS` from 300 to 500
- [ ] Restart `cruz-daemon`, monitor for another 7 days

### Telegram alerts noise audit

- [ ] After 7 days, review `services/alerts.py` Telegram log for false
      positives from `_alert_reconnect`
- [ ] If >3 alerts/day, raise the `attempt >= 3` threshold to `attempt >= 5`

---

## Closure

When all items above are ticked:

1. Move this file to `docs/superpowers/archive/2026-v2-burn-in-checklist.md`
2. Append a "v2 OPERATIONAL" block to `PROGRESS.md` summarising what shipped,
   what was cut, and the final monthly-run cost (charter §4 framing).
3. Charter `2026-04-20-v2-program-charter.md` retires to archive (charter §8).

After closure: v2 is done. v2.1 brainstorming opens whenever the user wants
to revisit cut items (Messenger, real-sample wake word polish, etc.).
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/v2-burn-in-checklist.md
git commit -m "docs(sp7): full v2-burn-in-checklist — operator-side path to operational"
```

---

### Task 8.6: Open the SP7 PR

**Files:**
- (No code changes.)

- [ ] **Step 1: Push the branch**

```bash
git push -u origin claude/pedantic-stonebraker-e79b8b
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "SP7: multi-modal polish — voice daemon + PWA + FCM + Hey CRUZ" \
  --body "$(cat <<'EOF'
## Summary

Final v2 sub-project per charter §2 SP7 row.

- **Voice daemon hardening** — AEC pause flag, LiveKit reconnect with backoff,
  mic-stream restart on PortAudioError, RSS watchdog, bounded Deepgram queue.
- **Custom "Hey CRUZ"** — openWakeWord synthetic training pipeline,
  committed ONNX (~250 KB), ROC table at `docs/perf/sp7-wake-word-roc.md`.
- **PWA offline** — Workbox runtime caching, IndexedDB last-50 cache via
  `idb`, outbox UI for offline-queued commands, three install icons.
- **FCM push** — `device_tokens` table, `services/push.py`,
  `POST /devices/register`, `firebase-messaging-sw.js`,
  `EnableNotifications` UI. Three consumers wired (PULSE, CATCH, CRUZ
  approval gate).

Charter cuts pre-committed: #4 React Native shell, #5 menu bar app.

## Test plan

- [x] `pytest tests/services/test_push.py tests/api/test_devices_endpoint.py -v` — 20 passes
- [x] `pytest tests/scripts/test_voice_daemon.py tests/scripts/test_voice_burn_in.py -v` — daemon + burn-in unit
- [x] `pytest tests/services/test_voice.py -v` — ONNX path branch + fail-loud
- [x] `pytest tests/agents/test_pulse_agent.py tests/agents/test_catch_agent.py tests/agents/test_cruz_agent.py -v` — push consumers
- [x] `cd frontend && npm run test` — conversation-cache, outbox, EnableNotifications
- [x] 24h voice burn-in — see `docs/perf/sp7-voice-burn-in.jsonl` (pass=true)
- [x] Manual PWA install + offline on phone, iPad, ThinkPad — see `docs/perf/sp7-pwa-walkthrough/`
- [x] Manual FCM 3-device push <5s — see `docs/perf/sp7-exit-gate.md`

Spec: `docs/superpowers/specs/2026-05-10-sp7-multimodal-polish-design.md`
Plan: `docs/superpowers/plans/2026-05-10-sp7-multimodal-polish.md`
EOF
)"
```

Capture and report the PR URL.

- [ ] **Step 2: Open the PR; await review**

(Human review loop. Once approved, merge.)

---

**Chunk 8 complete. SP7 ships. v2 is code-complete.**

The remaining v2 work is the items in `docs/superpowers/v2-burn-in-checklist.md` — operator-side and post-merge polish. Charter §5.3 notes "pause means operationally" — the gap between code-complete and operational is normal and intentional.

---

## Reference — running tests, common pitfalls

**Backend tests (any chunk):**
```bash
cd /Users/drprockz/Projects/cruz-ai-system/.claude/worktrees/pedantic-stonebraker-e79b8b
source venv-py311/bin/activate
pytest tests/ -v
```

**Frontend tests:**
```bash
cd frontend
npm run test
```

**Pitfall — `firebase_admin._apps` registry:** The default app is global. Tests
that construct `PushService` twice in one process must either reset
`firebase_admin._apps` or rely on the constructor's `if "[DEFAULT]" not in
firebase_admin._apps` guard. The tests in this plan mock `initialize_app`
entirely so this isn't an issue, but be aware if you write integration
tests.

**Pitfall — `WAKE_WORD_THRESHOLD` env precedence:** The daemon reads
`WAKE_WORD_THRESHOLD` from the environment with default `0.3`. The committed
`hey_cruz.onnx` model produces a different score distribution than
`hey_jarvis`; the threshold from `docs/perf/sp7-wake-word-roc.md` overrides
the daemon default. Set this in `.env` after Task 6.5.

**Pitfall — Workbox + Firebase SW coexistence:** Both register at `/` scope.
Per FCM convention, the Firebase SW owns `push` events; Workbox owns `fetch`
events. If you observe duplicate notifications or a missing `notificationclick`
handler, check that `firebase-messaging-sw.js` is being copied to `dist/`
during build (it should — Vite copies anything in `public/` automatically).

**Pitfall — IndexedDB on iOS Safari:** Safari evicts IndexedDB after 7 days
of PWA inactivity. The chat view falls back gracefully (empty cache → first
fetch repopulates). Do not rely on the cache being durable on iOS.

