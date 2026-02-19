import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import response_middleware as response_middleware_mod


def _build_client(monkeypatch, *, trust_proxy_headers: bool, trusted_proxy_ips=None) -> TestClient:
    trusted = list(trusted_proxy_ips or ["127.0.0.1", "::1"])
    ban_file = Path(tempfile.gettempdir()) / f"grok2api-banned-{uuid.uuid4().hex}.txt"

    def _fake_get_config(key, default=None):
        if key == "security.auto_ban_unknown_path":
            return True
        if key == "security.auto_ban_exempt_ips":
            return []
        if key == "security.trust_proxy_headers":
            return trust_proxy_headers
        if key == "security.trusted_proxy_ips":
            return trusted
        return default

    monkeypatch.setattr(response_middleware_mod, "get_config", _fake_get_config)
    monkeypatch.setattr(
        response_middleware_mod.ResponseLoggerMiddleware,
        "_ban_file_path",
        ban_file,
        raising=False,
    )

    cls = response_middleware_mod.ResponseLoggerMiddleware
    cls._banned_ips.clear()
    if hasattr(cls, "_banned_ips_loaded"):
        cls._banned_ips_loaded = False
    if hasattr(cls, "_banned_ips_file_mtime"):
        cls._banned_ips_file_mtime = None

    app = FastAPI()
    app.add_middleware(response_middleware_mod.ResponseLoggerMiddleware)

    @app.get("/health")
    async def _health():
        return {"ok": True}

    return TestClient(app)


def test_auto_ban_uses_forwarded_ip_when_trusted(monkeypatch):
    monkeypatch.setenv("STORAGE_MODE", "memory")
    client = _build_client(monkeypatch, trust_proxy_headers=True, trusted_proxy_ips=["testclient"])

    headers = {"X-Forwarded-For": "198.51.100.7"}

    first = client.get("/not-a-real-api", headers=headers)
    assert first.status_code == 403

    # Should ban the real client IP, not the proxy/testclient socket address.
    assert "198.51.100.7" in response_middleware_mod.ResponseLoggerMiddleware._banned_ips
    assert "testclient" not in response_middleware_mod.ResponseLoggerMiddleware._banned_ips

    second = client.get("/health", headers=headers)
    assert second.status_code == 403
