CRUZ AI Assistant System - Product Requirements Document (PRD)
Document Control
Document Title

CRUZ AI Assistant System - Product Requirements Document

Version 

1.1 

Author 

Darshan Parmar 

Status 

Draft 

Last Updated 

April 12, 2026 

Approvers 

Technical Lead, Project Stakeholder 

Classification 

Internal Use Only 

Table of Contents
Executive Summary

Project Overview

Business Case & Objectives

System Architecture

The 11 CRUZ Agents

Functional Requirements

Non-Functional Requirements

Technical Stack

User Stories & Use Cases

Development Roadmap

Cost Analysis

Risk Assessment

Success Metrics

Dependencies & Constraints

Appendices

Executive Summary
Vision Statement
CRUZ is a personal AI assistant system that provides Friday-from-Iron-Man level automation for freelance software development workflows, enabling voice-controlled, cross-device, autonomous execution of development, communication, and business operations tasks.

Problem Statement
As a freelance full-stack developer managing multiple clients (Simple Inc, AMA Solutions, Shooterista, SuiteAdvisors) and building MIDAR as a product venture, the current workflow involves:

Manual context switching between 4+ client projects

Repetitive tasks (client communication, meeting notes, code deployment, documentation)

Lost productivity on train commutes (1.5 hours daily)

After-hours work (client calls, email responses, project planning)

Fragmented tools (Slack, Linear, Notion, GitHub, email, calendar)

Time cost: Estimated 15-20 hours/week on tasks that could be automated.

Proposed Solution
Build CRUZ: A multi-agent AI system running on Mac Mini M4 24GB (command center) with:

11 specialized AI agents for different workflows

Voice interface across all devices (Mac, ThinkPad, Phone, iPad)

24/7 autonomous operation (agents work overnight)

Cross-device synchronization via Tailscale VPN

Persistent context memory (PostgreSQL + Redis + Qdrant)

Natural language commands ("Hey CRUZ, deploy AMA website to Hostinger")

Expected Outcomes
Productivity gain: 8-15 hours/week saved

Cost savings: ₹5,000-7,000/month vs. hiring VA or using enterprise SaaS

Revenue impact: Ability to take on 1-2 additional clients with same time investment

Quality improvement: Automated testing, code review, documentation

Stress reduction: Less manual work, more strategic focus

Investment Required
Development time: 6-8 weeks (part-time) or 3-4 weeks (full-time)

Monthly operating cost: ₹3,288/month (Months 1-2), ₹3,172/month (Month 3+)

One-time hardware: ₹9,000 (UPS + backup drive)

ROI: Break-even at 1 additional client (₹25,000/month) = 1.2 months

Project Overview
Project Name
CRUZ - AI Command Center for Unified Resource Zone

Project Type
Internal Tool / Personal Productivity System

Project Duration
Phase 1 (Foundation): 2 weeks

Phase 2 (Core Agents): 3 weeks

Phase 3 (Voice & Mobile): 2 weeks

Phase 4 (Optimization): 1 week

Total: 8 weeks (part-time: 15-20 hours/week)

Stakeholders
Role

Name

Responsibility

Product Owner 

Darshan Parmar 

Requirements, acceptance criteria, prioritization 

Developer 

Darshan Parmar 

Architecture, implementation, testing 

End User 

Darshan Parmar 

Daily usage, feedback, iteration 

Clients (Indirect) 

AMA Solutions, Shooterista, SuiteAdvisors, Asia Capital 

Benefit from improved delivery speed 

Success Criteria
✅ Voice command accuracy >95% (tested over 100 commands)

✅ Agent task completion rate >90%

✅ Cross-device sync latency <2 seconds

✅ System uptime >99% (Mac Mini + agents)

✅ Time saved: 8+ hours/week (measured over 4 weeks)

✅ Monthly cost <₹3,500

✅ Client delivery speed improvement: 20%+

Business Case & Objectives
Business Problem
Current state inefficiencies:

Client Acquisition: Manual LinkedIn research, email crafting, follow-up tracking (5-7 hrs/week)

Meeting Management: Manual note-taking, action item tracking, follow-up scheduling (3-4 hrs/week)

Project Management: Manual sprint planning, task breakdown, status updates (2-3 hrs/week)

Code Deployment: Manual build → test → deploy cycle for each client (1-2 hrs/deployment)

Documentation: Writing API docs, README files, changelogs manually (2-3 hrs/week)

Communication: Drafting client emails, proposals, status updates (2-3 hrs/week)

Total inefficiency: 15-22 hours/week

Business Objectives
Objective

Metric

Target

Timeline

Reduce manual work 

Hours saved per week 

8-15 hours 

3 months 

Increase client capacity 

Number of active clients 

+1 to 2 clients 

6 months 

Improve delivery speed 

Average task completion time 

-20% 

3 months 

Enhance code quality 

Test coverage 

80%+ 

3 months 

Better work-life balance 

After-hours work reduction 

-30% 

3 months 

Cost efficiency 

Monthly tool costs 

<₹3,500 

Immediate 

Value Proposition
For Darshan (Primary User):

Time freedom: Reclaim 8-15 hours/week for strategic work or personal time

Scalability: Handle more clients without proportional time increase

Quality: Automated testing, code review, documentation ensures consistency

Flexibility: Work from anywhere (train, home, office) with voice commands

Learning: Deep experience building production AI systems

For Clients (Indirect):

Faster delivery: Automated workflows reduce turnaround time

Higher quality: Consistent testing, code review, documentation standards

Better communication: Prompt responses, detailed meeting notes, clear proposals

Reliability: Automated monitoring catches issues before clients notice

ROI Calculation
Investment:

Development: 120 hours × ₹0 (own time, opportunity cost ~₹1,50,000 if billed)

Monthly operating cost: ₹3,067

One-time hardware: ₹9,000

Returns:

Time saved: 12 hours/week = 48 hours/month = ₹60,000/month value (at ₹1,250/hr rate)

Additional client capacity: +1 client = ₹25,000/month revenue

Reduced tool costs: Enterprise SaaS would cost ₹8,000-10,000/month

Net benefit: ₹81,933/month (₹85,000 value - ₹3,067 cost)
Payback period: 1.8 months (₹1,59,000 investment ÷ ₹81,933 monthly benefit)

System Architecture
High-Level Architecture

Data Flow Example: Voice Command Execution

Network Architecture
Internal network: All devices + Mac Mini on same WiFi (home) or Tailscale mesh (remote)

VPN: Tailscale for secure device-to-Mac Mini communication

External access: Cloudflare Tunnel for HTTPS endpoint (optional)

API endpoints: 

Internal: <http://192.168.1.100:8000> (Mac Mini local IP)

VPN: <http://100.x.x.x:8000> (Tailscale IP)

Public (optional): <https://cruz.yourdomain.com> (Cloudflare Tunnel)

The 11 CRUZ Agents
Agent 1: REACH 📨
Purpose: Client acquisition and lead generation automation

Responsibilities:

Search for potential clients based on criteria (industry, location, funding stage)

Find contact information (emails, LinkedIn profiles)

Draft personalized outreach emails

Track email opens, clicks, replies

Manage lead pipeline in Notion/Linear

Schedule follow-up sequences

AI Model: Gemini Flash 2.5 (discovery) + Qwen 2.5 Coder 14B (personalization)

Inputs:

Search criteria (voice/text): "Find 10 SaaS startups in Bangalore that raised Series A"

Email templates (stored in Notion)

CRM data (Notion database)

Outputs:

List of qualified leads with contact info

Drafted personalized emails ready for review

Pipeline updates in Notion

Analytics (open rates, reply rates)

Triggers:

Voice: "REACH, find leads for [criteria]"

Scheduled: Daily at 2 AM (overnight lead generation)

Manual: Button in dashboard

Integrations:

Gemini API (company research)

AI Sales Platform | Apollo.io - Outbound, Inbound & Automation  (50 free credits/month)

Trouver des emails en quelques secondes • Hunter (Email Hunter)  (50 free searches/month)

SendGrid (100 emails/day free)

Notion (CRM database)

Success Metrics:

50+ qualified leads/month

30%+ email open rate

5%+ reply rate

2+ meetings booked/month

Example Workflow:


Agent 2: CATCH 📝
Purpose: Meeting intelligence and transcription

Responsibilities:

Automatically detect and record meetings (Teams, Meet, Zoom)

Real-time transcription with speaker diarization

Extract action items and decisions

Generate meeting summaries

Create tasks in Linear/JIRA from action items

Send meeting notes to participants

AI Model: Whisper Large v3 (local transcription)

Inputs:

Audio/video from meeting platforms

Calendar events (to anticipate meetings)

Participant names (for speaker labels)

Outputs:

Full transcript with timestamps

Speaker-labeled dialogue

Action items list

Key decisions summary

Searchable meeting archive in Notion

Triggers:

Auto: Calendar event starts

Voice: "CATCH, record this meeting"

Manual: Start/stop recording button

Integrations:

Teams, Google Meet, Zoom (via OBS recording)

Notion (transcript storage)

Linear (task creation)

Gmail (send meeting notes)

Success Metrics:

100% meeting capture rate (no missed recordings)

<2% transcription error rate

90%+ action item extraction accuracy

<5 min from meeting end to notes ready

Example Workflow:


Agent 3: ECHO 💬
Purpose: Communication and proposal generation

Responsibilities:

Draft client emails (cold outreach, follow-ups, status updates)

Generate technical proposals

Create meeting agendas

Schedule follow-up reminders

Track communication history

Auto-reply to common questions (with human approval)

AI Model: Qwen 2.5 Coder 14B (local)

Inputs:

Email templates (Notion)

Client history (CRM)

Project context (Linear, GitHub)

User instructions (voice/text)

Outputs:

Drafted emails (ready for review)

Proposals (PDF or Notion doc)

Scheduled emails (via SendGrid)

Communication logs (Notion)

Triggers:

Voice: "ECHO, draft email to [client] about [topic]"

Scheduled: Daily follow-up check (9 AM)

Event-based: Reply received → draft response

Integrations:

Gmail (via IMAP/SMTP)

SendGrid (scheduling)

Notion (templates, logs)

Linear (project context)

Calendar (meeting scheduling)

Success Metrics:

90%+ draft accuracy (human edits <10% of content)

<2 min draft generation time

100% follow-up completion (no dropped balls)

Client satisfaction with communication quality

Example Workflow:


Agent 4: PM ⏱️
Purpose: Project and task management automation

Responsibilities:

Create sprint plans from project requirements

Break down features into tasks

Estimate task duration

Assign tasks (or suggest assignments)

Sync with Linear/JIRA

Generate Gantt charts and timelines

Track blockers and dependencies

Send status updates

AI Model: Qwen 2.5 Coder 14B (local)

Inputs:

Project requirements (Notion docs, client emails)

Historical velocity data

Current team capacity (just you)

Existing tasks in Linear/JIRA

Outputs:

Sprint plans (2-week cycles)

Task breakdowns with estimates

Gantt charts (Mermaid or exported image)

Status reports

Blocker alerts

Triggers:

Voice: "PM, plan sprint for [project]"

Scheduled: Monday 9 AM (weekly sprint planning)

Event-based: New project added to Linear

Integrations:

Linear (primary PM tool)

JIRA (if client requires it)

Notion (project docs)

GitHub (issues, PRs)

Calendar (time blocking)

Success Metrics:

Sprint completion rate >80%

Estimate accuracy within 20%

Zero tasks fall through cracks

Client always has visibility into progress

Example Workflow:


Agent 5: FORGE ⚒️
Purpose: Code generation and feature development

Responsibilities:

Generate boilerplate code (components, API routes, schemas)

Implement features from specifications

Refactor existing code for better structure

Fix bugs based on error logs

Create database migrations

Write unit tests

Integrate third-party APIs

AI Model: Claude Sonnet 4 (via Max plan, unlimited)

Inputs:

Feature specifications (Linear tasks, Notion docs)

Existing codebase context (repo files)

API documentation (for integrations)

Code style preferences (ESLint, Prettier configs)

Outputs:

Production-ready code files

Git commits with descriptive messages

Code documentation (JSDoc, comments)

Unit tests (Jest, Vitest)

Triggers:

Voice: "FORGE, build [feature] for [project]"

Git webhook: New branch created

Linear: Task status → "In Progress"

Integrations:

GitHub (clone, commit, push)

VS Code (via remote server)

Linear (task status updates)

Claude Code API (for complex generation)

Success Metrics:

Generated code passes tests 95%+ of time

Human edit rate <15% of generated code

No security vulnerabilities introduced

Follows project coding standards

Example Workflow:


Agent 6: TITAN 🏗️
Purpose: DevOps, deployment, and infrastructure management

Responsibilities:

Build production bundles (Next.js, React, etc.)

Deploy to hosting platforms (Vercel, Railway, Hostinger)

Manage VPS servers (SSH, updates, monitoring)

Configure CI/CD pipelines

Monitor application health

Handle rollbacks if deployment fails

Manage environment variables and secrets

AI Model: Qwen 2.5 Coder 14B (local)

Inputs:

Deployment targets (Vercel, Hostinger VPS)

Build configurations (package.json scripts)

SSH credentials (stored in Bitwarden)

Environment variables (from .env files)

Outputs:

Deployed applications (live URLs)

Build logs

Health check results

Deployment status updates

Rollback confirmations (if needed)

Triggers:

Voice: "TITAN, deploy [project] to [environment]"

Git webhook: Push to main branch

Linear: Task moved to "Deploy" column

Integrations:

Vercel API (frontend deployments)

Railway API (backend deployments)

Hostinger VPS (via SSH)

GitHub Actions (CI/CD)

Uptime Kuma (monitoring)

Success Metrics:

Deployment success rate >98%

Average deployment time <5 min (frontend), <10 min (backend)

Zero downtime deployments

Automatic rollback on health check failure

Example Workflow:


Agent 7: MARK 🖊️
Purpose: Technical documentation generation

Responsibilities:

Generate API documentation from code

Write README files for repositories

Create component documentation (Storybook)

Generate changelogs from Git commits

Write user guides and tutorials

Update Confluence/Notion documentation

Document environment setup

AI Model: Qwen 2.5 Coder 14B (local)

Inputs:

Source code (API routes, components, functions)

Git commit history

Existing documentation (to maintain style)

Documentation templates

Outputs:

Markdown documentation files

JSDoc/TSDoc comments in code

OpenAPI/Swagger specs (for APIs)

Notion/Confluence pages

README.md files

Triggers:

Voice: "MARK, document [API/component/project]"

Git webhook: New code committed by FORGE

Scheduled: Weekly documentation review (Friday 5 PM)

Integrations:

GitHub (read code, write docs to repo)

Notion API (create/update documentation pages)

Confluence API (if client uses it)

Swagger/OpenAPI generators

Success Metrics:

100% of new code has documentation

Documentation accuracy >95%

Client documentation requests <2/month (self-service)

Onboarding time for new collaborators reduced 50%

Example Workflow:


Agent 8: QT 🛡️
Purpose: Quality assurance and automated testing

Responsibilities:

Generate unit tests from code

Run integration tests

Execute end-to-end tests (Playwright)

Perform security scans (OWASP, dependency vulnerabilities)

Check accessibility compliance (WCAG)

Run performance audits (Lighthouse)

Verify mobile responsiveness

Execute smoke tests post-deployment

AI Model: Qwen 2.5 Coder 14B (local)

Inputs:

Source code (for test generation)

Test specifications (from Linear tasks)

Existing test suites (to maintain patterns)

Production URLs (for smoke tests)

Outputs:

Test files (Jest, Vitest, Playwright)

Test execution reports

Coverage reports

Security scan results

Performance audit scores

Bug reports (if tests fail)

Triggers:

Git webhook: New code pushed

Voice: "QT, run tests for [project]"

Pre-deploy: Before TITAN deploys (automatic gate)

Scheduled: Nightly full test suite (2 AM)

Integrations:

Jest/Vitest (unit tests)

Playwright (e2e tests)

Lighthouse CI (performance)

npm audit (security)

ESLint (code quality)

GitHub Actions (CI pipeline)

Success Metrics:

Test coverage >80%

Zero high-severity security vulnerabilities

Lighthouse score >90 (performance)

Accessibility score >95

All tests pass before deployment

Example Workflow:


Agent 9: SENTINEL 👁️
Purpose: Code review and production readiness audit

Responsibilities:

Review pull requests for code quality

Enforce coding standards and best practices

Identify security vulnerabilities

Check performance implications

Verify accessibility compliance

Assess production readiness

Suggest improvements and refactors

Maintain code review checklist

AI Model: Claude Sonnet 4 (via Max plan, unlimited)

Inputs:

Pull requests (GitHub)

Code diffs

Test results (from QT)

Project coding standards (ESLint, Prettier configs)

Security policies

Outputs:

Code review comments on GitHub

Approval/rejection status

Refactoring suggestions

Security vulnerability reports

Production readiness assessment

Triggers:

Git webhook: New pull request created

Voice: "SENTINEL, review [PR/file/project]"

Scheduled: Daily production code audit (11 PM)

Integrations:

GitHub (PR comments, approvals)

Linear (link to tasks)

Notion (code review guidelines)

Slack (review notifications)

Success Metrics:

Catch 95%+ of code issues before production

Zero production bugs from missed reviews

Review turnaround time <30 minutes

Developer satisfaction with review quality >90%

Example Workflow:


Agent 10: RAW 🔬
Purpose: Technical research and knowledge updates

Responsibilities:

Research new frameworks and libraries

Check for dependency updates

Find solutions to technical problems

Summarize technical documentation

Track breaking changes in dependencies

Discover best practices and patterns

Monitor tech news relevant to stack

Update knowledge base in Notion

AI Model: Llama 3.1 8B (local, efficient for research)

Inputs:

Tech stack list (package.json, requirements.txt)

Research queries (voice/text)

RSS feeds (tech blogs, changelogs)

Documentation URLs

Outputs:

Research summaries (Notion pages)

Dependency update recommendations

Breaking change alerts

Best practice guides

Code examples from docs

Triggers:

Voice: "RAW, research [topic/framework/problem]"

Scheduled: Daily tech updates (3 AM)

Event: Dependency alert from Dependabot

Manual: Research request from other agents

Integrations:

npm/yarn (check for updates)

GitHub (Dependabot alerts)

RSS feeds (tech blogs)

Documentation sites (MDN, React docs, etc.)

Notion (knowledge base storage)

Success Metrics:

Stay current with 95%+ of relevant tech updates

Zero missed breaking changes that cause production issues

Research query response time <5 minutes

Knowledge base covers 90%+ of common development questions

Example Workflow:


Additional RAW Use Cases:

Use Case 1: On-Demand Research


Use Case 2: Post-Meeting Research


Agent 11: PULSE 📰
Purpose: News aggregation and market intelligence

Responsibilities:

Aggregate tech news from multiple sources

Track competitor activity

Monitor industry trends

Curate personalized news briefings

Alert on important breaking news

Summarize long articles

Filter noise, highlight signal

Archive notable stories in Notion

AI Model: Llama 3.1 8B (local, efficient for summarization)

Inputs:

RSS feeds (tech blogs, news sites)

Keyword lists (technologies you use, competitors)

Source preferences (Hacker News, TechCrunch, etc.)

Categories (tech, business, geopolitical, local Mumbai/Vasai)

Outputs:

Daily morning briefing

Breaking news alerts (if critical)

Weekly digest (every Monday)

Curated articles in Notion

Trend analysis reports

Triggers:

Scheduled: Daily at 6 AM (prepare morning briefing)

Voice: "PULSE, brief me on today's news"

RSS: New article published (for breaking news detection)

Manual: "What's new in [topic]?"

Integrations:

RSS feeds (50+ tech sources)

Hacker News API

Reddit (r/webdev, r/reactjs, etc.)

Notion (news archive)

Slack/Telegram (breaking news alerts)

Success Metrics:

Daily briefing ready by 6 AM (100% on-time)

Signal-to-noise ratio >80% (relevant articles)

Breaking news alert latency <30 minutes

User satisfaction: "Briefing is useful" >90%

Example Workflow:


Additional PULSE Use Cases:

Use Case 1: Competitor Monitoring


Use Case 2: Custom Topic Deep Dive



User: "PULSE, what's happening in the Indian SaaS ecosystem?"
  ↓
PULSE agent:
  1. Search last 30 days of articles:
     - YourStory, Inc42, The Ken (Indian tech news)
     - Keywords: SaaS, B2B, funding, Indian startups
  2. Find 23 relevant articles
  3. Generate summary report:
     ```
     Indian SaaS Ecosystem - March 2026 Snapshot
     FUNDING:
     • $2.1B raised across 47 deals (Q1 2026)
     • Avg ticket size: $44.7M (up from $31M in Q1 2025)
     • Largest: Postman ($150M Series E)
     TRENDS:
     • AI-powered SaaS tools dominating new launches
     • Vertical SaaS (healthcare, education) growing 3x
     • International expansion: 60% targeting US/EU
     NOTABLE COMPANIES:
     • Freshworks: Acquired US competitor for $200M
     • Zoho: Launched AI assistant "Zia 2.0"
     • Razorpay: Expanded to 4 new countries
     OPPORTUNITIES:
     • Gap in AI-powered project management for SMBs
     • Need for India-first pricing strategies
     • Underserved: Marathi/regional language SaaS
     YOUR MIDAR POSITIONING:
     MIDAR's India-first pricing (₹2,999 vs $99 competitors) 
     aligns with market trend. Consider emphasizing this in 
     positioning and marketing.
     ```
  4. Save to Notion: "Indian SaaS Report - March 2026"
  5. Notify user: "Indian SaaS deep dive complete. 
                   23 articles analyzed. Report in Notion."
End of Agent Descriptions
Summary of CRUZ Agents:

Agent

Primary Model

Primary Function

Autonomous?

REACH 📨 

Gemini + Qwen 14B 

Lead generation 

Yes (2 AM daily) 

CATCH 📝 

Whisper Large v3 

Meeting transcription 

Semi (auto-detect) 

ECHO 💬 

Qwen 14B 

Communication 

No (on-demand) 

PM ⏱️ 

Qwen 14B 

Project management 

Semi (Monday 9 AM) 

FORGE ⚒️ 

Claude Sonnet 4 

Code generation 

No (on-demand) 

TITAN 🏗️ 

Qwen 14B 

DevOps & deployment 

Semi (on-deploy) 

MARK 🖊️ 

Qwen 14B 

Documentation 

Yes (post-commit) 

QT 🛡️ 

Qwen 14B 

Testing & QA 

Yes (pre-deploy) 

SENTINEL 👁️ 

Claude Sonnet 4 

Code review 

Yes (on-PR) 

RAW 🔬 

Llama 8B 

Tech research 

Yes (3 AM daily) 

PULSE 📰 

Llama 8B 

News aggregation 

Yes (6 AM daily) 

Next sections in PRD:

Functional Requirements

Non-Functional Requirements

Technical Stack

User Stories

Development Roadmap

Cost Analysis

Risk Assessment

Success Metrics

Functional Requirements
FR-1: Voice Interface
ID

Requirement

Priority

Acceptance Criteria

FR-1.1 

System SHALL accept voice commands via microphone on all devices 

P0 

Voice input works on Mac Mini, ThinkPad, Phone, iPad 

FR-1.2 

System SHALL convert speech to text with >95% accuracy 

P0 

Tested with 100 sample commands, <5 errors 

FR-1.3 

System SHALL respond with natural voice (not robotic) 

P1 

User survey: "Voice sounds natural" >80% 

FR-1.4 

System SHALL support wake word "Hey CRUZ" 

P1 

Wake word detection works from 3 meters away 

FR-1.5 

System SHALL process voice commands within 2 seconds 

P0 

95% of commands processed in <2 sec 

FR-1.6 

System SHALL handle multi-step voice commands 

P1 

"Do X, then Y, then notify me" works correctly 

FR-1.7 

System SHALL confirm ambiguous commands before executing 

P0 

Destructive actions always confirmed 

FR-2: Cross-Device Synchronization
ID

Requirement

Priority

Acceptance Criteria

FR-2.1 

System SHALL sync context across all devices in <2 seconds 

P0 

Context update on Phone visible on Mac <2 sec 

FR-2.2 

System SHALL persist conversation history 

P0 

History available after Mac Mini reboot 

FR-2.3 

System SHALL support offline mode with sync on reconnect 

P1 

Commands queued offline, executed on reconnect 

FR-2.4 

System SHALL show real-time agent status on all devices 

P1 

Active agent visible on all devices simultaneously 

FR-2.5 

System SHALL handle concurrent commands from multiple devices 

P1 

Two devices can issue commands simultaneously 

FR-3: Agent Orchestration
ID

Requirement

Priority

Acceptance Criteria

FR-3.1 

System SHALL route commands to appropriate agent 

P0 

95%+ routing accuracy over 100 commands 

FR-3.2 

System SHALL execute multi-agent workflows 

P0 

Complex workflows (3+ agents) complete successfully 

FR-3.3 

System SHALL handle agent failures gracefully 

P0 

Failed agent → retry or fallback, never crash 

FR-3.4 

System SHALL queue tasks when agents are busy 

P1 

Tasks queued and executed in order 

FR-3.5 

System SHALL provide real-time progress updates 

P1 

User sees "FORGE working..." notifications 

FR-3.6 

System SHALL allow manual agent override 

P2 

User can force specific agent for task 

FR-4: REACH Agent (Lead Generation)
ID

Requirement

Priority

Acceptance Criteria

FR-4.1 

Agent SHALL find leads based on search criteria 

P0 

Find 10+ leads for given criteria 

FR-4.2 

Agent SHALL extract contact information (email, LinkedIn) 

P0 

80%+ email discovery rate 

FR-4.3 

Agent SHALL draft personalized outreach emails 

P0 

Drafts pass human review 90%+ of time 

FR-4.4 

Agent SHALL track email open/reply rates 

P1 

Metrics visible in dashboard 

FR-4.5 

Agent SHALL schedule follow-up sequences 

P1 

Follow-ups sent on schedule 

FR-4.6 

Agent SHALL integrate with Notion CRM 

P0 

Leads saved to Notion database 

FR-5: CATCH Agent (Meeting Transcription)
ID

Requirement

Priority

Acceptance Criteria

FR-5.1 

Agent SHALL auto-detect and record meetings 

P0 

Calendar integration detects meetings 

FR-5.2 

Agent SHALL transcribe with <2% error rate 

P0 

Tested on 10 meetings, accuracy >98% 

FR-5.3 

Agent SHALL identify speakers (diarization) 

P0 

"You" vs "Client" labeled correctly 

FR-5.4 

Agent SHALL extract action items automatically 

P0 

90%+ of action items captured 

FR-5.5 

Agent SHALL generate meeting summaries 

P1 

Summary ready within 5 min of meeting end 

FR-5.6 

Agent SHALL create Linear tasks from action items 

P0 

Tasks created with correct details 

FR-5.7 

Agent SHALL send meeting notes to participants 

P1 

Notes emailed within 10 min of meeting 

FR-6: ECHO Agent (Communication)
ID

Requirement

Priority

Acceptance Criteria

FR-6.1 

Agent SHALL draft emails in <2 minutes 

P0 

90%+ of drafts ready in <2 min 

FR-6.2 

Agent SHALL match specified tone (professional/casual) 

P0 

User satisfaction >90% with tone 

FR-6.3 

Agent SHALL use appropriate email templates 

P0 

Template selection accurate 95%+ 

FR-6.4 

Agent SHALL include relevant context from CRM 

P1 

Client history referenced in emails 

FR-6.5 

Agent SHALL schedule follow-up reminders 

P1 

Reminders trigger on schedule 

FR-6.6 

Agent SHALL generate technical proposals 

P1 

Proposals require <15% human editing 

FR-7: PM Agent (Project Management)
ID

Requirement

Priority

Acceptance Criteria

FR-7.1 

Agent SHALL break features into tasks 

P0 

Task breakdown matches human expectations 

FR-7.2 

Agent SHALL estimate task duration 

P1 

Estimates within 20% of actual time 

FR-7.3 

Agent SHALL create sprint plans 

P0 

Sprint plans created in Linear 

FR-7.4 

Agent SHALL sync with Linear/JIRA 

P0 

Bi-directional sync works 

FR-7.5 

Agent SHALL generate Gantt charts 

P1 

Charts exported as images 

FR-7.6 

Agent SHALL track dependencies 

P1 

Blocked tasks flagged automatically 

FR-8: FORGE Agent (Code Generation)
ID

Requirement

Priority

Acceptance Criteria

FR-8.1 

Agent SHALL generate production-ready code 

P0 

Code passes tests 95%+ of time 

FR-8.2 

Agent SHALL follow project coding standards 

P0 

ESLint/Prettier checks pass 

FR-8.3 

Agent SHALL write unit tests for generated code 

P1 

Tests achieve 80%+ coverage 

FR-8.4 

Agent SHALL commit code with descriptive messages 

P0 

Commit messages follow convention 

FR-8.5 

Agent SHALL integrate third-party APIs 

P1 

API integrations work first try 80%+ 

FR-8.6 

Agent SHALL refactor existing code 

P1 

Refactors maintain functionality 

FR-9: TITAN Agent (DevOps)
ID

Requirement

Priority

Acceptance Criteria

FR-9.1 

Agent SHALL deploy to multiple platforms (Vercel, VPS) 

P0 

Deployments succeed 98%+ of time 

FR-9.2 

Agent SHALL perform health checks post-deploy 

P0 

Health checks run automatically 

FR-9.3 

Agent SHALL rollback on failure 

P0 

Automatic rollback on failed health check 

FR-9.4 

Agent SHALL manage environment variables 

P1 

Env vars synced across environments 

FR-9.5 

Agent SHALL monitor application uptime 

P1 

Downtime alerts sent within 2 min 

FR-9.6 

Agent SHALL backup before deployments 

P0 

Backups created every deployment 

FR-10: MARK Agent (Documentation)
ID

Requirement

Priority

Acceptance Criteria

FR-10.1 

Agent SHALL generate API documentation 

P0 

OpenAPI specs generated from code 

FR-10.2 

Agent SHALL write README files 

P0 

README includes setup, usage, examples 

FR-10.3 

Agent SHALL add JSDoc comments to code 

P1 

All functions have JSDoc 

FR-10.4 

Agent SHALL generate changelogs from commits 

P1 

Changelog follows Keep a Changelog format 

FR-10.5 

Agent SHALL sync docs to Notion/Confluence 

P1 

Docs updated within 10 min of code change 

FR-11: QT Agent (Testing)
ID

Requirement

Priority

Acceptance Criteria

FR-11.1 

Agent SHALL generate unit tests 

P0 

Tests achieve 80%+ coverage 

FR-11.2 

Agent SHALL run e2e tests (Playwright) 

P0 

E2E tests run on every deployment 

FR-11.3 

Agent SHALL perform security scans 

P0 

Zero high-severity vulnerabilities 

FR-11.4 

Agent SHALL check accessibility (WCAG) 

P1 

Accessibility score >95 

FR-11.5 

Agent SHALL run performance audits (Lighthouse) 

P1 

Performance score >90 

FR-11.6 

Agent SHALL block deployments if tests fail 

P0 

No deployment with failing tests 

FR-12: SENTINEL Agent (Code Review)
ID

Requirement

Priority

Acceptance Criteria

FR-12.1 

Agent SHALL review all pull requests 

P0 

All PRs reviewed within 30 min 

FR-12.2 

Agent SHALL check for security vulnerabilities 

P0 

Security issues flagged 100% 

FR-12.3 

Agent SHALL enforce coding standards 

P0 

Standards violations flagged 

FR-12.4 

Agent SHALL assess production readiness 

P0 

Readiness score provided for each PR 

FR-12.5 

Agent SHALL post inline code comments 

P1 

Comments posted on specific lines 

FR-12.6 

Agent SHALL auto-approve simple PRs 

P2 

Trivial changes auto-approved 

FR-13: RAW Agent (Research)
ID

Requirement

Priority

Acceptance Criteria

FR-13.1 

Agent SHALL check for dependency updates daily 

P0 

Daily checks run at 3 AM 

FR-13.2 

Agent SHALL research technical topics on demand 

P0 

Research summaries ready in <5 min 

FR-13.3 

Agent SHALL alert on breaking changes 

P0 

Breaking changes flagged within 24 hours 

FR-13.4 

Agent SHALL maintain knowledge base in Notion 

P1 

Research saved to Notion automatically 

FR-13.5 

Agent SHALL recommend library alternatives 

P1 

Alternatives provided when requested 

FR-14: PULSE Agent (News)
ID

Requirement

Priority

Acceptance Criteria

FR-14.1 

Agent SHALL deliver daily briefing by 6 AM 

P0 

Briefing ready 100% of days 

FR-14.2 

Agent SHALL filter news by relevance 

P0 

Signal-to-noise ratio >80% 

FR-14.3 

Agent SHALL alert on breaking tech news 

P1 

Alerts sent within 30 min 

FR-14.4 

Agent SHALL summarize long articles 

P1 

Summaries are 80%+ accurate 

FR-14.5 

Agent SHALL generate weekly digests 

P1 

Digest sent every Monday 9 AM 

FR-15: Data & Context Management
ID

Requirement

Priority

Acceptance Criteria

FR-15.1 

System SHALL persist conversation history 

P0 

History survives Mac Mini reboot 

FR-15.2 

System SHALL enable semantic search of history 

P1 

"Remember when we discussed X" works 

FR-15.3 

System SHALL back up data daily 

P0 

Automated daily backups 

FR-15.4 

System SHALL encrypt sensitive data at rest 

P0 

PostgreSQL encryption enabled 

FR-15.5 

System SHALL support data export 

P2 

User can export all data as JSON 

FR-16: Mobile & Remote Access
ID

Requirement

Priority

Acceptance Criteria

FR-16.1 

System SHALL work on Android (Nothing Phone 2) 

P0 

PWA installable and functional 

FR-16.2 

System SHALL work on iPad 

P0 

Web interface responsive on iPad 

FR-16.3 

System SHALL work on ThinkPad (Windows) 

P0 

Browser interface works on Windows 

FR-16.4 

System SHALL send push notifications 

P0 

Notifications received on phone 

FR-16.5 

System SHALL work over mobile data (4G/5G) 

P1 

Performance acceptable on mobile 

FR-16.6 

System SHALL support VPN access (Tailscale) 

P0 

Remote access works from anywhere 

Non-Functional Requirements
NFR-1: Performance
ID

Requirement

Target

Measurement

NFR-1.1 

Voice command response time 

<2 seconds 

Average latency over 100 commands 

NFR-1.2 

Cross-device sync latency 

<2 seconds 

Time from Phone action to Mac update 

NFR-1.3 

Agent task completion time 

Varies by agent 

See agent-specific metrics 

NFR-1.4 

Web dashboard load time 

<3 seconds 

Time to interactive on 4G 

NFR-1.5 

Database query response time 

<100ms 

95th percentile 

NFR-1.6 

Model inference time (local) 

<500ms 

Qwen 14B, Llama 8B average 

NFR-1.7 

API endpoint response time 

<200ms 

95th percentile 

NFR-2: Availability & Reliability
ID

Requirement

Target

Measurement

NFR-2.1 

System uptime 

99% 

Monthly uptime percentage 

NFR-2.2 

Mac Mini uptime 

24/7 

Continuous operation 

NFR-2.3 

Agent success rate 

90% 

Tasks completed / tasks started 

NFR-2.4 

Deployment success rate 

98% 

Successful deploys / total deploys 

NFR-2.5 

Data backup success rate 

100% 

Daily backups verified 

NFR-2.6 

Mean time to recovery (MTTR) 

<15 minutes 

Average recovery time 

NFR-2.7 

Error rate 

<1% 

Failed requests / total requests 

NFR-3: Scalability
ID

Requirement

Target

Measurement

NFR-3.1 

Concurrent agent tasks 

5+ simultaneous 

Tested with 5 parallel tasks 

NFR-3.2 

Voice commands per day 

100+ 

System handles 100+ commands/day 

NFR-3.3 

Database size growth 

<1 GB/month 

PostgreSQL database size 

NFR-3.4 

Conversation history retention 

1 year 

Old conversations archived 

NFR-3.5 

Model swap time 

<15 seconds 

Time to switch between Qwen/Llama 

NFR-4: Security
ID

Requirement

Target

Measurement

NFR-4.1 

Data encryption at rest 

AES-256 

PostgreSQL encryption verified 

NFR-4.2 

Data encryption in transit 

TLS 1.3 

All API calls use HTTPS 

NFR-4.3 

API authentication 

API key + secret 

All endpoints require auth 

NFR-4.4 

Secret management 

Bitwarden 

No secrets in code/config 

NFR-4.5 

VPN security 

WireGuard (Tailscale) 

All remote access via VPN 

NFR-4.6 

Dependency vulnerabilities 

Zero high-severity 

npm audit passes 

NFR-4.7 

Code injection prevention 

100% 

Input validation on all endpoints 

NFR-5: Usability
ID

Requirement

Target

Measurement

NFR-5.1 

Voice command accuracy 

95% 

Speech-to-text accuracy 

NFR-5.2 

Natural voice quality 

80% satisfaction 

User survey: "Sounds natural" 

NFR-5.3 

Dashboard intuitiveness 

<10 min onboarding 

Time to first successful command 

NFR-5.4 

Error messages clarity 

100% actionable 

All errors explain next steps 

NFR-5.5 

Mobile responsiveness 

All breakpoints 

Tested on 375px, 768px, 1920px 

NFR-6: Maintainability
ID

Requirement

Target

Measurement

NFR-6.1 

Code documentation 

100% coverage 

All functions have JSDoc 

NFR-6.2 

System documentation 

Complete 

README, API docs, architecture 

NFR-6.3 

Test coverage 

80% 

Unit + integration tests 

NFR-6.4 

Codebase organization 

Follows standards 

Linting passes 100% 

NFR-6.5 

Dependency updates 

Monthly 

Dependencies reviewed monthly 

NFR-7: Compliance & Privacy
ID

Requirement

Target

Measurement

NFR-7.1 

Data privacy 

Self-hosted only 

No data sent to third parties* 

NFR-7.2 

Client data isolation 

100% 

Client A cannot see Client B data 

NFR-7.3 

Data retention policy 

1 year 

Old data archived/deleted 

NFR-7.4 

Right to delete 

100% 

User can delete all data 

*Except AI API calls (Claude, Gemini) which are necessary for functionality and use enterprise data policies.

Technical Stack
Infrastructure
Component

Technology

Version

Purpose

Cost

Command Center 

Mac Mini M4 

24GB RAM 

Central server, runs all agents 

Owned 

Office Workstation 

ThinkPad 

32GB RAM 

Browser-based access 

Owned 

Mobile 

Nothing Phone 2 

Android 14 

PWA/voice interface 

Owned 

Tablet 

iPad 

iPadOS 17 

Web dashboard 

Owned 

UPS 

1000VA UPS 

 

Power backup 

₹6,000 

Backup Storage 

External HDD 

2TB 

Daily backups 

₹3,000 

Core Services
Service

Technology

Version

Purpose

Cost

Operating System 

macOS 

Sequoia 15.x 

Mac Mini OS 

₹0 

VPN 

Tailscale 

Latest 

Cross-device connectivity 

₹0 (free tier) 

Reverse Proxy 

Cloudflare Tunnel 

Latest 

Secure HTTPS access (optional) 

₹0 

Process Manager 

PM2 

5.x 

Keep agents running 

₹0 

Container Runtime 

Docker 

Latest 

Optional containerization 

₹0 

AI Models
Model

Provider

Parameters

Purpose

Cost

Claude Sonnet 4 

Anthropic 

 

FORGE, SENTINEL agents 

₹1,660/mo (Max) 

Claude API 

Anthropic 

 

Verification, validation tasks 

₹900/mo (estimated) 

Qwen 2.5 Coder 

Alibaba (local) 

14B 

REACH, ECHO, PM, TITAN, MARK, QT 

₹0 

Llama 3.1 

Meta (local) 

8B 

RAW, PULSE agents 

₹0 

Whisper Large v3 

OpenAI (local) 

 

CATCH agent (transcription) 

₹0 

Gemini Flash 2.5 

Google 

 

REACH supplementary research 

₹0 (250/day) 

Inworld TTS 1.5 Max 

Inworld 

 

Natural voice output (all devices) 

₹187/mo (Months 1-2), ₹71/mo (Month 3+ with caching) 

Deepgram 

Deepgram 

 

Alternative STT (optional) 

₹0 (200h/mo) 

Model Serving
Component

Technology

Version

Purpose

Cost

Local Model Runtime 

Ollama 

Latest 

Run Qwen, Llama, Whisper locally 

₹0 

Model Management 

Ollama CLI 

Latest 

Download, manage models 

₹0 

Agent Orchestration
Component

Technology

Version

Purpose

Cost

Framework 

CrewAI 

Latest 

Multi-agent coordination 

₹0 (open source) 

Alternative 

LangGraph 

Latest 

State machine orchestration (backup) 

₹0 

Job Queue 

BullMQ 

Latest 

Async task processing 

₹0 

Message Bus 

Redis 

7.x 

Agent communication 

₹0 (self-hosted) 

Data Layer
Component

Technology

Version

Purpose

Cost

Primary Database 

PostgreSQL 

16.x 

Persistent storage 

₹0 (self-hosted) 

Cache 

Redis 

7.x 

Fast context lookup 

₹0 (self-hosted) 

Vector Database 

Qdrant 

Latest 

Semantic memory 

₹0 (self-hosted) 

ORM 

Prisma 

6.x 

Database client 

₹0 

API Layer
Component

Technology

Version

Purpose

Cost

Backend Framework 

FastAPI 

0.110+ 

Python REST API 

₹0 

Alternative 

Express.js 

4.x 

Node.js REST API (backup) 

₹0 

WebSocket 

Socket.IO  

4.x 

Real-time updates 

₹0 

API Documentation 

Swagger/OpenAPI 

3.0 

Auto-generated docs 

₹0 

Frontend
Component

Technology

Version

Purpose

Cost

Framework 

React 

18.x 

Web dashboard 

₹0 

Build Tool 

Vite 

6.x 

Fast dev builds 

₹0 

Styling 

Tailwind CSS 

4.x 

UI styling 

₹0 

UI Components 

shadcn/ui 

Latest 

Component library 

₹0 

State Management 

Zustand 

Latest 

Global state 

₹0 

HTTP Client 

Axios 

Latest 

API requests 

₹0 

Voice Interface
Component

Technology

Version

Purpose

Cost

Speech-to-Text 

Whisper Large v3 

Local 

Voice input 

₹0 

Text-to-Speech 

Inworld TTS 1.5 Max 

Cloud API 

Natural voice output (all devices) 

₹187/mo (Months 1-2), ₹71/mo (Month 3+) 

Wake Word Detection 

Porcupine 

3.x 

"Hey CRUZ" detection 

₹0 (free tier) 

Audio Processing 

Web Audio API 

 

Browser audio capture 

₹0 

Voice Cloning 

Inworld 

Free 

Custom JARVIS British voice 

₹0 (included) 

Mobile Access
Component

Technology

Version

Purpose

Cost

Telegram Bot 

Telegraf.js 

4.x 

Simple text interface 

₹0 

PWA Framework 

Vite PWA 

Latest 

Installable web app 

₹0 

Push Notifications 

Firebase Cloud Messaging 

 

Mobile notifications 

₹0 (free tier) 

Alternative App 

React Native 

0.73+ 

Native mobile app (optional) 

₹0 

Development Tools
Component

Technology

Version

Purpose

Cost

Version Control 

GitHub 

 

Code repository 

₹0 (free tier) 

CI/CD 

GitHub Actions 

 

Automated pipelines 

₹0 (free tier) 

Code Editor 

VS Code 

Latest 

Development environment 

₹0 

Linter 

ESLint 

9.x 

Code quality 

₹0 

Formatter 

Prettier 

3.x 

Code formatting 

₹0 

TypeScript 

TypeScript 

5.x 

Type safety 

₹0 

Testing
Component

Technology

Version

Purpose

Cost

Unit Testing 

Vitest 

2.x 

Fast unit tests 

₹0 

E2E Testing 

Playwright 

Latest 

Browser automation 

₹0 

API Testing 

Postman 

 

Manual API testing 

₹0 (free tier) 

Load Testing 

Artillery 

Latest 

Performance testing 

₹0 

Security Scanning 

npm audit 

Built-in 

Dependency vulnerabilities 

₹0 

Accessibility 

axe-core 

Latest 

WCAG compliance 

₹0 

Deployment & Hosting
Component

Technology

Version

Purpose

Cost

Frontend Hosting 

Vercel 

 

Dashboard deployment 

₹0 (free tier) 

Backend Hosting 

Railway 

 

API deployment (optional) 

₹0 (free tier) 

VPS 

Hostinger 

 

Client deployments 

Varies by client 

DNS 

Cloudflare 

 

Domain management 

₹0 (free tier) 

SSL 

Let's Encrypt 

 

HTTPS certificates 

₹0 

Project Management
Component

Technology

Version

Purpose

Cost

Task Management 

Linear 

 

Issue tracking 

₹0 (free tier) 

Documentation 

Notion 

 

Knowledge base 

₹0 (free tier) 

Time Tracking 

Toggl 

 

Time logging (optional) 

₹0 (free tier) 

Communication
Component

Technology

Version

Purpose

Cost

Email 

Gmail 

 

Client communication 

₹0 

Email Sending 

SendGrid 

 

Automated emails 

₹0 (100/day) 

Messaging 

Slack 

 

Team/client chat 

₹0 (free tier) 

Video Calls 

Teams/Meet 

 

Client meetings 

₹0 

Lead Generation
Component

Technology

Version

Purpose

Cost

Contact Data 

AI Sales Platform | Apollo.io - Outbound, Inbound & Automation  

 

Email finding 

₹0 (50/mo) 

Email Verification 

Trouver des emails en quelques secondes • Hunter (Email Hunter)  

 

Email validation 

₹0 (50/mo) 

Proxy (Optional) 

Bright Data 

 

LinkedIn scraping 

₹500/mo 

Monitoring
Component

Technology

Version

Purpose

Cost

Uptime Monitoring 

Uptime Kuma 

Latest 

Service health checks 

₹0 (self-hosted) 

Log Aggregation 

Loki 

Latest 

Centralized logging 

₹0 (self-hosted) 

Error Tracking 

Sentry 

 

Error monitoring (optional) 

₹0 (free tier) 

Security
Component

Technology

Version

Purpose

Cost

Password Manager 

Bitwarden 

 

Secret storage 

₹0 (free tier) 

Encryption 

macOS FileVault 

Built-in 

Disk encryption 

₹0 

Firewall 

macOS Firewall 

Built-in 

Network protection 

₹0 

User Stories & Use Cases
Epic 1: Morning Routine Automation
As a freelance developer, I want CRUZ to brief me each morning so I can start my day informed and prepared.

User Story 1.1: Morning Briefing


As a user
I want to receive a daily briefing at 8 AM
So that I know my schedule, overnight updates, and action items
Acceptance Criteria:
- Briefing includes: today's calendar, overnight agent work, pending tasks, tech news
- Delivered via voice when I say "Good morning CRUZ"
- Also available as text notification on phone
- Takes <2 minutes to consume
Priority: P0
Story Points: 5
User Story 1.2: Overnight Lead Generation


As a user
I want REACH to find leads while I sleep
So that I wake up to new business opportunities
Acceptance Criteria:
- REACH runs at 2 AM daily (autonomous)
- Finds 5-10 qualified leads based on my criteria
- Saves leads to Notion CRM
- Includes contact info and brief company summary
- Results ready in morning briefing
Priority: P1
Story Points: 8
Epic 2: Mobile Productivity (Train Commute)
As a user commuting by train, I want to manage tasks via voice on my phone so I don't waste 1.5 hours daily.

User Story 2.1: Voice To-Do Management


As a user on my phone
I want to add tasks to my to-do list via voice
So that I can capture ideas during my commute
Acceptance Criteria:
- Say "Add to to-do: [task description]"
- Task created in Linear with appropriate project
- Confirmation spoken back to me
- Works offline, syncs when connection restored
Priority: P0
Story Points: 5
User Story 2.2: Email Draft Review


As a user on my phone
I want to review and approve email drafts created by ECHO
So that I can handle communication during commute
Acceptance Criteria:
- ECHO drafts appear in mobile interface
- I can edit, approve, or reject
- Approved emails sent immediately
- Works via Telegram bot or PWA
Priority: P1
Story Points: 3
Epic 3: Office Deployment Automation
As a developer at the office, I want to deploy projects via voice command so I can focus on strategic work.

User Story 3.1: Voice-Commanded Deployment


As a user at my ThinkPad
I want to say "Deploy AMA website to production"
So that deployment happens hands-free
Acceptance Criteria:
- FORGE builds production bundle
- QT runs all tests
- SENTINEL does final review
- TITAN deploys to Hostinger VPS
- I receive notification when complete (15-20 min)
- Rollback automatic if health checks fail
Priority: P0
Story Points: 13
User Story 3.2: Real-Time Deployment Progress


As a user who initiated a deployment
I want to see real-time progress updates
So that I know what's happening
Acceptance Criteria:
- Dashboard shows: "FORGE building... 40% complete"
- Each agent step visible (build → test → review → deploy)
- ETA provided based on historical data
- Can view detailed logs if needed
Priority: P1
Story Points: 5
Epic 4: Meeting Intelligence
As a user in client calls, I want CATCH to handle note-taking so I can focus on the conversation.

User Story 4.1: Automatic Meeting Recording


As a user with a calendar event
I want CATCH to automatically record when meeting starts
So that I don't have to remember to start recording
Acceptance Criteria:
- Calendar integration detects meeting start
- Recording begins automatically (with consent banner)
- Transcription happens in real-time
- Speaker labels: "You" vs "Client Name"
- Recording stops when meeting ends
Priority: P0
Story Points: 8
User Story 4.2: Action Item Extraction


As a user in a meeting
I want CATCH to extract action items automatically
So that nothing falls through the cracks
Acceptance Criteria:
- Action items detected from phrases like "you will", "I'll", "we need to"
- Each action item has: what, who, when
- Linear tasks created automatically
- Action items included in meeting summary
- 90%+ accuracy (tested on 10 meetings)
Priority: P0
Story Points: 8
User Story 4.3: Post-Meeting Workflow


As a user who just finished a client call
I want CRUZ to automatically handle follow-up tasks
So that I don't waste time on administrative work
Acceptance Criteria:
- Meeting transcript saved to Notion
- Action items converted to Linear tasks
- Meeting notes emailed to client
- PM agent creates project plan if new project discussed
- ECHO drafts follow-up email
- All happens within 10 minutes of call ending
Priority: P0
Story Points: 13
Epic 5: Code Quality Assurance
As a developer, I want automated code review and testing so code quality stays high without manual effort.

User Story 5.1: Automatic PR Review


As a user who creates a pull request
I want SENTINEL to review it within 30 minutes
So that I get fast feedback
Acceptance Criteria:
- Review covers: security, performance, accessibility, best practices
- Inline comments on specific lines
- Overall assessment (Approve / Request Changes / Comment)
- Suggests fixes for issues found
- GitHub PR updated with review
Priority: P0
Story Points: 13
User Story 5.2: Pre-Deployment Testing Gate


As a user deploying code
I want QT to block deployment if tests fail
So that broken code never reaches production
Acceptance Criteria:
- QT runs automatically before TITAN deploys
- Tests include: unit, integration, e2e, security, accessibility
- Deployment halted if any test fails
- Clear error message explains which test failed
- Manual override available (with confirmation)
Priority: P0
Story Points: 8
Epic 6: Cross-Device Continuity
As a user working across multiple devices, I want seamless context so I can pick up where I left off.

User Story 6.1: Device Handoff


As a user who starts a task on my phone
I want to continue it on my Mac
So that I'm not limited by device
Acceptance Criteria:
- Start command on phone: "FORGE, create contact form"
- Switch to Mac, say "Show me what FORGE is building"
- See exact same context, progress, and results
- Sync latency <2 seconds
- Works across all 4 devices (Mac, ThinkPad, Phone, iPad)
Priority: P0
Story Points: 8
User Story 6.2: Context Awareness


As a user who says "Deploy that"
I want CRUZ to know what "that" refers to
So that I don't have to repeat myself
Acceptance Criteria:
- CRUZ maintains conversation context
- "Deploy that" works if I just discussed AMA website
- "Email him" works if I just mentioned a client name
- Context survives device switches
- Context clears after 30 min of inactivity or explicit "Clear context"
Priority: P1
Story Points: 8
Epic 7: Research & Knowledge Management
As a developer, I want CRUZ to handle research so I stay current without spending hours reading.

User Story 7.1: Dependency Update Monitoring


As a user with multiple projects
I want RAW to alert me about important dependency updates
So that I'm not caught off-guard by breaking changes
Acceptance Criteria:
- Daily check of all project dependencies (3 AM)
- Categorize updates: patch (safe), minor (review), major (breaking)
- Alert on security vulnerabilities immediately
- Research major updates (breaking changes, migration effort)
- Create Linear tasks for updates with recommended timeline
Priority: P0
Story Points: 8
User Story 7.2: On-Demand Technical Research


As a user debugging a problem
I want to ask RAW to research solutions
So that I get answers faster than Googling
Acceptance Criteria:
- Say "RAW, why am I getting [error message]"
- RAW searches: docs, Stack Overflow, GitHub issues
- Provides synthesized answer in <5 minutes
- Includes code examples when relevant
- Saves research to Notion for future reference
Priority: P1
Story Points: 5
Epic 8: Client Communication
As a freelancer, I want CRUZ to handle routine communication so I can focus on delivery.

User Story 8.1: Email Drafting


As a user who needs to email a client
I want ECHO to draft it for me
So that I save 10-15 minutes per email
Acceptance Criteria:
- Say "ECHO, draft email to [client] about [topic]"
- ECHO loads client context from CRM
- Generates email in appropriate tone
- I can specify tone: professional / casual / urgent
- Draft ready for review in <2 minutes
- I can edit before sending
Priority: P0
Story Points: 5
User Story 8.2: Proposal Generation


As a user who received a project inquiry
I want PM and ECHO to generate a proposal
So that I don't spend 2-3 hours on it
Acceptance Criteria:
- Input: project requirements (from email or meeting notes)
- PM breaks down into tasks and estimates timeline
- PM calculates cost based on hourly rate
- ECHO writes proposal document with: scope, timeline, cost, deliverables
- Output: PDF ready to send
- Time to generate: <15 minutes
Priority: P1
Story Points: 13
Development Roadmap
Phase 1: Foundation (Weeks 1-2)
Goal: Get basic agent infrastructure working with 3 core agents on Mac Mini

Week 1: Core Infrastructure Setup
Day 1-2: Mac Mini environment setup

Install Ollama, PostgreSQL, Redis

Download Qwen 14B, Llama 8B, Whisper Large v3

Test model loading and inference

Set up Python/Node.js development environment

Day 3-4: Data layer setup

PostgreSQL schema design (users, conversations, tasks, logs)

Redis cache structure

Prisma ORM setup and migrations

Database backup automation (daily cron job)

Day 5-7: API server foundation

FastAPI project structure

Basic endpoints: /health, /chat, /agents

WebSocket for real-time updates

Authentication middleware (API keys)

Error handling and logging

Deliverables:

✅ Mac Mini running 24/7 with UPS

✅ All models loaded and tested

✅ Database schema created

✅ API server responding to basic requests

Week 2: First 3 Agents (PM, ECHO, FORGE)
Day 1-2: Agent orchestration framework

CrewAI integration

Agent base class

Job queue setup (BullMQ + Redis)

Agent-to-agent communication bus

Day 3: PM Agent (basic version)

Linear API integration

Task creation from text description

Basic sprint planning

Test with simple project

Day 4: ECHO Agent (basic version)

Email template system

Qwen 14B integration for drafting

Gmail SMTP for sending

Test with sample emails

Day 5-6: FORGE Agent (basic version)

Claude Sonnet 4 API integration

Simple code generation (single file)

Git integration (commit, push)

Test with React component generation

Day 7: Integration testing

Test multi-agent workflow: PM creates task → FORGE builds code → Git commit

Fix bugs

Document learnings

Deliverables:

✅ 3 agents operational

✅ Agents can be triggered via API

✅ Multi-agent workflow works

✅ Basic logging and monitoring

Phase 2: Voice & Mobile (Weeks 3-4)
Goal: Add voice interface and mobile access

Week 3: Voice Interface (Mac Mini + ThinkPad)
Day 1-2: Speech-to-Text setup

Whisper Large v3 integration

Microphone input capture (macOS)

Real-time transcription pipeline

Test accuracy with 50 sample commands

Day 3-4: Text-to-Speech setup

ElevenLabs API integration

Voice synthesis for agent responses

Audio playback (macOS + browser)

Test naturalness with multiple phrases

Day 5: Voice command parser

Intent classification (which agent?)

Entity extraction (project names, actions)

Claude Sonnet 4 as NLU engine

Test with 100 varied commands

Day 6-7: Web dashboard (ThinkPad)

React + Vite + Tailwind setup

Voice input via browser (Web Speech API)

Real-time agent status display

WebSocket integration for updates

Deploy to Vercel

Deliverables:

✅ Voice commands work on Mac Mini

✅ Voice commands work via web dashboard

✅ Natural voice responses (not robotic)

✅ 95%+ command accuracy

Week 4: Mobile Access
Day 1-2: Telegram Bot

Bot creation and token setup

Telegraf.js server on Mac Mini

Text command processing

Push notification on task completion

Test on Nothing Phone 2

Day 3-5: Progressive Web App

Make web dashboard installable (PWA)

Service worker for offline support

Push notification setup (Firebase)

Voice input via mobile browser

Responsive design (375px, 768px, 1920px)

Test on Phone, iPad, ThinkPad

Day 6-7: Cross-device sync

Tailscale VPN setup

Test phone → Mac Mini → ThinkPad sync

Sync latency measurement (<2 sec target)

Context persistence across devices

Deliverables:

✅ Telegram bot functional

✅ PWA installable on Android

✅ Voice works on all devices

✅ Cross-device sync <2 seconds

Phase 3: Remaining Agents (Weeks 5-6)
Goal: Implement the remaining 8 agents

Week 5: DevOps & Quality (TITAN, QT, SENTINEL, MARK)
Day 1-2: TITAN Agent

Vercel API integration

SSH to Hostinger VPS

Deployment pipeline (build → test → deploy → health check)

Rollback mechanism

Test with AMA website deployment

Day 2-3: QT Agent

Playwright setup for e2e tests

Test generation with Qwen 14B

Lighthouse CI integration

npm audit automation

Test with multiple projects

Day 4: SENTINEL Agent

GitHub API for PR access

Code review with Claude Sonnet 4

Inline comment posting

Approval/rejection workflow

Test with sample PRs

Day 5: MARK Agent

JSDoc generation from code

OpenAPI spec generation

README template system

Notion API for doc sync

Test with existing projects

Day 6-7: Integration testing

Test full deployment workflow: FORGE → QT → SENTINEL → TITAN → MARK

Verify all agents work together

Fix edge cases

Deliverables:

✅ 4 more agents operational (total: 7/11)

✅ Full CI/CD pipeline working

✅ Automated deployment to production

Week 6: Research & Automation (REACH, CATCH, RAW, PULSE)
Day 1-2: REACH Agent

Gemini API integration

AI Sales Platform | Apollo.io - Outbound, Inbound & Automation  + Trouver des emails en quelques secondes • Hunter (Email Hunter)  integration

Email template system

SendGrid for outreach

Notion CRM integration

Test with lead generation

Day 2-3: CATCH Agent

OBS Studio for screen recording

Audio extraction pipeline

Real-time Whisper transcription

Speaker diarization

Action item extraction (Qwen 14B)

Test with sample meeting recording

Day 4: RAW Agent

npm outdated automation

Dependency changelog scraping

Documentation search

Notion knowledge base integration

Schedule for 3 AM daily run

Day 5: PULSE Agent

RSS feed aggregation (50+ sources)

Hacker News API

Article summarization (Llama 8B)

Categorization and filtering

Notion archive integration

Schedule for 6 AM daily run

Day 6-7: Autonomous agent testing

Let REACH, RAW, PULSE run overnight

Verify morning briefing ready by 8 AM

Test CATCH with real client call

Measure accuracy and usefulness

Deliverables:

✅ All 11 agents operational

✅ Autonomous agents running on schedule

✅ Morning briefing system working

Phase 4: Polish & Optimization (Weeks 7-8)
Goal: Refine UX, optimize performance, add production-ready features

Week 7: UX Refinement
Day 1-2: Dashboard improvements

Real-time agent status visualization

Task progress indicators

Conversation history search

Dark mode support

Keyboard shortcuts

Day 3-4: Voice UX enhancements

Wake word detection ("Hey CRUZ")

Conversation context memory

Multi-turn dialogues

Interruption handling

Error recovery ("I didn't understand, please repeat")

Day 5-6: Mobile UX polish

Offline mode improvements

Better push notifications

Quick actions (Siri Shortcuts)

Widget for common commands

Day 7: User testing

Use CRUZ for 1 full day across all devices

Document friction points

Collect improvement ideas

Deliverables:

✅ Dashboard polished and intuitive

✅ Voice UX smooth and natural

✅ Mobile experience comparable to desktop

Week 8: Performance & Reliability
Day 1-2: Performance optimization

Database query optimization

Redis caching strategy

Model inference speed tuning

API response time optimization

Bundle size reduction

Day 3-4: Reliability improvements

Error handling hardening

Retry logic for failed tasks

Circuit breakers for external APIs

Health check system

Alerting setup (Uptime Kuma)

Day 5: Documentation

System architecture diagram

Agent interaction flows

API documentation (Swagger)

Deployment guide

Troubleshooting guide

Day 6-7: Final testing

Run 100+ commands across all agents

Measure success rate (target: >90%)

Stress test with concurrent tasks

24-hour uptime test

Deliverables:

✅ System optimized for performance

✅ Reliability hardened

✅ Complete documentation

✅ Production-ready CRUZ system

Post-Launch: Iteration (Week 9+)
Goal: Use CRUZ daily, gather data, iterate based on real usage

Week 9-10: Real-World Usage
Use CRUZ for all daily workflows

Track metrics:

Time saved per day

Agent success rates

Commands issued

Failed tasks (and why)

User satisfaction

Week 11-12: Data-Driven Improvements
Analyze usage data

Identify most/least used agents

Find and fix pain points

Add missing features

Tune agent prompts for better results

Ongoing Maintenance
Weekly dependency updates (RAW agent)

Monthly model updates (Qwen, Llama)

Quarterly feature additions

Continuous prompt refinement

Cost Analysis
One-Time Costs
Item

Cost

Justification

Mac Mini M4 24GB 

₹0 

Already owned (purchased 1 year ago) 

UPS (1000VA) 

₹6,000 

Power backup for 24/7 operation 

External HDD (2TB) 

₹3,000 

Daily backups (optional if using existing) 

Domain (1 year) 

₹500 

cruz.yourdomain.com subdomain 

TOTAL 

₹9,500 

One-time investment 

Monthly Recurring Costs
Months 1-2 (No Caching):

Category

Item

Cost

Annual

Notes

Infrastructure 

Mac Mini power (24/7) 

₹202 

₹2,424 

35W avg × ₹8/kWh 

 

UPS amortization 

₹167 

₹2,000 

₹6,000 ÷ 36 months 

 

Internet 

₹0 

₹0 

Already paid 2 years 

 

Static IP 

₹0 

₹0 

Included 

 

Domain 

₹42 

₹500 

SSL + DNS 

 

Subtotal 

₹411 

₹4,924 

 

AI Services 

Claude Max 

₹1,660 

₹19,920 

Unlimited Sonnet 4 

 

Claude API (verify) 

₹900 

₹10,800 

Estimated usage 

 

Gemini Flash 

₹0 

₹0 

250 req/day free 

 

Subtotal 

₹2,560 

₹30,720 

 

Voice 

Inworld TTS 1.5 Max 

₹187 

₹2,244 

300 min/month, pay-as-you-go 

 

Deepgram STT 

₹0 

₹0 

200 hrs/mo free (backup) 

 

Subtotal 

₹187 

₹2,244 

 

Backup 

Google Drive 

₹130 

₹1,560 

100GB storage 

 

Subtotal 

₹130 

₹1,560 

 

Tools 

Linear 

₹0 

₹0 

Free tier 

 

Notion 

₹0 

₹0 

Free tier 

 

GitHub 

₹0 

₹0 

Free tier 

 

Tailscale 

₹0 

₹0 

Free tier (100 devices) 

 

Firebase 

₹0 

₹0 

Free tier 

 

Vercel 

₹0 

₹0 

Free tier 

 

All other tools 

₹0 

₹0 

Free tiers sufficient 

 

Subtotal 

₹0 

₹0 

 

Lead Gen 

AI Sales Platform | Apollo.io - Outbound, Inbound & Automation  

₹0 

₹0 

50 credits/mo free 

 

Trouver des emails en quelques secondes • Hunter (Email Hunter)  

₹0 

₹0 

50 searches/mo free 

 

SendGrid 

₹0 

₹0 

100 emails/day free 

 

Proxy (optional) 

₹0 

₹0 

Not using initially 

 

Subtotal 

₹0 

₹0 

 

TOTAL (Months 1-2) 

 

₹3,288 

₹39,456 

Without caching 

Month 3+ (With Caching):

Category

Item

Cost

Annual

Notes

Infrastructure 

 

₹411 

₹4,924 

Same as above 

AI Services 

 

₹2,560 

₹30,720 

Same as above 

Voice 

Inworld TTS (cached) 

₹71 

₹852 

60% cached, 40% API calls 

 

Cache setup (one-time) 

₹125 

 

Month 3 only 

 

Subtotal 

₹71 

₹852 

 

Backup 

Google Drive 

₹130 

₹1,560 

Same as above 

Tools 

 

₹0 

₹0 

Same as above 

Lead Gen 

 

₹0 

₹0 

Same as above 

TOTAL (Month 3+) 

 

₹3,172 

₹38,064 

With caching 

Cost Comparison
Scenario

Monthly Cost

What You Get

Hiring VA 

₹15,000 - ₹25,000 

Limited hours, single person, no technical skills 

SaaS Tools Bundle 

₹8,000 - ₹12,000 

Zapier Pro + Linear + Notion + monday.com | Outpace everyone with the best AI work platform  + others 

AI Assistants (Enterprise) 

₹10,000 - ₹20,000 

GitHub Copilot Business + ChatGPT Team + others 

CRUZ (Months 1-2) 

₹3,288 

11 specialized agents, 24/7, voice control, cross-device 

CRUZ (Month 3+) 

₹3,172 

Same as above with optimized TTS caching 

Savings: ₹4,712 - ₹21,828 per month vs. alternatives

ROI Calculation
Investment:

Development time: 120 hours × ₹1,250/hr = ₹1,50,000 (opportunity cost)

One-time costs: ₹9,500

Total initial investment: ₹1,59,500

Monthly Benefits:

Time saved: 12 hrs/week × 4 weeks = 48 hrs/month × ₹1,250/hr = ₹60,000

Additional client capacity: +1 client = ₹25,000/month

Avoided SaaS costs: ₹8,000/month

Total monthly benefit: ₹93,000

Net Monthly Gain:

Months 1-2: ₹93,000 (benefits) - ₹3,288 (operating cost) = ₹89,712/month

Month 3+: ₹93,000 (benefits) - ₹3,172 (operating cost) = ₹89,828/month

Payback Period:
₹1,59,500 (investment) ÷ ₹89,712 (monthly gain) = 1.78 months

12-Month ROI:

First 2 months: ₹89,712 × 2 = ₹1,79,424

Next 10 months: ₹89,828 × 10 = ₹8,98,280

One-time cache setup (Month 3): -₹125

Total gain: ₹10,77,579

Less investment: ₹1,59,500

Net gain: ₹9,18,079

Risk Assessment
Technical Risks
Risk

Probability

Impact

Mitigation

Mac Mini hardware failure 

Low 

High 

UPS for power protection, daily backups, keep old laptop as backup server 

Internet outage 

Medium 

High 

Mobile hotspot as backup, queue tasks offline 

Model inference too slow 

Medium 

Medium 

Profile and optimize, reduce batch sizes, consider Mac Mini M4 Pro upgrade 

Claude API quota exhausted 

Low 

Medium 

Max plan has unlimited Sonnet 4, implement rate limiting just in case 

Data loss 

Low 

High 

Daily automated backups, weekly manual verification, external HDD storage 

Voice recognition accuracy poor 

Low 

Medium 

Fall back to text commands, retrain on personal voice patterns 

Agent coordination failures 

Medium 

Medium 

Robust error handling, retry logic, manual intervention mode 

Operational Risks
Risk

Probability

Impact

Mitigation

Over-reliance on automation 

High 

Medium 

Manual review for critical tasks, always verify agent work 

Context confusion across devices 

Medium 

Low 

Clear context timeout (30 min), explicit context reset command 

Incomplete agent tasks 

Medium 

Medium 

Task timeout alerts, stuck task detector, manual completion mode 

Privacy breach (accidental) 

Low 

High 

No client data in public repos, encrypted database, secure VPN only 

Burnout from maintenance 

Medium 

Medium 

Keep system simple, automate maintenance tasks, schedule downtime 

Business Risks
Risk

Probability

Impact

Mitigation

Time investment doesn't pay off 

Low 

High 

Start with 3 agents (MVP), validate value before building all 11 

Client dissatisfaction with AI-generated work 

Low 

Medium 

Always human-review before sending to clients, position as "AI-assisted" 

Dependency on specific AI providers 

Medium 

Medium 

Support multiple models (Claude + Qwen + Llama), easy to swap 

Regulatory changes (AI laws) 

Low 

Medium 

Keep usage personal, avoid client data in AI training, comply with GDPR-like principles 

Security Risks
Risk

Probability

Impact

Mitigation

API key compromise 

Low 

High 

Store in Bitwarden, never commit to Git, rotate quarterly 

Unauthorized access to Mac Mini 

Low 

High 

Tailscale VPN only, no public IP exposure, macOS firewall enabled 

Client data leak 

Low 

Critical 

Separate databases per client, encryption at rest, no logs of sensitive data 

Model injection attacks 

Low 

Medium 

Input validation, sanitize all user inputs, never execute code blindly 

Success Metrics
Primary Metrics (Measured Weekly)
Metric

Target

Measurement Method

Review Frequency

Time Saved 

8-15 hours/week 

Manual time tracking of tasks done by agents 

Weekly 

Agent Success Rate 

90% 

Completed tasks ÷ Total tasks initiated 

Weekly 

Voice Command Accuracy 

95% 

Correctly interpreted ÷ Total commands 

Weekly 

System Uptime 

99% 

Mac Mini uptime percentage 

Weekly 

User Satisfaction 

4/5 

Weekly self-rating: "Was CRUZ helpful this week?" 

Weekly 

Secondary Metrics (Measured Monthly)
Metric

Target

Measurement Method

Client Capacity 

+1 to 2 clients 

Number of active clients vs. baseline 

Delivery Speed 

-20% time 

Average task completion time vs. baseline 

Code Quality 

80%+ test coverage 

Code coverage reports from QT agent 

Documentation Coverage 

100% 

All functions have JSDoc (MARK agent) 

Lead Generation 

50+ leads/month 

REACH agent output count 

Email Response Time 

<4 hours 

Time from email received to draft ready 

Deployment Frequency 

20+ deploys/month 

TITAN agent deployment count 

Incident Rate 

<2 incidents/month 

Production bugs, downtime events 

Tertiary Metrics (Measured Quarterly)
Metric

Target

Measurement Method

ROI 

300% 

(Time saved value - Operating cost) ÷ Operating cost 

Client Satisfaction 

4.5/5 

Client feedback surveys 

After-Hours Work 

-30% 

Hours worked after 8 PM 

Work-Life Balance 

Improved 

Self-assessment, spouse feedback 

New Features Shipped 

+30% 

Features delivered to clients vs. baseline 

Agent-Specific Metrics
Agent

Success Metric

Target

REACH 

Leads found per week 

10-15 leads 

CATCH 

Transcription accuracy 

98% 

ECHO 

Draft acceptance rate 

90% (minimal edits) 

PM 

Sprint completion rate 

80% 

FORGE 

Code pass rate (tests) 

95% 

TITAN 

Deployment success rate 

98% 

MARK 

Documentation coverage 

100% 

QT 

Bug catch rate 

90% of bugs found pre-production 

SENTINEL 

False positive rate 

<10% (issues flagged incorrectly) 

RAW 

Research query response time 

<5 minutes 

PULSE 

Daily briefing on-time rate 

100% (ready by 6 AM) 

Dashboard KPIs (Real-Time)
Track these in a real-time dashboard:

Active agent status (which agents are running)

Tasks queued (waiting to be processed)

Tasks in progress (currently being executed)

Tasks completed today

System health (CPU, RAM, disk, network)

API quota usage (Claude, Gemini)

Error rate (last hour, last 24 hours)

Dependencies & Constraints
Technical Dependencies
Dependency

Version

Critical?

Fallback

macOS 

Sequoia 15.x 

Yes 

Cannot run on Windows/Linux (Ollama works but ecosystem optimized for macOS) 

Ollama 

Latest 

Yes 

Manual model serving with llama.cpp (harder to manage) 

Claude Max Subscription 

Active 

Yes 

Switch to GPT-4 or other API (major rework for FORGE/SENTINEL) 

Tailscale 

Active account 

Yes 

Manual VPN setup (WireGuard) 

PostgreSQL 

16.x 

Yes 

SQLite (less scalable) or MySQL 

Redis 

7.x 

Yes 

In-memory JavaScript objects (loses persistence) 

Node.js 

20.x LTS 

Yes 

Bun (experimental) 

Python 

3.11+ 

Yes 

None (needed for FastAPI) 

External Service Dependencies
Service

Free Tier Limit

Paid Alternative

Risk

Gemini API 

250 req/day 

Upgrade to paid tier (₹1,000/mo) 

Low (REACH can use only Claude) 

Linear 

Unlimited issues 

GitHub Issues (free) 

Low 

Notion 

Personal workspace 

Confluence (₹500/mo) 

Low 

Vercel 

100 GB bandwidth/mo 

Netlify or self-host 

Low 

Firebase 

Unlimited notifications 

Self-hosted push server 

Medium 

AI Sales Platform | Apollo.io - Outbound, Inbound & Automation  

50 credits/mo 

Paid tier (₹2,000/mo) 

Medium 

Trouver des emails en quelques secondes • Hunter (Email Hunter)  

50 searches/mo 

Paid tier (₹1,500/mo) 

Medium 

SendGrid 

100 emails/day 

AWS SES (₹0.10/email) 

Low 

Hardware Constraints
Constraint

Impact

Workaround

24GB RAM limit 

Can only run ONE large model at a time 

Model swapping (5-15 sec), prioritize critical agents 

Single Mac Mini 

No redundancy 

Accept downtime risk, keep old laptop as backup 

256GB SSD 

Limited storage for models 

External SSD (₹3,000), delete unused models 

50W power limit 

Can't run all agents simultaneously at full load 

Job queue, serialize heavy tasks 

No GPU 

Slower model inference 

Accept slower speed, use smaller models when possible 

Time Constraints
Phase

Duration

Can't Compress Because...

Phase 1 

2 weeks 

Need to learn CrewAI, test models, validate architecture 

Phase 2 

2 weeks 

Voice UX requires iteration, mobile testing takes time 

Phase 3 

2 weeks 

Each agent needs testing, integration complexity 

Phase 4 

2 weeks 

Polish requires real usage data, can't rush UX 

Total 

8 weeks 

Minimum viable timeline at 15-20 hrs/week 

Regulatory & Compliance Constraints
Constraint

Applies To

Compliance Approach

GDPR (if EU clients) 

Client data 

Store in EU region (not applicable yet), get consent 

DPDPA (India) 

Personal data 

Minimize data collection, explicit consent, easy deletion 

Client NDAs 

Client code/data 

Secure storage, no AI training on client data, encryption 

Tax Regulations 

Income from clients 

Separate concern (already filing ITR-3) 

Appendices
Appendix A: Glossary
Term

Definition

Agent 

Specialized AI assistant focused on a specific workflow (e.g., FORGE for coding, ECHO for communication) 

Orchestration 

Coordination of multiple agents to complete complex workflows 

NLU 

Natural Language Understanding - parsing user commands to extract intent and entities 

STT 

Speech-to-Text - converting spoken words to text 

TTS 

Text-to-Speech - converting text to natural-sounding speech 

Wake Word 

Specific phrase that activates voice assistant (e.g., "Hey CRUZ") 

Context Window 

Recent conversation history the system remembers 

Model Swap 

Switching from one AI model to another (e.g., Qwen 14B → Llama 8B) 

Vector Database 

Database optimized for semantic search (Qdrant) 

Semantic Memory 

System's ability to recall past conversations by meaning, not just keywords 

PWA 

Progressive Web App - web app that can be installed like native app 

Diarization 

Identifying different speakers in audio/video 

Appendix B: Command Examples
Voice Commands:



"Hey CRUZ, good morning"
"Add to to-do: review Shooterista payment module by 2 PM"
"Draft email to AMA Solutions about website launch"
"FORGE, create contact form component for Asia Capital website"
"Deploy AMA website to Hostinger production"
"CATCH, record this meeting"
"Show me what REACH found overnight"
"PULSE, brief me on today's tech news"
"RAW, research Next.js 15 breaking changes"
"What's on my agenda today?"
"Create sprint plan for Razorpay integration project"
"Run tests on Shooterista backend"
"SENTINEL, review PR #42"
"Document the contact API endpoint"
"What did we discuss in yesterday's client call?"
Text Commands (via Telegram/PWA):



/add Review PR before EOD
/draft Email to client about timeline
/deploy ama production
/brief Show morning summary
/status What agents are running?
/leads Show new leads from REACH
/help List available commands
Appendix C: Agent Interaction Flows
Example 1: "Deploy AMA website to production"


Example 2: "REACH, find SaaS startups in Mumbai"


Appendix D: Database Schema (Simplified)
PostgreSQL Tables:



-- Users (just you for now, but designed for multi-user)
CREATE TABLE users (
  id UUID PRIMARY KEY,
  name VARCHAR(255),
  email VARCHAR(255) UNIQUE,
  created_at TIMESTAMP DEFAULT NOW()
);
-- Conversations (chat history)
CREATE TABLE conversations (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  title VARCHAR(255),
  started_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
-- Messages (individual messages in conversations)
CREATE TABLE messages (
  id UUID PRIMARY KEY,
  conversation_id UUID REFERENCES conversations(id),
  role VARCHAR(50), -- 'user' or 'assistant'
  content TEXT,
  agent VARCHAR(50), -- which agent responded
  created_at TIMESTAMP DEFAULT NOW()
);
-- Tasks (agent tasks, separate from Linear tasks)
CREATE TABLE tasks (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  agent VARCHAR(50),
  type VARCHAR(100),
  status VARCHAR(50), -- 'queued', 'running', 'completed', 'failed'
  input JSONB,
  output JSONB,
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  error TEXT
);
-- Logs (system logs, errors, audit trail)
CREATE TABLE logs (
  id UUID PRIMARY KEY,
  level VARCHAR(50), -- 'info', 'warn', 'error'
  agent VARCHAR(50),
  message TEXT,
  metadata JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);
-- Client CRM (for REACH agent)
CREATE TABLE leads (
  id UUID PRIMARY KEY,
  company_name VARCHAR(255),
  contact_name VARCHAR(255),
  email VARCHAR(255),
  phone VARCHAR(50),
  linkedin_url VARCHAR(500),
  status VARCHAR(50), -- 'new', 'contacted', 'replied', 'qualified', 'lost'
  source VARCHAR(100), -- 'REACH agent', 'manual', 'referral'
  notes TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
-- Meeting Transcripts (for CATCH agent)
CREATE TABLE meetings (
  id UUID PRIMARY KEY,
  title VARCHAR(255),
  participants TEXT[],
  started_at TIMESTAMP,
  ended_at TIMESTAMP,
  transcript TEXT,
  action_items JSONB,
  summary TEXT,
  recording_url VARCHAR(500)
);
Redis Keys:



# Active context per user
context:{user_id}  → JSON object with last 10 messages
# Agent status
agent:{agent_name}:status  → "idle" | "busy" | "error"
agent:{agent_name}:current_task  → task_id
# Job queue (managed by BullMQ)
bull:queue:name  → Queue metadata
Qdrant Collections:



# Conversation embeddings for semantic search
Collection: conversations
Vector size: 1536 (from text-embedding-ada-002 or similar)
Payload: { conversation_id, message_text, timestamp }
# Knowledge base embeddings
Collection: knowledge
Vector size: 1536
Payload: { source, content, url, timestamp }
Appendix E: Development Environment Setup
Mac Mini M4 Setup:



# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
# Install dependencies
brew install postgresql@16 redis python@3.11 node@20
# Install Ollama
curl https://ollama.ai/install.sh | sh
# Pull models
ollama pull qwen2.5-coder:14b
ollama pull llama3.1:8b
ollama pull whisper:large-v3
# Install Python packages
pip3 install fastapi uvicorn psycopg2-binary redis anthropic --break-system-packages
# Install Node packages globally
npm install -g pm2 pnpm
# Setup PostgreSQL
brew services start postgresql@16
createdb cruz_db
# Setup Redis
brew services start redis
# Clone project (when ready)
git clone https://github.com/yourusername/cruz.git
cd cruz
# Install dependencies
pnpm install
# Setup environment variables
cp .env.example .env
# Edit .env with API keys from Bitwarden
# Run migrations
npx prisma migrate dev
# Start development server
pnpm dev
VS Code Extensions:

Python (ms-python.python)

Pylance (ms-python.vscode-pylance)

ESLint (dbaeumer.vscode-eslint)

Prettier (esbenp.prettier-vscode)

Tailwind CSS IntelliSense (bradlc.vscode-tailwindcss)

Prisma (Prisma.prisma)

REST Client (humao.rest-client)

Appendix F: Backup & Recovery Procedures
Daily Backup (Automated):



#!/bin/bash
# /Users/darshan/cruz/scripts/backup.sh
DATE=$(date +%Y-%m-%d)
BACKUP_DIR="/Volumes/Backup/cruz/$DATE"
mkdir -p "$BACKUP_DIR"
# Backup PostgreSQL
pg_dump cruz_db > "$BACKUP_DIR/database.sql"
# Backup Redis (if persistence enabled)
redis-cli --rdb "$BACKUP_DIR/dump.rdb"
# Backup Qdrant data
cp -r ~/.qdrant/collections "$BACKUP_DIR/qdrant"
# Backup configuration
cp ~/.env "$BACKUP_DIR/.env"
# Backup conversation logs
cp -r ~/cruz/logs "$BACKUP_DIR/logs"
echo "Backup complete: $BACKUP_DIR"
Cron job (runs daily at 2 AM):



0 2 * * * /Users/darshan/cruz/scripts/backup.sh
Recovery Procedure:



# Stop all services
pm2 stop all
brew services stop postgresql redis
# Restore PostgreSQL
dropdb cruz_db
createdb cruz_db
psql cruz_db < /Volumes/Backup/cruz/2026-04-11/database.sql
# Restore Redis
redis-cli --rdb /Volumes/Backup/cruz/2026-04-11/dump.rdb
# Restore Qdrant
rm -rf ~/.qdrant/collections
cp -r /Volumes/Backup/cruz/2026-04-11/qdrant ~/.qdrant/collections
# Restart services
brew services start postgresql redis
pm2 restart all
echo "Recovery complete"
Appendix F: TTS Provider Selection Decision
Decision Date: April 12, 2026

Final Selection: Inworld TTS 1.5 Max
Decision Rationale:

After comprehensive research across 15+ TTS providers, Inworld TTS 1.5 Max was selected as the voice provider for CRUZ based on the following factors:

Quality:

#1 ranked in independent benchmarks (Artificial Analysis Speech Arena, ELO 1,217)

Beats ElevenLabs (ELO 1,177) and OpenAI TTS-1 (ELO 1,102) in blind A/B tests

59.1% win rate vs. ElevenLabs in preference testing

Latency:

<250ms P90 latency (excellent for real-time conversation)

4× faster than ElevenLabs v3 (500-2000ms)

WebSocket streaming support for instant response feel

Cost-Effectiveness:

$10 per 1M characters (pay-as-you-go, no subscription)

20× cheaper per quality-point than ElevenLabs

Matches user's light usage pattern (300 min/month)

Multi-Device Support:

Single API works across Mac Mini, Android, iOS, web

Consistent voice quality on all platforms

No per-device deployment complexity

Features:

Free voice cloning (5-15 seconds of audio)

271+ pre-built voices including British accents

Word-level timestamps for lip-sync

Experimental emotion tags ([happy], [sad], [angry])

Cost Breakdown for User's Usage Pattern:
User's Routine:

Outside home (12 hours): Minimal use (~100 min/month)

At home working (2 hours): Active sessions (~200 min/month)

Total: 300 minutes/month = 225,000 characters

Months 1-2 (No Caching):



225,000 chars × $10/1M = $2.25/month = ₹187/month
Month 3+ (With 60% Caching):



90,000 chars × $10/1M = $0.86/month = ₹71/month
One-time cache setup: ₹125
Annual Cost:



Year 1: (₹187 × 2) + (₹71 × 10) + ₹125 = ₹1,209
Implementation Plan:
Week 1-2 (Deployment):

Create Inworld account

Obtain API key

Clone British voice sample for JARVIS persona

Integrate into CRUZ backend (Mac Mini)

Deploy to React Native app (Android/iOS)

Deploy to web dashboard

Week 3-4 (Testing):

Monitor usage patterns

Track costs via Inworld dashboard

Fine-tune voice settings

Optimize integration performance

Month 3 (Caching Layer):

Analyze 2 months of usage data

Identify 100 most common phrases

Pre-generate cached MP3 files

Implement Redis cache with deterministic hash keys

Deploy optimized version

Monitor cost reduction (target: 60-70% savings)

Alternatives Considered:
Provider

Why Not Selected

ElevenLabs v3 

Too expensive (₹915-57,270/month), lacks WebSocket, slower latency 

Cartesia Sonic 3 

Lower quality (ELO 1,062), less natural despite faster latency (40ms) 

OpenAI TTS-1 

Lower quality (ELO 1,102), similar price, fewer voices 

Deepgram Aura-2 

Lower quality, not ranked in independent benchmarks 

Free options 

Poor quality (3-7/10), robotic, not suitable for premium experience 

Success Metrics:
Voice Quality (Target: >4.5/5):

User survey: "Voice sounds natural and pleasant"

Cost Efficiency:

Months 1-2: Stay within ₹187/month budget

Month 3+: Achieve ₹71/month with caching (62% reduction)

Multi-Device Consistency:

Voice quality parity across all devices

Latency:

End-to-end voice response <2 seconds

Migration Strategy (If Needed):
If Inworld fails to meet expectations, switch to:

Primary alternative: Cartesia Sonic 3 (faster, good quality)

Budget alternative: Deepgram Aura-2 (cheaper, acceptable quality)

Quality alternative: ElevenLabs Flash v2.5 (if budget allows)

Switching Cost: Low - TTS module isolated, can swap in <1 day

Document Approval
Role

Name

Signature

Date

Product Owner 

Darshan Parmar 

Technical Lead 

Darshan Parmar 

Stakeholder 

Darshan Parmar 

Version History
Version

Date

Author

Changes

Version

Date

Author

Changes

1.0 

2026-04-11 

Darshan Parmar 

Initial PRD creation 

1.1 

2026-04-12 

Darshan Parmar 

Updated TTS provider to Inworld TTS 1.5 Max, revised cost analysis, added Appendix F 

Next Steps
✅ Review this PRD - Read through, verify requirements match your vision

⏳ Approve & Sign Off - Mark this document as approved

⏳ Create GitHub Repository - Initialize project structure

⏳ Setup Development Environment - Follow Appendix E

⏳ Start Phase 1, Week 1 - Begin core infrastructure setup

⏳ Weekly Progress Reviews - Every Friday, review progress against roadmap

END OF PRODUCT REQUIREMENTS DOCUMENT

Total Pages: ~60 pages
Word Count: ~25,000 words
Sections: 15 major sections + 6 appendices
Status: Ready for Confluence