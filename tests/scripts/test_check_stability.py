"""Tests for scripts/uptime/check_stability.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = ROOT / "scripts" / "uptime" / "check_stability.py"
spec = importlib.util.spec_from_file_location("check_stability", MOD_PATH)
assert spec and spec.loader
check_stability = importlib.util.module_from_spec(spec)
sys.modules["check_stability"] = check_stability
spec.loader.exec_module(check_stability)


def _probe_ok(ts="2026-04-14T00:00:00Z"):
    return check_stability.Probe(ts, 200, True, 12, "healthy")


def _probe_fail(ts="2026-04-14T00:05:00Z"):
    return check_stability.Probe(ts, 0, False, 5, None, error="connect")


def test_probe_to_json_roundtrip():
    record = json.loads(_probe_ok().to_json())
    assert record["ok"] is True
    assert record["status_code"] == 200
    assert record["body_status"] == "healthy"


def test_run_writes_one_line_per_probe(tmp_path):
    out = tmp_path / "stability.jsonl"
    results = [_probe_ok(), _probe_fail(), _probe_ok("2026-04-14T00:10:00Z")]
    calls = iter(results)

    # Fake clock: first 3 calls return 0 (under deadline), 4th call returns
    # the deadline so the loop terminates after the 3rd probe.
    times = iter([0, 0, 0, 100])

    count = check_stability.run(
        "http://x/health",
        out,
        interval=0,
        duration=50,
        clock=lambda: next(times),
        sleep=lambda _s: None,
        probe=lambda _url: next(calls),
    )

    lines = [json.loads(l) for l in out.read_text().splitlines()]
    assert count == 3
    assert len(lines) == 3
    assert [r["ok"] for r in lines] == [True, False, True]


def test_summarize_counts():
    records = [
        {"ok": True}, {"ok": True}, {"ok": False}, {"ok": True},
    ]
    summary = check_stability.summarize(records)
    assert summary == {"total": 4, "ok": 3, "fail": 1, "pct_ok": 75.0}


def test_summarize_empty():
    assert check_stability.summarize([]) == {"total": 0, "ok": 0, "pct_ok": 0.0}


def test_probe_once_handles_connection_error(monkeypatch):
    class BoomClient:
        def __init__(self, *a, **kw): pass
        def get(self, url):
            raise RuntimeError("connect refused")
        def close(self): pass

    monkeypatch.setattr(check_stability.httpx, "Client", BoomClient)
    result = check_stability.probe_once("http://nope/health")
    assert result.ok is False
    assert result.status_code == 0
    assert "connect" in (result.error or "")


def test_locustfile_imports_cleanly():
    path = ROOT / "scripts" / "load" / "locustfile.py"
    spec = importlib.util.spec_from_file_location("cruz_locustfile", path)
    assert spec and spec.loader
    try:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("locust"):
            import pytest
            pytest.skip("locust not installed in this env")
        raise
    assert hasattr(mod, "MorningRushUser")
    assert hasattr(mod, "AgentMixUser")
    assert hasattr(mod, "SSEStreamUser")
    assert hasattr(mod, "OvernightCronUser")
