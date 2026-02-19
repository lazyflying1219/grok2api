"""
Admin 页面路由
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from app.api.v1.admin.common import render_template

router = APIRouter()


@router.get("/", include_in_schema=False)
async def root_redirect():
    """Default entry -> /login (consistent with Workers/Pages)."""
    return RedirectResponse(url="/login", status_code=302)


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page():
    """Login page (default)."""
    return await render_template("login/login.html")


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_login_page():
    """Legacy login entry (redirect to /login)."""
    return RedirectResponse(url="/login", status_code=302)


@router.get("/admin/config", response_class=HTMLResponse, include_in_schema=False)
async def admin_config_page():
    """配置管理页"""
    return await render_template("config/config.html")


@router.get("/admin/token", response_class=HTMLResponse, include_in_schema=False)
async def admin_token_page():
    """Token 管理页"""
    return await render_template("token/token.html")


@router.get("/admin/datacenter", response_class=HTMLResponse, include_in_schema=False)
async def admin_datacenter_page():
    """数据中心页"""
    return await render_template("datacenter/datacenter.html")


@router.get("/admin/keys", response_class=HTMLResponse, include_in_schema=False)
async def admin_keys_page():
    """API Key 管理页"""
    return await render_template("keys/keys.html")


@router.get("/chat", response_class=HTMLResponse, include_in_schema=False)
async def chat_page():
    """在线聊天页（公开入口）"""
    return await render_template("chat/chat.html")


@router.get("/admin/chat", response_class=HTMLResponse, include_in_schema=False)
async def admin_chat_page():
    """在线聊天页（后台入口）"""
    return await render_template("chat/chat_admin.html")


@router.get("/admin/cache", response_class=HTMLResponse, include_in_schema=False)
async def admin_cache_page():
    """缓存管理页"""
    return await render_template("cache/cache.html")
