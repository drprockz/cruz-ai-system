# CRUZ AI System - Prompting Guidelines

This document contains optimal prompts and patterns for working with Claude Code and the CRUZ agent system.

---

## Table of Contents

1. [General Prompting Principles](#general-prompting-principles)
2. [Agent-Specific Prompts](#agent-specific-prompts)
3. [Code Generation Patterns](#code-generation-patterns)
4. [Debugging Prompts](#debugging-prompts)
5. [Testing Prompts](#testing-prompts)

---

## General Prompting Principles

### When Working with Claude Code

**Be Specific:**
```
❌ "Fix the database issue"
✅ "Fix the connection error in backend/api/main.py line 42 where psycopg2 is raising 'connection refused' when connecting to PostgreSQL"
```

**Provide Context:**
```
❌ "Add error handling"
✅ "Add try-catch error handling to the relay_agent.py parse_command() method to handle cases where Claude API returns non-JSON responses"
```

**Reference Files:**
```
❌ "Update the agent"
✅ "Update agents/relay/relay_agent.py to add a timeout parameter (default 30s) to the parse_command() method"
```

**State Your Goal:**
```
❌ "Help with the API"
✅ "Goal: Create a /command endpoint in backend/api/main.py that accepts POST requests with JSON body containing 'command' field and returns agent routing result"
```

---

## Agent-Specific Prompts

### Relay Agent Prompts

**System Prompt Template:**
```python
system_prompt = """You are the Relay Agent for CRUZ AI system.
Your job is to parse user commands and respond with JSON containing:
{
  "agent": "AGENT_NAME",
  "intent": "specific_action",
  "entities": {
    "key": "value"
  },
  "priority": 1-5,
  "confidence": 0.0-1.0
}

Available agents:
- FORGE: Code generation, feature development
- ECHO: Email/message drafting
- REACH: Lead generation
- PM: Project management
- CATCH: Meeting transcription
- TITAN: Deployment
- MARK: Documentation
- QT: Testing
- SENTINEL: Code review
- RAW: Research
- PULSE: Briefings

Guidelines:
1. Extract explicit agent names from command (e.g., "FORGE, create...")
2. Infer intent when agent not specified
3. Set priority: 1=urgent, 3=normal, 5=low
4. Confidence >0.9 for explicit commands, lower for ambiguous

Examples:
"FORGE, create login component" → {agent: "FORGE", intent: "create_component", entities: {component: "login"}}
"Draft email to client" → {agent: "ECHO", intent: "draft_email", entities: {recipient: "client"}}
"Deploy to production" → {agent: "TITAN", intent: "deploy", entities: {environment: "production"}}
"""
```

**Testing Relay:**
```python
# Test command parsing accuracy
test_commands = [
    "FORGE, create a contact form with name, email, message",
    "Draft professional email to Ateet about project delay",
    "Find 20 SaaS leads in India",
    "What's my schedule today?",
    "Deploy AMA website to production"
]

for cmd in test_commands:
    result = relay.process(cmd)
    print(f"Command: {cmd}")
    print(f"Routed to: {result['parsed']['agent']}")
    print(f"Confidence: {result['parsed']['confidence']}")
```

---

### FORGE Agent Prompts

**System Prompt Template:**
```python
system_prompt = f"""You are FORGE, an expert code generation agent.

Tech Stack:
- Frontend: {framework} (React/Next.js)
- Language: {language} (TypeScript)
- Styling: Tailwind CSS
- State: Zustand (if needed)
- Forms: React Hook Form + Zod
- Icons: Lucide React

Code Quality Standards:
1. Production-ready, not prototype code
2. Include TypeScript types (no 'any')
3. Add JSDoc comments for complex logic
4. Follow React best practices (hooks, composition)
5. Include error handling
6. Add accessibility (aria labels, keyboard nav)
7. Mobile responsive (Tailwind breakpoints)

Output Format:
- Return ONLY the code, no explanations
- If multiple files, separate with comments
- Include import statements
- Use modern ES2023+ syntax

Example Structure:
```typescript
// ComponentName.tsx
import { useState } from 'react';
import { z } from 'zod';

// Schema
const schema = z.object({...});

// Types
type Props = {...};

// Component
export function ComponentName({ prop }: Props) {
  // Implementation
}
```
"""
```

**FORGE Usage Examples:**
```python
# Simple component
forge.process({
    "task": "Create a Button component with variants (primary, secondary, outline) and sizes (sm, md, lg)",
    "framework": "React",
    "style": "TypeScript"
})

# Complex component
forge.process({
    "task": """Create a ContactForm component with:
    - Fields: name, email, company, message
    - Validation using zod (email format, required fields)
    - Submit handler with loading state
    - Success/error toast notifications
    - Tailwind styling
    """,
    "framework": "React",
    "style": "TypeScript"
})

# API route
forge.process({
    "task": "Create FastAPI endpoint POST /api/leads that accepts {name, email, company} and saves to PostgreSQL leads table",
    "framework": "FastAPI",
    "style": "Python"
})
```

---

### ECHO Agent Prompts

**System Prompt Template:**
```python
system_prompt = f"""You are ECHO, a professional communication assistant.

Communication Style:
- Tone: {tone} (professional/friendly/formal)
- Length: Concise but complete
- Structure: Clear subject + organized body
- Action: Always include clear next steps

Email Structure:
Subject: [Clear, specific subject line]

[Greeting]

[Context/Background - 1-2 sentences]

[Main Message - 2-4 sentences]

[Action Items/Next Steps]

[Closing]
Best regards,
Darshan

Guidelines:
1. No fluff or filler words
2. One email = one topic
3. Clear call-to-action
4. Professional but warm
5. Proofread (no typos)

Examples:
Topic: "Project delay due to client feedback"
→ Subject: "AMA Website Launch - Revised Timeline"
→ Body: Acknowledge, explain, propose solution, confirm next steps
"""
```

**ECHO Usage Examples:**
```python
# Client update email
echo.process({
    "type": "draft_email",
    "recipient": "Ateet (AMA Solutions)",
    "topic": "Website delivery and maintenance retainer proposal",
    "tone": "professional",
    "points": [
        "Website completed ahead of schedule",
        "Propose ₹50k/month retainer for ongoing support",
        "Includes 15 hours/month of updates and maintenance"
    ]
})

# Follow-up email
echo.process({
    "type": "draft_email",
    "recipient": "prospect from Apollo.io",
    "topic": "Follow up on MIDAR demo",
    "tone": "friendly",
    "context": "Had demo call 3 days ago, they showed interest but haven't responded"
})

# Internal communication
echo.process({
    "type": "draft_message",
    "recipient": "team",
    "topic": "Sprint retrospective summary",
    "tone": "casual",
    "platform": "Slack"
})
```

---

## Code Generation Patterns

### Pattern 1: Component with State

**Prompt:**
```
Create a [ComponentName] component that:
- Manages state for [state variables]
- Handles [user interactions]
- Validates [data] using zod
- Displays [UI elements]
- Styling: Tailwind CSS
- Framework: React + TypeScript
```

**Example:**
```
Create a SearchBar component that:
- Manages state for search query and results
- Handles real-time search as user types (debounced 300ms)
- Validates query minimum length 3 characters
- Displays autocomplete dropdown with results
- Styling: Tailwind CSS with dark mode support
- Framework: React + TypeScript
```

---

### Pattern 2: API Endpoint

**Prompt:**
```
Create a FastAPI endpoint:
- Method: [GET/POST/PUT/DELETE]
- Path: /api/[resource]
- Accepts: [request schema]
- Returns: [response schema]
- Database: [operations]
- Error handling: [specific errors]
```

**Example:**
```
Create a FastAPI endpoint:
- Method: POST
- Path: /api/tasks
- Accepts: {agent: string, title: string, description: string, priority: int}
- Returns: {id: int, status: string, created_at: datetime}
- Database: Insert into tasks table, return generated ID
- Error handling: 400 for validation errors, 500 for database errors
```

---

### Pattern 3: Database Query

**Prompt:**
```
Write a SQL query to [operation]:
- Tables: [table names]
- Conditions: [WHERE clauses]
- Joins: [if needed]
- Returns: [expected columns]
- Optimize for: [performance consideration]
```

**Example:**
```
Write a SQL query to get agent performance metrics:
- Tables: agent_logs, tasks
- Conditions: Last 7 days, status = 'completed'
- Joins: agent_logs.task_id = tasks.id
- Returns: agent_name, task_count, avg_duration_ms, success_rate
- Optimize for: Large dataset (100k+ logs)
```

---

## Debugging Prompts

### Pattern: Debugging Errors

**Template:**
```
I'm getting [error type] in [file path] at [line/function].

Error message:
```
[paste exact error]
```

Code context:
```python
[paste relevant code]
```

What I've tried:
- [attempted solution 1]
- [attempted solution 2]

Expected behavior:
[what should happen]

Actual behavior:
[what's happening]

How do I fix this?
```

**Example:**
```
I'm getting a KeyError in agents/relay/relay_agent.py in the parse_command() method.

Error message:
```
KeyError: 'agent'
```

Code context:
```python
def route(self, parsed_command: Dict) -> Dict[str, Any]:
    agent_name = parsed_command.get("agent")  # Line 84
    
    if agent_name not in self.agents:
        return {"success": False, "error": f"Unknown agent: {agent_name}"}
```

What I've tried:
- Added print(parsed_command) - shows the dict is empty {}
- Checked parse_command() - it returns valid JSON

Expected behavior:
parsed_command should contain {"agent": "FORGE", ...}

Actual behavior:
parsed_command is empty {}

How do I fix this?
```

---

### Pattern: Performance Issues

**Template:**
```
[Function/Endpoint] is slow.

Measured performance:
- Current: [timing]
- Expected: [target timing]

Profiling data:
[paste profiling output if available]

Suspected bottleneck:
[your hypothesis]

Code:
```python
[paste function]
```

How can I optimize this?
```

---

## Testing Prompts

### Pattern: Unit Test

**Prompt:**
```
Write pytest unit tests for [function/class] in [file path].

Test cases:
1. [happy path case]
2. [edge case 1]
3. [error case 1]
4. [error case 2]

Mocking needed:
- [external dependency 1]
- [external dependency 2]

Coverage target: >80%
```

**Example:**
```
Write pytest unit tests for RelayAgent.parse_command() in agents/relay/relay_agent.py.

Test cases:
1. Explicit agent name in command ("FORGE, create button")
2. Implicit agent inference ("draft email to client")
3. Ambiguous command requiring clarification
4. Invalid command (empty string)
5. Claude API timeout error
6. Non-JSON response from Claude

Mocking needed:
- Anthropic API client
- Database connection (not used in this function but imported)

Coverage target: >90%
```

---

### Pattern: Integration Test

**Prompt:**
```
Write integration test for [workflow]:

Flow:
1. [step 1]
2. [step 2]
3. [step 3]

Dependencies:
- [service 1]: [how to set up]
- [service 2]: [how to set up]

Assertions:
- [assertion 1]
- [assertion 2]

Cleanup:
- [what to clean up after test]
```

**Example:**
```
Write integration test for Relay → FORGE workflow:

Flow:
1. Send command "FORGE, create button component"
2. Relay parses and routes to FORGE
3. FORGE generates TypeScript code
4. Code is saved to file
5. Return success response

Dependencies:
- PostgreSQL: Use test database cruz_test_db
- Redis: Use test instance (port 6380)
- Anthropic API: Use real API with test mode

Assertions:
- Command successfully routed to FORGE
- Generated file exists and contains valid TypeScript
- agent_logs table has entry for this command
- Response contains success=True and file_path

Cleanup:
- Delete generated files
- Clear agent_logs table
- Reset Redis cache
```

---

## Quick Reference: Common Prompts

### File Creation
```
Create [file path] with [description].
Include: [requirements]
Follow: [pattern/template from existing file]
```

### Refactoring
```
Refactor [function/class] in [file] to:
- [improvement 1]
- [improvement 2]
Maintain: [what shouldn't change]
```

### Documentation
```
Add docstrings to [file/function] following Google style.
Include:
- Function purpose
- Args with types
- Returns with type
- Raises (if applicable)
- Example usage
```

### Code Review
```
Review [file path] for:
- Code quality issues
- Performance problems
- Security vulnerabilities
- Best practice violations
Provide: Specific line numbers and suggestions
```

---

## Anti-Patterns (What NOT to Do)

❌ **Too Vague:**
"Make it better"

❌ **No Context:**
"Fix the bug" (which bug? where?)

❌ **Unrealistic:**
"Build entire CRUD app in one prompt"

❌ **No Verification:**
Not testing generated code before moving on

❌ **Over-Specifying:**
Dictating exact implementation when high-level goal would suffice

---

## Best Practices

✅ **Iterative Approach:**
1. Get basic version working
2. Test it
3. Refine based on issues
4. Add edge case handling
5. Optimize if needed

✅ **Reference Previous Work:**
"Create REACH agent following the same pattern as FORGE agent in agents/forge/forge_agent.py"

✅ **Provide Examples:**
"Similar to how we handle errors in relay_agent.py lines 82-90"

✅ **State Constraints:**
"Must work with Python 3.11, cannot use deprecated psycopg2 features"

---

**Last Updated:** Day 2
**For:** CRUZ AI System Development
**Maintained By:** Darshan Parmar
