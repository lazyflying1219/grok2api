import asyncio

from app.services.token.manager import TokenManager


def test_flush_loop_cancel_should_not_reschedule_save_task():
    async def _run():
        mgr = TokenManager()
        mgr._save_delay = 60.0
        mgr._dirty = True

        mgr._schedule_save()
        task = mgr._save_task
        assert task is not None
        assert not task.done()

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        await asyncio.sleep(0)
        assert mgr._save_task is None

    asyncio.run(_run())
