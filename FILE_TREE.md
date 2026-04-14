# CRUZ AI System — File Tree

Generated: 2026-04-14

Excludes: `.git/`, `venv/`, `__pycache__/`, `.pytest_cache/`, `node_modules/`, `.DS_Store`, `*.pyc`

```
cruz-ai-system/
├── .claude/
│   └── settings.local.json
├── agents/                                    # All CRUZ agents (extend BaseAgent)
│   ├── catch/
│   │   ├── __init__.py
│   │   └── catch_agent.py                     # Meeting transcription, action items
│   ├── cruz/
│   │   ├── __init__.py
│   │   └── cruz_agent.py                      # Main assistant — entry point
│   ├── echo/
│   │   ├── __init__.py
│   │   └── echo_agent.py                      # Email drafts, proposals
│   ├── forge/
│   │   ├── __init__.py
│   │   └── forge_agent.py                     # Code gen, bug fixes, refactors
│   ├── general/
│   │   ├── __init__.py
│   │   └── general_agent.py                   # Catch-all sub-agent
│   ├── mark/
│   │   ├── __init__.py
│   │   └── mark_agent.py                      # Docs, README, changelogs
│   ├── pm/
│   │   ├── __init__.py
│   │   └── pm_agent.py                        # Sprint planning, task breakdown
│   ├── pulse/
│   │   ├── __init__.py
│   │   └── pulse_agent.py                     # Daily briefings, news
│   ├── qt/
│   │   ├── __init__.py
│   │   └── qt_agent.py                        # Tests, security scans
│   ├── raw/
│   │   ├── __init__.py
│   │   └── raw_agent.py                       # Research, dep updates
│   ├── reach/
│   │   ├── __init__.py
│   │   └── reach_agent.py                     # Lead research, outreach
│   ├── relay/
│   │   ├── __init__.py
│   │   └── relay_agent.py                     # Keyword classifier (no LLM)
│   ├── sentinel/
│   │   ├── __init__.py
│   │   └── sentinel_agent.py                  # Code review, security audit
│   ├── titan/
│   │   ├── __init__.py
│   │   └── titan_agent.py                     # Deployments, CI/CD, rollbacks
│   ├── __init__.py
│   └── base_agent.py                          # Mandatory parent for all agents
│
├── backend/
│   ├── api/
│   │   └── main.py                            # FastAPI app, SSE streaming
│   ├── models/
│   │   └── schema.sql                         # Source-of-truth schema
│   ├── services/                              # (placeholder)
│   └── requirements.txt
│
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-04-12-cruz-implementation-plan.md
│
├── logs/
│   ├── .gitignore
│   └── .gitkeep
│
├── migrations/                                # Alembic versioned migrations
│   ├── versions/
│   │   ├── 0001_initial_schema.py
│   │   └── 0002_uuid_conversations_and_user_preferences.py
│   ├── README
│   ├── env.py
│   └── script.py.mako
│
├── services/                                  # Shared infrastructure singletons
│   ├── __init__.py
│   ├── conversation.py                        # Conversation/message persistence
│   ├── db.py                                  # PostgreSQL async pool
│   ├── device_handoff.py                      # Cross-device continuity
│   ├── email.py                               # Gmail / SendGrid
│   ├── embedding.py                           # all-MiniLM-L6-v2
│   ├── github.py                              # GitHub API
│   ├── notion.py                              # Notion API
│   ├── ollama.py                              # Local model client
│   ├── plane.py                               # Plane.so PM integration
│   ├── qdrant.py                              # Vector DB client
│   ├── redis_client.py                        # Redis async
│   ├── semantic_memory.py                     # Qdrant + embeddings
│   └── voice.py                               # Whisper STT + Inworld TTS
│
├── tests/
│   ├── agents/                                # One test file per agent
│   │   ├── __init__.py
│   │   ├── test_agent_logging.py
│   │   ├── test_base_agent.py
│   │   ├── test_catch_agent.py
│   │   ├── test_cruz_agent.py
│   │   ├── test_cruz_conversation.py
│   │   ├── test_cruz_device_handoff.py
│   │   ├── test_cruz_semantic.py
│   │   ├── test_echo_agent.py
│   │   ├── test_forge_agent.py
│   │   ├── test_general_agent.py
│   │   ├── test_mark_agent.py
│   │   ├── test_pm_agent.py
│   │   ├── test_pulse_agent.py
│   │   ├── test_qt_agent.py
│   │   ├── test_raw_agent.py
│   │   ├── test_reach_agent.py
│   │   ├── test_relay_agent.py
│   │   ├── test_sentinel_agent.py
│   │   └── test_titan_agent.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── test_command_device.py
│   │   ├── test_command_endpoint.py
│   │   ├── test_conversations_endpoint.py
│   │   ├── test_health_endpoint.py
│   │   ├── test_logs_endpoint.py
│   │   ├── test_missing_endpoints.py
│   │   ├── test_startup_validation.py
│   │   ├── test_streaming.py
│   │   └── test_voice_endpoint.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_forge_echo.py
│   │   └── test_real_db.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── test_conversation.py
│   │   ├── test_db.py
│   │   ├── test_device_handoff.py
│   │   ├── test_email.py
│   │   ├── test_embedding.py
│   │   ├── test_github.py
│   │   ├── test_notion.py
│   │   ├── test_ollama.py
│   │   ├── test_plane.py
│   │   ├── test_qdrant.py
│   │   ├── test_redis_client.py
│   │   ├── test_semantic_memory.py
│   │   └── test_voice.py
│   ├── workers/
│   │   ├── __init__.py
│   │   └── test_arq_worker.py
│   ├── __init__.py
│   └── conftest.py
│
├── workers/                                   # ARQ background workers
│   ├── tasks/
│   │   ├── __init__.py
│   │   ├── pulse_tasks.py                     # 6 AM daily briefing
│   │   ├── raw_tasks.py                       # 3 AM research update
│   │   └── reach_tasks.py                     # 2 AM lead generation
│   ├── __init__.py
│   └── arq_worker.py                          # Worker entrypoint
│
├── .env                                       # (gitignored)
├── .env.example
├── .gitignore
├── CLAUDE.md                                  # Project bible
├── Orchestration.md
├── PRD.md
├── PROGRESS.md
├── PROMPTS.md
├── QUICK_START_DAY3.md
├── README.md
├── SETUP.md
├── Tech.md
├── Tool.md
├── alembic.ini
├── docker-compose.yml
├── ecosystem.config.js                        # PM2 process config
├── pytest.ini
├── requirements.txt
└── setup_claude_code_docs.sh
```

**Totals:** 36 directories, 132 files
