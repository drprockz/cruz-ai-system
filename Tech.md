CRUZ AI System - Complete Tech Stack



By Darshan Parmar

2 min

See views

Add a reaction
CRUZ AI System - Complete Tech Stack
Document Control
Document Title

Complete Technology Stack for CRUZ AI System

Version 

1.0 

Author 

Darshan Parmar 

Date 

April 12, 2026 

Status 

Final 

Table of Contents
Infrastructure & Hardware

Operating System & Runtime

Programming Languages

Backend Frameworks & APIs

Frontend Technologies

Mobile Development

Databases

AI Models & Machine Learning

Voice Technologies

Task Queue & Background Jobs

Agent Orchestration

Development Tools

Testing & Quality

DevOps & Deployment

Monitoring & Logging

Security & Authentication

External APIs & Integrations

Libraries & Dependencies

Complete Package List

Infrastructure & Hardware
Physical Infrastructure
Component

Specification

Purpose

Command Center 

Mac Mini M4 (24GB RAM, 256GB SSD) 

Central server running all CRUZ services 

Processor 

Apple M4 chip (10-core CPU, 10-core GPU) 

Runs Ollama models, handles parallel processing 

Memory 

24GB Unified Memory 

Sufficient for 2 AI models + databases + services 

Storage 

256GB SSD 

macOS + databases + AI models 

UPS 

1000VA UPS (APC/Luminous) 

Power backup for 30-60 min 

Backup Drive 

2TB External HDD (Seagate/WD) 

Daily backups 

Network 

200 Mbps Fiber (Already owned) 

Internet connectivity 

Router 

Dual-band WiFi Router 

Network infrastructure 

Client Devices
Device

Specification

Access Method

ThinkPad 

32GB RAM, Intel i7 

Web dashboard, SSH, Tailscale 

Nothing Phone 2 

Android 14 

PWA/React Native app, voice commands 

iPad 

iPadOS 17 

Web dashboard (optional) 

Operating System & Runtime
Operating System


Primary OS:
  Name: macOS Sequoia
  Version: 15.x
  Architecture: ARM64 (Apple Silicon)
  Features:
    - FileVault (disk encryption)
    - Built-in firewall
    - Metal GPU acceleration
    - Unix-based (BSD)
System Services:
  - launchd (service management)
  - Spotlight (indexing)
  - Time Machine (backups)
Runtime Environments
Runtime

Version

Purpose

Node.js 

20.x LTS 

JavaScript runtime for backend 

Python 

3.11+ 

AI agents, FastAPI, Whisper 

Bun 

Latest (optional) 

Faster JS runtime alternative 

Ollama 

Latest 

Local LLM serving runtime 

Docker 

Latest 

Container runtime (Qdrant) 

Programming Languages
Primary Languages


Python 3.11+:
  Purpose: 
    - AI agent logic
    - FastAPI backend
    - Whisper STT
    - Data processing
  Key Features:
    - Async/await support
    - Type hints (Python 3.11+)
    - Virtual environments
TypeScript 5.x:
  Purpose:
    - Frontend (React)
    - Type-safe backend (optional)
    - Agent types/interfaces
  Key Features:
    - Static typing
    - ES2023+ support
    - Strict mode
JavaScript ES2023+:
  Purpose:
    - Node.js backend
    - Task queues (BullMQ)
    - Build scripts
  Key Features:
    - Async/await
    - Modules (ESM)
    - Modern syntax
SQL:
  Purpose:
    - PostgreSQL queries
    - Database schema
    - Complex queries
  Dialect: PostgreSQL 16
Bash/Shell:
  Purpose:
    - Deployment scripts
    - Automation
    - System administration
  Shell: zsh (macOS default)
Backend Frameworks & APIs
API Framework


FastAPI:
  Version: 0.110+
  Language: Python
  Features:
    - Automatic OpenAPI docs
    - Async support
    - WebSocket support
    - Type validation (Pydantic)
    - CORS middleware
  Endpoints:
    - REST API (HTTP)
    - WebSocket (real-time)
    - Server-Sent Events (SSE)
Alternative (Optional):
  Express.js:
    Version: 4.x
    Language: Node.js
    Use: Backup API server
API Documentation


Swagger/OpenAPI:
  Version: 3.0
  Auto-generated: Yes (via FastAPI)
  UI: Swagger UI (built-in)
  Access: http://localhost:3000/docs
Redoc:
  Alternative documentation UI
  Access: http://localhost:3000/redoc
ASGI Server


Uvicorn:
  Version: Latest
  Purpose: ASGI server for FastAPI
  Features:
    - HTTP/1.1 and HTTP/2
    - WebSocket
    - ASGI 3.0 spec
  Production: 
    Workers: 4 (CPU cores)
    Host: 0.0.0.0
    Port: 3000
Frontend Technologies
Core Framework


React:
  Version: 18.x
  Purpose: Web dashboard UI
  Features:
    - Hooks (useState, useEffect, etc.)
    - Concurrent rendering
    - Server components (future)
  Build: Vite 6.x
TypeScript:
  Version: 5.x
  Strict mode: Enabled
  Config: tsconfig.json
Build Tools


Vite:
  Version: 6.x
  Features:
    - Fast HMR (Hot Module Replacement)
    - ESBuild bundler
    - TypeScript support
    - React Fast Refresh
  Plugins:
    - @vitejs/plugin-react
    - vite-plugin-pwa
ESBuild:
  Purpose: Bundler (via Vite)
  Speed: 10-100x faster than Webpack
UI Framework & Components


Tailwind CSS:
  Version: 4.x
  Features:
    - Utility-first CSS
    - JIT (Just-In-Time) compiler
    - Dark mode support
    - Custom color palette
  Config: tailwind.config.js
shadcn/ui:
  Purpose: Component library
  Components:
    - Button, Input, Select
    - Dialog, Dropdown, Toast
    - Sheet, Tabs, Card
  Base: Radix UI primitives
  Styling: Tailwind CSS
Radix UI:
  Version: Latest
  Purpose: Unstyled accessible components
  Components:
    - Dialog, DropdownMenu
    - Popover, Toast
    - Tabs, Accordion
State Management


Zustand:
  Version: Latest
  Purpose: Global state management
  Features:
    - Minimal boilerplate
    - React hooks API
    - DevTools support
    - Persist middleware
  Stores:
    - userStore (user session)
    - agentStore (agent status)
    - taskStore (active tasks)
HTTP Client


Axios:
  Version: Latest
  Purpose: HTTP requests to FastAPI
  Features:
    - Interceptors
    - Request/response transformation
    - Automatic JSON parsing
    - Error handling
  Config: Base URL, timeout, headers
TanStack Query (React Query):
  Version: 5.x
  Purpose: Server state management
  Features:
    - Caching
    - Automatic refetching
    - Optimistic updates
    - Pagination/infinite queries
Routing


React Router:
  Version: 6.x
  Purpose: Client-side routing
  Routes:
    - / (Dashboard)
    - /agents (Agent status)
    - /tasks (Task list)
    - /settings (Configuration)
Real-Time Communication


Socket.io Client:
  Version: 4.x
  Purpose: WebSocket client
  Features:
    - Auto-reconnection
    - Event-based communication
    - Room support
  Events:
    - agent_status_update
    - task_completed
    - new_message
Icons & Fonts


Lucide React:
  Version: Latest
  Purpose: Icon library
  Icons: 1000+ open source icons
  Usage: Tree-shakable imports
Google Fonts:
  Fonts:
    - Inter (UI text)
    - JetBrains Mono (code)
  Loading: Self-hosted for performance
Mobile Development
Cross-Platform Framework


React Native (Optional):
  Version: 0.73+
  Purpose: Native mobile app
  Platforms: iOS, Android
  Alternative: PWA via Vite
Progressive Web App (PWA):
  Framework: Vite PWA Plugin
  Features:
    - Installable on mobile
    - Offline support
    - Push notifications
  Manifest: manifest.json
  Service Worker: Auto-generated
Mobile Features


Push Notifications:
  Service: Firebase Cloud Messaging (FCM)
  Platforms: Android, iOS, Web
Camera/Microphone:
  Access: Web APIs (getUserMedia)
  Permissions: Native prompts
Geolocation:
  API: Navigator.geolocation
  Purpose: Location-aware responses
Databases
Primary Database (PostgreSQL)


PostgreSQL:
  Version: 16.x
  Installation: Homebrew (macOS)
  Port: 5432
  Database: cruz_db
  User: cruz
  Schema:
    Tables:
      - users
      - tasks
      - agent_logs
      - conversations
      - messages
      - agent_state
      - documents
      - projects
  Features:
    - JSONB columns (flexible data)
    - Full-text search (tsvector)
    - Indexes (performance)
    - Foreign keys (referential integrity)
    - Triggers (automation)
  Extensions:
    - pg_trgm (fuzzy search)
    - pgcrypto (encryption)
  Backup:
    - pg_dump daily to Google Drive
    - Point-in-time recovery (WAL)
ORM


Prisma:
  Version: 6.x
  Language: TypeScript/JavaScript
  Features:
    - Type-safe queries
    - Migrations
    - Schema visualization
    - Query builder
  Schema: schema.prisma
Alternative (Python):
  SQLAlchemy:
    Version: 2.x
    Purpose: Python ORM
    Features:
      - Session management
      - Complex queries
      - Relationships
In-Memory Cache (Redis)


Redis:
  Version: 7.x
  Installation: Homebrew (macOS)
  Port: 6379
  Use Cases:
    - Session storage
    - Task queue (BullMQ)
    - Pub/Sub (real-time updates)
    - Cache (API responses)
    - Agent state (temporary)
  Data Structures:
    - Strings (simple cache)
    - Lists (queues)
    - Sets (unique values)
    - Hashes (objects)
    - Sorted Sets (leaderboards)
  Persistence:
    - RDB snapshots (hourly)
    - AOF append-only file (optional)
  Client Libraries:
    - ioredis (Node.js)
    - redis-py (Python)
Vector Database (Qdrant)


Qdrant:
  Version: Latest
  Installation: Docker container
  Port: 6333
  Purpose: Semantic memory/search
  Collections:
    - cruz_memory (conversation vectors)
    - document_vectors (RAW agent research)
  Vector Size: 384 dimensions
  Distance Metric: Cosine similarity
  Features:
    - Semantic search
    - Filtering (metadata)
    - Batch operations
    - HNSW index (fast search)
  Client: qdrant-client (Python)
  Embedding Model: 
    sentence-transformers/all-MiniLM-L6-v2
AI Models & Machine Learning
Cloud AI Services


Anthropic Claude:
  Models:
    - Claude Sonnet 4 (claude-sonnet-4-20250514)
  Access:
    - Claude Max Subscription (₹1,660/month)
    - API Key (via Anthropic Console)
  Usage:
    - FORGE agent (code generation)
    - SENTINEL agent (code review)
    - Relay agent (command parsing)
  SDK:
    - anthropic (Python)
    - @anthropic-ai/sdk (TypeScript)
  Features:
    - 200k context window
    - Streaming responses
    - System prompts
    - Tool use (function calling)
Google Gemini:
  Model: gemini-flash-2.5
  Access:
    - Free tier (250 requests/day)
    - API Key (Google AI Studio)
  Usage:
    - REACH agent (supplementary research)
  SDK:
    - google-generativeai (Python)
  Features:
    - Fast inference
    - Multimodal (text, images)
    - 2M token context window
Local AI Models (Ollama)


Ollama:
  Version: Latest
  Installation: curl install script
  Service: ollama serve
  Port: 11434
  Models:
    Qwen 2.5 Coder:
      Size: 14B parameters
      Quantization: Q4_0 (8GB RAM)
      Context: 32k tokens
      Purpose: Code-focused tasks
      Agents: REACH, ECHO, PM, TITAN, MARK, QT
    Llama 3.1:
      Size: 8B parameters
      Quantization: Q4_0 (5GB RAM)
      Context: 128k tokens
      Purpose: General tasks
      Agents: RAW, PULSE
    Whisper Large v3:
      Size: 1.5B parameters
      Purpose: Speech-to-text
      Agent: CATCH
      Languages: 99 languages
      Accuracy: >98% (English)
  API:
    - Compatible with OpenAI API
    - HTTP REST API
    - Streaming support
  Features:
    - Model management (pull/push/delete)
    - GPU acceleration (Metal on Mac)
    - Multi-model serving
    - Concurrent requests
Embedding Model


Sentence Transformers:
  Model: all-MiniLM-L6-v2
  Size: 80MB
  Dimensions: 384
  Purpose:
    - Generate embeddings for Qdrant
    - Semantic search
    - Document similarity
  Library: sentence-transformers (Python)
  Performance:
    - Inference: ~20ms per sentence
    - Batch processing: 100 sentences/sec
Voice AI Services


Inworld TTS:
  Model: tts-1.5-max
  Features:
    - Natural voice synthesis
    - Voice cloning (5-15 sec audio)
    - 271+ pre-built voices
    - WebSocket streaming
    - Word-level timestamps
    - Emotion tags
  Pricing: $10 per 1M characters
  Monthly: ₹187 (Months 1-2), ₹71 (Month 3+)
  API: 
    - REST (https://api.inworld.ai/v1/tts)
    - WebSocket (wss://tts.inworld.ai/v1/stream)
  Output Formats:
    - MP3, WAV, PCM
    - Sample rates: 16kHz, 24kHz, 48kHz
Voice Technologies
Speech-to-Text (STT)


OpenAI Whisper:
  Model: large-v3
  Size: 1.5GB
  Installation: pip install openai-whisper
  Features:
    - 99 languages
    - Automatic language detection
    - Timestamps
    - Word-level confidence
  Accuracy: >98% (English)
  Latency: ~500ms for 5-second audio
  Alternatives (Backup):
    Deepgram:
      Model: nova-3
      Latency: ~150ms (cloud)
      Free tier: 200 hours/month
Text-to-Speech (TTS)


Inworld TTS 1.5 Max:
  (See AI Models section above)
Backup/Free Options:
  Web Speech API:
    Platforms: Browser-based
    Quality: 7/10 (iOS/Mac), 5/10 (Windows)
    Cost: Free
  macOS 'say' command:
    Quality: 3/10 (robotic)
    Languages: 30+
    Offline: Yes
Wake Word Detection


Porcupine:
  Version: 3.x
  Provider: Picovoice
  Wake Words:
    - "Hey CRUZ" (custom trained)
    - "Jarvis" (pre-built)
  Features:
    - On-device processing
    - Low CPU usage (<1%)
    - Cross-platform
  Accuracy: >95%
  False Positives: <1%
  SDK:
    - @picovoice/porcupine-node (Node.js)
    - pvporcupine (Python)
  License: Free for personal use
Audio Processing


Web Audio API:
  Platform: Browser
  Features:
    - Audio capture (microphone)
    - Audio playback (speaker)
    - Real-time processing
    - Audio analysis (waveform)
  Nodes:
    - MediaStreamSource (input)
    - AudioDestination (output)
    - AnalyserNode (visualization)
Python Audio Libraries:
  sounddevice:
    Purpose: Record/playback audio
  numpy:
    Purpose: Audio data processing
  scipy:
    Purpose: Audio file I/O
Task Queue & Background Jobs
Queue System


BullMQ:
  Version: 5.x
  Platform: Node.js
  Backend: Redis
  Queues (11 total, one per agent):
    - reach-queue
    - catch-queue
    - echo-queue
    - pm-queue
    - forge-queue
    - titan-queue
    - mark-queue
    - qt-queue
    - sentinel-queue
    - raw-queue
    - pulse-queue
  Features:
    - Job scheduling
    - Retries with exponential backoff
    - Priority queues
    - Job progress tracking
    - Job completion events
    - Concurrency control
  Worker Configuration:
    Concurrency: 2-4 per agent
    Retry: 3 attempts max
    Backoff: Exponential (2s, 4s, 8s)
  UI (Optional):
    - Bull Board (web dashboard)
    - Access: http://localhost:3001
Cron/Scheduling


Node-Cron:
  Version: Latest
  Purpose: Scheduled tasks
  Jobs:
    Morning Briefing:
      Schedule: "0 6 * * *" (6 AM daily)
      Agent: PULSE
    Database Backup:
      Schedule: "0 2 * * *" (2 AM daily)
      Task: pg_dump to Google Drive
    Lead Generation:
      Schedule: "0 22 * * *" (10 PM daily)
      Agent: REACH (optional, on-demand)
Alternative:
  PM2 Cron:
    Purpose: Schedule PM2 tasks
    Config: ecosystem.config.js
Agent Orchestration
Multi-Agent Framework


CrewAI:
  Version: Latest
  Language: Python
  Features:
    - Multi-agent coordination
    - Task delegation
    - Agent communication
    - Hierarchical workflows
  Agents:
    - Each of 11 CRUZ agents
    - Relay as manager/coordinator
  Alternative:
    LangGraph:
      Purpose: State machine orchestration
      Features: Visual workflows, cycles
    AutoGen:
      Purpose: Multi-agent conversations
      Microsoft framework
Process Management


PM2:
  Version: 5.x
  Purpose: Keep services running 24/7
  Processes:
    - cruz-api (FastAPI)
    - cruz-workers (BullMQ workers)
    - ollama-service
  Features:
    - Auto-restart on crash
    - Load balancing
    - Log management (rotation)
    - Startup on boot
    - Monitoring dashboard
  Config: ecosystem.config.js
  Commands:
    - pm2 start ecosystem.config.js
    - pm2 status
    - pm2 logs
    - pm2 restart all
    - pm2 save (persist)
Development Tools
Code Editors


VS Code:
  Version: Latest
  Extensions:
    - Python (Microsoft)
    - ESLint
    - Prettier
    - Tailwind CSS IntelliSense
    - Prisma
    - GitLens
    - Thunder Client (API testing)
    - Docker
    - PostgreSQL Explorer
  Settings:
    - Format on save
    - Auto imports
    - Type checking
Version Control


Git:
  Version: 2.x+
  Platform: Local + GitHub
  Workflow:
    - main (production)
    - develop (staging)
    - feature/* (features)
  Hooks:
    - pre-commit (linting)
    - pre-push (tests)
GitHub:
  Organization: simple-inc-dev (or your choice)
  Repository: cruz-ai-system (private)
  Features:
    - Issues (bug tracking)
    - Projects (kanban)
    - Actions (CI/CD)
    - Releases (versioning)
Linting & Formatting


ESLint:
  Version: 9.x
  Config: eslint.config.js
  Rules: Airbnb + custom
  Plugins:
    - @typescript-eslint
    - eslint-plugin-react
    - eslint-plugin-react-hooks
Prettier:
  Version: 3.x
  Config: .prettierrc
  Settings:
    - Semi: true
    - Single quotes: true
    - Trailing comma: es5
    - Tab width: 2
Python:
  Black:
    Purpose: Code formatter
    Line length: 88
  Ruff:
    Purpose: Fast linter
    Rules: Similar to flake8 + isort
Testing & Quality
Testing Frameworks


Python Testing:
  Pytest:
    Version: Latest
    Purpose: Unit tests
    Plugins:
      - pytest-asyncio (async tests)
      - pytest-cov (coverage)
      - pytest-mock (mocking)
    Structure:
      tests/
        ├── unit/
        ├── integration/
        └── conftest.py
JavaScript Testing:
  Vitest:
    Version: 2.x
    Purpose: Unit tests (Vite-native)
    Features:
      - Fast (ESBuild)
      - TypeScript support
      - Watch mode
      - Coverage (c8)
  React Testing Library:
    Purpose: Component testing
    Features: User-centric testing
E2E Testing


Playwright:
  Version: Latest
  Purpose: Browser automation
  Browsers:
    - Chromium
    - Firefox
    - WebKit (Safari)
  Features:
    - Auto-wait
    - Screenshots
    - Video recording
    - Network interception
  Tests:
    - User flows
    - Voice interaction
    - Agent status checks
API Testing


Postman:
  Version: Free tier
  Purpose: Manual API testing
  Collections:
    - CRUZ API endpoints
    - Authentication flows
    - Agent commands
Alternative:
  Thunder Client (VS Code extension)
  HTTPie (CLI tool)
Code Coverage


Coverage Tools:
  Python:
    - pytest-cov
    - Target: >80%
  JavaScript:
    - c8 (native coverage)
    - Target: >80%
  Reports:
    - Terminal output
    - HTML reports
    - GitHub Actions integration
DevOps & Deployment
Containerization


Docker:
  Version: Latest
  Platform: macOS (Docker Desktop)
  Containers:
    Qdrant:
      Image: qdrant/qdrant
      Port: 6333
      Volume: ./qdrant_storage
    PostgreSQL (Optional backup):
      Image: postgres:16
      Port: 5432
    Redis (Optional backup):
      Image: redis:7
      Port: 6379
  Docker Compose:
    File: docker-compose.yml
    Services: qdrant, postgres, redis
CI/CD


GitHub Actions:
  Workflows:
    - test.yml (run tests on push)
    - deploy.yml (deploy on merge to main)
    - lint.yml (code quality checks)
  Triggers:
    - push to main/develop
    - pull request
    - manual dispatch
  Steps:
    1. Checkout code
    2. Setup Node/Python
    3. Install dependencies
    4. Run linters
    5. Run tests
    6. Build artifacts
    7. Deploy (optional)
  Secrets:
    - ANTHROPIC_API_KEY
    - INWORLD_API_KEY
    - DATABASE_URL
Deployment


Self-Hosted (Mac Mini):
  Method: PM2 + systemd (auto-start)
  Domain: cruz.simpleinc.cloud
  SSL: Let's Encrypt (Cloudflare)
  Process:
    1. git pull origin main
    2. npm install / pip install
    3. Build frontend (npm run build)
    4. Run migrations (prisma migrate)
    5. pm2 restart all
Cloud Hosting (Backup):
  Vercel:
    Purpose: Frontend hosting
    Deployment: Auto from GitHub
  Railway:
    Purpose: Backend API (backup)
    Free tier: $5 credit/month
Reverse Proxy & SSL


Cloudflare Tunnel:
  Purpose: Expose Mac Mini securely
  Domain: cruz.simpleinc.cloud
  Features:
    - Free SSL certificate
    - DDoS protection
    - CDN
    - No port forwarding needed
  Setup:
    1. Install cloudflared
    2. Login to Cloudflare
    3. Create tunnel
    4. Point to localhost:3000
Alternative:
  Tailscale:
    Purpose: VPN mesh network
    Devices: Mac Mini, Phone, ThinkPad
    Access: Secure remote access
Monitoring & Logging
Application Monitoring


Uptime Kuma:
  Version: Latest
  Installation: Docker or npm
  Port: 3001
  Monitors:
    - FastAPI (http://localhost:3000/health)
    - PostgreSQL (port 5432)
    - Redis (port 6379)
    - Qdrant (port 6333)
    - Ollama (port 11434)
  Notifications:
    - Slack webhook
    - Telegram bot
    - Email (optional)
  Dashboard:
    - Service status
    - Response times
    - Uptime percentage
    - Historical data
Log Management


Grafana Loki:
  Version: Latest
  Installation: Docker
  Port: 3100
  Log Sources:
    - PM2 logs
    - FastAPI logs
    - Agent execution logs
    - System logs
  Features:
    - Centralized logging
    - Full-text search
    - Label-based filtering
    - Retention policies
  Visualization: Grafana (port 3000)
Alternative:
  Winston (Node.js):
    Purpose: Application logging
    Levels: error, warn, info, debug
    Transports: Console, file, HTTP
Error Tracking


Sentry (Optional):
  Version: Latest
  Plan: Free tier (5k events/month)
  Integration:
    - Python SDK (@sentry/python)
    - JavaScript SDK (@sentry/browser)
  Features:
    - Error grouping
    - Stack traces
    - User context
    - Release tracking
  Alerts:
    - Email notifications
    - Slack integration
Metrics & Analytics


Prometheus (Optional):
  Purpose: Metrics collection
  Port: 9090
  Metrics:
    - HTTP requests (count, latency)
    - Database queries
    - Queue lengths
    - Model inference time
  Exporters:
    - node_exporter (system metrics)
    - postgres_exporter
    - redis_exporter
Grafana:
  Purpose: Metrics visualization
  Dashboards:
    - System overview
    - Agent performance
    - API latency
    - Database stats
Security & Authentication
Security Tools


Bitwarden:
  Purpose: Password/secrets manager
  Plan: Free tier
  Stored:
    - API keys (Claude, Inworld, Gemini)
    - Database passwords
    - SSH keys
    - Webhook secrets
  Access: Browser extension + CLI
macOS Security:
  FileVault:
    Purpose: Disk encryption
    Algorithm: AES-XTS 256-bit
  Firewall:
    Status: Enabled
    Rules: Block all incoming except allowed
  Gatekeeper:
    Purpose: App verification
    Status: Enabled
SSL/TLS


Let's Encrypt:
  Purpose: Free SSL certificates
  Renewal: Automatic (90 days)
  Domain: cruz.simpleinc.cloud
  Certbot:
    Installation: Homebrew
    Renewal: Cron job (daily check)
Authentication


JWT (JSON Web Tokens):
  Library: PyJWT (Python), jsonwebtoken (JS)
  Token Types:
    - Access token (15 min expiry)
    - Refresh token (7 days)
  Algorithm: HS256
  Secret: Stored in .env
Session Management:
  Store: Redis
  Expiry: 24 hours
  Cookie: httpOnly, secure, sameSite
API Security


Rate Limiting:
  Library: slowapi (Python FastAPI)
  Limits:
    - 100 requests/min per IP
    - 1000 requests/hour per user
CORS:
  Allowed Origins:
    - http://localhost:5173 (dev)
    - https://cruz.simpleinc.cloud (prod)
  Methods: GET, POST, PUT, DELETE
  Headers: Authorization, Content-Type
API Key Management:
  .env file (never committed)
  Environment variables
  Bitwarden backup
External APIs & Integrations
Communication


Gmail API:
  Purpose: Send/receive emails (ECHO agent)
  Scope: gmail.send, gmail.readonly
  Auth: OAuth 2.0
Google Calendar API:
  Purpose: Schedule, events (PULSE agent)
  Scope: calendar.readonly
SendGrid:
  Purpose: Transactional emails
  Free tier: 100 emails/day
  API Key: Stored in Bitwarden
Slack API:
  Purpose: Team chat integration
  Webhooks: Incoming webhooks
  Bot: Post updates to channels
Telegram Bot API:
  Purpose: Mobile command interface
  Bot: @CRUZBot (custom)
  Features: Commands, notifications
Project Management


Plane.so API:
  Purpose: Task management
  Endpoints:
    - Create issues
    - Update status
    - Get sprints
  Auth: API token
  Integration:
    - PM agent reads/writes tasks
    - Daily sprint summaries
Notion API:
  Version: 2022-06-28
  Purpose: Knowledge base, CRM
  Databases:
    - Clients
    - Leads
    - Projects
    - Meeting notes
  Integration:
    - CATCH saves transcripts
    - MARK syncs documentation
    - REACH saves leads
Lead Generation


Apollo.io API:
  Purpose: B2B lead database
  Free tier: 50 credits/month
  Endpoints:
    - Search companies
    - Get contact info
    - Export to CSV
Hunter.io API:
  Purpose: Email verification
  Free tier: 50 searches/month
  Features:
    - Find emails
    - Verify emails
    - Domain search
AI Services


Anthropic API:
  (See AI Models section)
Google AI API:
  (See AI Models section)
Inworld API:
  (See Voice Technologies section)
Libraries & Dependencies
Python Libraries


Core:
  - fastapi==0.110.0
  - uvicorn[standard]==0.27.0
  - python-dotenv==1.0.0
  - pydantic==2.6.0
Database:
  - psycopg2-binary==2.9.9
  - redis==5.0.1
  - qdrant-client==1.7.0
  - sqlalchemy==2.0.25 (optional)
AI/ML:
  - anthropic==0.18.0
  - google-generativeai==0.3.2
  - sentence-transformers==2.3.1
  - openai-whisper==20231117
Voice:
  - sounddevice==0.4.6
  - numpy==1.26.3
  - scipy==1.11.4
  - pvporcupine==3.0.0
Testing:
  - pytest==7.4.4
  - pytest-asyncio==0.23.3
  - pytest-cov==4.1.0
  - pytest-mock==3.12.0
Utilities:
  - requests==2.31.0
  - aiohttp==3.9.1
  - python-multipart==0.0.6
  - websockets==12.0
Node.js Libraries


Backend:
  - bullmq==5.1.7
  - ioredis==5.3.2
  - socket.io==4.6.1
  - express==4.18.2 (optional)
Task Queue:
  - bull-board==5.12.0 (UI)
  - node-cron==3.0.3
Utilities:
  - dotenv==16.3.1
  - axios==1.6.5
  - winston==3.11.0 (logging)
Frontend Libraries


Core:
  - react==18.2.0
  - react-dom==18.2.0
  - typescript==5.3.3
  - vite==6.0.0
UI:
  - tailwindcss==4.0.0
  - @radix-ui/react-dialog==1.0.5
  - @radix-ui/react-dropdown-menu==2.0.6
  - lucide-react==0.309.0
State:
  - zustand==4.4.7
  - @tanstack/react-query==5.17.9
Routing:
  - react-router-dom==6.21.1
HTTP:
  - axios==1.6.5
  - socket.io-client==4.6.1
Forms:
  - react-hook-form==7.49.3
  - zod==3.22.4 (validation)
Complete Package List
package.json (Node.js)


{
  "name": "cruz-ai-system",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "api": "node backend/api/server.js",
    "worker": "node backend/workers/index.js"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.21.1",
    "@tanstack/react-query": "^5.17.9",
    "zustand": "^4.4.7",
    "axios": "^1.6.5",
    "socket.io-client": "^4.6.1",
    "lucide-react": "^0.309.0",
    "@radix-ui/react-dialog": "^1.0.5",
    "@radix-ui/react-dropdown-menu": "^2.0.6",
    "react-hook-form": "^7.49.3",
    "zod": "^3.22.4",
    "bullmq": "^5.1.7",
    "ioredis": "^5.3.2",
    "socket.io": "^4.6.1",
    "dotenv": "^16.3.1",
    "node-cron": "^3.0.3",
    "winston": "^3.11.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.47",
    "@types/react-dom": "^18.2.18",
    "@types/node": "^20.10.7",
    "@vitejs/plugin-react": "^4.2.1",
    "typescript": "^5.3.3",
    "vite": "^6.0.0",
    "tailwindcss": "^4.0.0",
    "autoprefixer": "^10.4.16",
    "postcss": "^8.4.33",
    "eslint": "^9.0.0",
    "prettier": "^3.1.1",
    "vitest": "^2.0.0",
    "@testing-library/react": "^14.1.2"
  }
}
requirements.txt (Python)


# FastAPI & Server
fastapi==0.110.0
uvicorn[standard]==0.27.0
python-dotenv==1.0.0
pydantic==2.6.0
python-multipart==0.0.6
# Database
psycopg2-binary==2.9.9
redis==5.0.1
qdrant-client==1.7.0
sqlalchemy==2.0.25
# AI Services
anthropic==0.18.0
google-generativeai==0.3.2
# ML/Embeddings
sentence-transformers==2.3.1
torch==2.1.2
transformers==4.36.2
# Voice
openai-whisper==20231117
sounddevice==0.4.6
numpy==1.26.3
scipy==1.11.4
pvporcupine==3.0.0
# Agent Framework
crewai==0.1.25
langchain==0.1.0
langgraph==0.0.26
# Utilities
requests==2.31.0
aiohttp==3.9.1
websockets==12.0
python-jose[cryptography]==3.3.0
# Testing
pytest==7.4.4
pytest-asyncio==0.23.3
pytest-cov==4.1.0
pytest-mock==3.12.0
httpx==0.26.0
# Integrations
google-auth==2.25.2
google-api-python-client==2.111.0
notion-client==2.2.1
slack-sdk==3.26.1
Summary: Tech Stack at a Glance
Languages
Python 3.11+ (Backend, AI agents)

TypeScript 5.x (Frontend, type safety)

JavaScript ES2023+ (Node.js backend)

SQL (PostgreSQL queries)

Bash/Shell (Automation)

Frameworks
Backend: FastAPI (Python), Express.js (Node, optional)

Frontend: React 18.x + Vite 6.x

Mobile: PWA + React Native (optional)

Databases
PostgreSQL 16 (Primary data)

Redis 7 (Cache, queues)

Qdrant (Vector search)

AI
Cloud: Claude Sonnet 4, Gemini Flash

Local: Qwen 2.5 Coder 14B, Llama 3.1 8B, Whisper Large v3

Voice: Inworld TTS 1.5 Max, Porcupine (wake word)

Infrastructure
Hardware: Mac Mini M4 24GB

Runtime: Node.js 20, Python 3.11, Ollama

Process Mgmt: PM2

Containers: Docker (Qdrant)

DevOps
Version Control: Git + GitHub

CI/CD: GitHub Actions

Deployment: Self-hosted + Vercel (frontend backup)

Monitoring: Uptime Kuma, Grafana Loki

Tools & Services
Project Mgmt: Plane.so, Notion

Communication: Gmail, Slack, Telegram

Lead Gen: AI Sales Platform | Apollo.io - Outbound, Inbound & Automation , Trouver des emails en quelques secondes • Hunter (Email Hunter) 

Security: Bitwarden, Let's Encrypt, FileVault

Total Technologies: 100+ tools, libraries, frameworks, and services  
Primary Stack: Python + TypeScript + PostgreSQL + Redis + Ollama  
Cost: ₹3,288/month (mostly Claude + Inworld)

Complete, production-ready tech stack! 🚀






