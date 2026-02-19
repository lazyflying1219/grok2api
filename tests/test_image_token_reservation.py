import asyncio

import pytest

from app.api.v1 import image as image_mod
from app.core.exceptions import AppException


def test_image_get_token_for_model_uses_reservation(monkeypatch):
    async def _run():
        class _DummyTokenManager:
            def __init__(self):
                self.calls = []

            async def reserve_token_for_model(self, model_id: str, exclude=None):
                self.calls.append((model_id, exclude))
                return "token-demo", "req-1"

        mgr = _DummyTokenManager()

        async def _fake_get_token_manager():
            return mgr

        monkeypatch.setattr(image_mod, "get_token_manager", _fake_get_token_manager)

        token_mgr, token, reservation_id = await image_mod._get_token_for_model("grok-imagine-1.0")
        assert token_mgr is mgr
        assert token == "token-demo"
        assert reservation_id == "req-1"
        assert mgr.calls == [("grok-imagine-1.0", None)]

    asyncio.run(_run())


def test_image_get_token_for_model_returns_429_when_no_token(monkeypatch):
    async def _run():
        class _DummyTokenManager:
            async def reserve_token_for_model(self, model_id: str, exclude=None):
                return None, None

        async def _fake_get_token_manager():
            return _DummyTokenManager()

        recorded = []

        async def _fake_record_request(model_id: str, success: bool):
            recorded.append((model_id, success))

        monkeypatch.setattr(image_mod, "get_token_manager", _fake_get_token_manager)
        monkeypatch.setattr(image_mod, "_record_request", _fake_record_request)

        with pytest.raises(AppException) as exc:
            await image_mod._get_token_for_model("grok-imagine-1.0")

        assert exc.value.status_code == 429
        assert recorded == [("grok-imagine-1.0", False)]

    asyncio.run(_run())
