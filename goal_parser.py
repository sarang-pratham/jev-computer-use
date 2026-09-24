from __future__ import annotations

import json
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ValidationError

from settings import Settings


class GoalParserError(RuntimeError):
    pass


class GoalContext(BaseModel):
    application_name: str | None = None
    capability: Literal["web_browser", "camera", "calendar"] | None = None
    application_required: bool = False


class OpenRouterGoalParser:
    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | Any | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.client = client or httpx.Client(timeout=25)
        self._owns_client = client is None

    def __call__(self, goal: str) -> GoalContext:
        api_key = self.settings.openrouter_api_key
        if api_key is None:
            raise GoalParserError(
                "OPENROUTER_API_KEY is required to identify the target application"
            )

        body = {
            "model": self.settings.openrouter_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Interpret the macOS application intent in the goal. The "
                        "goal may use arbitrary natural language. Set "
                        "application_name only when a specific application is "
                        "named, such as Safari or Calendar. Otherwise set it to "
                        "null and use one canonical capability when the goal "
                        "describes an application role: web_browser, camera, or "
                        "calendar. For example, browser maps to web_browser and "
                        "taking a picture maps to camera. Set application_required "
                        "to true when the goal depends on an application or "
                        "capability. A specific application name takes precedence "
                        "over a capability. Return JSON only."
                    ),
                },
                {"role": "user", "content": goal},
            ],
            "temperature": 0,
            "max_tokens": 256,
            "reasoning": {"effort": "none"},
            "provider": {"require_parameters": True},
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "goal_context",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "application_name": {
                                "type": ["string", "null"],
                            },
                            "capability": {
                                "type": ["string", "null"],
                                "enum": [
                                    "web_browser",
                                    "camera",
                                    "calendar",
                                    None,
                                ],
                            },
                            "application_required": {"type": "boolean"},
                        },
                        "required": [
                            "application_name",
                            "capability",
                            "application_required",
                        ],
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
            raise GoalParserError("OpenRouter connection failed") from error

        if response.status_code >= 400:
            raise GoalParserError(f"OpenRouter returned HTTP {response.status_code}")

        try:
            payload = response.json()
            choice = payload["choices"][0]
            content = choice["message"]["content"]
            if not content:
                finish_reason = choice.get("finish_reason", "unknown")
                raise GoalParserError(
                    "OpenRouter returned no goal context "
                    f"(finish_reason={finish_reason})"
                )
            context = GoalContext.model_validate_json(content)
        except GoalParserError:
            raise
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as error:
            raise GoalParserError("OpenRouter returned invalid goal context") from error

        if context.application_name is not None:
            context.application_name = context.application_name.strip() or None
        return context

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
