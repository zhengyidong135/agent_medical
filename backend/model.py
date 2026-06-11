from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import (
    MODELS,
    TOOLS,
    WEATHER_CODES,
    api_base_url,
    api_key,
    env_int,
    estimate_tokens_from_text,
    json_request,
)
from rag import retrieve_rag_context

def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for message in messages:
        total += 4
        total += estimate_tokens_from_text(str(message.get("role", "")))
        total += estimate_tokens_from_text(str(message.get("content", "")))
    return total


def format_history_for_summary(messages: list[dict[str, Any]]) -> str:
    lines = []
    for message in messages:
        role = "用户" if message.get("role") == "user" else "助手"
        lines.append(f"{role}: {message.get('content', '')}")
    return "\n".join(lines)


def summarize_memory(model: str, messages: list[dict[str, Any]], headers: dict[str, str]) -> str:
    if not messages:
        return ""

    summary_payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你负责整理聊天长期记忆。请把历史对话压缩成中文摘要，保留："
                    "用户偏好、已确认事实、重要约束、未完成任务、关键上下文。"
                    "不要加入历史中没有的信息。控制在 500 字以内。"
                ),
            },
            {
                "role": "user",
                "content": format_history_for_summary(messages),
            },
        ],
    }
    response = json_request(f"{api_base_url()}/chat/completions", summary_payload, headers)
    return response["choices"][0]["message"].get("content", "").strip()


def build_memory_messages(
    model: str,
    messages: list[dict[str, Any]],
    headers: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    summary_trigger_tokens = env_int("SUMMARY_TRIGGER_TOKENS", 3000)
    force_new_chat_tokens = env_int("FORCE_NEW_CHAT_TOKENS", 8000)
    recent_message_count = env_int("RECENT_MESSAGE_COUNT", 8)
    estimated_tokens = estimate_messages_tokens(messages)
    if estimated_tokens < summary_trigger_tokens or len(messages) <= recent_message_count:
        return messages, {
            "mode": "full",
            "summary": "",
            "estimated_tokens": estimated_tokens,
            "summary_trigger_tokens": summary_trigger_tokens,
            "force_new_chat_tokens": force_new_chat_tokens,
            "recent_message_count": len(messages),
        }

    recent_messages = messages[-recent_message_count:]
    older_messages = messages[:-recent_message_count]
    summary = summarize_memory(model, older_messages, headers)
    memory_messages = [
        {
            "role": "system",
            "content": f"以下是本轮对话的长期记忆摘要，请回答时参考：\n{summary}",
        },
        *recent_messages,
    ]
    return memory_messages, {
        "mode": "summary",
        "summary": summary,
        "estimated_tokens": estimated_tokens,
        "summary_trigger_tokens": summary_trigger_tokens,
        "force_new_chat_tokens": force_new_chat_tokens,
        "recent_message_count": len(recent_messages),
        "summarized_message_count": len(older_messages),
    }


def get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "model-agent/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def get_current_time(timezone: str = "Asia/Shanghai") -> dict[str, Any]:
    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        timezone = "Asia/Shanghai"
        tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    return {
        "timezone": timezone,
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "utc_offset": now.strftime("%z"),
    }


def get_weather(location: str) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {"name": location, "count": 1, "language": "zh", "format": "json"}
    )
    geo = get_json(f"https://geocoding-api.open-meteo.com/v1/search?{query}")
    results = geo.get("results") or []
    if not results:
        return {"location": location, "error": "没有找到这个地点的天气信息。"}

    place = results[0]
    params = urllib.parse.urlencode(
        {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "timezone": "auto",
        }
    )
    weather = get_json(f"https://api.open-meteo.com/v1/forecast?{params}")
    current = weather.get("current", {})
    code = current.get("weather_code")
    return {
        "location": place.get("name", location),
        "country": place.get("country", ""),
        "temperature_c": current.get("temperature_2m"),
        "humidity_percent": current.get("relative_humidity_2m"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "condition": WEATHER_CODES.get(code, f"天气代码 {code}"),
        "time": current.get("time"),
    }


def run_tool(name: str, arguments: str) -> dict[str, Any]:
    try:
        args = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        args = {}

    try:
        if name == "get_current_time":
            return get_current_time(args.get("timezone", "Asia/Shanghai"))
        if name == "get_weather":
            return get_weather(args.get("location", "Beijing"))
        return {"error": f"未知工具: {name}"}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"error": f"工具调用失败: {exc}"}


def call_model(
    model: str,
    messages: list[dict[str, Any]],
    enable_tools: bool,
    rag_file_ids: list[str] | None = None,
) -> dict[str, Any]:
    key = api_key()
    if not key:
        raise RuntimeError("未找到 API Key，请在 agent/.env 中配置 KEY、API_KEY 或 OPENAI_API_KEY。")
    if model not in MODELS:
        raise ValueError("不支持的模型名称。")

    headers = {"Authorization": f"Bearer {key}"}
    incoming_tokens = estimate_messages_tokens(messages)
    force_new_chat_tokens = env_int("FORCE_NEW_CHAT_TOKENS", 8000)
    if incoming_tokens >= force_new_chat_tokens:
        return {
            "model": model,
            "content": "",
            "memory_count": len(messages),
            "memory_info": {
                "mode": "force_new_chat",
                "estimated_tokens": incoming_tokens,
                "force_new_chat_tokens": force_new_chat_tokens,
            },
            "force_new_chat": True,
            "tool_results": [],
        }

    memory_messages, memory_info = build_memory_messages(model, messages, headers)
    last_user_query = next(
        (message.get("content", "") for message in reversed(messages) if message.get("role") == "user"),
        "",
    )
    rag_context, rag_sources = retrieve_rag_context(rag_file_ids or [], str(last_user_query))
    request_messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "你是一个中文优先的智能助手。回答要准确、简洁。"
                "你会把本次请求中提供的历史对话和长期记忆摘要当作聊天记忆，回答时主动参考用户之前说过的信息。"
                "如果提供了 RAG 检索片段，请优先依据片段回答；片段不足时明确说明缺少依据。"
                "当用户询问“我”“自己”“这个人”“简历”等内容时，如果 RAG 片段来自简历或个人资料，请把这些片段视为用户指定的资料来源。"
                "当用户询问天气或时间等实时信息时，优先使用可用工具。"
            ),
        },
        *memory_messages,
    ]
    if rag_context:
        request_messages.insert(
            1,
            {
                "role": "system",
                "content": f"以下是从用户选择文件中检索到的 RAG 上下文：\n{rag_context}",
            },
        )
    payload: dict[str, Any] = {"model": model, "messages": request_messages}
    if enable_tools:
        payload["tools"] = TOOLS
        payload["tool_choice"] = "auto"

    first = json_request(f"{api_base_url()}/chat/completions", payload, headers)
    message = first["choices"][0]["message"]
    tool_calls = message.get("tool_calls") or []
    tool_results: list[dict[str, Any]] = []

    if enable_tools and tool_calls:
        request_messages.append(message)
        for tool_call in tool_calls:
            function = tool_call.get("function", {})
            result = run_tool(function.get("name", ""), function.get("arguments", "{}"))
            tool_results.append(
                {
                    "name": function.get("name", ""),
                    "result": result,
                }
            )
            request_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id"),
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
        second_payload = {"model": model, "messages": request_messages}
        second = json_request(f"{api_base_url()}/chat/completions", second_payload, headers)
        message = second["choices"][0]["message"]

    return {
        "model": model,
        "content": message.get("content", ""),
        "memory_count": len(messages),
        "memory_info": memory_info,
        "rag_sources": rag_sources,
        "tool_results": tool_results,
    }
