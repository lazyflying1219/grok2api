"""
Admin WebSocket 路由（图像生成实时流）
"""

import asyncio
import time
import uuid
from typing import Optional

import orjson
from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.core.auth import verify_session_token
from app.core.config import get_config
from app.core.logger import logger
from app.services.grok.model import ModelService
from app.services.grok.imagine_generation import (
    collect_experimental_generation_images,
    is_valid_image_value as is_valid_imagine_image_value,
    resolve_aspect_ratio as resolve_imagine_aspect_ratio,
)
from app.services.token import get_token_manager

router = APIRouter()


async def _verify_ws_api_key(websocket: WebSocket) -> bool:
    app_key = str(get_config("app.app_key", "") or "").strip()
    if not app_key:
        return False
    token = str(websocket.query_params.get("api_key") or "").strip()
    if not token:
        return False
    import hmac
    # Accept raw app_key or session token
    return hmac.compare_digest(token, app_key) or verify_session_token(token, app_key)


async def _collect_imagine_batch(token: str, prompt: str, aspect_ratio: str) -> list[str]:
    return await collect_experimental_generation_images(
        token=token,
        prompt=prompt,
        n=6,
        response_format="b64_json",
        aspect_ratio=aspect_ratio,
        concurrency=1,
    )


@router.websocket("/api/v1/admin/imagine/ws")
async def admin_imagine_ws(websocket: WebSocket):
    if not await _verify_ws_api_key(websocket):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    stop_event = asyncio.Event()
    run_task: Optional[asyncio.Task] = None

    async def _send(payload: dict) -> bool:
        try:
            await websocket.send_text(orjson.dumps(payload).decode())
            return True
        except Exception:
            return False

    async def _stop_run():
        nonlocal run_task
        stop_event.set()
        if run_task and not run_task.done():
            run_task.cancel()
            try:
                await run_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        run_task = None
        stop_event.clear()

    async def _run(prompt: str, aspect_ratio: str):
        model_id = "grok-imagine-1.0"
        model_info = ModelService.get(model_id)
        if not model_info or not model_info.is_image:
            await _send(
                {
                    "type": "error",
                    "message": "Image model is not available.",
                    "code": "model_not_supported",
                }
            )
            return

        token_mgr = await get_token_manager()
        sequence = 0
        run_id = uuid.uuid4().hex
        await _send(
            {
                "type": "status",
                "status": "running",
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "run_id": run_id,
            }
        )

        while not stop_event.is_set():
            token = None
            reservation_id = None
            try:
                token, reservation_id = await token_mgr.reserve_token_for_model(model_info.model_id)
                if not token:
                    await _send(
                        {
                            "type": "error",
                            "message": "No available tokens. Please try again later.",
                            "code": "rate_limit_exceeded",
                        }
                    )
                    await asyncio.sleep(2)
                    continue

                start_at = time.time()
                images = await _collect_imagine_batch(token, prompt, aspect_ratio)
                elapsed_ms = int((time.time() - start_at) * 1000)

                sent_any = False
                for image_b64 in images:
                    if not is_valid_imagine_image_value(image_b64):
                        continue
                    sent_any = True
                    sequence += 1
                    ok = await _send(
                        {
                            "type": "image",
                            "b64_json": image_b64,
                            "sequence": sequence,
                            "created_at": int(time.time() * 1000),
                            "elapsed_ms": elapsed_ms,
                            "aspect_ratio": aspect_ratio,
                            "run_id": run_id,
                        }
                    )
                    if not ok:
                        stop_event.set()
                        break

                if sent_any:
                    try:
                        await token_mgr.sync_usage(
                            token,
                            model_info.model_id,
                            consume_on_fail=True,
                            is_usage=True,
                        )
                    except Exception as e:
                        logger.warning(f"Imagine ws token sync failed: {e}")
                else:
                    await _send(
                        {
                            "type": "error",
                            "message": "Image generation returned empty data.",
                            "code": "empty_image",
                        }
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Imagine stream error: {e}")
                await _send(
                    {
                        "type": "error",
                        "message": str(e),
                        "code": "internal_error",
                    }
                )
                await asyncio.sleep(1.5)
            finally:
                if token:
                    try:
                        await token_mgr.release_token_reservation(token, reservation_id)
                    except Exception:
                        pass

        await _send({"type": "status", "status": "stopped", "run_id": run_id})

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except (RuntimeError, WebSocketDisconnect):
                break

            try:
                payload = orjson.loads(raw)
            except Exception:
                await _send(
                    {
                        "type": "error",
                        "message": "Invalid message format.",
                        "code": "invalid_payload",
                    }
                )
                continue

            msg_type = payload.get("type")
            if msg_type == "start":
                prompt = str(payload.get("prompt") or "").strip()
                if not prompt:
                    await _send(
                        {
                            "type": "error",
                            "message": "Prompt cannot be empty.",
                            "code": "empty_prompt",
                        }
                    )
                    continue
                ratio = resolve_imagine_aspect_ratio(str(payload.get("aspect_ratio") or "2:3").strip())
                await _stop_run()
                run_task = asyncio.create_task(_run(prompt, ratio))
            elif msg_type == "stop":
                await _stop_run()
            elif msg_type == "ping":
                await _send({"type": "pong"})
            else:
                await _send(
                    {
                        "type": "error",
                        "message": "Unknown command.",
                        "code": "unknown_command",
                    }
                )
    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected by client")
    except asyncio.CancelledError:
        logger.debug("WebSocket handler cancelled")
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
    finally:
        await _stop_run()
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close(code=1000, reason="Server closing connection")
        except Exception as e:
            logger.debug(f"WebSocket close ignored: {e}")
