from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_browser_health_probe_passes(monkeypatch):
    from workers.tasks.browser_health import browser_health_probe
    import services.browser.service as browser_mod

    fake_svc = MagicMock()
    fake_svc.search = AsyncMock(return_value=[
        {"title": f"r{i}", "url": "https://x", "snippet": "", "rank": i}
        for i in range(1, 6)
    ])
    monkeypatch.setattr(browser_mod, "_instance", fake_svc)

    fake_alerts = MagicMock()
    fake_alerts.notify = AsyncMock()
    monkeypatch.setattr(
        "workers.tasks.browser_health.get_alert_service", lambda: fake_alerts
    )

    result = await browser_health_probe(ctx={})
    assert result["status"] == "ok"
    assert result["result_count"] == 5
    fake_alerts.notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_browser_health_probe_alerts_on_zero_results(monkeypatch):
    from workers.tasks.browser_health import browser_health_probe
    import services.browser.service as browser_mod

    fake_svc = MagicMock()
    fake_svc.search = AsyncMock(return_value=[])
    monkeypatch.setattr(browser_mod, "_instance", fake_svc)

    fake_alerts = MagicMock()
    fake_alerts.notify = AsyncMock()
    monkeypatch.setattr(
        "workers.tasks.browser_health.get_alert_service", lambda: fake_alerts
    )

    result = await browser_health_probe(ctx={})
    assert result["status"] == "degraded"
    fake_alerts.notify.assert_awaited()


@pytest.mark.asyncio
async def test_browser_health_probe_alerts_on_exception(monkeypatch):
    from workers.tasks.browser_health import browser_health_probe
    import services.browser.service as browser_mod

    fake_svc = MagicMock()
    fake_svc.search = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(browser_mod, "_instance", fake_svc)

    fake_alerts = MagicMock()
    fake_alerts.notify = AsyncMock()
    monkeypatch.setattr(
        "workers.tasks.browser_health.get_alert_service", lambda: fake_alerts
    )

    result = await browser_health_probe(ctx={})
    assert result["status"] == "error"
    fake_alerts.notify.assert_awaited()
