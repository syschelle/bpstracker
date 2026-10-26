"""v0.9.66: unexpected poller tick failures must not stop data collection."""

import asyncio
import logging

import pytest

from app import poller as poller_module


@pytest.mark.asyncio
async def test_poller_continues_after_unhandled_tick_error(monkeypatch, caplog):
    poller = poller_module.Poller()
    poller.loop_seconds = 0.001
    calls = 0

    async def flaky_tick():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError('temporary database failure')
        poller._stop.set()

    monkeypatch.setattr(poller, 'tick', flaky_tick)

    with caplog.at_level(logging.ERROR, logger='app.poller'):
        await asyncio.wait_for(poller._run(), timeout=1)

    assert calls == 2
    assert 'Unhandled error in polling loop; continuing with next cycle' in caplog.text
    assert 'temporary database failure' in caplog.text
