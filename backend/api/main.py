"""
CRUZ AI System - FastAPI Application
Main entry point for the CRUZ API server.
"""

import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Literal, Optional

import anthropic
import psycopg2
import redis.asyncio as aioredis
from arq import create_pool
from arq.connections import RedisSettings
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Make project root importable so agents/ and services/ can be resolved
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from agents.cruz.cruz_agent import CruzAgent          # noqa: E402
from agents.base_agent import AgentInput              # noqa: E402
from services.conversation import ConversationService  # noqa: E402
from services.db import get_db_service                # noqa: E402
from services.ollama import OllamaService             # noqa: E402
from services.qdrant import get_qdrant_service        # noqa: E402
from services.redis_client import get_redis_service   # noqa: E402
from services.alerts import install_loki_logging      # noqa: E402
from services.voice import VoicePipeline              # noqa: E402

# Don't load .env under pytest — test fixtures use monkeypatch and conftest
# sets ENVIRONMENT=test; reloading .env would clobber monkeypatched vars.
if os.environ.get("ENVIRONMENT") != "test":
    from dotenv import dotenv_values

    load_dotenv(override=False)
    # Fill empty shell-exported vars with their .env value (protects against
    # shell configs that export `KEY=""` for required secrets).
    for _k, _v in dotenv_values().items():
        if _v and not os.environ.get(_k, "").strip():
            os.environ[_k] = _v

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
PORT = int(os.getenv("PORT", "3000"))


_REQUIRED_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "DATABASE_URL",
    "REDIS_URL",
    "QDRANT_URL",
)

# Ollama models required by CRUZ agents. Missing means agents hang or must
# fall back to Claude (expensive + defeats the point of local inference).
#   qwen2.5-coder:14b — ECHO, REACH, PM, TITAN, MARK, QT
#   llama3.1:8b       — RAW, PULSE
_REQUIRED_OLLAMA_MODELS = (
    "qwen2.5-coder:14b",
    "llama3.1:8b",
)


def _validate_required_env() -> None:
    """
    Fail fast if any required environment variable is missing or empty.

    Called at lifespan startup. Deferring these checks to the first agent
    call leaves operators debugging "why is CRUZ silent at 3 AM" when the
    real answer is "ANTHROPIC_API_KEY wasn't set."
    """
    missing = [var for var in _REQUIRED_ENV_VARS if not os.environ.get(var, "").strip()]
    if missing:
        raise RuntimeError(
            "CRUZ cannot start — required environment variables missing or empty: "
            f"{', '.join(missing)}. "
            "Set these in your .env file (see .env.example) and restart."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown events."""
    _validate_required_env()

    # ── Sentry (optional) ───────────────────────────────────────────────
    sentry_dsn = os.environ.get("SENTRY_DSN", "").strip()
    if sentry_dsn:
        try:
            import sentry_sdk  # type: ignore

            sentry_sdk.init(
                dsn=sentry_dsn,
                environment=os.environ.get("ENVIRONMENT", "development"),
                traces_sample_rate=0.1,
            )
        except Exception as exc:
            print(f"⚠️  Sentry init failed (non-fatal): {exc}")

    # ── Loki log shipping (optional) ────────────────────────────────────
    install_loki_logging(labels={"app": "cruz", "component": "api"})

    print(f"🚀 CRUZ AI System starting on port {PORT}")
    db = get_db_service()
    await db.connect()
    redis = get_redis_service()
    await redis.connect()
    qdrant = get_qdrant_service()
    await qdrant.connect()
    yield
    print("👋 CRUZ AI System shutting down")
    await qdrant.disconnect()
    await redis.disconnect()
    await db.disconnect()


app = FastAPI(
    title="CRUZ AI System",
    description="Multi-agent AI assistant system for 3-5x developer productivity",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check() -> JSONResponse:
    """
    Full dependency health check.

    Probes PostgreSQL, Redis, Ollama, and the Claude API.
    Always returns HTTP 200 — operators read the body to see what's wrong.

    Overall status:
      "healthy"  — all critical services reachable
      "degraded" — one or more services are down
    """
    results: dict[str, Any] = {}

    # ── PostgreSQL ────────────────────────────────────────────────────────
    try:
        db = get_db_service()
        await db.fetchrow("SELECT 1 AS result")
        results["postgresql"] = "connected"
    except Exception as exc:
        results["postgresql"] = f"error: {exc}"

    # ── Redis ─────────────────────────────────────────────────────────────
    try:
        r = aioredis.from_url(REDIS_URL)
        await r.ping()
        await r.aclose()
        results["redis"] = "connected"
    except Exception as exc:
        results["redis"] = f"error: {exc}"

    # ── Ollama ────────────────────────────────────────────────────────────
    try:
        ollama = OllamaService()
        reachable = await ollama.health_check()
        if reachable:
            models = await ollama.list_models()
            # Ollama's /api/tags returns [{"name": "...", ...}] — normalise to
            # just the names so membership checks work regardless of whether
            # callers pass list[str] (tests) or list[dict] (real API).
            model_names = [
                m.get("name", "") if isinstance(m, dict) else str(m)
                for m in models
            ]
            missing = [m for m in _REQUIRED_OLLAMA_MODELS if m not in model_names]
            results["ollama"] = {
                "status": "reachable",
                "models": models,
                "required": list(_REQUIRED_OLLAMA_MODELS),
                "missing": missing,
            }
        else:
            results["ollama"] = {
                "status": "unreachable",
                "models": [],
                "required": list(_REQUIRED_OLLAMA_MODELS),
                "missing": list(_REQUIRED_OLLAMA_MODELS),
            }
    except Exception as exc:
        results["ollama"] = {
            "status": f"error: {exc}",
            "models": [],
            "required": list(_REQUIRED_OLLAMA_MODELS),
            "missing": list(_REQUIRED_OLLAMA_MODELS),
        }

    # ── Qdrant ────────────────────────────────────────────────────────────
    try:
        qdrant = get_qdrant_service()
        reachable = await qdrant.health_check()
        results["qdrant"] = "connected" if reachable else "unreachable"
    except Exception as exc:
        results["qdrant"] = f"error: {exc}"

    # ── Claude API ────────────────────────────────────────────────────────
    try:
        claude = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        await claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            messages=[{"role": "user", "content": "ping"}],
        )
        results["claude_api"] = "reachable"
    except Exception as exc:
        results["claude_api"] = f"error: {exc}"

    # ── Overall status ────────────────────────────────────────────────────
    # Only gate on the LLM backend that's actually in use. If the operator
    # has selected LLM_BACKEND=ollama, a dead Claude API shouldn't flip
    # the system to degraded — it's intentionally not being called.
    llm_backend = os.environ.get("LLM_BACKEND", "anthropic").strip().lower()
    results["llm_backend"] = llm_backend

    critical = [results["postgresql"], results["redis"]]
    if llm_backend == "anthropic":
        critical.append(results["claude_api"])
    # gemini backend does not have a dedicated /health probe yet — it's
    # exercised via the first real call. ollama's reachability is gated
    # below on the Ollama service check, which already runs.

    services_ok = all(
        v in ("connected", "reachable") for v in critical
    ) and results["ollama"]["status"] == "reachable"

    # Model-availability check only matters for Ollama-backed paths.
    # Every agent path ultimately uses Ollama either as primary (most
    # specialists) or as the LLMRouter backend when LLM_BACKEND=ollama.
    models_ok = not results["ollama"].get("missing")

    results["status"] = "healthy" if (services_ok and models_ok) else "degraded"
    results["version"] = "0.1.0"

    return JSONResponse(status_code=200, content=results)


@app.get("/test/db")
async def test_database() -> dict[str, Any]:
    """
    Test PostgreSQL database connectivity.

    Returns:
        Dict with connection status and database version string.
    """
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return {
            "status": "connected",
            "database": "PostgreSQL",
            "version": version,
        }
    except Exception as e:
        return {
            "status": "error",
            "database": "PostgreSQL",
            "error": str(e),
        }


@app.get("/test/redis")
async def test_redis() -> dict[str, Any]:
    """
    Test Redis connectivity.

    Returns:
        Dict with connection status and ping result.
    """
    try:
        client = aioredis.from_url(REDIS_URL)
        pong = await client.ping()
        await client.aclose()
        return {
            "status": "connected",
            "service": "Redis",
            "ping": pong,
        }
    except Exception as e:
        return {
            "status": "error",
            "service": "Redis",
            "error": str(e),
        }


@app.get("/test/claude")
async def test_claude() -> dict[str, Any]:
    """
    Test Anthropic Claude API connectivity.

    Returns:
        Dict with connection status and a short model response.
    """
    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=50,
            messages=[
                {"role": "user", "content": "Reply with exactly: CRUZ online"}
            ],
        )
        return {
            "status": "connected",
            "service": "Anthropic Claude",
            "model": message.model,
            "response": message.content[0].text,
        }
    except Exception as e:
        return {
            "status": "error",
            "service": "Anthropic Claude",
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# POST /command — main entry point for all user requests
# ---------------------------------------------------------------------------

class CommandRequest(BaseModel):
    command: str = Field(..., min_length=1, description="User's natural-language command")
    trace_id: Optional[str] = Field(None, description="Optional trace ID for request tracing")
    conversation_id: Optional[str] = Field(None, description="Existing conversation ID to continue")
    device: Optional[str] = Field(None, description="Originating device: phone | ipad | thinkpad | mac_mini | web")
    stream: bool = Field(False, description="If True, respond with an SSE stream instead of JSON")


class CommandResponse(BaseModel):
    success: bool
    result: Any
    agent: str
    duration_ms: int
    tokens_used: int
    error: Optional[str]
    requires_approval: bool
    approval_prompt: Optional[str]
    trace_id: str


def _sse_event(payload: dict) -> str:
    """Format a single SSE event line.

    If payload has ``__event__``, emit a named SSE event:
        event: <name>\\ndata: <json>\\n\\n
    Otherwise emit a plain data-only event.
    """
    event_name = payload.get("__event__") if isinstance(payload, dict) else None
    if event_name:
        data = payload.get("data", {})
        return f"event: {event_name}\ndata: {json.dumps(data, default=str)}\n\n"
    return f"data: {json.dumps(payload, default=str)}\n\n"


async def _sse_stream(
    agent: CruzAgent,
    agent_input: AgentInput,
    trace_id: str,
    conversation_id: str,
) -> AsyncGenerator[str, None]:
    """
    Run CruzAgent.stream_response and yield SSE events.

    Events emitted (in order):
      - text              — one full sentence, ready for TTS
      - tool_start        — a specialist agent has been invoked
      - tool_finish       — specialist returned a result
      - approval_required — when requires_approval=True (stream ends after)
      - error             — when an exception is raised
      - done              — always last, carries trace_id + conversation_id
    """
    from agents.cruz.stream_events import (
        Text, ToolStart, ToolFinish, ApprovalRequired, Done,
    )
    try:
        async for ev in agent.stream_response(
            task=agent_input["task"],
            conversation_id=conversation_id,
            trace_id=trace_id,
            device=agent_input["context"].get("device"),
        ):
            if isinstance(ev, Text):
                yield _sse_event({"type": "text", "content": ev.content})
            elif isinstance(ev, ToolStart):
                yield _sse_event({"type": "tool_start", "agent": ev.agent, "summary": ev.summary})
            elif isinstance(ev, ToolFinish):
                yield _sse_event({"type": "tool_finish", "agent": ev.agent, "result": ev.result_preview})
            elif isinstance(ev, ApprovalRequired):
                yield _sse_event({
                    "type": "approval_required", "agent": ev.agent,
                    "approval_prompt": ev.prompt,
                })
            elif isinstance(ev, Done):
                yield _sse_event({
                    "type": "done", "trace_id": trace_id,
                    "conversation_id": conversation_id,
                    "tokens_used": ev.tokens_used,
                })
    except Exception as exc:
        yield _sse_event({"type": "error", "error": str(exc)})
        yield _sse_event({"type": "done", "trace_id": trace_id,
                          "conversation_id": conversation_id})


@app.post("/command")
async def command(request: CommandRequest):
    """
    Main command endpoint. Routes user requests through CruzAgent.

    JSON mode  (stream=False, default):
      200 on success | 202 approval required | 500 error

    SSE mode (stream=True):
      text/event-stream with events: text | approval_required | error | done
    """
    trace_id = request.trace_id or str(uuid.uuid4())
    conversation_id = request.conversation_id or str(uuid.uuid4())

    agent = CruzAgent()
    agent_input: AgentInput = {
        "task": request.command,
        "context": {"device": request.device},
        "trace_id": trace_id,
        "conversation_id": conversation_id,
    }

    if request.stream:
        return StreamingResponse(
            _sse_stream(agent, agent_input, trace_id, conversation_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # disable nginx buffering
            },
        )

    output = await agent.process(agent_input)

    response_body = {
        "success": output["success"],
        "result": output["result"],
        "agent": output["agent"],
        "duration_ms": output["duration_ms"],
        "tokens_used": output["tokens_used"],
        "error": output["error"],
        "requires_approval": output["requires_approval"],
        "approval_prompt": output["approval_prompt"],
        "trace_id": trace_id,
    }

    if not output["success"]:
        return JSONResponse(status_code=500, content=response_body)

    if output["requires_approval"]:
        return JSONResponse(status_code=202, content=response_body)

    return JSONResponse(status_code=200, content=response_body)


# ---------------------------------------------------------------------------
# GET /logs/{trace_id} — full execution trace for a single request
# ---------------------------------------------------------------------------

@app.get("/explain/{trace_id}")
async def explain_trace(trace_id: str) -> JSONResponse:
    """
    Human-readable reasoning chain for a trace_id.

    Stitches all agent_logs rows into a summary + per-step breakdown so the
    user (or CRUZ itself) can answer "why did you do that?".
    """
    from agents.cruz.persona.explainability import build_explanation
    db = get_db_service()
    ex = await build_explanation(db, trace_id)
    if ex is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"no logs for trace_id {trace_id}"},
        )
    return JSONResponse(ex.to_dict())


@app.get("/logs/{trace_id}")
async def get_logs(trace_id: str) -> JSONResponse:
    """
    Return all agent_logs rows for a trace_id in chronological order.

    Used to inspect every agent invoked during a single CRUZ request.
    Always returns 200 — unknown trace_id yields an empty list.

    Each entry includes: agent, action, status, tokens_used, duration_ms,
    created_at. Internal fields (id, input_data, output_data) are omitted.
    """
    _FIELDS = {"agent", "action", "status", "tokens_used", "duration_ms", "created_at"}

    db = get_db_service()
    rows = await db.fetch(
        """
        SELECT agent, action, status, tokens_used, duration_ms,
               created_at::text AS created_at
        FROM agent_logs
        WHERE trace_id = $1
        ORDER BY created_at ASC
        """,
        trace_id,
    )
    return JSONResponse(
        status_code=200,
        content=[{k: v for k, v in dict(row).items() if k in _FIELDS} for row in rows],
    )


# ---------------------------------------------------------------------------
# GET /conversations/{conversation_id}/messages — cross-device history pickup
# ---------------------------------------------------------------------------

@app.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str) -> JSONResponse:
    """
    Return the last 50 messages for a conversation in chronological order.

    200 + list  — conversation exists (may be empty list for new conversations)
    404         — conversation_id not found or load_history raised an error
    """
    try:
        db = get_db_service()
        conv_service = ConversationService(db)
        history = await conv_service.load_history(conversation_id)
        return JSONResponse(status_code=200, content=history)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# POST /voice/transcribe — audio bytes → text via Whisper Large v3
# ---------------------------------------------------------------------------

class VoiceSpeakRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to synthesise")


@app.post("/voice/speak")
async def voice_speak(request: VoiceSpeakRequest):
    """
    Synthesise speech from text.

    Tries Inworld TTS first (requires INWORLD_API_KEY); falls back to
    macOS `say` on failure. Returns raw audio bytes.

    200 — audio/mpeg (Inworld) or audio/aiff (say fallback)
    500 — both TTS backends failed
    """
    from fastapi.responses import Response

    pipeline = VoicePipeline()
    try:
        audio = await pipeline.speak(request.text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(content=audio, media_type="audio/mpeg")


@app.post("/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...)) -> JSONResponse:
    """
    Transcribe an uploaded audio file using Whisper Large v3 (local).

    Args:
        file: Multipart audio upload (WAV, MP3, OGG, etc.)

    Returns:
        {"text": "<transcription>"} — empty string if audio is silent or unclear.
    """
    audio_bytes = await file.read()
    pipeline = VoicePipeline()
    text = await pipeline.transcribe(audio_bytes)
    return JSONResponse(status_code=200, content={"text": text})


# ---------------------------------------------------------------------------
# POST /conversations — start a new conversation
# ---------------------------------------------------------------------------

class NewConversationRequest(BaseModel):
    device: Optional[str] = Field(None, description="Originating device: phone | ipad | thinkpad | web")


@app.post("/conversations")
async def create_conversation(request: NewConversationRequest = NewConversationRequest()) -> JSONResponse:
    """
    Start a new conversation and return its UUID.

    The caller stores the returned conversation_id and passes it on
    subsequent POST /command calls for continuity across turns.

    201  — conversation created, returns {"conversation_id": "<uuid>"}
    """
    conversation_id = str(uuid.uuid4())
    db = get_db_service()
    await db.execute(
        "INSERT INTO conversations (id, device) VALUES ($1, $2)",
        conversation_id,
        request.device,
    )
    return JSONResponse(status_code=201, content={"conversation_id": conversation_id})


# ---------------------------------------------------------------------------
# GET /agents/status — per-agent last run time + status
# ---------------------------------------------------------------------------

@app.get("/agents/status")
async def agents_status() -> JSONResponse:
    """
    Return the most recent log entry per agent from agent_logs.

    Used by dashboards and monitoring to see which agents ran and when.
    Always returns 200 — empty list when no logs exist.

    Each entry: {agent, status, last_run}
    """
    db = get_db_service()
    rows = await db.fetch(
        """
        SELECT DISTINCT ON (agent)
            agent,
            status,
            created_at::text AS last_run
        FROM agent_logs
        ORDER BY agent, created_at DESC
        """
    )
    return JSONResponse(
        status_code=200,
        content=[dict(row) for row in rows],
    )


# ---------------------------------------------------------------------------
# GET /tasks — list tasks with optional status filter
# ---------------------------------------------------------------------------

@app.get("/tasks")
async def get_tasks(status: Optional[str] = None) -> JSONResponse:
    """
    List tasks, optionally filtered by status.

    Query params:
      status  — "pending" | "done" | "error" (omit for all)

    Always returns 200 — empty list when no matching tasks.
    """
    db = get_db_service()
    if status:
        rows = await db.fetch(
            """
            SELECT id, agent, title, status, priority,
                   created_at::text AS created_at
            FROM tasks
            WHERE status = $1
            ORDER BY priority ASC, created_at DESC
            """,
            status,
        )
    else:
        rows = await db.fetch(
            """
            SELECT id, agent, title, status, priority,
                   created_at::text AS created_at
            FROM tasks
            ORDER BY priority ASC, created_at DESC
            """
        )
    return JSONResponse(
        status_code=200,
        content=[dict(row) for row in rows],
    )


# ─── Webhook endpoints (Phase 6.4 — Cloudflare Tunnel) ─────────────────────
#
# Each endpoint validates an HMAC signature (GitHub/Vercel) or a static token
# (Google Calendar), enqueues a background ARQ task, and returns 200 fast so
# the sender does not time out. Signature failure → 401.


async def get_arq_pool():
    """Create an ARQ Redis pool for enqueueing webhook tasks."""
    return await create_pool(RedisSettings.from_dsn(REDIS_URL))


def _verify_hmac(secret: str, body: bytes, header_value: str, algo: str) -> bool:
    if not secret or not header_value:
        return False
    prefix = f"{algo}="
    provided = header_value[len(prefix):] if header_value.startswith(prefix) else header_value
    expected = hmac.new(secret.encode(), body, getattr(hashlib, algo)).hexdigest()
    return hmac.compare_digest(expected, provided)


@app.post("/webhooks/github")
async def webhook_github(request: Request) -> JSONResponse:
    body = await request.body()
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    sig = request.headers.get("x-hub-signature-256", "")
    if not _verify_hmac(secret, body, sig, "sha256"):
        raise HTTPException(status_code=401, detail="invalid signature")
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid json")
    event = request.headers.get("x-github-event", "unknown")
    pool = await get_arq_pool()
    await pool.enqueue_job("process_github_webhook", event, payload)
    return JSONResponse(status_code=200, content={"queued": True, "event": event})


@app.post("/webhooks/vercel")
async def webhook_vercel(request: Request) -> JSONResponse:
    body = await request.body()
    secret = os.environ.get("VERCEL_WEBHOOK_SECRET", "")
    sig = request.headers.get("x-vercel-signature", "")
    if not _verify_hmac(secret, body, sig, "sha1"):
        raise HTTPException(status_code=401, detail="invalid signature")
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid json")
    pool = await get_arq_pool()
    await pool.enqueue_job("process_vercel_webhook", payload)
    return JSONResponse(status_code=200, content={"queued": True})


@app.post("/webhooks/google-calendar")
async def webhook_google_calendar(request: Request) -> JSONResponse:
    expected = os.environ.get("GOOGLE_WEBHOOK_TOKEN", "")
    provided = request.headers.get("x-goog-channel-token", "")
    if not expected or not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="invalid token")
    headers = {k: v for k, v in request.headers.items() if k.lower().startswith("x-goog-")}
    pool = await get_arq_pool()
    await pool.enqueue_job("process_google_calendar_webhook", headers)
    return JSONResponse(status_code=200, content={"queued": True})


# ─── Gmail Pub/Sub push receiver (SP5) ──────────────────────────────────────

# google-auth comes in transitively via google-api-python-client (already
# in v1 for Calendar). If it's not installed in this env, requirements
# need google-auth>=2.0.
try:
    from google.oauth2 import id_token as _g_id_token
    from google.auth.transport import requests as _g_requests
    _GOOGLE_AUTH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _GOOGLE_AUTH_AVAILABLE = False


def _verify_pubsub_jwt(token: str) -> Optional[dict]:
    """Verify a Pub/Sub OIDC token. Returns the decoded claims dict on
    success, None on failure. See Google docs:
      https://cloud.google.com/pubsub/docs/push#authentication

    Returns None on every failure mode to avoid leaking why to the caller
    (the endpoint just responds 401). For operators, each branch logs a
    distinct warning so misconfiguration (e.g. missing audience env, missing
    google-auth dep) is distinguishable from an actual attack in logs.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)
    if not _GOOGLE_AUTH_AVAILABLE:
        _log.warning("gmail pubsub: google-auth not installed; verification disabled")
        return None
    audience = os.environ.get("GMAIL_PUBSUB_AUDIENCE", "")
    expected_email = os.environ.get("GMAIL_PUBSUB_SERVICE_ACCOUNT", "")
    if not audience:
        _log.warning("gmail pubsub: GMAIL_PUBSUB_AUDIENCE not set; cannot verify")
        return None
    try:
        claims = _g_id_token.verify_oauth2_token(
            token, _g_requests.Request(), audience=audience,
        )
        if expected_email and claims.get("email") != expected_email:
            _log.warning("gmail pubsub: email claim mismatch")
            return None
        return claims
    except Exception as exc:
        _log.warning("gmail pubsub: jwt verify failed: %s", exc)
        return None


@app.post("/webhooks/gmail")
async def webhook_gmail(request: Request) -> JSONResponse:
    """Pub/Sub push receiver for Gmail watch notifications.

    Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §3.5
    """
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = auth.split(None, 1)[1].strip()
    claims = _verify_pubsub_jwt(token)
    if claims is None:
        raise HTTPException(status_code=401, detail="invalid pubsub jwt")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    pubsub_message = (body or {}).get("message", {})
    pool = await get_arq_pool()
    await pool.enqueue_job("process_gmail_webhook", pubsub_message)
    return JSONResponse(status_code=200, content={"queued": True})


# ---------------------------------------------------------------------------
# POST /voice/token — mint a short-lived LiveKit JWT for a voice session
# ---------------------------------------------------------------------------

class VoiceTokenRequest(BaseModel):
    device_id: str
    conversation_id: Optional[str] = None


@app.post("/voice/token")
async def voice_token(req: VoiceTokenRequest) -> JSONResponse:
    """
    Mint a short-lived LiveKit JWT for a voice session.

    Creates (or re-uses) a conversation_id and room name of the form
    ``cruz-<conversation_id>-<device_id>``, then signs a 15-minute JWT
    that grants publish + subscribe rights on that room.

    200  — {"room", "token", "ws_url", "conversation_id"}
    500  — LiveKit env vars not configured
    """
    import datetime

    from livekit import api as lkapi  # lazy import — only needed at call time
    from livekit.protocol.agent_dispatch import RoomAgentDispatch
    from livekit.protocol.room import RoomConfiguration

    api_key = os.environ.get("LIVEKIT_API_KEY", "")
    api_secret = os.environ.get("LIVEKIT_API_SECRET", "")
    ws_url = os.environ.get("LIVEKIT_URL") or os.environ.get("LIVEKIT_WS_URL") or ""
    if not (api_key and api_secret and ws_url):
        raise HTTPException(status_code=500, detail="LiveKit not configured")

    conversation_id = req.conversation_id or str(uuid.uuid4())
    # `__` as the delimiter — safe against UUID dashes in conversation_id.
    room = f"cruz__{conversation_id}__{req.device_id}"

    # Explicit agent dispatch — required for livekit-agents >=1.x workers that
    # register with a named agent (`cruz-voice`). Without this the worker
    # never gets dispatched to the room and the browser sees silence.
    room_cfg = RoomConfiguration(
        name=room,
        agents=[RoomAgentDispatch(agent_name="cruz-voice")],
    )

    token = (
        lkapi.AccessToken(api_key, api_secret)
        .with_identity(req.device_id)
        .with_name(req.device_id)
        .with_grants(
            lkapi.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
            )
        )
        .with_room_config(room_cfg)
        .with_ttl(datetime.timedelta(minutes=15))
        .to_jwt()
    )
    return JSONResponse(
        status_code=200,
        content={
            "room": room,
            "token": token,
            "ws_url": ws_url,
            "conversation_id": conversation_id,
        },
    )


# ─── Events SSE ──────────────────────────────────────────────────────────────

@app.get("/events")
async def events_stream(
    request: Request,
    last_id: Optional[int] = None,
) -> StreamingResponse:
    """
    SSE stream of agent_logs rows.

    - On connect: emit ``event: replay`` with up to 50 recent rows (or rows
      after ``last_id`` when provided).
    - Then emit ``event: sync`` so the client knows it has caught up.
    - Then subscribe to the Redis channel ``cruz:agent_logs`` and emit
      ``event: log`` for each incoming message.
    - Emit ``event: ping`` every 25 s to keep the connection alive.
    """
    import asyncio as _asyncio

    async def _gen() -> AsyncGenerator[str, None]:
        db = get_db_service()
        redis_svc = get_redis_service()
        pubsub = redis_svc.pubsub()
        try:
            # ── Replay ──────────────────────────────────────────────────────
            if last_id is None:
                rows = await db.fetch(
                    "SELECT id, trace_id, agent, action, status, "
                    "tokens_used, duration_ms, created_at "
                    "FROM agent_logs ORDER BY id DESC LIMIT 50",
                )
                rows = list(reversed(rows))
            else:
                rows = await db.fetch(
                    "SELECT id, trace_id, agent, action, status, "
                    "tokens_used, duration_ms, created_at "
                    "FROM agent_logs WHERE id > $1 ORDER BY id ASC LIMIT 500",
                    last_id,
                )
            replay = [dict(r) for r in rows]
            yield _sse_event({"__event__": "replay", "data": replay})

            last_replay_id = replay[-1]["id"] if replay else last_id
            yield _sse_event({"__event__": "sync", "data": {"last_id": last_replay_id}})

            # ── Subscribe ────────────────────────────────────────────────────
            await pubsub.subscribe("cruz:agent_logs")
            last_ping = _asyncio.get_event_loop().time()

            async for msg in pubsub.listen():
                if await request.is_disconnected():
                    break
                now = _asyncio.get_event_loop().time()
                if now - last_ping > 25:
                    yield _sse_event({"__event__": "ping", "data": {"t": int(now)}})
                    last_ping = now
                if msg.get("type") != "message":
                    continue
                data = msg.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(data) if isinstance(data, str) else data
                except Exception:
                    parsed = {"raw": str(data)}
                yield _sse_event({"__event__": "log", "data": parsed})
        finally:
            try:
                await pubsub.unsubscribe("cruz:agent_logs")
                await pubsub.close()
            except Exception:
                pass

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# GET /dashboard — aggregate payload for the Dashboard tab
# ---------------------------------------------------------------------------

@app.get("/dashboard")
async def dashboard() -> JSONResponse:
    """
    Aggregate payload for the DashboardTab.

    Returns four blocks:
      today        — calendar events, emails, PRs, deploys (Phase 2 integrations)
      metrics      — today's agent_logs roll-up (turns, tokens, cost, time saved)
      system_health — key service reachability derived from env vars + /health probe
      upcoming     — scheduled background agents
    """
    db = get_db_service()

    # ── Metrics — today's agent_logs roll-up ──────────────────────────────
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*)::int AS turns, "
            "COALESCE(SUM(tokens_used),0)::int AS tokens, "
            "COALESCE(SUM(duration_ms),0)::int AS duration_total_ms "
            "FROM agent_logs WHERE created_at > NOW() - INTERVAL '1 day'"
        )
        turns = row["turns"] if row else 0
        tokens = row["tokens"] if row else 0
        duration_total_ms = row["duration_total_ms"] if row else 0
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).warning("dashboard metrics fetch failed: %s", exc)
        turns, tokens, duration_total_ms = 0, 0, 0

    # ── System health — probe via health_check() + env-var presence ───────
    try:
        health_resp = await health_check()
        # health_check returns a JSONResponse; extract its body
        import json as _json_inner
        sh_raw = _json_inner.loads(health_resp.body) if hasattr(health_resp, "body") else {}
    except Exception:
        sh_raw = {}

    def _state(x: Any) -> str:
        if isinstance(x, dict):
            s = x.get("status", "")
            return "healthy" if s in ("reachable", "connected", "loaded", "healthy") else "degraded"
        if x in ("healthy", "connected", "reachable"):
            return "healthy"
        return "degraded"

    system_health = {
        "deepgram": "healthy" if os.environ.get("DEEPGRAM_API_KEY") else "degraded",
        "livekit": "healthy" if os.environ.get("LIVEKIT_API_KEY") else "degraded",
        "postgres": _state(sh_raw.get("postgresql")),
        "redis": _state(sh_raw.get("redis")),
        "qdrant": _state(sh_raw.get("qdrant")),
        "ollama": _state(sh_raw.get("ollama")),
        "claude_api": _state(sh_raw.get("claude_api", "healthy")),
    }

    # ── Cost heuristics ────────────────────────────────────────────────────
    # Weighted avg of $3/M input + $15/M output ≈ $9/M blended
    estimated_cost = round((tokens / 1_000_000.0) * 9.0, 2)
    # Rough heuristic: each CRUZ turn saves ~6 minutes
    estimated_time_saved_hours = round(turns * 0.1, 1)

    return JSONResponse(
        status_code=200,
        content={
            "today": {
                "calendar_events": [],   # Phase 2 — Google Calendar integration
                "unread_emails": 0,      # Phase 2 — Gmail integration
                "open_prs": 0,           # Phase 2 — GitHub webhook mirror
                "deploys_today": 0,      # Phase 2 — Vercel/Railway webhook mirror
            },
            "metrics": {
                "turns_today": turns,
                "tokens_today": tokens,
                "estimated_cost_usd": estimated_cost,
                "estimated_time_saved_hours": estimated_time_saved_hours,
            },
            "system_health": system_health,
            "upcoming": [
                {"agent": "pulse", "scheduled_at": "tomorrow 06:00", "label": "Morning brief"},
                {"agent": "raw", "scheduled_at": "tonight 03:00", "label": "Research scan"},
            ],
        },
    )


# ---------------------------------------------------------------------------
# GET /approvals — list pending (or any state) approval requests
# POST /approvals/:id/approve — approve a pending action
# POST /approvals/:id/deny   — deny a pending action
# ---------------------------------------------------------------------------

class ApprovalRow(BaseModel):
    """Shape of a row in the approval_requests table."""

    id: str
    trace_id: str
    agent: str
    action: str
    payload: Any
    state: str
    requested_at: Any
    responded_at: Optional[Any] = None
    expires_at: Any


@app.get("/approvals", response_model=list[ApprovalRow])
async def list_approvals(state: str = "pending", limit: int = 25):
    """
    List approval requests filtered by state.

    Query params:
      state  — "pending" | "approved" | "denied" (default: "pending")
      limit  — max rows to return (default: 25, max: 200)

    Returns a list of ApprovalRow objects ordered newest-first.
    Always 200 — unknown state yields an empty list.
    """
    db = get_db_service()
    rows = await db.fetch(
        "SELECT id, trace_id, agent, action, payload, state, "
        "requested_at, responded_at, expires_at "
        "FROM approval_requests WHERE state = $1 "
        "ORDER BY requested_at DESC LIMIT $2",
        state,
        limit,
    )
    return [dict(r) for r in rows]


async def _respond_to_approval(
    approval_id: str,
    new_state: Literal["approved", "denied"],
) -> dict:
    """
    Shared logic for approve + deny actions.

    1. UPDATE approval_requests SET state = new_state, responded_at = NOW()
    2. Publish {state} to redis channel ``cruz:approval:<id>`` (non-fatal)
    3. Return {"state": new_state}
    """
    db = get_db_service()
    redis_svc = get_redis_service()

    await db.execute(
        "UPDATE approval_requests SET state = $1, responded_at = NOW() "
        "WHERE id = $2",
        new_state,
        approval_id,
    )

    try:
        await redis_svc.publish(
            f"cruz:approval:{approval_id}",
            json.dumps({"state": new_state}),
        )
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "approval publish failed (non-fatal): %s", exc
        )

    return {"state": new_state}


@app.post("/approvals/{approval_id}/approve")
async def approve_approval(approval_id: str) -> JSONResponse:
    """
    Approve a pending action.

    200 — {"state": "approved"}
    Publishes to ``cruz:approval:<id>`` so waiting agents can unblock.
    """
    result = await _respond_to_approval(approval_id, "approved")
    return JSONResponse(status_code=200, content=result)


@app.post("/approvals/{approval_id}/deny")
async def deny_approval(approval_id: str) -> JSONResponse:
    """
    Deny a pending action.

    200 — {"state": "denied"}
    Publishes to ``cruz:approval:<id>`` so waiting agents can unblock.
    """
    result = await _respond_to_approval(approval_id, "denied")
    return JSONResponse(status_code=200, content=result)


# ─── Notification callbacks (SP5) ───────────────────────────────────────────


class FalseAlarmRequest(BaseModel):
    """Request body for a user-acked false-critical notification."""

    agent: str
    dedup_key: str


@app.post("/notifications/false-alarm")
async def notifications_false_alarm(req: FalseAlarmRequest) -> JSONResponse:
    """Record a user-acked false-critical for the SP5 exit-gate measurement.

    Called by Telegram inline button on a `critical` notification, OR by
    any other channel that wants to surface a false-positive ack.
    Writes agent_state(<agent>, "false_critical:<dedup_key>") and stays
    silent — no further action. The SP5 daily briefing handler scans
    these rows for the 7-day measurement window.

    Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §7, §8.2
    """
    from services.agent_state import get_state_service

    state = get_state_service()
    await state.set(
        req.agent,
        f"false_critical:{req.dedup_key}",
        {"ack_at": time.time(), "agent": req.agent, "dedup_key": req.dedup_key},
        ttl_seconds=86400 * 365,
    )
    return JSONResponse(status_code=200, content={"recorded": True})


# ── SPA mount (must be the LAST route registered so it doesn't shadow API routes) ──
# Serves the built React PWA from frontend/dist. Frontend production build uses
# VITE_API_BASE="" so it calls API routes on the same origin (e.g. /command).
# This collapses the previously-separate cruz-ui PM2 app onto port 3000, which
# means a single Cloudflare Tunnel ingress rule serves both UI and API.
_FRONTEND_DIST = os.path.join(_PROJECT_ROOT, "frontend", "dist")
if os.path.isdir(_FRONTEND_DIST):
    app.mount(
        "/",
        StaticFiles(directory=_FRONTEND_DIST, html=True),
        name="frontend",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
