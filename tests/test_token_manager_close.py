import asyncio

from app.services.token.manager import TokenManager


def test_token_manager_close_should_flush_dirty_and_clear_task(monkeypatch):
    async def _run():
        mgr = TokenManager()
        mgr._save_delay = 60.0
        mgr._dirty = True

        saved = {"count": 0}

        async def _fake_save():
            saved["count"] += 1

        monkeypatch.setattr(mgr, "_save", _fake_save)

        mgr._schedule_save()
        assert mgr._save_task is not None

        await mgr.close()

        assert mgr._save_task is None
        assert saved["count"] == 1
        assert mgr._dirty is False

    asyncio.run(_run())
