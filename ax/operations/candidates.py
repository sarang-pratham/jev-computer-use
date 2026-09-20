from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..snapshot import AXElementSnapshot
from .models import JEVOperation, TargetKind
from .registry import operation_spec, supported_operations


@dataclass(frozen=True, slots=True)
class ActionCandidate:
    operation: JEVOperation
    element_id: str | None
    target_kind: TargetKind
    label: str | None = None
    role: str | None = None
    value: str | int | float | bool | None = None
    focused: bool = False
    state: str | None = None
    parent_path: tuple[str, ...] = ()
    redacted: bool = False

    def to_jev(self, index: int) -> dict[str, Any]:
        target: dict[str, Any] | None = None
        if self.element_id is not None:
            target = {
                "id": self.element_id,
                "label": self.label,
                "role": self.role,
                "value": None if self.redacted else self.value,
                "focused": self.focused,
                "state": self.state,
                "context": list(self.parent_path),
            }

        spec = operation_spec(self.operation)
        return {
            "index": index,
            "operation": self.operation.value,
            "target": target,
            "arguments": list(spec.arguments),
            "risk": spec.risk.value,
        }


def _state(element: AXElementSnapshot) -> str | None:
    if element.role in {"AXCheckBox", "AXRadioButton"}:
        if isinstance(element.value, bool):
            return "checked" if element.value else "unchecked"
        if element.selected is not None:
            return "checked" if element.selected else "unchecked"
    if element.expanded is not None:
        return "expanded" if element.expanded else "collapsed"
    return None


def build_candidates(
    elements: Iterable[AXElementSnapshot],
    *,
    include_global_operations: bool = True,
) -> tuple[ActionCandidate, ...]:
    candidates: list[ActionCandidate] = []
    for element in elements:
        for operation in supported_operations(element):
            spec = operation_spec(operation)
            candidates.append(
                ActionCandidate(
                    operation=operation,
                    element_id=element.element_id,
                    target_kind=spec.target_kind,
                    label=element.label,
                    role=element.role,
                    value=element.value,
                    focused=element.focused,
                    state=_state(element),
                    parent_path=element.parent_path,
                    redacted=element.redacted,
                )
            )

    if include_global_operations:
        for operation in (JEVOperation.WAIT, JEVOperation.DONE, JEVOperation.BLOCKED):
            spec = operation_spec(operation)
            candidates.append(
                ActionCandidate(
                    operation=operation,
                    element_id=None,
                    target_kind=spec.target_kind,
                )
            )

    return tuple(candidates)


def candidates_to_jev(candidates: Iterable[ActionCandidate]) -> list[dict[str, Any]]:
    return [candidate.to_jev(index) for index, candidate in enumerate(candidates)]
