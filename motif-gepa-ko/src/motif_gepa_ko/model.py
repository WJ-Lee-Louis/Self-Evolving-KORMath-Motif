"""OpenAI-compatible Motif 3 callable for GEPA task and reflection roles."""

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from openai import AsyncOpenAI, OpenAI, OpenAIError

from motif_gepa_ko.settings import Settings


class RequestDeadlineExceeded(OpenAIError):
    """The complete request exceeded its wall-clock deadline."""


class EmptyModelResponseError(RuntimeError):
    """The provider returned no usable text."""


class MotifLM:
    """Accept GEPA's chat messages or reflection prompt and return plain text."""

    def __init__(self, settings: Settings, *, client: OpenAI | None = None):
        self.settings = settings
        self.last_response_metadata: dict[str, Any] | None = None
        self.client = client

    def __call__(self, prompt: str | Sequence[Mapping[str, Any]]) -> str:
        self.last_response_metadata = None
        is_reflection = isinstance(prompt, str)
        messages: list[dict[str, Any]]
        if is_reflection:
            messages = [{"role": "user", "content": prompt}]
        else:
            messages = [dict(message) for message in prompt]

        request = dict(
            model=self.settings.model,
            messages=messages,
            temperature=self.settings.temperature,
            max_completion_tokens=(
                self.settings.reflection_max_output_tokens if is_reflection else self.settings.max_output_tokens
            ),
            extra_body={"usage": {"include": True}},
        )
        if self.client is not None:
            # A supplied client is used by unit tests and local integrations.
            response = self.client.chat.completions.create(**request)
        else:
            async def send_request():
                async with AsyncOpenAI(
                    api_key=self.settings.api_key,
                    base_url=self.settings.base_url,
                    timeout=self.settings.timeout_seconds,
                    max_retries=0,
                ) as client:
                    return await client.chat.completions.create(**request)

            try:
                response = asyncio.run(asyncio.wait_for(
                    send_request(), timeout=self.settings.timeout_seconds,
                ))
            except asyncio.TimeoutError as exc:
                raise RequestDeadlineExceeded(
                    f"Motif request exceeded {self.settings.timeout_seconds:g} seconds"
                ) from exc
        usage = getattr(response, "usage", None)
        self.last_response_metadata = {
            "response_id": getattr(response, "id", None),
            "request_id": getattr(response, "_request_id", None),
            "resolved_model": getattr(response, "model", None),
            "created": getattr(response, "created", None),
            "system_fingerprint": getattr(response, "system_fingerprint", None),
            "finish_reason": response.choices[0].finish_reason if response.choices else None,
            "requested_max_completion_tokens": (
                self.settings.reflection_max_output_tokens if is_reflection else self.settings.max_output_tokens
            ),
            "usage": usage.model_dump(mode="json") if hasattr(usage, "model_dump") else usage,
        }
        if not response.choices:
            raise EmptyModelResponseError("Motif API 응답에 choices가 없습니다.")
        content = response.choices[0].message.content
        if not content:
            raise EmptyModelResponseError(
                f"Motif API의 텍스트 응답이 비어 있습니다. finish_reason={response.choices[0].finish_reason!r}"
            )
        return content
