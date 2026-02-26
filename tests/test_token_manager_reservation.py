import asyncio
from contextlib import asynccontextmanager

from app.services.token import manager as manager_mod
from app.services.token.manager import TokenManager
from app.services.token.models import TokenInfo, TokenStatus
from app.services.token.pool import TokenPool


def test_reserve_allows_concurrent_and_releases_correctly(monkeypatch):
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

        # First reservation — picks tok-a (highest quota)
        selected_1, request_id_1 = await mgr.reserve_token_for_model("grok-3")
        assert selected_1 == "tok-a"

        # Second reservation — with unlimited concurrency, same token is eligible
        # but load balancing prefers tok-b (0 inflight vs 1 inflight, quota 80 vs 100)
        # The selection prefers higher quota first, so tok-a (100) is still picked
        selected_2, request_id_2 = await mgr.reserve_token_for_model("grok-3")
        assert request_id_1 and request_id_2 and request_id_1 != request_id_2
        assert selected_2 == "tok-a"  # same token, higher quota wins

        # Verify inflight_map tracks both reservations
        assert request_id_1 in token_a.inflight_map
        assert request_id_2 in token_a.inflight_map

        # Release first reservation
        released = await mgr.release_token_reservation("tok-a", request_id_1)
        assert released is True
        assert request_id_1 not in token_a.inflight_map
        assert request_id_2 in token_a.inflight_map  # second still held

        # Release second reservation
        released = await mgr.release_token_reservation("tok-a", request_id_2)
        assert released is True
        assert len(token_a.inflight_map) == 0

    asyncio.run(_run())


def test_reserve_respects_max_concurrent(monkeypatch):
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

        async def _noop():
            pass

        monkeypatch.setattr(manager_mod, "get_storage", lambda: _FakeStorage())
        monkeypatch.setattr(mgr, "reload", _noop)
        monkeypatch.setattr(mgr, "_save", _noop)
        # Set max concurrent to 1 — exclusive reservation
        monkeypatch.setattr(manager_mod, "get_config",
                            lambda k, d=None: 1 if k == "token.max_concurrent_per_token" else d)

        selected_1, rid_1 = await mgr.reserve_token_for_model("grok-3")
        assert selected_1 == "tok-a"

        # tok-a is at capacity (1), should fall through to tok-b
        selected_2, rid_2 = await mgr.reserve_token_for_model("grok-3")
        assert selected_2 == "tok-b"

        # Both at capacity — should return None
        selected_3, _ = await mgr.reserve_token_for_model("grok-3")
        assert selected_3 is None

        # Release tok-a — should become available again
        await mgr.release_token_reservation("tok-a", rid_1)
        selected_4, _ = await mgr.reserve_token_for_model("grok-3")
        assert selected_4 == "tok-a"

    asyncio.run(_run())
