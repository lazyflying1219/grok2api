import asyncio
from pathlib import Path

from app.services.request_stats import RequestStats


def test_request_stats_close_should_flush_dirty_and_clear_task(monkeypatch, tmp_path):
    async def _run():
        RequestStats._instance = None
        stats = RequestStats()
        stats.file_path = Path(tmp_path) / "stats.json"
        stats._loaded = True
        stats._flush_delay = 60.0
        stats._dirty = True

        saved = {"count": 0}

        async def _fake_save_data():
            saved["count"] += 1

        monkeypatch.setattr(stats, "_save_data", _fake_save_data)

        stats._schedule_save()
        assert stats._flush_task is not None

        await stats.close()

        assert stats._flush_task is None
        assert stats._dirty is False
        assert saved["count"] == 1

    asyncio.run(_run())


def test_request_stats_cancelled_flush_should_not_reschedule():
    async def _run():
        RequestStats._instance = None
        stats = RequestStats()
        stats._loaded = True
        stats._flush_delay = 60.0
        stats._dirty = True

        stats._schedule_save()
        task = stats._flush_task
        assert task is not None

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        await asyncio.sleep(0)
        assert stats._flush_task is None

    asyncio.run(_run())
