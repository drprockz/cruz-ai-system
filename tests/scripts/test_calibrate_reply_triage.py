"""Smoke test the calibration flow with mocked Gmail + LLM + input()."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_calibration_passes_when_80pct_match(capsys):
    from scripts.calibrate_reply_triage import main

    fake_msg = {"id": "1", "from": "x@y.com", "subject": "hi", "body": "",
                "thread_id": "t", "date": ""}
    with patch("scripts.calibrate_reply_triage.list_recent_inbound",
               AsyncMock(return_value=["1", "2", "3", "4", "5"])), \
         patch("scripts.calibrate_reply_triage.fetch_message",
               AsyncMock(return_value=fake_msg)), \
         patch("scripts.calibrate_reply_triage._classify_email",
               AsyncMock(return_value={"label": "fyi", "urgency": "later",
                                        "client_match": None,
                                        "confidence": 0.5, "reason": ""})), \
         patch("builtins.input", side_effect=["fyi", "later"] * 5):
        rc = await main(limit=5)
    out = capsys.readouterr().out
    assert "PASSES" in out
    assert rc == 0


@pytest.mark.asyncio
async def test_calibration_fails_below_80pct(capsys):
    from scripts.calibrate_reply_triage import main
    fake_msg = {"id": "1", "from": "x@y.com", "subject": "x", "body": "",
                "thread_id": "t", "date": ""}
    with patch("scripts.calibrate_reply_triage.list_recent_inbound",
               AsyncMock(return_value=["1", "2", "3", "4", "5"])), \
         patch("scripts.calibrate_reply_triage.fetch_message",
               AsyncMock(return_value=fake_msg)), \
         patch("scripts.calibrate_reply_triage._classify_email",
               AsyncMock(return_value={"label": "fyi", "urgency": "later",
                                        "client_match": None,
                                        "confidence": 0.5, "reason": ""})), \
         patch("builtins.input",
               side_effect=["needs_reply", "now"] * 5):  # all disagree
        rc = await main(limit=5)
    out = capsys.readouterr().out
    assert "FAILS" in out
    assert rc == 2
