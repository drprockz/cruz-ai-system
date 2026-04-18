# CRUZ Persona Intelligence Layer — v1 Spec

**Date:** 2026-04-18
**Status:** Approved by user AFK; autonomous execution
**Supersedes:** No prior persona spec. User pasted a 16-module wish-list; this doc scopes down to the shippable subset.

---

## 1. Goal

Make CRUZ feel like a **consistent, JARVIS-inspired trusted advisor** rather than a generic assistant — starting today, with code that compiles against signals we actually have.

## 2. Scope cut — honest

User's pasted spec had 16 modules. Six of those need data we don't collect yet; building them would produce dead code. This v1 ships **7 modules that bite** and explicitly defers 9.

### v1 SHIPS (7 modules)

| Module | What it does | Signal it uses |
|---|---|---|
| `core_identity.yaml` | Personality traits loaded into CRUZ's system prompt | Static config |
| `language_patterns.py` | Vocab substitutions + greeting patterns applied post-LLM | Time of day, role |
| `behavior_engine.py` | Response-depth decision (time + query complexity + device) | Already-known: time, task, device |
| `privacy_engine.py` | PII regex redaction before Qdrant store | Text content |
| `humor_engine.py` | Situational phrase suggestions (late night, post-success, frustrated) | Time + recent failure/success |
| `relationship_memory.py` | Lazy user profile built from `agent_logs` + `messages` (work hours, common tasks, approval rate) | SQL aggregates |
| `explainability.py` | New `POST /explain/:trace_id` endpoint returns reasoning chain for any past turn | `agent_logs` rows by trace_id |

### v2 DEFERRED — each listed with what's missing

| Module | Why deferred | What we'd need first |
|---|---|---|
| `predictive_context.py` | No calendar read, no email read | Gmail READ + Google Calendar READ (1 week each) |
| `energy_tracking.py` | No typing-speed signal (our inputs arrive as finalized text) | Browser-side typing telemetry; opt-in |
| `multimodal_context.py` | No active-window or clipboard access | Native helper app (privacy-sensitive; needs user config UI) |
| `delegation_engine.py` | Approval history is too sparse (< 10 rows) | Wait 2 weeks of real use → compute approval rates, then ship |
| `orchestration_intelligence.py` | CRUZ already orchestrates via tool_use; workflow-mediation is overkill until agent conflicts actually happen | Real inter-agent conflict event; ship reactively |
| `interruption_intelligence.py` | No notification delivery system yet (FCM not built — that's voice v2 Phase 2) | FCM push + notification DB model |
| `failure_recovery.py` | Already 80% implemented (Qdrant graceful, Inworld fallback, Deepgram retry); generalising is YAGNI | Concrete 3rd failure pattern to extract from |
| `voice_intelligence.py` | Aura-2's SSML support is limited to a subset; emphasis/pauses need custom research | 2 days experimentation with the TTS `<break>` + `<emphasis>` tags |
| `learning_engine.py` | A/B testing at single-user scale is statistically meaningless — need multi-user signal | Multi-user (future) OR explicit user-feedback thumbs-up/down wiring |

## 3. Architecture

```
agents/cruz/persona/                 ← new package
├── __init__.py                      ← exports PersonaLayer
├── core_identity.yaml               ← the facts
├── identity_loader.py               ← parses YAML → system-prompt snippet
├── language_patterns.py             ← vocab + greetings
├── behavior_engine.py               ← response-depth + time-context
├── privacy_engine.py                ← PII redaction
├── humor_engine.py                  ← situational phrase picker
├── relationship_memory.py           ← user profile (cached)
└── explainability.py                ← reasoning chain builder

agents/cruz/cruz_agent.py             ← MODIFY: inject persona pre/post hooks
backend/api/main.py                   ← MODIFY: add GET /explain/:trace_id
tests/agents/persona/                 ← one test per module
```

## 4. Integration into CRUZ

Two integration points (minimal — we don't rewrite CruzAgent):

### 4.1 Pre-LLM: inject personality into system prompt

In both `process()` and `stream_response()`, after `system_prompt` is built, append:

```python
from agents.cruz.persona import PersonaLayer
persona = PersonaLayer.get()  # singleton
system_prompt = persona.augment_system_prompt(
    base=system_prompt,
    user_id=user_id,
    device=device,
    now=datetime.now().astimezone(),
)
```

The augmenter adds:
- Core identity block (from YAML)
- Response-depth hint (brief / normal / detailed)
- Time-of-day context ("it's 11 PM; user is likely winding down")
- User profile summary (if available)
- Relevant humor permission flag ("humor=ok" or "humor=off; recent failure")

### 4.2 Post-LLM: vocab + privacy pass

```python
text = persona.apply_language_patterns(text)  # "do" → "handle", etc.
text = persona.sanitize_for_memory(text)      # PII redact before Qdrant store
```

### 4.3 New endpoint for explainability

```
GET /explain/:trace_id
→ { summary: "I delegated to qt because...", tool_chain: [...] }
```

## 5. Data model — zero new tables

v1 uses existing tables:
- `agent_logs` — for profile aggregates + explainability chains
- `messages` — for conversation patterns
- `voice_sessions` — for voice-mode preference inference

No migrations needed.

## 6. Success criteria

- [ ] CRUZ's replies noticeably match the personality matrix (user test: "does it feel like JARVIS?")
- [ ] Late-night messages get "Morning Mode Off" briefness automatically
- [ ] Same vocab ("handle", "noted", "wrapped up") across all replies
- [ ] Credit-card-like strings never land in Qdrant
- [ ] `GET /explain/:trace_id` returns a human-readable reasoning chain for any past turn
- [ ] No regression in the 1148 existing pytest tests
- [ ] Adds ~7 focused tests (one per module)

## 7. Non-goals v1

- Learning feedback loops (deferred to v2)
- Proactive suggestions (deferred — needs interruption channel)
- Voice TTS tone/rate adjustments (deferred)
- UI changes (v2 may show "why" button per event)

## 8. Effort

7 small files, ~1000 LOC Python, ~7 tests, 2 integration points. One focused coding session.
