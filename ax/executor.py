from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .backend import AXBackendError
from .constants import (
    AX_DECREMENT,
    AX_FOCUSED,
    AX_INCREMENT,
    AX_PRESS,
    AX_SCROLL_DOWN,
    AX_SCROLL_UP,
    AX_VALUE,
)
from .operations.candidates import ActionCandidate
from .operations.models import JEVOperation


class AXBackend(Protocol):
    def perform_action(self, element_id: str, action: str) -> None:
        ...

    def set_attribute(self, element_id: str, attribute: str, value: Any) -> None:
        ...


class ExecutionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    operation: JEVOperation
    element_id: str | None
    dispatch: str


class OperationExecutor:
    def __init__(self, backend: AXBackend) -> None:
        self._backend = backend

    def execute(
        self,
        candidate: ActionCandidate,
        arguments: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        arguments = arguments or {}
        operation = candidate.operation

        if operation in {
            JEVOperation.WAIT,
            JEVOperation.DONE,
            JEVOperation.BLOCKED,
        }:
            if candidate.element_id is not None:
                raise ExecutionError(f"{operation} must not have an AX target")
            return ExecutionResult(operation, None, operation.value)

        if candidate.element_id is None:
            raise ExecutionError(f"{operation} requires an AX target")

        element_id = candidate.element_id

        action_by_operation = {
            JEVOperation.CLICK: AX_PRESS,
            JEVOperation.SELECT_OPTION: AX_PRESS,
            JEVOperation.CHECK: AX_PRESS,
            JEVOperation.UNCHECK: AX_PRESS,
            JEVOperation.INCREMENT: AX_INCREMENT,
            JEVOperation.DECREMENT: AX_DECREMENT,
            JEVOperation.EXPAND: AX_PRESS,
            JEVOperation.COLLAPSE: AX_PRESS,
            JEVOperation.SCROLL_UP: AX_SCROLL_UP,
            JEVOperation.SCROLL_DOWN: AX_SCROLL_DOWN,
        }
        if operation in action_by_operation:
            try:
                self._backend.perform_action(element_id, action_by_operation[operation])
            except AXBackendError as error:
                raise ExecutionError(str(error)) from error
            return ExecutionResult(
                operation, element_id, action_by_operation[operation]
            )

        if operation == JEVOperation.TYPE_TEXT:
            text = arguments.get("text")
            if not isinstance(text, str):
                raise ExecutionError(
                    "TYPE_TEXT requires a string argument named 'text'"
                )
            try:
                self._backend.set_attribute(element_id, AX_VALUE, text)
            except AXBackendError as error:
                raise ExecutionError(str(error)) from error
            return ExecutionResult(operation, element_id, f"{AX_VALUE}=<redacted>")

        if operation == JEVOperation.FOCUS:
            try:
                self._backend.set_attribute(element_id, AX_FOCUSED, True)
            except AXBackendError as error:
                raise ExecutionError(str(error)) from error
            return ExecutionResult(operation, element_id, f"{AX_FOCUSED}=True")

        raise ExecutionError(f"No AX handler implemented for {operation}")
