from __future__ import annotations

from typing import Any

import ApplicationServices


class AXBackendError(RuntimeError):
    pass


class PyObjCAXBackend:
    def __init__(self) -> None:
        self._elements: dict[str, Any] = {}

    def bind(self, element_id: str, element: Any) -> None:
        self._elements[element_id] = element

    def element(self, element_id: str) -> Any:
        try:
            return self._elements[element_id]
        except KeyError as exc:
            raise AXBackendError(f"Unknown AX element id: {element_id}") from exc

    def perform_action(self, element_id: str, action: str) -> None:
        error = ApplicationServices.AXUIElementPerformAction(
            self.element(element_id), action
        )
        self._check(error, f"perform {action} on {element_id}")

    def set_attribute(self, element_id: str, attribute: str, value: Any) -> None:
        error = ApplicationServices.AXUIElementSetAttributeValue(
            self.element(element_id), attribute, value
        )
        self._check(error, f"set {attribute} on {element_id}")

    def copy_attribute(self, element_id: str, attribute: str) -> Any:
        error, value = ApplicationServices.AXUIElementCopyAttributeValue(
            self.element(element_id), attribute, None
        )
        self._check(error, f"read {attribute} from {element_id}")
        return value

    def copy_actions(self, element_id: str) -> tuple[str, ...]:
        error, actions = ApplicationServices.AXUIElementCopyActionNames(
            self.element(element_id), None
        )
        self._check(error, f"read actions from {element_id}")
        return tuple(actions or ())

    def is_attribute_settable(self, element_id: str, attribute: str) -> bool:
        error, settable = ApplicationServices.AXUIElementIsAttributeSettable(
            self.element(element_id), attribute, None
        )
        self._check(error, f"check whether {attribute} is settable on {element_id}")
        return bool(settable)

    @staticmethod
    def _check(error: int, operation: str) -> None:
        if error != ApplicationServices.kAXErrorSuccess:
            raise AXBackendError(
                f"Accessibility error {error} while trying to {operation}"
            )
