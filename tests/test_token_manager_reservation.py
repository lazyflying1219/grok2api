import asyncio
from contextlib import asynccontextmanager

from app.services.token import manager as manager_mod
from app.services.token.manager import TokenManager
from app.services.token.models import TokenInfo, TokenStatus
from app.services.token.pool import TokenPool


def test_reserve_token_avoids_duplicate_until_release(monkeypatch):
    async def _run():
        mgr = TokenManager()

        pool = TokenPool("ssoBasic")
        token_a = TokenInfo(token="tok-a", quota=100, status=TokenStatus.ACTIVE)
        token_b = TokenInfo(token="tok-b", quota=80, status=TokenStatus.ACTIVE)
        pool.add(token_a)
        pool.add(token_b)
        mgr.pools = {"ssoBasic": pool}

        class _FakeStorage:
            @asynccontextmanager
            async def acquire_lock(self, _name: str, timeout: int = 10):
                yield

        async def _fake_reload():
            return None

        async def _fake_save():
            return None

        monkeypatch.setattr(manager_mod, "get_storage", lambda: _FakeStorage())
        monkeypatch.setattr(mgr, "reload", _fake_reload)
        monkeypatch.setattr(mgr, "_save", _fake_save)

        selected_1, request_id_1 = await mgr.reserve_token_for_model("grok-3")
        selected_2, request_id_2 = await mgr.reserve_token_for_model("grok-3")

        assert selected_1 == "tok-a"
        assert selected_2 == "tok-b"
        assert request_id_1 and request_id_2 and request_id_1 != request_id_2
        assert token_a.inflight_until > 0
        assert token_a.inflight_request_id == request_id_1

        released = await mgr.release_token_reservation("tok-a", request_id_1)
        assert released is True
        assert token_a.inflight_until == 0
        assert token_a.inflight_request_id is None

        selected_3, _request_id_3 = await mgr.reserve_token_for_model("grok-3")
        assert selected_3 == "tok-a"

    asyncio.run(_run())
