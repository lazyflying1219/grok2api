from __future__ import annotations

from app.services.register.runner import RegisterRunner


def test_extract_set_cookie_url_from_plain_text_payload():
    text = '1:https://grok.com/set-cookie?q=abc123xyz,'
    url = RegisterRunner._extract_set_cookie_url(text, headers={})
    assert url == "https://grok.com/set-cookie?q=abc123xyz"


def test_extract_set_cookie_url_from_json_escaped_payload():
    text = '{"redirect":"https:\\/\\/grok.com\\/set-cookie?q=abc123xyz"}'
    url = RegisterRunner._extract_set_cookie_url(text, headers={})
    assert url == "https://grok.com/set-cookie?q=abc123xyz"


def test_extract_set_cookie_url_from_response_headers():
    headers = {"x-action-redirect": "https://grok.com/set-cookie?q=abc123xyz"}
    url = RegisterRunner._extract_set_cookie_url("", headers=headers)
    assert url == "https://grok.com/set-cookie?q=abc123xyz"
