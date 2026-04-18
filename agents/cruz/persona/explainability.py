"""
ExplainabilityEngine — given a trace_id, reconstruct a human-readable
reasoning chain from agent_logs rows.

Used by the new GET /explain/:trace_id endpoint.  Zero LLM calls — just
stitches together logs so the user can ask "why did you do that?".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class ExplanationStep:
    agent: str
    action: str
    status: str
    duration_ms: int
    tokens_used: int
    summary: Optional[str] = None


@dataclass
class Explanation:
    trace_id: str
    steps: List[ExplanationStep]
    total_duration_ms: int
    total_tokens: int
    final_status: str
    headline: str  # single-sentence summary

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "headline": self.headline,
            "final_status": self.final_status,
            "total_duration_ms": self.total_duration_ms,
            "total_tokens": self.total_tokens,
            "steps": [
                {
                    "agent": s.agent,
                    "action": s.action,
                    "status": s.status,
                    "duration_ms": s.duration_ms,
                    "tokens_used": s.tokens_used,
                    "summary": s.summary,
                }
                for s in self.steps
            ],
        }


async def build_explanation(db, trace_id: str) -> Optional[Explanation]:
    """
    Fetch all agent_logs rows for trace_id and fold into a chain.
    Returns None if no rows found.
    """
    rows = await db.fetch(
        "SELECT agent, action, status, duration_ms, tokens_used, "
        "input_data, output_data, created_at "
        "FROM agent_logs WHERE trace_id = $1 ORDER BY created_at ASC",
        trace_id,
    )
    if not rows:
        return None

    steps: List[ExplanationStep] = []
    total_duration = 0
    total_tokens = 0
    final_status = "success"

    for r in rows:
        output = r.get("output_data") or {}
        summary = _short_summary(output)
        step = ExplanationStep(
            agent=r["agent"],
            action=r["action"],
            status=r["status"] or "unknown",
            duration_ms=r.get("duration_ms") or 0,
            tokens_used=r.get("tokens_used") or 0,
            summary=summary,
        )
        steps.append(step)
        total_duration += step.duration_ms
        total_tokens += step.tokens_used
        if step.status == "error":
            final_status = "error"

    headline = _build_headline(steps, final_status)
    return Explanation(
        trace_id=trace_id,
        steps=steps,
        total_duration_ms=total_duration,
        total_tokens=total_tokens,
        final_status=final_status,
        headline=headline,
    )


def _short_summary(output: Any) -> Optional[str]:
    """Extract a human hint from output_data JSON."""
    if not isinstance(output, dict):
        return None
    if "result" in output:
        result = output["result"]
        if isinstance(result, str) and result:
            return result[:200]
    if "error" in output:
        return f"ERROR: {str(output['error'])[:200]}"
    return None


def _build_headline(steps: List[ExplanationStep], final_status: str) -> str:
    """One-sentence human summary of the whole trace."""
    if not steps:
        return "No log entries for this trace."
    primary = steps[0]
    agents_touched = sorted({s.agent for s in steps})
    agent_str = " → ".join(agents_touched)
    adj = "succeeded" if final_status == "success" else "errored"
    return (
        f"{primary.agent}.{primary.action} {adj} "
        f"via {agent_str} in {len(steps)} step(s), "
        f"{sum(s.duration_ms for s in steps)}ms total."
    )
