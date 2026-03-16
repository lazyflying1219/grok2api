"""
Chat Completions API 路由
"""

from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.core.auth import verify_api_key
from app.services.grok.chat import ChatService
from app.services.grok.model import ModelService
from app.core.exceptions import ValidationException
from app.services.quota import enforce_daily_quota


router = APIRouter(tags=["Chat"])


VALID_ROLES = ["developer", "system", "user", "assistant", "tool"]
USER_CONTENT_TYPES = ["text", "image_url", "input_audio", "file"]


class MessageItem(BaseModel):
    """消息项"""
    role: str
    # OpenAI 的 tool_calls 场景下 assistant.content 可能为 null；tool.content 也可能是对象。
    content: Union[str, List[Dict[str, Any]], Dict[str, Any], None] = None

    # 允许携带 tool_call_id / tool_calls / name 等字段，并在 model_dump 时保留。
    model_config = {"extra": "allow"}
    
    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in VALID_ROLES:
            raise ValueError(f"role must be one of {VALID_ROLES}")
        return v


class VideoConfig(BaseModel):
    """视频生成配置"""
    aspect_ratio: Optional[str] = Field("3:2", description="视频比例: 3:2, 16:9, 1:1 等")
    video_length: Optional[int] = Field(6, description="视频时长(秒): 5-15")
    resolution: Optional[str] = Field("SD", description="视频分辨率: SD, HD")
    preset: Optional[str] = Field("custom", description="风格预设: fun, normal, spicy")
    
    @field_validator("aspect_ratio")
    @classmethod
    def validate_aspect_ratio(cls, v):
        allowed = ["2:3", "3:2", "1:1", "9:16", "16:9"]
        if v and v not in allowed:
            raise ValidationException(
                message=f"aspect_ratio must be one of {allowed}",
                param="video_config.aspect_ratio",
                code="invalid_aspect_ratio"
            )
        return v
    
    @field_validator("video_length")
    @classmethod
    def validate_video_length(cls, v):
        if v is not None:
            if v < 5 or v > 15:
                raise ValidationException(
                    message="video_length must be between 5 and 15 seconds",
                    param="video_config.video_length",
                    code="invalid_video_length"
                )
        return v

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, v):
        allowed = ["SD", "HD"]
        if v and v not in allowed:
            raise ValidationException(
                message=f"resolution must be one of {allowed}",
                param="video_config.resolution",
                code="invalid_resolution"
            )
        return v
    
    @field_validator("preset")
    @classmethod
    def validate_preset(cls, v):
        # 允许为空，默认 custom
        if not v:
            return "custom"
        allowed = ["fun", "normal", "spicy", "custom"]
        if v not in allowed:
             raise ValidationException(
                message=f"preset must be one of {allowed}",
                param="video_config.preset",
                code="invalid_preset"
             )
        return v


class ChatCompletionRequest(BaseModel):
    """Chat Completions 请求"""
    model: str = Field(..., description="模型名称")
    messages: List[MessageItem] = Field(..., description="消息数组")
    stream: Optional[bool] = Field(False, description="是否流式输出")
    thinking: Optional[str] = Field(None, description="思考模式: enabled/disabled/None")

    # OpenAI tools / tool_calls 相关参数
    tools: Optional[List[Dict[str, Any]]] = Field(None, description="工具定义（OpenAI tools 规范）")
    tool_choice: Optional[Any] = Field("auto", description="工具选择策略（auto/none/required/指定函数）")
    parallel_tool_calls: Optional[bool] = Field(True, description="是否允许并行工具调用")
    
    # 视频生成配置
    video_config: Optional[VideoConfig] = Field(None, description="视频生成参数")
    
    model_config = {
        "extra": "ignore"
    }


def validate_request(request: ChatCompletionRequest):
    """验证请求参数"""
    # 验证模型
    if not ModelService.valid(request.model):
        raise ValidationException(
            message=f"The model `{request.model}` does not exist or you do not have access to it.",
            param="model",
            code="model_not_found"
        )
    
    # 验证消息
    for idx, msg in enumerate(request.messages):
        content = msg.content
        role = msg.role

        # 字符串内容
        if isinstance(content, str):
            if not content.strip():
                raise ValidationException(
                    message="Message content cannot be empty",
                    param=f"messages.{idx}.content",
                    code="empty_content"
                )
        
        # 列表内容
        elif isinstance(content, list):
            if not content:
                raise ValidationException(
                    message="Message content cannot be an empty array",
                    param=f"messages.{idx}.content",
                    code="empty_content"
                )
            
            for block_idx, block in enumerate(content):
                # 检查空对象
                if not block:
                    raise ValidationException(
                        message="Content block cannot be empty",
                        param=f"messages.{idx}.content.{block_idx}",
                        code="empty_block"
                    )
                
                # 检查 type 字段
                if "type" not in block:
                    raise ValidationException(
                        message="Content block must have a 'type' field",
                        param=f"messages.{idx}.content.{block_idx}",
                        code="missing_type"
                    )
                
                block_type = block.get("type")
                
                # 检查 type 空值
                if not block_type or not isinstance(block_type, str) or not block_type.strip():
                    raise ValidationException(
                        message="Content block 'type' cannot be empty",
                        param=f"messages.{idx}.content.{block_idx}.type",
                        code="empty_type"
                    )
                
                # 验证 type 有效性
                if msg.role == "user":
                    if block_type not in USER_CONTENT_TYPES:
                        raise ValidationException(
                            message=f"Invalid content block type: '{block_type}'",
                            param=f"messages.{idx}.content.{block_idx}.type",
                            code="invalid_type"
                        )
                elif block_type != "text":
                    raise ValidationException(
                        message=f"The `{msg.role}` role only supports 'text' type, got '{block_type}'",
                        param=f"messages.{idx}.content.{block_idx}.type",
                        code="invalid_type"
                    )
                
                # 验证字段是否存在 & 非空
                if block_type == "text":
                    text = block.get("text", "")
                    if not isinstance(text, str) or not text.strip():
                        raise ValidationException(
                            message="Text content cannot be empty",
                            param=f"messages.{idx}.content.{block_idx}.text",
                            code="empty_text"
                        )
                elif block_type == "image_url":
                    image_url = block.get("image_url")
                    if not image_url or not (isinstance(image_url, dict) and image_url.get("url")):
                        raise ValidationException(
                            message="image_url must have a 'url' field",
                            param=f"messages.{idx}.content.{block_idx}.image_url",
                            code="missing_url"
                        )

        # tool 结果允许对象内容（会在下游格式化为文本）
        elif isinstance(content, dict):
            if role != "tool":
                raise ValidationException(
                    message="Only 'tool' role supports object content",
                    param=f"messages.{idx}.content",
                    code="invalid_content"
                )

        # content 允许为 null（常见于 assistant.tool_calls）
        elif content is None:
            continue

        else:
            raise ValidationException(
                message="Invalid message content type",
                param=f"messages.{idx}.content",
                code="invalid_content"
            )


@router.post("/chat/completions")
async def chat_completions(request: ChatCompletionRequest, api_key: Optional[str] = Depends(verify_api_key)):
    """Chat Completions API - 兼容 OpenAI"""
    
    # 参数验证
    validate_request(request)

    # Daily quota (best-effort)
    await enforce_daily_quota(api_key, request.model)
    
    # 兼容 OpenAI：仅在显式 true 时走流式，缺省/null 一律按非流式处理
    is_stream = request.stream is True

    # 检测视频模型
    model_info = ModelService.get(request.model)
    if model_info and model_info.is_video:
        from app.services.grok.media import VideoService
        
        # 提取视频配置 (默认值在 Pydantic 模型中处理)
        v_conf = request.video_config or VideoConfig()
        
        result = await VideoService.completions(
            model=request.model,
            messages=[msg.model_dump() for msg in request.messages],
            stream=is_stream,
            thinking=request.thinking,
            aspect_ratio=v_conf.aspect_ratio,
            video_length=v_conf.video_length,
            resolution=v_conf.resolution,
            preset=v_conf.preset
        )
    else:
        result = await ChatService.completions(
            model=request.model,
            messages=[msg.model_dump() for msg in request.messages],
            stream=is_stream,
            thinking=request.thinking,
            tools=request.tools,
            tool_choice=request.tool_choice,
            parallel_tool_calls=request.parallel_tool_calls,
        )
    
    if isinstance(result, dict):
        return JSONResponse(content=result)
    else:
        return StreamingResponse(
            result,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )


__all__ = ["router"]
