from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import chat as chat_api


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(chat_api.router, prefix="/v1")
    app.dependency_overrides[chat_api.verify_api_key] = lambda: "test-key"
    return TestClient(app)


def test_chat_completions_default_stream_should_be_false(monkeypatch):
    observed: dict[str, object] = {}

    monkeypatch.setattr(chat_api.ModelService, "valid", staticmethod(lambda _m: True))
    monkeypatch.setattr(
        chat_api.ModelService,
        "get",
        staticmethod(lambda _m: SimpleNamespace(is_video=False)),
    )

    async def _fake_quota(_api_key, _model):
        return None

    async def _fake_completions(*, model, messages, stream=None, thinking=None):
        observed["stream"] = stream
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok", "refusal": None, "annotations": []},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    monkeypatch.setattr(chat_api, "enforce_daily_quota", _fake_quota)
    monkeypatch.setattr(chat_api.ChatService, "completions", staticmethod(_fake_completions))

    client = _build_client()
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "grok-4.2-fast",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert resp.status_code == 200
    assert resp.json()["object"] == "chat.completion"
    assert observed["stream"] is False
