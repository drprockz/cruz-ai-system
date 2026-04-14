"""Locust scenarios for CRUZ load testing.

Run a single scenario via the ``LOCUST_SCENARIO`` env var (see
``run_scenarios.sh``). All scenarios hit the public CRUZ API contract
defined in ``backend/api/main.py``.

Scenarios:
    morning_rush  — 20 users, 5 commands each, short burst
    agent_mix     — FORGE / ECHO / REACH / PM balanced, ~50 RPS
    sse_streaming — 10 concurrent streams, 60s each
    overnight     — simulates ARQ cron firing PULSE+RAW+REACH together
"""

from __future__ import annotations

import json
import os
import random
import time
from typing import Iterator

from locust import HttpUser, between, constant, events, task

SCENARIO = os.getenv("LOCUST_SCENARIO", "morning_rush")


MORNING_PROMPTS = [
    "What's on my calendar today?",
    "Draft a standup update for AMA Solutions.",
    "Summarize yesterday's commits on MIDAR.",
    "Any overnight failures I should know about?",
    "Give me the top priority for today.",
]

AGENT_PROMPTS = {
    "FORGE": "FORGE, scaffold a POST /tasks route with validation.",
    "ECHO": "ECHO, draft a status email to ateet@ama.com about the deploy.",
    "REACH": "REACH, find 5 SaaS founders in Mumbai for outreach.",
    "PM": "PM, break the MIDAR auth epic into sprint tasks.",
}


def _post_command(client, message: str, stream: bool = False) -> None:
    payload = {"message": message, "stream": stream, "device": "locust"}
    with client.post(
        "/command",
        json=payload,
        name=f"/command [{SCENARIO}]",
        catch_response=True,
        stream=stream,
    ) as resp:
        if resp.status_code >= 400:
            resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
            return
        if stream:
            consumed = 0
            started = time.monotonic()
            for line in resp.iter_lines():
                if not line:
                    continue
                consumed += 1
                if time.monotonic() - started > 60:
                    break
            if consumed == 0:
                resp.failure("SSE returned zero events")


class MorningRushUser(HttpUser):
    """Scenario 1: 20 users send 5 commands over ~30s, then stop."""

    wait_time = between(4, 7)

    def on_start(self) -> None:
        self._remaining = 5

    @task
    def send(self) -> None:
        if self._remaining <= 0:
            self.environment.runner.quit()
            return
        self._remaining -= 1
        _post_command(self.client, random.choice(MORNING_PROMPTS))


class AgentMixUser(HttpUser):
    """Scenario 2: Balanced FORGE/ECHO/REACH/PM mix, ~50 RPS target."""

    wait_time = constant(0.1)

    @task
    def forge(self) -> None:
        _post_command(self.client, AGENT_PROMPTS["FORGE"])

    @task
    def echo(self) -> None:
        _post_command(self.client, AGENT_PROMPTS["ECHO"])

    @task
    def reach(self) -> None:
        _post_command(self.client, AGENT_PROMPTS["REACH"])

    @task
    def pm(self) -> None:
        _post_command(self.client, AGENT_PROMPTS["PM"])


class SSEStreamUser(HttpUser):
    """Scenario 3: 10 concurrent SSE streams, each ~60s."""

    wait_time = constant(1)

    @task
    def stream(self) -> None:
        _post_command(
            self.client,
            "Walk me through the full deployment status of AMA, Shooterista, and MIDAR.",
            stream=True,
        )


class OvernightCronUser(HttpUser):
    """Scenario 4: simulate ARQ cron firing PULSE+RAW+REACH together.

    Each user represents one cron job; three cron jobs × small replication.
    """

    wait_time = constant(60)

    cron_endpoints: list[tuple[str, dict]] = [
        ("/command", {"message": "PULSE briefing run", "stream": False}),
        ("/command", {"message": "RAW tech scan run", "stream": False}),
        ("/command", {"message": "REACH nightly discovery", "stream": False}),
    ]

    @task
    def fire_all(self) -> None:
        for path, payload in self.cron_endpoints:
            self.client.post(path, json=payload, name=f"cron {payload['message'][:20]}")


# Disable classes that don't belong to the active scenario so locust only
# spawns the requested user type.
_SCENARIO_CLASS = {
    "morning_rush": MorningRushUser,
    "agent_mix": AgentMixUser,
    "sse_streaming": SSEStreamUser,
    "overnight": OvernightCronUser,
}


@events.init.add_listener
def _restrict_user_classes(environment, **_):
    cls = _SCENARIO_CLASS.get(SCENARIO)
    if cls is None:
        return
    environment.user_classes = [cls]
