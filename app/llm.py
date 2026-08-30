"""MiniMax OpenAI-compatible client used by product agents."""

from collections.abc import Callable
import json
from typing import Any

from openai import OpenAI

from app.config import settings


class LLMError(RuntimeError):
    """Safe, credential-free error raised for model failures."""


ToolRunner = Callable[[str, dict[str, Any]], str]


def _client() -> OpenAI:
    if not settings.minimax_api_key:
        raise LLMError("MiniMax API key is not configured")
    if not settings.minimax_base_url or not settings.minimax_model:
        raise LLMError("MiniMax endpoint or model is not configured")

    return OpenAI(
        api_key=settings.minimax_api_key,
        base_url=settings.minimax_base_url,
        timeout=90,
        max_retries=1,
    )


def _parse_json_object(content: str) -> dict[str, Any]:
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end <= start:
        raise LLMError("MiniMax response did not contain a JSON object")

    try:
        parsed = json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError("MiniMax response JSON was invalid") from exc
    if not isinstance(parsed, dict):
        raise LLMError("MiniMax response must be a JSON object")
    return parsed


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"query": raw.strip()[:500]}
    if isinstance(parsed, dict):
        return parsed
    return {"query": str(parsed)}


def _message_content(message: Any) -> str:
    content = getattr(message, "content", None)
    return content if isinstance(content, str) else ""


def _create_completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> Any:
    payload: dict[str, Any] = {
        "model": settings.minimax_model,
        "messages": messages,
        "temperature": 0.2,
        "max_completion_tokens": 8192,
        "extra_body": {
            "thinking": {"type": "adaptive"},
            "reasoning_split": True,
        },
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    try:
        return _client().chat.completions.create(**payload)
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError("MiniMax request failed") from exc


def complete_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Call MiniMax M3 with adaptive thinking and parse the final JSON object."""

    response = _create_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )
    content = _message_content(response.choices[0].message)
    if not content.strip():
        raise LLMError("MiniMax returned an empty response")
    return _parse_json_object(content)


def complete_json_with_tools(
    system_prompt: str,
    user_prompt: str,
    *,
    tools: list[dict[str, Any]],
    run_tool: ToolRunner,
    max_tool_rounds: int = 1,
) -> dict[str, Any]:
    """One tool-enabled round, then continue and parse the existing turn JSON."""

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for round_index in range(max_tool_rounds + 1):
        use_tools = tools if round_index < max_tool_rounds else None
        response = _create_completion(messages, use_tools)
        message = response.choices[0].message
        tool_calls = list(getattr(message, "tool_calls", None) or [])

        if tool_calls and round_index < max_tool_rounds:
            serialized_calls: list[dict[str, Any]] = []
            tool_messages: list[dict[str, Any]] = []
            for index, call in enumerate(tool_calls):
                function = getattr(call, "function", None)
                name = getattr(function, "name", None) or "code_inspect"
                raw_args = getattr(function, "arguments", None)
                call_id = getattr(call, "id", None) or f"call_{index}"
                serialized_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": raw_args
                            if isinstance(raw_args, str)
                            else json.dumps(raw_args or {}, ensure_ascii=False),
                        },
                    }
                )
                tool_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": run_tool(name, _parse_tool_arguments(raw_args)),
                    }
                )
            messages.append(
                {
                    "role": "assistant",
                    "content": _message_content(message) or None,
                    "tool_calls": serialized_calls,
                }
            )
            messages.extend(tool_messages)
            continue

        content = _message_content(message)
        if not content.strip():
            raise LLMError("MiniMax returned an empty response")
        return _parse_json_object(content)

    raise LLMError("MiniMax did not return a JSON object after tools")
