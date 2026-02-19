import asyncio

from app.services.grok import media as media_mod


def test_video_completions_releases_reservation_on_non_stream(monkeypatch):
    async def _run():
        class _DummyTokenManager:
            def __init__(self):
                self.release_calls = []
                self.sync_calls = 0

            async def reserve_token_for_model(self, _model: str, exclude=None):
                return "token-demo", "req-video-1"

            async def release_token_reservation(self, token: str, request_id: str):
                self.release_calls.append((token, request_id))
                return True

            async def sync_usage(self, *args, **kwargs):
                self.sync_calls += 1
                return True

        token_mgr = _DummyTokenManager()

        async def _fake_get_token_manager():
            return token_mgr

        async def _fake_generate(self, *args, **kwargs):
            async def _resp():
                if False:
                    yield b""
            return _resp()

        async def _fake_generate_from_image(self, *args, **kwargs):
            async def _resp():
                if False:
                    yield b""
            return _resp()

        class _DummyCollectProcessor:
            def __init__(self, *_args, **_kwargs):
                pass

            async def process(self, _response):
                return {"ok": True}

        async def _fake_record_request(_model: str, _success: bool):
            return None

        from app.services.grok import chat as chat_mod

        monkeypatch.setattr(media_mod, "get_token_manager", _fake_get_token_manager)
        monkeypatch.setattr(media_mod.VideoService, "generate", _fake_generate)
        monkeypatch.setattr(media_mod.VideoService, "generate_from_image", _fake_generate_from_image)
        monkeypatch.setattr(media_mod, "VideoCollectProcessor", _DummyCollectProcessor)
        monkeypatch.setattr(media_mod.request_stats, "record_request", _fake_record_request)
        monkeypatch.setattr(chat_mod.MessageExtractor, "extract", staticmethod(lambda _m, is_video=False: ("hello", [])))

        result = await media_mod.VideoService.completions(
            model="grok-imagine-1.0-video",
            messages=[{"role": "user", "content": "hello"}],
            stream=False,
        )

        assert result == {"ok": True}
        assert token_mgr.sync_calls == 1
        assert token_mgr.release_calls == [("token-demo", "req-video-1")]

    asyncio.run(_run())
