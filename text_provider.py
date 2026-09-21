from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from ax.operations.candidates import ActionCandidate
from settings import Settings


class TextProviderError(RuntimeError):
    pass


class TextAnswer(BaseModel):
    text: str


class OpenRouterTextProvider:
    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | Any | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.client = client or httpx.Client(timeout=25)
        self._owns_client = client is None

    def __call__(
        self,
        goal: str,
        candidate: ActionCandidate,
        history: list[dict[str, Any]],
    ) -> str:
        api_key = self.settings.openrouter_api_key
        if api_key is None:
            raise TextProviderError(
                "OPENROUTER_API_KEY is required when JEV selects TYPE_TEXT"
            )

        body = {
            "model": self.settings.openrouter_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return the exact text that should be entered into the "
                        "selected computer field. Return only the requested JSON "
                        "object. Do not explain, add markdown, or include quotes "
                        "around the text value."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": goal,
                            "field": {
                                "label": candidate.label,
                                "role": candidate.role,
                                "context": list(candidate.parent_path),
                            },
                            "recent_actions": history[-10:],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "temperature": 0,
            "max_tokens": 256,
            "reasoning": {"effort": "none"},
            "provider": {"require_parameters": True},
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "text_value",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                        "additionalProperties": False,
                    },
                },
            },
        }

        try:
            response = self.client.post(
                self.settings.openrouter_url,
                json=body,
                headers={
                    "Authorization": f"Bearer {api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as error:
            raise TextProviderError("OpenRouter connection failed") from error

        if response.status_code >= 400:
            raise TextProviderError(f"OpenRouter returned HTTP {response.status_code}")

        try:
            content = response.json()["choices"][0]["message"]["content"]
            answer = TextAnswer.model_validate_json(content)
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as error:
            raise TextProviderError("OpenRouter returned invalid text") from error

        text = answer.text.strip()
        if not text:
            raise TextProviderError("OpenRouter returned empty text")
        return text

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
