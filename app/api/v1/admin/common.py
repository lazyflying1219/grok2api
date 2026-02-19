"""
Admin 共享工具
"""

from pathlib import Path
from typing import Any

import aiofiles
from fastapi.responses import HTMLResponse

TEMPLATE_DIR = Path(__file__).parent.parent.parent.parent / "static"


async def render_template(filename: str):
    """渲染指定模板"""
    template_path = TEMPLATE_DIR / filename
    if not template_path.exists():
        return HTMLResponse(f"Template {filename} not found.", status_code=404)

    async with aiofiles.open(template_path, "r", encoding="utf-8") as f:
        content = await f.read()
    return HTMLResponse(content)


def _display_key(key: str) -> str:
    k = str(key or "")
    if len(k) <= 12:
        return k
    return f"{k[:6]}...{k[-4:]}"


def _normalize_limit(v: Any) -> int:
    if v is None or v == "":
        return -1
    try:
        return max(-1, int(v))
    except Exception:
        return -1


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default
