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
        timeout=45,
        max_retries=0,
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


def _unescape_json_char(escaped: str) -> str:
    mapping = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/"}
    return mapping.get(escaped, escaped)


def partial_json_string_field(buffer: str, field: str) -> str | None:
    """Return a JSON string field that may still be streaming (unescaped so far)."""

    key = f'"{field}"'
    index = buffer.find(key)
    if index < 0:
        return None
    colon = buffer.find(":", index + len(key))
    if colon < 0:
        return None
    rest = buffer[colon + 1 :].lstrip()
    if not rest.startswith('"'):
        return None
    chars: list[str] = []
    escaped = False
    for char in rest[1:]:
        if escaped:
            chars.append(_unescape_json_char(char))
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            return "".join(chars)
        chars.append(char)
    return "".join(chars)


def _delta_content(chunk: Any) -> str:
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return ""
    delta = getattr(choices[0], "delta", None)
    content = getattr(delta, "content", None) if delta is not None else None
    return content if isinstance(content, str) else ""


def _consume_streamed_json(response: Any, on_progress: Callable[[dict[str, Any]], None] | None) -> str:
    """Read a streaming or non-streaming completion and emit thought as it appears."""

    if hasattr(response, "choices") and getattr(response, "choices", None):
        content = _message_content(response.choices[0].message)
        thought = partial_json_string_field(content, "thought") if content else None
        if on_progress and thought:
            on_progress({"kind": "thought_delta", "text": thought})
        return content

    content = ""
    emitted = 0
    for chunk in response:
        piece = _delta_content(chunk)
        if not piece:
            continue
        content += piece
        thought = partial_json_string_field(content, "thought")
        if on_progress and thought and len(thought) > emitted:
            on_progress({"kind": "thought_delta", "text": thought[emitted:]})
            emitted = len(thought)
    return content


def _create_completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    *,
    max_tokens: int = 2048,
    stream: bool = False,
) -> Any:
    payload: dict[str, Any] = {
        "model": settings.minimax_model,
        "messages": messages,
        "temperature": 0.2,
        "max_completion_tokens": max_tokens,
        "extra_body": {
            "thinking": {"type": "disabled"},
        },
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if stream:
        payload["stream"] = True

    try:
        return _client().chat.completions.create(**payload)
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError("MiniMax request failed") from exc


def complete_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Call MiniMax and parse the final JSON object. Thinking stays disabled."""

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
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """One tool-enabled round, then continue and parse the existing turn JSON.

    The runner may expose multiple tools in one list (e.g. code_inspect 与
    code_exercise 并列). This loop does not special-case names.
    Final JSON may be streamed so thought can appear before the object is complete.
    Model thinking stays disabled; only the JSON `thought` field is streamed.
    """

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for round_index in range(max_tool_rounds + 1):
        use_tools = tools if round_index < max_tool_rounds else None
        # MiniMax streamed content often contains raw newlines inside JSON
        # strings, which breaks parsing. Tools still emit live via run_tool.
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
        thought = partial_json_string_field(content, "thought")
        if on_progress and thought:
            on_progress({"kind": "thought_delta", "text": thought})
        return _parse_json_object(content)

    raise LLMError("MiniMax did not return a JSON object after tools")


def complete_text_with_tools(
    system_prompt: str,
    user_prompt: str,
    *,
    tools: list[dict[str, Any]],
    run_tool: ToolRunner,
    max_tool_rounds: int = 2,
    max_tokens: int = 8192,
) -> str:
    """Tool-enabled completion that returns the final markdown/text body."""

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for round_index in range(max_tool_rounds + 1):
        use_tools = tools if round_index < max_tool_rounds else None
        response = _create_completion(messages, use_tools, max_tokens=max_tokens)
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
        return content

    raise LLMError("MiniMax did not return text after tools")
