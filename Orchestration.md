CRUZ AI System - Complete Orchestration & Flow Documentation



By Darshan Parmar

2 min

See views

Add a reaction
CRUZ AI System - Complete Orchestration & Flow Documentation
Document Control
Document Title

CRUZ System Orchestration, Agent Workflows & Flow Diagrams

Version

1.0

Author

Darshan Parmar

Date

April 12, 2026

Status

Final

Table of Contents
System Startup Sequence

Command Processing Flow

Relay Agent Orchestration

Agent Execution Patterns

Context Management

Model Manager & Swapping

Multi-Agent Workflows

Error Handling & Recovery

Voice Pipeline Flow

Task Queue Management

Real-World Scenarios

System Startup Sequence
What Happens When You Power On Mac Mini

Detailed Startup Checklist

Startup Time Breakdown
Phase

Duration

What's Happening

macOS Boot

15-25 seconds

Operating system initialization

PostgreSQL Start

3-5 seconds

Database service startup

Redis Start

1-2 seconds

In-memory cache ready

Docker/Qdrant

5-8 seconds

Container initialization

Ollama Start

2-3 seconds

LLM serving daemon

Model Warm-Up

10-15 seconds

Load Qwen 2.5 14B into RAM

FastAPI Init

2-3 seconds

API server ready

Agent Pool

5-7 seconds

Initialize all 11 agents

TOTAL

45-70 seconds

From power on to ready

First command after startup: Add +5-10 seconds (cold start)

Subsequent commands: <2 seconds (models loaded)

Command Processing Flow
End-to-End: User Command → Response

Command Processing Timeline

Total Latency: ~5.5 seconds (voice to response start)

Target: <2 seconds for most commands

Relay Agent Orchestration
Relay Agent: The Brain of CRUZ

Intent Classification Examples

Agent Execution Patterns
Single Agent Execution

Multi-Agent Sequential Workflow

Multi-Agent Parallel Workflow

Context Management
Context Layers in CRUZ

Context Retrieval Flow

Context Window Management

Context Window Limits:

Claude Sonnet 4: 200k tokens (~150k words)

Qwen 2.5 Coder: 32k tokens (~24k words)

Llama 3.1: 128k tokens (~96k words)

CRUZ Strategy: Keep last 50 messages + top 10 semantic matches

Model Manager & Swapping
Model Selection Logic

Dynamic Model Swapping

Model Loading States

Model Swap Time:

Same model: 0 seconds (already loaded)

Different model (RAM available): 5-10 seconds

Different model (need to free RAM): 10-15 seconds

Fallback to Claude API: <1 second

Model Resource Requirements

Multi-Agent Workflows
Example: Complete Website Deployment

Estimated Time: 3-5 minutes end-to-end

Example: Morning Briefing (Autonomous)

Runs automatically every morning, ready when you wake up

Error Handling & Recovery
Error Classification & Recovery

Retry Strategy with Exponential Backoff

Retry Delays: 2s → 4s → 8s → Fail

Voice Pipeline Flow
Complete Voice Interaction

Voice Latency Breakdown

Breakdown:

Wake word: 150ms

User speaks: 2 seconds

STT (Whisper): 500ms

Processing: 700ms

TTS (Inworld): 250ms

Total: ~3.6 seconds from "Hey CRUZ" to response

Optimizations:

Cache common phrases → -250ms

Parallel processing → -200ms

Optimized: ~3.1 seconds

Task Queue Management
BullMQ Queue Architecture

Queue Job Lifecycle

Priority Queue Management

Priority Levels:

Critical (urgent bugs, security)

High (deployments, client-facing)

Normal (regular tasks)

Low (research, optimization)

Background (cleanup, analytics)

Real-World Scenarios
Scenario 1: Morning Routine

Time: 3 minutes total interaction

Scenario 2: Complex Deployment Workflow

Estimated Duration: 5-8 minutes

Agents Involved: 5 (FORGE, QT, SENTINEL, TITAN, ECHO)

Touchpoints: 15+ (with error handling)

Scenario 3: Lead Generation Campaign

Duration: 10-15 minutes

Leads Found: 18 qualified

Emails Sent: 5 personalized

Cost: ₹0 (within free tiers)

System Health Monitoring
Real-Time System Status Dashboard

Loading app...
Summary: CRUZ Operating Modes
Three Operating States

Loading app...
END OF ORCHESTRATION DOCUMENTATION

Total Diagrams: 35+ Mermaid flow diagrams

Coverage: Complete system from power-on to complex multi-agent workflows

Use Cases: 10+ real-world scenarios documented

Ready to understand CRUZ inside-out! 🚀






