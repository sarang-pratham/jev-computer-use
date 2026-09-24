from __future__ import annotations

import unittest

from application_resolver import resolve_application
from goal_parser import GoalContext
from settings import Settings


class ApplicationResolverTests(unittest.TestCase):
    def test_explicit_application_takes_precedence(self) -> None:
        resolution = resolve_application(
            GoalContext(
                application_name="Safari",
                capability="web_browser",
                application_required=True,
            ),
            Settings(typesafe_api_key="test"),
        )

        self.assertEqual(resolution.name, "Safari")
        self.assertEqual(resolution.source, "explicit")

    def test_alias_resolves_to_application_name(self) -> None:
        resolution = resolve_application(
            GoalContext(application_name="iCal"),
            Settings(typesafe_api_key="test"),
        )

        self.assertEqual(resolution.name, "Calendar")
        self.assertEqual(resolution.source, "alias")

    def test_capability_uses_configured_default(self) -> None:
        resolution = resolve_application(
            GoalContext(capability="web_browser", application_required=True),
            Settings(typesafe_api_key="test", default_browser="Google Chrome"),
        )

        self.assertEqual(resolution.name, "Google Chrome")
        self.assertEqual(resolution.source, "configured default")


if __name__ == "__main__":
    unittest.main()
