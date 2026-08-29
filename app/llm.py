"""MiniMax OpenAI-compatible client used by product agents."""

import json
from typing import Any

from openai import OpenAI

from app.config import settings


class LLMError(RuntimeError):
    """Safe, credential-free error raised for model failures."""


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


def complete_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Call MiniMax M3 with adaptive thinking and parse the final JSON object."""

    try:
        response = _client().chat.completions.create(
            model=settings.minimax_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_completion_tokens=8192,
            extra_body={
                "thinking": {"type": "adaptive"},
                "reasoning_split": True,
            },
        )
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError("MiniMax request failed") from exc

    content = response.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise LLMError("MiniMax returned an empty response")
    return _parse_json_object(content)
