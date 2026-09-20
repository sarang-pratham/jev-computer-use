from __future__ import annotations

import unittest

from ax.constants import (
    AX_FOCUSED,
    AX_PRESS,
    AX_VALUE,
    ROLE_BUTTON,
    ROLE_CHECKBOX,
    ROLE_TEXT_FIELD,
)
from ax.executor import OperationExecutor
from ax.snapshot import AXElementSnapshot
from ax.operations.candidates import build_candidates
from ax.operations.models import JEVOperation


class FakeBackend:
    def __init__(self) -> None:
        self.actions: list[tuple[str, str]] = []
        self.attributes: list[tuple[str, str, object]] = []

    def perform_action(self, element_id: str, action: str) -> None:
        self.actions.append((element_id, action))

    def set_attribute(self, element_id: str, attribute: str, value: object) -> None:
        self.attributes.append((element_id, attribute, value))


class OperationBehaviourTests(unittest.TestCase):
    def test_button_candidate_is_executable(self) -> None:
        element = AXElementSnapshot(
            element_id="search",
            role=ROLE_BUTTON,
            title="Search",
            actions=frozenset({AX_PRESS}),
        )
        candidate = next(
            candidate
            for candidate in build_candidates((element,), include_global_operations=False)
            if candidate.operation == JEVOperation.CLICK
        )

        backend = FakeBackend()
        result = OperationExecutor(backend).execute(candidate)

        self.assertEqual(result.operation, JEVOperation.CLICK)
        self.assertEqual(backend.actions, [("search", AX_PRESS)])

    def test_text_candidate_writes_the_requested_value(self) -> None:
        element = AXElementSnapshot(
            element_id="query",
            role=ROLE_TEXT_FIELD,
            title="Search",
            settable_attributes=frozenset({AX_VALUE, AX_FOCUSED}),
        )
        candidate = next(
            candidate
            for candidate in build_candidates((element,), include_global_operations=False)
            if candidate.operation == JEVOperation.TYPE_TEXT
        )

        backend = FakeBackend()
        OperationExecutor(backend).execute(candidate, {"text": "macOS"})

        self.assertEqual(backend.attributes, [("query", AX_VALUE, "macOS")])

    def test_toggle_candidates_only_offer_the_needed_state_change(self) -> None:
        def candidates_for(value: bool):
            return build_candidates(
                (
                    AXElementSnapshot(
                        element_id="remember",
                        role=ROLE_CHECKBOX,
                        title="Remember me",
                        value=value,
                        actions=frozenset({AX_PRESS}),
                    ),
                ),
                include_global_operations=False,
            )

        unchecked = {candidate.operation for candidate in candidates_for(False)}
        checked = {candidate.operation for candidate in candidates_for(True)}

        self.assertIn(JEVOperation.CHECK, unchecked)
        self.assertNotIn(JEVOperation.UNCHECK, unchecked)
        self.assertIn(JEVOperation.UNCHECK, checked)
        self.assertNotIn(JEVOperation.CHECK, checked)

    def test_control_candidates_are_available_without_an_element(self) -> None:
        operations = {
            candidate.operation for candidate in build_candidates(())
        }

        self.assertEqual(
            operations,
            {JEVOperation.WAIT, JEVOperation.DONE, JEVOperation.BLOCKED},
        )


if __name__ == "__main__":
    unittest.main()
