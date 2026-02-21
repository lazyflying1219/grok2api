import asyncio

from app.services.token.manager import TokenManager
from app.services.token.models import TokenInfo, TokenStatus
from app.services.token.pool import TokenPool
from app.services.grok import usage as usage_mod


def test_sync_usage_consumes_locally_before_remote_sync(monkeypatch):
    async def _run():
        mgr = TokenManager()
        token_info = TokenInfo(token="tok-1", quota=10, status=TokenStatus.ACTIVE)
        pool = TokenPool("ssoBasic")
        pool.add(token_info)
        mgr.pools = {"ssoBasic": pool}

        # Avoid touching storage in unit test.
        monkeypatch.setattr(mgr, "_schedule_save", lambda: None)

        gate = asyncio.Event()

        class _FakeUsageService:
            async def get(self, _token: str, model_name: str = "grok-3", retry: bool = True):
                await gate.wait()
                return {"remainingTokens": 7}

        monkeypatch.setattr(usage_mod, "UsageService", _FakeUsageService)

        # Should return quickly even if remote sync is blocked.
        ok = await asyncio.wait_for(
            mgr.sync_usage("tok-1", "grok-3", consume_on_fail=True, is_usage=True),
            timeout=0.05,
        )
        assert ok is True
        assert token_info.quota == 9
        assert token_info.use_count == 1

        gate.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        # Remote sync eventually corrects local estimate.
        assert token_info.quota == 7
        assert token_info.use_count == 1

    asyncio.run(_run())
