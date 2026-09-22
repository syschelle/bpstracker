"""v0.9.57: day finalization must never block the login/health event loop."""

import asyncio
import threading
from datetime import datetime, timedelta, timezone

import pytest

from app import poller as poller_module


@pytest.mark.asyncio
async def test_daily_maintenance_is_dispatched_to_worker_thread(monkeypatch):
    ran = threading.Event()
    release = threading.Event()
    thread_ids = []

    def slow_maintenance(_now):
        thread_ids.append(threading.get_ident())
        ran.set()
        assert release.wait(timeout=2)

    monkeypatch.setattr(poller_module.Poller, '_run_maintenance_sync', staticmethod(slow_maintenance))
    poller = poller_module.Poller()
    task = asyncio.create_task(poller.run_maintenance_if_due())
    try:
        # If synchronous work ran on the server event loop, this await could
        # not complete while the simulated maintenance thread is still busy.
        await asyncio.wait_for(asyncio.to_thread(ran.wait, 1), timeout=1.5)
        assert ran.is_set()
        assert not task.done()
        assert thread_ids[0] != threading.get_ident()
    finally:
        release.set()
        await asyncio.wait_for(task, timeout=2)


@pytest.mark.asyncio
async def test_day_change_triggers_maintenance_even_before_hour_elapsed(monkeypatch):
    frozen = datetime(2026, 9, 23, 0, 3, tzinfo=timezone.utc)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen if tz is not None else frozen.replace(tzinfo=None)

    calls = []
    monkeypatch.setattr(poller_module, 'datetime', FrozenDatetime)
    monkeypatch.setattr(
        poller_module.Poller, '_run_maintenance_sync', staticmethod(lambda now: calls.append(now))
    )
    poller = poller_module.Poller()
    poller._last_maintenance = frozen - timedelta(minutes=5)  # Yesterday 23:58 UTC.
    await poller.run_maintenance_if_due()
    assert calls == [frozen]
    await poller.run_maintenance_if_due()
    assert calls == [frozen]
