"""OpenAI-compatible Motif 3 callable for GEPA task and reflection roles."""

from collections.abc import Mapping, Sequence
from typing import Any

from openai import OpenAI

from motif_gepa_ko.settings import Settings


class MotifLM:
    """Accept GEPA's chat messages or reflection prompt and return plain text."""

    def __init__(self, settings: Settings, *, client: OpenAI | None = None):
        self.settings = settings
        self.last_response_metadata: dict[str, Any] | None = None
        self.client = client or OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
            max_retries=2,
        )

    def __call__(self, prompt: str | Sequence[Mapping[str, Any]]) -> str:
        self.last_response_metadata = None
        is_reflection = isinstance(prompt, str)
        messages: list[dict[str, Any]]
        if is_reflection:
            messages = [{"role": "user", "content": prompt}]
        else:
            messages = [dict(message) for message in prompt]

        response = self.client.chat.completions.create(
            model=self.settings.model,
            messages=messages,
            temperature=self.settings.temperature,
            max_completion_tokens=(
                self.settings.reflection_max_output_tokens if is_reflection else self.settings.max_output_tokens
            ),
            extra_body={"usage": {"include": True}},
        )
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
            raise RuntimeError("Motif API 응답에 choices가 없습니다.")
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError(
                f"Motif API의 텍스트 응답이 비어 있습니다. finish_reason={response.choices[0].finish_reason!r}"
            )
        return content
