"""
CRUZ AI System - FastAPI Application
Main entry point for the CRUZ API server.
"""

import hashlib
import hmac
import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

import anthropic
import psycopg2
import redis.asyncio as aioredis
from arq import create_pool
from arq.connections import RedisSettings
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
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

load_dotenv()

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
    """Format a single SSE event line."""
    return f"data: {json.dumps(payload)}\n\n"


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

    api_key = os.environ.get("LIVEKIT_API_KEY", "")
    api_secret = os.environ.get("LIVEKIT_API_SECRET", "")
    ws_url = os.environ.get("LIVEKIT_WS_URL", "")
    if not (api_key and api_secret and ws_url):
        raise HTTPException(status_code=500, detail="LiveKit not configured")

    conversation_id = req.conversation_id or str(uuid.uuid4())
    room = f"cruz-{conversation_id}-{req.device_id}"

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
