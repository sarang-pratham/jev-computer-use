from __future__ import annotations

import unittest

from ax.constants import (
    AX_CHILDREN,
    AX_FOCUSED,
    AX_FOCUSED_WINDOW,
    AX_PRESS,
    AX_ROLE,
    AX_SUBROLE,
    AX_TITLE,
    AX_VALUE,
    AX_WINDOWS,
    ROLE_BUTTON,
    ROLE_CHECKBOX,
    ROLE_TEXT_FIELD,
)
from ax.backend import AXBackendError
from ax.executor import ExecutionError, OperationExecutor
from ax.reader import AXReader
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


class FailingBackend(FakeBackend):
    def perform_action(self, element_id: str, action: str) -> None:
        raise AXBackendError("action failed")


class FakeReaderBackend:
    def __init__(self) -> None:
        self.bound: dict[str, str] = {}
        self.attributes = {
            "root": {
                AX_ROLE: "AXApplication",
                AX_TITLE: "Demo",
                AX_CHILDREN: [],
                AX_WINDOWS: [],
                AX_FOCUSED_WINDOW: "window",
            },
            "window": {
                AX_ROLE: "AXWindow",
                AX_TITLE: "Demo window",
                AX_CHILDREN: ["button", "secret"],
            },
            "button": {AX_ROLE: ROLE_BUTTON, AX_TITLE: "Search"},
            "secret": {
                AX_ROLE: ROLE_TEXT_FIELD,
                AX_SUBROLE: "AXSecureTextField",
                AX_TITLE: "Password",
                AX_VALUE: "hidden",
            },
        }
        self.actions = {"button": (AX_PRESS,)}

    def clear(self) -> None:
        self.bound.clear()

    def bind(self, element_id: str, element: str) -> None:
        self.bound[element_id] = element

    def copy_attribute(self, element_id: str, attribute: str):
        element = self.attributes[self.bound[element_id]]
        if attribute not in element:
            raise AXBackendError(attribute)
        return element[attribute]

    def copy_actions(self, element_id: str) -> tuple[str, ...]:
        return self.actions.get(self.bound[element_id], ())

    def is_attribute_settable(self, element_id: str, attribute: str) -> bool:
        return self.bound[element_id] == "secret" and attribute == AX_VALUE


class OperationBehaviourTests(unittest.TestCase):
    def test_reader_builds_snapshot_and_redacts_secure_values(self) -> None:
        backend = FakeReaderBackend()
        snapshot = AXReader(backend=backend).read_root(
            "root",
            pid=7,
            application_name="Demo",
        )

        button = snapshot.by_id("app:7/0/0")
        secret = snapshot.by_id("app:7/0/1")

        self.assertEqual(button.label, "Search")
        self.assertIn("app:7/0", backend.bound)
        self.assertIn("app:7/0/0", backend.bound)
        self.assertTrue(secret.redacted)
        self.assertIsNone(secret.value)

    def test_button_candidate_is_executable(self) -> None:
        element = AXElementSnapshot(
            element_id="search",
            role=ROLE_BUTTON,
            title="Search",
            actions=frozenset({AX_PRESS}),
        )
        candidate = next(
            candidate
            for candidate in build_candidates(
                (element,), include_global_operations=False
            )
            if candidate.operation == JEVOperation.CLICK
        )

        backend = FakeBackend()
        result = OperationExecutor(backend).execute(candidate)

        self.assertEqual(result.operation, JEVOperation.CLICK)
        self.assertEqual(backend.actions, [("search", AX_PRESS)])

    def test_backend_action_failure_becomes_execution_error(self) -> None:
        element = AXElementSnapshot(
            element_id="search",
            role=ROLE_BUTTON,
            title="Search",
            actions=frozenset({AX_PRESS}),
        )
        candidate = next(
            candidate
            for candidate in build_candidates(
                (element,), include_global_operations=False
            )
            if candidate.operation == JEVOperation.CLICK
        )

        with self.assertRaises(ExecutionError):
            OperationExecutor(FailingBackend()).execute(candidate)

    def test_text_candidate_writes_the_requested_value(self) -> None:
        element = AXElementSnapshot(
            element_id="query",
            role=ROLE_TEXT_FIELD,
            title="Search",
            settable_attributes=frozenset({AX_VALUE, AX_FOCUSED}),
        )
        candidate = next(
            candidate
            for candidate in build_candidates(
                (element,), include_global_operations=False
            )
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
        operations = {candidate.operation for candidate in build_candidates(())}

        self.assertEqual(
            operations,
            {JEVOperation.WAIT, JEVOperation.DONE, JEVOperation.BLOCKED},
        )


if __name__ == "__main__":
    unittest.main()
