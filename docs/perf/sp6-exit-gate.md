# SP6 — Screen Perception Exit-Gate Verification

**Charter:** §5.1 SP6 row.
**Spec:** [`docs/superpowers/specs/2026-05-03-sp6-screen-perception-design.md`](../superpowers/specs/2026-05-03-sp6-screen-perception-design.md)
**Date completed:** _to fill in at sign-off_

## Gate 1 — "What am I working on?" 10/10 across 10 distinct app contexts

For each row, set up the app context, then run from any device:

```
curl -X POST http://<mac-mini-or-tunnel>/command \\
  -H 'Content-Type: application/json' \\
  -d '{"message": "what am I working on?", "stream": false}'
```

Tick the row if the answer is materially correct (mentions the right app + a true-ish description of what's visible). False details, hallucinations, or wrong app = fail.

| # | App context | Answer (truncated to 200 chars) | Correct? |
|---|---|---|---|
| 1 | VS Code editing a real file | | [ ] |
| 2 | Browser on a documentation page | | [ ] |
| 3 | Mail composing an email | | [ ] |
| 4 | Terminal running a process | | [ ] |
| 5 | PDF reader (Preview) | | [ ] |
| 6 | Design tool (Figma / Sketch) | | [ ] |
| 7 | Slack | | [ ] |
| 8 | Calendar app | | [ ] |
| 9 | Music app (Spotify / Music) | | [ ] |
| 10 | Blank desktop / Finder | | [ ] |

**Pass condition:** 10/10. Anything less = SP6 not ready to ship; investigate Vision prompt or screenshot quality.

## Gate 2 — Active-app context reaches FORGE on a test case

See `sp6-forge-improvement-test.md` for the full A/B procedure. Outcome:

- [ ] FORGE's output references the active file when active-app injection is enabled.
- [ ] FORGE's output asks for the file or guesses wrong when injection is disabled (control).
- [ ] Difference is materially better in the enabled run.

## Gate 3 — No regression on existing CRUZ tests

```
source venv/bin/activate
pytest tests/agents/test_cruz_agent.py tests/agents/test_cruz_conversation.py tests/agents/test_cruz_stream.py -v
```

- [ ] All pre-existing CRUZ tests pass.

## Gate 4 — No P95 latency regression > 100ms on /command warm-cache

Run the existing load harness with the active-app injection in place. Compare to the SP1/SP2 baseline in `docs/perf/load_results.md`.

```
./scripts/load/run_scenarios.sh agent_mix --duration 5m
```

- [ ] P95 of `/command` warm-cache requests is within +100ms of the previous baseline.
- [ ] Recorded in `docs/perf/load_results.md` under an "SP6" row.

## Sign-off

Append to `PROGRESS.md` once all four gates are ticked:

```
## SP6 — Screen Perception (sign-off YYYY-MM-DD)

✅ Gate 1: 10/10 ad-hoc accuracy (see docs/perf/sp6-exit-gate.md)
✅ Gate 2: Active-app reaches FORGE; A/B improvement demonstrated
   (see docs/perf/sp6-forge-improvement-test.md)
✅ Gate 3: All pre-existing CRUZ tests green
✅ Gate 4: P95 /command latency within +<X>ms of baseline

Branch: claude/silly-goldwasser-aac011 → merged to main
Tests added: 23 unit + 11 CRUZ integration + 3 live (env-gated)
Files added: services/screen_perception.py + 4 test/doc files
Files modified: agents/cruz/cruz_agent.py + services/mac_controller.py (refactor)
```
