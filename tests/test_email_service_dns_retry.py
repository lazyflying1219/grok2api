from __future__ import annotations

import requests

from app.services.register.services.email_service import EmailService
import app.services.register.services.email_service as email_module


def test_create_email_fallbacks_to_doh_when_dns_resolution_fails(monkeypatch):
    called = {"count": 0}

    def _fake_post(*_args, **_kwargs):
        raise requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='mail-back.caidao.workers.dev', port=443): "
            "Max retries exceeded with url: /admin/new_address "
            "(Caused by NameResolutionError(\"Failed to resolve host\"))"
        )

    def _fake_doh_fallback(self, path: str, payload: dict, headers: dict):
        called["count"] += 1
        assert path == "/admin/new_address"
        assert payload["domain"] == "5179.nyc.mn"
        assert headers["x-admin-auth"] == "x"
        return "jwt-token", "test@5179.nyc.mn"

    monkeypatch.setattr(email_module.requests, "post", _fake_post)
    monkeypatch.setattr(email_module.random, "choices", lambda seq, k: [seq[0]] * k)
    monkeypatch.setattr(email_module.random, "randint", lambda a, _b: a)
    monkeypatch.setattr(EmailService, "_create_email_via_doh", _fake_doh_fallback, raising=False)

    svc = EmailService(
        worker_domain="mail-back.caidao.workers.dev",
        email_domain="5179.nyc.mn",
        admin_password="x",
    )

    jwt, address = svc.create_email()

    assert called["count"] == 1
    assert jwt == "jwt-token"
    assert address == "test@5179.nyc.mn"


def test_create_email_does_not_fallback_on_non_dns_errors(monkeypatch):
    called = {"count": 0}

    def _fake_post(*_args, **_kwargs):
        raise requests.exceptions.ConnectTimeout("connect timeout")

    def _fake_doh_fallback(self, path: str, payload: dict, headers: dict):
        called["count"] += 1
        return "jwt-token", "test@5179.nyc.mn"

    monkeypatch.setattr(email_module.requests, "post", _fake_post)
    monkeypatch.setattr(email_module.random, "choices", lambda seq, k: [seq[0]] * k)
    monkeypatch.setattr(email_module.random, "randint", lambda a, _b: a)
    monkeypatch.setattr(EmailService, "_create_email_via_doh", _fake_doh_fallback, raising=False)

    svc = EmailService(
        worker_domain="mail-back.caidao.workers.dev",
        email_domain="5179.nyc.mn",
        admin_password="x",
    )

    jwt, address = svc.create_email()

    assert called["count"] == 0
    assert jwt is None
    assert address is None


def test_fetch_first_email_retries_on_timeout_then_succeeds(monkeypatch):
    calls = {"count": 0}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"results": [{"raw": "mail-content"}]}

    def _fake_get(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise requests.exceptions.ReadTimeout("read timeout")
        return _Resp()

    monkeypatch.setattr(email_module.requests, "get", _fake_get)
    if hasattr(email_module, "time"):
        monkeypatch.setattr(email_module.time, "sleep", lambda *_args, **_kwargs: None)

    svc = EmailService(
        worker_domain="mail-back.caidao.workers.dev",
        email_domain="5179.nyc.mn",
        admin_password="x",
    )

    raw = svc.fetch_first_email("jwt-token")

    assert raw == "mail-content"
    assert calls["count"] == 3


def test_fetch_first_email_fallbacks_to_doh_when_dns_resolution_fails(monkeypatch):
    calls = {"count": 0}

    def _fake_get(*_args, **_kwargs):
        raise requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='mail-back.caidao.workers.dev', port=443): "
            "Max retries exceeded with url: /api/mails "
            "(Caused by NameResolutionError(\"Failed to resolve host\"))"
        )

    def _fake_fallback(self, jwt: str):
        calls["count"] += 1
        assert jwt == "jwt-token"
        return "mail-content-fallback"

    monkeypatch.setattr(email_module.requests, "get", _fake_get)
    monkeypatch.setattr(EmailService, "_fetch_first_email_via_doh", _fake_fallback, raising=False)

    svc = EmailService(
        worker_domain="mail-back.caidao.workers.dev",
        email_domain="5179.nyc.mn",
        admin_password="x",
    )

    raw = svc.fetch_first_email("jwt-token")

    assert raw == "mail-content-fallback"
    assert calls["count"] == 1
