"""
Admin API 路由包

将原始 admin.py 拆分为职责清晰的子模块，
对外仍暴露单一 router，main.py 无需修改。
"""

from fastapi import APIRouter

from app.api.v1.admin.pages import router as pages_router
from app.api.v1.admin.auth import router as auth_router
from app.api.v1.admin.tokens import router as tokens_router
from app.api.v1.admin.keys import router as keys_router
from app.api.v1.admin.cache import router as cache_router
from app.api.v1.admin.system import router as system_router
from app.api.v1.admin.websocket import router as ws_router

router = APIRouter()

router.include_router(pages_router)
router.include_router(auth_router)
router.include_router(tokens_router)
router.include_router(keys_router)
router.include_router(cache_router)
router.include_router(system_router)
router.include_router(ws_router)
