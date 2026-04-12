CRUZ AI System - Complete Tools & Services List



By Darshan Parmar

11 min

See views

Add a reaction
CRUZ AI System - Complete Tools & Services List
Document Control
Document Title

Complete Tools, Services & Cost Breakdown for CRUZ

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

AI Models & APIs

Databases & Storage

Development Tools

Project Management

Communication & Collaboration

Lead Generation & Outreach

Deployment & Hosting

Monitoring & Observability

Security & Backup

Total Cost Summary

Infrastructure & Hardware
Mac Mini M4 24GB (Command Center)
Component

Details

Use Case

Cost

Mac Mini M4

24GB RAM, 256GB SSD

Central server running all CRUZ agents 24/7

₹0 (Already owned)

Power Consumption

35W average

Electricity cost for 24/7 operation

₹202/month

UPS (1000VA)

APC/Luminous

Power backup during outages

₹6,000 (one-time)

UPS Amortization

Over 36 months

Monthly cost allocation

₹167/month

External HDD

2TB Seagate/WD

Daily automated backups

₹3,000 (one-time)

Cooling

Room fan/AC

Keep Mac Mini cool

₹0 (existing)

Use Cases:

Runs all 11 CRUZ agents simultaneously

Hosts PostgreSQL, Redis, Qdrant databases

Runs Ollama local AI models

Central API server (FastAPI)

Voice processing (Whisper STT)

Task orchestration (BullMQ queues)

Monthly Recurring: ₹369 (power + UPS)

One-Time: ₹9,000 (UPS + HDD)

Network Infrastructure
Component

Details

Use Case

Cost

Internet Connection

200 Mbps fiber

Already paid for 2 years

₹0/month

Router

Existing

Network connectivity

₹0 (owned)

Static IP

Included with plan

Remote access (optional)

₹0/month

Domain Name

simpleinc.cloud/cruz

Web access subdomain

₹500/year (₹42/month)

SSL Certificate

Let's Encrypt

HTTPS security

₹0 (free)

Use Cases:

Remote access to CRUZ from office/travel

Webhook endpoints for integrations

Web dashboard hosting

API access from mobile devices

Monthly Recurring: ₹42 (domain only)

One-Time: ₹0

Client Devices (Already Owned)
Device

Use Case

Cost

ThinkPad (32GB RAM)

Office workstation, web dashboard access

₹0 (owned)

Nothing Phone 2

Mobile voice commands, PWA app

₹0 (owned)

iPad

Optional tablet access

₹0 (owned)

AI Models & APIs
Cloud AI Services (Critical Tasks)
Service

Model

Use Case

Cost

Claude Max

Sonnet 4

Unlimited usage for Relay Agent orchestration

₹1,660/month

Claude API

Sonnet 4

FORGE (code gen), SENTINEL (code review), verification tasks

₹900/month (estimated)

Gemini Flash 2.5

Flash 2.5

REACH agent supplementary research

₹0 (250 requests/day free)

Inworld TTS 1.5 Max

TTS API

Natural voice output across all devices

₹187/month (Months 1-2)

Inworld TTS 1.5 Max

TTS API (cached)

Same, with 60% caching after Month 3

₹71/month (Month 3+)

Use Cases:

Claude Max (₹1,660/month):

Daily briefings via chat interface

Complex reasoning tasks

Research and analysis

Unlimited Sonnet 4 access via Claude.ai

Claude API (₹900/month):

FORGE: Generate React/Next.js components, full features

SENTINEL: Review PRs, security analysis, code quality

Relay Agent: Parse voice commands, route to agents

Multi-agent orchestration

Estimated: ~6M tokens/month input, ~2M output

Gemini Flash (Free):

REACH: Supplement lead research

Web scraping data enrichment

Quick fact-checking

250 requests/day = 7,500/month (sufficient)

Inworld TTS (₹187 → ₹71/month):

Convert text responses to natural British voice

Same voice on Mac Mini, Phone, ThinkPad, iPad

JARVIS persona (cloned British accent)

300 minutes/month usage

Drops to ₹71/month with caching in Month 3

Monthly Recurring: ₹2,747 (Months 1-2) → ₹2,631 (Month 3+)

One-Time: ₹125 (TTS cache setup in Month 3)

Local AI Models (Zero Cost)
Model

Size

Use Case

Agents Using

Cost

Qwen 2.5 Coder

14B params

Code-related tasks, technical work

REACH, ECHO, PM, TITAN, MARK, QT

₹0

Llama 3.1

8B params

General tasks, research, summaries

RAW, PULSE

₹0

Whisper Large v3

1.5B params

Speech-to-text transcription

CATCH

₹0

Use Cases:

Qwen 2.5 Coder (runs on Mac Mini):

REACH: Draft outreach emails, parse lead data

ECHO: Draft client emails and messages

PM: Generate sprint plans, task breakdowns

TITAN: Deployment scripts, infrastructure code

MARK: API documentation generation

QT: Test case generation

Llama 3.1 (runs on Mac Mini):

RAW: Research summaries, web content analysis

PULSE: Daily news briefing generation

Whisper Large v3 (runs on Mac Mini):

CATCH: Transcribe meeting recordings

Voice command input processing

Works offline (no API calls)

Hosting: Ollama (free, self-hosted)

Memory: Uses ~16GB RAM (fits on Mac Mini 24GB)

Monthly Recurring: ₹0

One-Time: ₹0

Databases & Storage
Primary Databases (Self-Hosted)
Database

Purpose

Storage

Cost

PostgreSQL 16

Persistent data (tasks, users, logs, projects)

~5GB

₹0 (self-hosted)

Redis 7

Cache, message queue, real-time state

~2GB RAM

₹0 (self-hosted)

Qdrant

Vector embeddings, semantic memory

~3GB

₹0 (Docker self-hosted)

Use Cases:

PostgreSQL:

Tables: users, tasks, agent_logs, conversations, messages, projects, documents

ACID transactions for critical data

Full-text search for messages

Historical data for analytics

Agent state persistence

Redis:

BullMQ task queues (one per agent)

Session storage

Real-time agent status

Cache for API responses

Pub/Sub for WebSocket updates

Qdrant (Vector DB):

Semantic search across conversations

Document embeddings for RAW agent

Context retrieval (remember past discussions)

Similar task matching

Monthly Recurring: ₹0 (all self-hosted on Mac Mini)

Storage Used: ~10GB total

Cloud Storage & Backup
Service

Plan

Use Case

Cost

Google Drive

100GB

Daily database backups, document sync

₹130/month

External HDD

2TB local

On-site backup (weekly)

₹0 (one-time ₹3,000)

Use Cases:

Google Drive:

Automated daily PostgreSQL dumps

Configuration backups (.env files)

Agent logs archive (older than 30 days)

Client documents (contracts, invoices)

Synced to all devices

External HDD:

Weekly full system backup

Disaster recovery

Offline storage

Monthly Recurring: ₹130

One-Time: ₹3,000 (HDD already counted above)

Development Tools
Code Editors & IDEs
Tool

Use Case

Cost

VS Code

Primary code editor

₹0 (free)

VS Code Extensions

ESLint, Prettier, Python, Tailwind

₹0 (free)

Cursor

AI-powered coding (optional)

₹0 (free tier) or ₹1,660/month (if using instead of Claude Max)

Use Cases:

Write agent code (Python/TypeScript)

Edit configuration files

Database queries (PostgreSQL extension)

Git integration

Monthly Recurring: ₹0 (using VS Code only)

Version Control & CI/CD
Service

Plan

Use Case

Cost

GitHub

Free tier

Private repo: cruz-ai-system

₹0 (unlimited private repos)

GitHub Actions

Free tier

CI/CD pipelines, automated tests

₹0 (2,000 min/month free)

Git

Local

Version control

₹0 (open source)

Use Cases:

GitHub:

Source code repository

Version history

Collaboration (if hiring help later)

Issue tracking

Code review

GitHub Actions:

Run tests on push

Auto-deploy to production

Database migrations

Lint checks

Monthly Recurring: ₹0

Usage: Well within free tier

Testing & Quality Tools
Tool

Purpose

Cost

Pytest

Python unit tests

₹0 (open source)

Vitest

JavaScript/TypeScript tests

₹0 (open source)

Playwright

E2E browser testing

₹0 (open source)

Postman

API testing

₹0 (free tier)

ESLint

JavaScript linting

₹0 (open source)

Prettier

Code formatting

₹0 (open source)

Black

Python formatting

₹0 (open source)

Use Cases:

Agent unit testing

API integration testing

Frontend E2E testing

Code quality enforcement

Monthly Recurring: ₹0 (all free/open source)

Database Management
Tool

Purpose

Cost

TablePlus

PostgreSQL GUI

₹0 (free tier) or $89 one-time (optional)

Redis Commander

Redis GUI

₹0 (open source)

psql

PostgreSQL CLI

₹0 (included with PostgreSQL)

redis-cli

Redis CLI

₹0 (included with Redis)

Use Cases:

Database schema design

Query testing

Data inspection

Performance monitoring

Monthly Recurring: ₹0 (using free tier)

Project Management
Task Management
Service

Plan

Use Case

Cost

Plane.so

Free tier

Agile board, sprint planning, task tracking

₹0 (unlimited for personal use)

Alternative: Linear

Free tier

Backup option (if prefer Linear)

₹0 (unlimited issues)

Use Cases:

Plane.so:

Track CRUZ development tasks

Sprint planning (2-week sprints)

Bug tracking

Feature requests

Agent-specific boards (one per agent)

Roadmap planning

Time estimates

Why Plane.so:

✅ Open source

✅ Self-hostable (can run on Mac Mini if needed)

✅ Better for solo developers

✅ Free forever for personal use

✅ Similar to Linear/Jira but simpler

Integration with CRUZ:

PM agent can read/write tasks via API

Auto-create tasks from voice commands

Daily sprint summaries in PULSE briefing

Monthly Recurring: ₹0

Storage: Uses own database or can connect to PostgreSQL

Documentation & Knowledge Base
Service

Plan

Use Case

Cost

Notion

Free tier

Knowledge base, meeting notes, client docs

₹0 (unlimited pages for personal)

Alternative: Confluence

Not using

-

-

Use Cases:

Notion:

CRUZ system documentation

Agent specifications

API documentation (auto-generated by MARK agent)

Client onboarding templates

Meeting notes (from CATCH agent)

Project wikis (one per client)

Sprint retrospectives

Personal knowledge base

Research notes (RAW agent outputs)

Notion Databases:

Clients (CRM-lite)

Projects

Leads (from REACH agent)

Meetings

Decisions log

Integration with CRUZ:

CATCH agent: Auto-save meeting transcripts to Notion

MARK agent: Sync documentation to Notion

ECHO agent: Draft emails using Notion templates

PM agent: Read sprint goals from Notion

Monthly Recurring: ₹0

Storage: Unlimited pages, 5MB file uploads

Communication & Collaboration
Email & Calendar
Service

Plan

Use Case

Cost

Gmail

Free

Client communication

₹0

Google Calendar

Free

Meeting scheduling

₹0

SendGrid

Free tier

Automated email sending (ECHO agent)

₹0 (100 emails/day)

Use Cases:

Gmail:

Client emails

ECHO agent drafts emails here

Email parsing for context

Google Calendar:

Client meetings

PULSE agent checks today's schedule

Reminder notifications

SendGrid:

Automated follow-up emails (REACH agent)

Deployment notifications (TITAN agent)

Daily briefing emails (PULSE agent)

Limit: 100/day = 3,000/month (sufficient)

Monthly Recurring: ₹0

Team Chat & Video
Service

Plan

Use Case

Cost

Slack

Free tier

Client communication channels

₹0 (10k message history)

Microsoft Teams

Free

Client meetings (some clients use this)

₹0

Google Meet

Free

Client video calls

₹0 (60 min limit)

Telegram

Free

CRUZ mobile interface (bot)

₹0

Use Cases:

Slack:

Client workspace channels

Quick messages

File sharing

Integration with CRUZ (post updates)

Telegram Bot:

Send commands to CRUZ from anywhere

Receive notifications

Quick status checks

No app needed (works via Telegram)

Monthly Recurring: ₹0

Voice & Network
Service

Plan

Use Case

Cost

Tailscale

Free tier

VPN for secure cross-device access

₹0 (100 devices, 1 user)

Cloudflare Tunnel

Free

Expose CRUZ API securely (optional)

₹0

Use Cases:

Tailscale:

Access Mac Mini from anywhere

Secure device-to-device communication

Phone → Mac Mini voice commands

ThinkPad → Mac Mini API calls

No port forwarding needed

Encrypted mesh network

Cloudflare Tunnel (Optional):

Public HTTPS endpoint for webhooks

No exposed ports on router

Free SSL

Monthly Recurring: ₹0

Lead Generation & Outreach
Contact Data & Email Finding
Service

Plan

Use Case

Cost

Apollo.io

Free tier

Find B2B leads, email addresses

₹0 (50 credits/month)

Hunter.io

Free tier

Email verification, domain search

₹0 (50 searches/month)

LinkedIn

Free

Manual prospecting

₹0

LinkedIn Sales Navigator

Not using

Too expensive

-

Use Cases:

Apollo.io (REACH agent):

Find leads matching criteria

Export to CSV

50 leads/month = enough for testing

Can upgrade to paid later if needed

Hunter.io (REACH agent):

Verify email addresses before sending

Find pattern (firstname@company.com)

Domain search (all emails at company)

LinkedIn (Manual + REACH):

Research companies

Find decision makers

Profile scraping (manual)

Monthly Recurring: ₹0 (using free tiers)

Paid Option: Apollo Pro ₹2,000/month (500 credits) - add later if scaling

Deployment & Hosting
Application Hosting
Service

Plan

Use Case

Cost

Mac Mini (Self-Hosted)

-

CRUZ API backend (primary)

₹0 (own hardware)

Vercel

Free tier

Frontend dashboard (optional cloud)

₹0 (100GB bandwidth/month)

Railway

Free tier

Backup API hosting (optional)

₹0 ($5 credit/month)

Hostinger VPS

Existing

Client websites (AMA, Shooterista)

₹0 (already paying)

Use Cases:

Mac Mini:

FastAPI backend (primary)

All agents run here

Databases (PostgreSQL, Redis, Qdrant)

Voice processing

24/7 uptime via PM2

Vercel (Optional):

React dashboard

Static site hosting

Auto-deploy from GitHub

Edge functions for serverless

Railway (Backup):

If Mac Mini goes down

Can quickly deploy API backup

PostgreSQL hosting option

Monthly Recurring: ₹0 (all free tiers or owned)

DNS & CDN
Service

Plan

Use Case

Cost

Cloudflare

Free tier

DNS, CDN, SSL, DDoS protection

₹0

Domain Registrar

Hostinger

simpleinc.cloud

₹500/year (₹42/month)

Use Cases:

Cloudflare:

DNS management (cruz.simpleinc.cloud)

Free SSL certificates

CDN for frontend assets

DDoS protection

Analytics

Monthly Recurring: ₹42 (domain)

Container & Orchestration
Tool

Purpose

Cost

Docker

Containerization (Qdrant)

₹0 (free)

PM2

Process management (keep agents running)

₹0 (open source)

Ollama

Local LLM serving

₹0 (open source)

Use Cases:

Docker:

Run Qdrant in container

Isolated environments

Easy backup/restore

PM2:

Keep FastAPI running 24/7

Auto-restart on crash

Load balancing

Log management

Process monitoring

Ollama:

Serve Qwen, Llama, Whisper models

API-compatible with OpenAI

Auto GPU acceleration

Monthly Recurring: ₹0

Monitoring & Observability
Application Monitoring
Service

Plan

Use Case

Cost

Uptime Kuma

Self-hosted

Service health checks

₹0 (open source)

Grafana Loki

Self-hosted

Log aggregation

₹0 (open source)

Sentry

Free tier

Error tracking (optional)

₹0 (5k events/month)

Prometheus

Self-hosted

Metrics collection (optional)

₹0 (open source)

Use Cases:

Uptime Kuma:

Monitor Mac Mini uptime

Check if agents are running

PostgreSQL health

API endpoint checks

Slack/Telegram alerts on downtime

Grafana Loki:

Centralized logs from all agents

Query logs by agent, time, error

Dashboard visualization

Sentry (Optional):

JavaScript errors from frontend

Python exceptions from agents

Error grouping and alerts

Monthly Recurring: ₹0 (all self-hosted)

Analytics & Insights
Tool

Purpose

Cost

PostgreSQL Views

Custom dashboards (agent performance)

₹0 (built-in)

Metabase

BI dashboards (optional)

₹0 (self-hosted open source)

Custom Dashboard

React app showing real-time agent status

₹0 (self-built)

Use Cases:

Agent success rates

Task completion times

Daily/weekly metrics

Cost tracking

Error analysis

Monthly Recurring: ₹0

Security & Backup
Security Tools
Tool

Purpose

Cost

Bitwarden

Password manager, API key storage

₹0 (free tier)

macOS FileVault

Disk encryption

₹0 (built-in)

macOS Firewall

Network protection

₹0 (built-in)

Let's Encrypt

SSL certificates

₹0 (free)

Fail2ban

Brute force protection (optional)

₹0 (open source)

Use Cases:

Bitwarden:

Store all API keys

Anthropic, Inworld, Gemini keys

Database passwords

Share nothing in Git

FileVault:

Encrypt Mac Mini SSD

Protect if stolen

Firewall:

Block unauthorized access

Only allow Tailscale connections

Monthly Recurring: ₹0

Backup Strategy
Method

Frequency

Storage

Cost

PostgreSQL Dump

Daily (automated)

Google Drive

₹130/month (already counted)

Redis RDB Snapshot

Daily

Google Drive

Included above

Code Backup

On every commit

GitHub

₹0

Full System Backup

Weekly

External HDD

₹0 (one-time ₹3,000)

Qdrant Backup

Weekly

Google Drive

Included above

Use Cases:

Disaster recovery

Rollback bad deployments

Data loss prevention

Migration to new hardware

Monthly Recurring: ₹0 (Google Drive already counted)

Total Cost Summary
One-Time Costs
Item

Cost

Notes

Mac Mini M4 24GB

₹0

Already owned

UPS (1000VA)

₹6,000

Power backup

External HDD (2TB)

₹3,000

Local backups

Domain (1 year)

₹500

Already counted in monthly

TOTAL ONE-TIME

₹9,000

Hardware only

Monthly Recurring Costs (Months 1-2)
Category

Items

Cost

Notes

Infrastructure

Mac Mini power + UPS + Domain

₹411

₹202 + ₹167 + ₹42

AI Services

Claude Max + Claude API

₹2,560

₹1,660 + ₹900

 

Gemini Flash

₹0

Free tier (250/day)

 

Inworld TTS

₹187

300 min/month

Storage

Google Drive 100GB

₹130

Backups + sync

Databases

PostgreSQL + Redis + Qdrant

₹0

Self-hosted

Project Mgmt

Plane.so + Notion

₹0

Free tiers

Communication

Gmail + Slack + Tailscale

₹0

Free tiers

Lead Gen

Apollo + Hunter

₹0

Free tiers (50 each)

Hosting

Vercel + Railway + Cloudflare

₹0

Free tiers

Monitoring

Uptime Kuma + Loki

₹0

Self-hosted

Security

Bitwarden + Let's Encrypt

₹0

Free tiers

Development

VS Code + GitHub + Testing

₹0

All free/open source

TOTAL MONTHS 1-2

 

₹3,288/month

 

Monthly Recurring Costs (Month 3+, With Caching)
Category

Cost (Month 3+)

Change

Infrastructure

₹411

Same

AI Services

₹2,560

Same (Claude)

 

₹71

Inworld TTS (cached, was ₹187)

Storage

₹130

Same

Everything Else

₹0

Same

TOTAL MONTH 3+

₹3,172/month

₹116 saved

One-Time in Month 3: ₹125 (TTS cache setup)

Annual Cost Breakdown
Year 1:

```

Months 1-2:  ₹3,288 × 2  = ₹6,576

Months 3-12: ₹3,172 × 10 = ₹31,720

Cache setup (Month 3):     ₹125

One-time hardware:         ₹9,000

────────────────────────────────

TOTAL YEAR 1:              ₹47,421

```

Year 2+ (Steady State):

```

12 months:   ₹3,172 × 12 = ₹38,064/year

```

Tool Usage by Agent
Agent-to-Tool Mapping
Agent

Primary Tools Used

Monthly Cost

RELAY

Claude Max, PostgreSQL, Redis

₹1,660 (Claude Max)

REACH

Qwen 2.5, Apollo.io, Hunter.io, Notion

₹0 (all free tiers)

CATCH

Whisper, Notion, Google Drive

₹0

ECHO

Llama 3.1/Qwen, Gmail, SendGrid, Notion

₹0

PM

Qwen 2.5, Plane.so, Notion, PostgreSQL

₹0

FORGE

Claude Sonnet 4 (API), GitHub, VS Code

₹600 (estimated API)

TITAN

Qwen 2.5, Hostinger VPS, GitHub Actions

₹0

MARK

Qwen 2.5, Notion, GitHub

₹0

QT

Qwen 2.5, GitHub, Pytest, Playwright

₹0

SENTINEL

Claude Sonnet 4 (API), GitHub

₹300 (estimated API)

RAW

Llama 3.1, Gemini Flash, Qdrant, Notion

₹0

PULSE

Llama 3.1, Notion, Google Calendar

₹0

Total Agent-Specific Costs: ₹2,560/month (Claude only)

Cost Optimization Tips
Current Optimizations
✅ Using Plane.so instead of Linear Pro - Saves ₹1,500/month

✅ Using Ollama instead of all cloud AI - Saves ₹15,000+/month

✅ Self-hosting databases - Saves ₹5,000/month

✅ Using free tiers everywhere possible

✅ Inworld TTS caching - Saves ₹116/month after Month 3

✅ Mac Mini self-hosting - Saves ₹8,000/month vs cloud VPS

Potential Future Optimizations
If scaling up:

Apollo.io Pro (₹2,000/month) → 500 leads vs 50

Plane.so Enterprise (₹8,000/month) → Team collaboration

More Google Drive storage (₹210/month for 200GB)

Claude API usage may increase

Current setup handles: 1-3 active clients comfortably

Free Tier Limits & Headroom
Services with Usage Limits
Service

Free Limit

Current Usage

Headroom

Gemini Flash

250 req/day

~50/day

5× headroom

GitHub Actions

2,000 min/month

~200/month

10× headroom

SendGrid

100 emails/day

~10/day

10× headroom

Apollo.io

50 credits/month

30-40/month

1.2× headroom ⚠️

Hunter.io

50 searches/month

20-30/month

2× headroom

Vercel

100GB bandwidth

~10GB/month

10× headroom

Tailscale

100 devices

3 devices

33× headroom

⚠️ Watch: Apollo.io may need upgrade if REACH agent scales

Comparison: CRUZ vs Alternatives
Cost vs Alternatives
Scenario

Monthly Cost

What You Get

Hiring Virtual Assistant

₹15,000-25,000

Limited hours, basic tasks only

SaaS Tool Stack

₹8,000-12,000

Zapier Pro + Linear + Notion Pro + others

AI Tools Enterprise

₹10,000-20,000

GitHub Copilot + ChatGPT Team + more

Managed AI Agency

₹50,000-1,00,000

Full service but no control

CRUZ (This Setup)

₹3,288 → ₹3,172

11 agents, 24/7, full control, multi-device

Savings: ₹4,712 - ₹96,828 per month vs alternatives

Quick Reference: Essential Tools Only
Absolutely Required (Can't Build Without)
Mac Mini M4 - ₹0 (owned)

Claude Max - ₹1,660/month (API access)

PostgreSQL - ₹0 (self-hosted)

Ollama - ₹0 (open source)

Internet - ₹0 (already paying)

Inworld TTS - ₹187/month (voice)

Minimum to start: ₹1,847/month

Highly Recommended
Redis - ₹0 (task queues)

Google Drive - ₹130/month (backups)

GitHub - ₹0 (version control)

Plane.so - ₹0 (project management)

Notion - ₹0 (documentation)

UPS - ₹6,000 one-time (power backup)

Recommended total: ₹1,977/month + ₹6,000 one-time

Nice to Have (Add Later)
Qdrant (semantic memory)

Monitoring tools

Error tracking

Advanced analytics

Paid lead gen tools

END OF TOOLS LIST

Total Unique Tools/Services: 50+

Monthly Cost (Optimized): ₹3,288 → ₹3,172

All using free tiers where possible: 35+ tools at ₹0

Only 5 paid services: Claude Max, Claude API, Inworld TTS, Google Drive, Domain

Ready to build with this stack! 🚀






Add a comment