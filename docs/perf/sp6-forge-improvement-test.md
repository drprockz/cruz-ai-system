# SP6 Gate 2 — FORGE Active-App A/B Test Record

**Charter §5.1 SP6 criterion:** "active-app context reaches at least one agent and improves its output on a test case"

## Setup

1. On the Mac Mini, open a project file in VS Code that has a known, isolated bug. Recommended: a single-file Python script with an obvious off-by-one (line range ≤30 lines).
2. Note the file path and the bug for the answer-key column.

## Procedure

### Run A — control (active-app injection disabled)

```
CRUZ_DISABLE_ACTIVE_APP=1 curl -X POST http://localhost:3000/command \\
  -H 'Content-Type: application/json' \\
  -d '{"message": "Fix the bug in the file I have open. Output a unified diff and nothing else.", "stream": false}'
```

Record FORGE's response.

### Run B — treatment (active-app injection enabled)

```
curl -X POST http://localhost:3000/command \\
  -H 'Content-Type: application/json' \\
  -d '{"message": "Fix the bug in the file I have open. Output a unified diff and nothing else.", "stream": false}'
```

Record FORGE's response.

## Comparison

| | Run A (control) | Run B (treatment) |
|---|---|---|
| Identified the right file? | | |
| Identified the bug? | | |
| Diff applies cleanly? | | |
| Asked clarifying questions? | | |

## Verdict

- [ ] Run B is materially better than Run A (e.g., correctly identifies the file in B but asks for it in A; or identifies the bug only in B).
- [ ] Recorded above.

If verdict is no, do NOT sign off SP6 — invoke charter §6 cut-list row #3 (defer SP6 entirely) or escalate via cut-trigger #2 in the spec (drop A/B and ship with weaker improvement claim — requires explicit Darshan approval).
