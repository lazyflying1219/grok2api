"""
工具调用（tool_calls）兼容工具。

本项目对外提供 OpenAI 兼容的 tools/tool_calls 接口，但上游 Grok 的聊天接口并不直接返回
OpenAI 的 tool_calls 结构。这里提供两种模式：

- prompt 模式：在消息里注入一段系统提示，要求模型用 `<tool_call>...</tool_call>` 输出工具调用 JSON。
- passthrough 模式：构造上游 `toolOverrides`（如果上游支持）。

无论哪种模式，下游都通过解析 `<tool_call>` 块，将其转换成 OpenAI 的 `tool_calls` 数据结构。
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any


TOOL_PROMPT_TEMPLATE = """
You have access to the following tools:
{tools_json}

When you need to call a tool, output a <tool_call> block with a JSON object, for example:
<tool_call>{{"name":"tool_name","arguments":{{"key":"value"}}}}</tool_call>

Rules:
- Only output <tool_call> blocks when calling tools.
- You can output multiple <tool_call> blocks only if parallel_tool_calls is true.
- If tool_choice is "none", do not call any tools.
- If tool_choice is "required", you must call at least one tool.
- If tool_choice is a tool name, you must call that tool.

tool_choice: {tool_choice}
parallel_tool_calls: {parallel_tool_calls}
""".strip()


def convert_tool_choice(tool_choice: Any) -> Any:
    """将 OpenAI tool_choice 规范化为字符串或函数名。"""
    if tool_choice is None:
        return "auto"
    if isinstance(tool_choice, str):
        return tool_choice
    if isinstance(tool_choice, dict):
        if tool_choice.get("type") == "function":
            fn = tool_choice.get("function") or {}
            if isinstance(fn, dict) and fn.get("name"):
                return fn["name"]
    return "auto"


def build_tool_prompt(
    tools: list[dict[str, Any]],
    tool_choice: Any = "auto",
    parallel_tool_calls: bool = True,
) -> str:
    """构造 prompt 模式下的工具系统提示。"""
    tool_choice = convert_tool_choice(tool_choice)
    tools_json = json.dumps(tools or [], ensure_ascii=False)
    return TOOL_PROMPT_TEMPLATE.format(
        tools_json=tools_json,
        tool_choice=tool_choice,
        parallel_tool_calls=str(bool(parallel_tool_calls)).lower(),
    )


def build_tool_overrides(
    tools: list[dict[str, Any]],
    tool_choice: Any = "auto",
    parallel_tool_calls: bool = True,
) -> dict[str, Any]:
    """构造上游 toolOverrides（passthrough 模式）。"""
    tool_choice = convert_tool_choice(tool_choice)
    return {
        "tools": tools or [],
        "toolChoice": tool_choice,
        "parallelToolCalls": bool(parallel_tool_calls),
    }


_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)


def parse_tool_call_block(block: str) -> dict[str, Any] | None:
    """
    解析单个 `<tool_call>...</tool_call>` 内的 JSON，返回 OpenAI tool_call 结构。
    """
    try:
        data = json.loads(block)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    name = data.get("name")
    arguments = data.get("arguments", {})
    if not isinstance(name, str) or not name.strip():
        return None

    # OpenAI 的 function.arguments 是 JSON 字符串
    if isinstance(arguments, str):
        arguments_str = arguments
    else:
        try:
            arguments_str = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            arguments_str = "{}"

    return {
        "id": f"call_{uuid.uuid4().hex[:24]}",
        "type": "function",
        "function": {"name": name, "arguments": arguments_str},
    }


def parse_tool_calls(
    content: str,
    tools: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """从内容中提取 tool_calls，同时返回剔除 `<tool_call>` 块后的文本。"""
    tools = tools or []
    allowed: set[str] = set()
    for t in tools:
        if isinstance(t, dict) and t.get("type") == "function":
            fn = t.get("function") or {}
            if isinstance(fn, dict) and isinstance(fn.get("name"), str):
                allowed.add(fn["name"])

    tool_calls: list[dict[str, Any]] = []
    for match in _TOOL_CALL_RE.finditer(content or ""):
        block = match.group(1)
        tool_call = parse_tool_call_block(block)
        if not tool_call:
            continue
        if allowed and tool_call["function"]["name"] not in allowed:
            continue
        tool_calls.append(tool_call)

    text_content = _TOOL_CALL_RE.sub("", content or "").strip()
    return text_content, tool_calls


def format_tool_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    将 OpenAI 工具调用历史转成可喂给 Grok 的文本消息格式。

    - assistant.tool_calls：拼接为 `<tool_call>` 块
    - role=tool：转成 user 文本（避免上游不认识 tool 角色）
    """
    new_messages: list[dict[str, Any]] = []

    for msg in messages or []:
        role = msg.get("role", "")

        # tool 结果消息：转换成 user 文本
        if role == "tool":
            tool_name = msg.get("name", "")
            tool_call_id = msg.get("tool_call_id", "")
            tool_content = msg.get("content", "")
            if isinstance(tool_content, (dict, list)):
                tool_content = json.dumps(tool_content, ensure_ascii=False)
            new_messages.append(
                {
                    "role": "user",
                    "content": f"[Tool Result] {tool_name}({tool_call_id}): {tool_content}",
                }
            )
            continue

        # assistant.tool_calls：转换成可解析的 <tool_call> 块文本
        if role == "assistant" and msg.get("tool_calls"):
            tool_calls = msg.get("tool_calls") or []
            text = msg.get("content", "") or ""
            parts: list[str] = []
            if text:
                parts.append(str(text))

            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") or {}
                if not isinstance(fn, dict):
                    continue
                name = fn.get("name")
                args = fn.get("arguments", "{}")
                if not isinstance(name, str) or not name.strip():
                    continue
                if not isinstance(args, str):
                    try:
                        args = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
                    except Exception:
                        args = "{}"
                block = json.dumps({"name": name, "arguments": args}, ensure_ascii=False)
                parts.append(f"<tool_call>{block}</tool_call>")

            new_msg = msg.copy()
            new_msg.pop("tool_calls", None)
            new_msg["content"] = "\n".join(parts).strip()
            new_messages.append(new_msg)
            continue

        new_messages.append(msg)

    return new_messages


__all__ = [
    "build_tool_prompt",
    "build_tool_overrides",
    "parse_tool_calls",
    "format_tool_history",
    "parse_tool_call_block",
]
