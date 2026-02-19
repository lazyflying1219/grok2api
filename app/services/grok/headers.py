"""
Grok 请求头构造（单一来源）

所有对 grok.com 的请求共用同一套浏览器指纹头。
只在此文件中维护，其他服务统一调用。
"""

import uuid

from app.core.config import get_config
from app.services.grok.statsig import StatsigService


def build_grok_headers(token: str, referer: str = "https://grok.com/") -> dict:
    """
    构建 Grok API 请求头。

    Args:
        token: SSO cookie（raw 或 sso= 前缀均可）
        referer: Referer 头（不同接口可能不同）
    """
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Baggage": "sentry-environment=production,sentry-release=d6add6fb0460641fd482d767a335ef72b9b6abb8,sentry-public_key=b311e0f2690c81f25e2c4cf6d4f7ce1c",
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "Origin": "https://grok.com",
        "Pragma": "no-cache",
        "Priority": "u=1, i",
        "Referer": referer,
        "Sec-Ch-Ua": '"Google Chrome";v="136", "Chromium";v="136", "Not(A:Brand";v="24"',
        "Sec-Ch-Ua-Arch": "arm",
        "Sec-Ch-Ua-Bitness": "64",
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Model": "",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    }

    # Statsig ID
    headers["x-statsig-id"] = StatsigService.gen_id()
    headers["x-xai-request-id"] = str(uuid.uuid4())

    # Cookie
    token = token[4:] if token.startswith("sso=") else token
    cf = get_config("grok.cf_clearance", "")
    headers["Cookie"] = f"sso={token};cf_clearance={cf}" if cf else f"sso={token}"

    return headers
