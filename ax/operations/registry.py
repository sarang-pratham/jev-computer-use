from __future__ import annotations

from typing import Iterable

from ..constants import (
    AX_DECREMENT,
    AX_FOCUSED,
    AX_INCREMENT,
    AX_PRESS,
    AX_SCROLL_DOWN,
    AX_SCROLL_UP,
    AX_VALUE,
    ROLE_CHECKBOX,
    ROLE_DISCLOSURE_TRIANGLE,
    ROLE_MENU_ITEM,
    SCROLLABLE_ROLES,
    TEXT_ROLES,
    TOGGLE_ROLES,
)
from ..snapshot import AXElementSnapshot
from .models import (
    JEVOperation,
    OperationSpec,
    RiskLevel,
    TargetKind,
)


_SPECS: dict[JEVOperation, OperationSpec] = {
    JEVOperation.CLICK: OperationSpec(
        JEVOperation.CLICK,
        TargetKind.ELEMENT,
        "press",
        "Press an accessible control.",
    ),
    JEVOperation.TYPE_TEXT: OperationSpec(
        JEVOperation.TYPE_TEXT,
        TargetKind.TEXT_FIELD,
        "set_value",
        "Replace the value of an editable text control.",
        arguments=("text",),
        risk=RiskLevel.STATE_CHANGE,
    ),
    JEVOperation.SELECT_OPTION: OperationSpec(
        JEVOperation.SELECT_OPTION,
        TargetKind.OPTION,
        "press",
        "Choose an exposed menu/list option.",
        risk=RiskLevel.STATE_CHANGE,
    ),
    JEVOperation.CHECK: OperationSpec(
        JEVOperation.CHECK,
        TargetKind.TOGGLE,
        "press",
        "Set an unchecked toggle to checked.",
        risk=RiskLevel.STATE_CHANGE,
    ),
    JEVOperation.UNCHECK: OperationSpec(
        JEVOperation.UNCHECK,
        TargetKind.TOGGLE,
        "press",
        "Set a checked toggle to unchecked.",
        risk=RiskLevel.STATE_CHANGE,
    ),
    JEVOperation.INCREMENT: OperationSpec(
        JEVOperation.INCREMENT,
        TargetKind.VALUE_CONTROL,
        "increment",
        "Increase a slider or stepper value.",
        risk=RiskLevel.STATE_CHANGE,
    ),
    JEVOperation.DECREMENT: OperationSpec(
        JEVOperation.DECREMENT,
        TargetKind.VALUE_CONTROL,
        "decrement",
        "Decrease a slider or stepper value.",
        risk=RiskLevel.STATE_CHANGE,
    ),
    JEVOperation.EXPAND: OperationSpec(
        JEVOperation.EXPAND,
        TargetKind.ELEMENT,
        "press",
        "Expand a disclosure control.",
        risk=RiskLevel.STATE_CHANGE,
    ),
    JEVOperation.COLLAPSE: OperationSpec(
        JEVOperation.COLLAPSE,
        TargetKind.ELEMENT,
        "press",
        "Collapse a disclosure control.",
        risk=RiskLevel.STATE_CHANGE,
    ),
    JEVOperation.FOCUS: OperationSpec(
        JEVOperation.FOCUS,
        TargetKind.ELEMENT,
        "focus",
        "Move keyboard focus to an element.",
    ),
    JEVOperation.SCROLL_UP: OperationSpec(
        JEVOperation.SCROLL_UP,
        TargetKind.SCROLL_CONTAINER,
        "scroll_up",
        "Scroll an accessible container upward.",
    ),
    JEVOperation.SCROLL_DOWN: OperationSpec(
        JEVOperation.SCROLL_DOWN,
        TargetKind.SCROLL_CONTAINER,
        "scroll_down",
        "Scroll an accessible container downward.",
    ),
    JEVOperation.WAIT: OperationSpec(
        JEVOperation.WAIT,
        TargetKind.NONE,
        "wait",
        "Wait for the UI to settle.",
        global_operation=True,
    ),
    JEVOperation.DONE: OperationSpec(
        JEVOperation.DONE,
        TargetKind.NONE,
        "done",
        "Declare that the goal is complete.",
        global_operation=True,
    ),
    JEVOperation.BLOCKED: OperationSpec(
        JEVOperation.BLOCKED,
        TargetKind.NONE,
        "blocked",
        "Declare that the current goal cannot proceed.",
        global_operation=True,
    ),
}


def operation_specs() -> tuple[OperationSpec, ...]:
    return tuple(_SPECS.values())


def operation_spec(operation: JEVOperation) -> OperationSpec:
    try:
        return _SPECS[operation]
    except KeyError as exc:
        raise ValueError(
            f"Operation is not available in the AX adapter: {operation}"
        ) from exc


def _checked(element: AXElementSnapshot) -> bool | None:
    if isinstance(element.value, bool):
        return element.value
    if isinstance(element.value, (int, float)):
        return element.value != 0
    if element.selected is not None:
        return element.selected
    return None


def supported_operations(element: AXElementSnapshot) -> tuple[JEVOperation, ...]:
    if element.hidden or not element.enabled:
        return ()

    supported: list[JEVOperation] = []

    if element.supports_action(AX_PRESS):
        supported.append(JEVOperation.CLICK)

    if element.role in TEXT_ROLES and element.can_set(AX_VALUE):
        supported.append(JEVOperation.TYPE_TEXT)

    if element.role == ROLE_MENU_ITEM and element.supports_action(AX_PRESS):
        supported.append(JEVOperation.SELECT_OPTION)

    if element.role in TOGGLE_ROLES and element.supports_action(AX_PRESS):
        state = _checked(element)
        if state is False:
            supported.append(JEVOperation.CHECK)
        elif state is True and element.role == ROLE_CHECKBOX:
            supported.append(JEVOperation.UNCHECK)

    if element.supports_action(AX_INCREMENT):
        supported.append(JEVOperation.INCREMENT)
    if element.supports_action(AX_DECREMENT):
        supported.append(JEVOperation.DECREMENT)

    if (
        element.role == ROLE_DISCLOSURE_TRIANGLE
        and element.supports_action(AX_PRESS)
        and element.expanded is not None
    ):
        supported.append(
            JEVOperation.COLLAPSE if element.expanded else JEVOperation.EXPAND
        )

    if element.can_set(AX_FOCUSED) or element.role in TEXT_ROLES:
        supported.append(JEVOperation.FOCUS)

    if element.role in SCROLLABLE_ROLES or element.supports_action(AX_SCROLL_UP):
        if element.supports_action(AX_SCROLL_UP):
            supported.append(JEVOperation.SCROLL_UP)
        if element.supports_action(AX_SCROLL_DOWN):
            supported.append(JEVOperation.SCROLL_DOWN)

    return tuple(dict.fromkeys(supported))


def supported_operations_for_all(
    elements: Iterable[AXElementSnapshot],
) -> dict[str, tuple[JEVOperation, ...]]:
    return {element.element_id: supported_operations(element) for element in elements}
