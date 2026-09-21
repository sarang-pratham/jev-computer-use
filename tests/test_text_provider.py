from __future__ import annotations

import unittest

from ax.operations.candidates import ActionCandidate
from ax.operations.models import JEVOperation, TargetKind
from settings import Settings
from text_provider import OpenRouterTextProvider


class FakeResponse:
    status_code = 200

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"text":"weather in Pune"}',
                    }
                }
            ]
        }


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def post(self, url, json, headers):
        self.calls.append((url, json, headers))
        return FakeResponse()


class TextProviderTests(unittest.TestCase):
    def test_openrouter_provider_returns_text_from_structured_response(self) -> None:
        client = FakeClient()
        provider = OpenRouterTextProvider(
            Settings(
                typesafe_api_key="test",
                openrouter_api_key="openrouter-test",
            ),
            client=client,
        )
        candidate = ActionCandidate(
            operation=JEVOperation.TYPE_TEXT,
            element_id="search",
            target_kind=TargetKind.TEXT_FIELD,
            label="Search",
            role="AXTextField",
        )

        text = provider("Search for weather in Pune", candidate, [])

        self.assertEqual(text, "weather in Pune")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][1]["model"], "openrouter/free")
        self.assertEqual(
            client.calls[0][1]["response_format"]["type"],
            "json_schema",
        )


if __name__ == "__main__":
    unittest.main()
