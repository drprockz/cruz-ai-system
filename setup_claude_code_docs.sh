#!/bin/bash

# CRUZ Claude Code Documentation Setup Script
# This script creates all necessary documentation files for Claude Code

PROJECT_DIR="$HOME/Projects/cruz-ai-system"

echo "🚀 Setting up CRUZ Claude Code documentation..."
echo ""

# Check if project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    echo "📁 Creating project directory: $PROJECT_DIR"
    mkdir -p "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"

echo "📝 Creating documentation files..."

# 1. CLAUDE.md (already created separately)
if [ ! -f "CLAUDE.md" ]; then
    echo "Creating CLAUDE.md..."
    # Will be copied from /home/claude/CLAUDE.md
fi

# 2. PROMPTS.md (already created separately)  
if [ ! -f "PROMPTS.md" ]; then
    echo "Creating PROMPTS.md..."
    # Will be copied from /home/claude/PROMPTS.md
fi

# 3. ARCHITECTURE.md
cat > ARCHITECTURE.md << 'ARCH_EOF'
# CRUZ System Architecture

## High-Level Overview
```
User → API Gateway → Relay Agent → Task Queue → Specialized Agents → Data Layer
```

## Components
1. **FastAPI Gateway** - Single entry point
2. **Relay Agent** - Command router (Claude Sonnet 4)
3. **BullMQ Queues** - Task distribution (11 queues)
4. **11 Specialized Agents** - Each with specific purpose
5. **Data Layer** - PostgreSQL + Redis + Qdrant

## Agent Flow
```
Voice/Text Command 
  → Whisper STT (if voice)
  → FastAPI /command
  → Relay.parse_command()
  → Queue.add(agent_queue, task)
  → Agent.process(task)
  → Result → Database
  → Response → TTS (if voice)
```

See full architecture details in planning documents.
ARCH_EOF

# 4. AGENTS.md
cat > AGENTS.md << 'AGENTS_EOF'
# CRUZ Agents

## Agent Template
```python
class Agent:
    def __init__(self, model):
        self.name = "AGENT_NAME"
        self.model = model
    
    def process(self, task: dict) -> dict:
        # 1. Load context
        # 2. Call AI model  
        # 3. Execute action
        # 4. Log result
        return {"success": True, "result": {}}
```

## All 11 Agents

| Agent | Purpose | Model | Priority |
|-------|---------|-------|----------|
| RELAY | Command routing | Claude Sonnet 4 | Critical |
| FORGE | Code generation | Claude Sonnet 4 | High |
| ECHO | Communication | Llama 3.1 | High |
| REACH | Lead generation | Qwen 2.5 | Normal |
| CATCH | Transcription | Whisper | Normal |
| PM | Project mgmt | Qwen 2.5 | Normal |
| TITAN | Deployment | Qwen 2.5 | High |
| MARK | Documentation | Qwen 2.5 | Normal |
| QT | Testing | Qwen 2.5 | Normal |
| SENTINEL | Code review | Claude Sonnet 4 | High |
| RAW | Research | Llama 3.1 | Low |
| PULSE | Briefings | Llama 3.1 | Low |

Status: See TASKS.md for current progress
AGENTS_EOF

# 5. API.md
cat > API.md << 'API_EOF'
# CRUZ API Reference

## Base URL
```
http://localhost:3000 (development)
```

## Endpoints

### POST /command
Process a command through CRUZ

**Request:**
```json
{
  "command": "FORGE, create button component",
  "context": {}
}
```

**Response:**
```json
{
  "success": true,
  "agent": "FORGE",
  "task_id": "task_123",
  "status": "queued"
}
```

### GET /health
Health check

### GET /tasks/{id}
Get task status

### WS /ws
WebSocket for real-time updates

See backend/api/main.py for implementation
API_EOF

# 6. DATABASE.md
cat > DATABASE.md << 'DB_EOF'
# CRUZ Database Schema

## PostgreSQL Tables

### tasks
```sql
CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    agent VARCHAR(50) NOT NULL,
    title TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    priority INTEGER DEFAULT 3,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### agent_logs
```sql
CREATE TABLE agent_logs (
    id SERIAL PRIMARY KEY,
    agent VARCHAR(50) NOT NULL,
    action VARCHAR(100),
    status VARCHAR(20),
    input_data JSONB,
    output_data JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### conversations & messages
See backend/models/schema.sql for complete schema

## Redis Keys
- `session:{user_id}` - User sessions
- `queue:{agent}` - BullMQ task queues
- `cache:*` - Command results

## Qdrant
- Collection: `cruz_memory`
- Vector size: 384 (all-MiniLM-L6-v2)
DB_EOF

# 7. TASKS.md
cat > TASKS.md << 'TASKS_EOF'
# CRUZ Development Tasks

## Current Status: Day 2 Complete ✅

### ✅ Completed
- [x] Environment setup
- [x] Dependencies installed
- [x] Database schema created
- [x] Redis configured
- [x] Ollama models pulled

### 🔨 Today (Day 3)
- [ ] Create backend/api/main.py
- [ ] Add health check endpoint
- [ ] Test database connection
- [ ] Test Claude API

### ⏳ This Week
- [ ] Day 4: Relay Agent
- [ ] Day 5: FORGE Agent  
- [ ] Day 6-7: Integration testing

### 📅 Next Week
- [ ] ECHO Agent
- [ ] Voice interface
- [ ] MVP complete

## Quick Commands
```bash
# Start development
source venv/bin/activate
python backend/api/main.py

# Test
curl http://localhost:3000/health
```
TASKS_EOF

# 8. README.md
cat > README.md << 'README_EOF'
# CRUZ AI System

Multi-agent AI assistant for 3-5x developer productivity.

## Quick Start

```bash
# Setup
source venv/bin/activate
pip install -r backend/requirements.txt

# Configure
cp .env.example .env
# Add your API keys

# Run
python backend/api/main.py
```

## Documentation
- [CLAUDE.md](./CLAUDE.md) - Main documentation for Claude Code
- [PROMPTS.md](./PROMPTS.md) - How to work with Claude Code
- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture
- [AGENTS.md](./AGENTS.md) - Agent specifications
- [API.md](./API.md) - API reference
- [DATABASE.md](./DATABASE.md) - Database schema
- [TASKS.md](./TASKS.md) - Development tasks

## Project Structure
```
cruz-ai-system/
├── backend/api/        # FastAPI
├── agents/            # 11 agents
├── frontend/          # React (future)
└── docs/             # Additional docs
```

## Status
**Day 2 Complete** - Ready to build API
**Target:** MVP in 2 weeks

## Tech Stack
Python 3.11 | FastAPI | PostgreSQL | Redis | Ollama | Claude Sonnet 4
README_EOF

# 9. .env.example
cat > .env.example << 'ENV_EOF'
# Database
DATABASE_URL=postgresql://cruz:password@localhost:5432/cruz_db
REDIS_URL=redis://localhost:6379

# AI Services
ANTHROPIC_API_KEY=sk-ant-xxxxx
GEMINI_API_KEY=xxxxx
INWORLD_API_KEY=xxxxx

# Environment
NODE_ENV=development
PORT=3000

# Secrets
JWT_SECRET=generate-random-string
SESSION_SECRET=generate-random-string
ENV_EOF

echo ""
echo "✅ Documentation files created in $PROJECT_DIR:"
echo ""
ls -la *.md .env.example 2>/dev/null
echo ""
echo "📚 Core files for Claude Code:"
echo "  - CLAUDE.md (main reference)"
echo "  - PROMPTS.md (how to prompt effectively)"
echo "  - ARCHITECTURE.md (system design)"
echo "  - AGENTS.md (agent specs)"
echo "  - API.md (endpoints)"
echo "  - DATABASE.md (schema)"
echo "  - TASKS.md (current progress)"
echo "  - README.md (project overview)"
echo ""
echo "🎯 Next Steps:"
echo "  1. Copy CLAUDE.md and PROMPTS.md from /home/claude/ to $PROJECT_DIR"
echo "  2. Review .env.example and create .env with your keys"
echo "  3. Open Claude Code and reference CLAUDE.md"
echo "  4. Start Day 3: Create backend/api/main.py"
echo ""
echo "🚀 Ready to build CRUZ!"
