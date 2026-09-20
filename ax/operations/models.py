from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class JEVOperation(StrEnum):
    CLICK = "CLICK"
    TYPE_TEXT = "TYPE_TEXT"
    SELECT_OPTION = "SELECT_OPTION"
    CHECK = "CHECK"
    UNCHECK = "UNCHECK"
    INCREMENT = "INCREMENT"
    DECREMENT = "DECREMENT"
    EXPAND = "EXPAND"
    COLLAPSE = "COLLAPSE"
    FOCUS = "FOCUS"
    SCROLL_UP = "SCROLL_UP"
    SCROLL_DOWN = "SCROLL_DOWN"
    WAIT = "WAIT"
    DONE = "DONE"
    BLOCKED = "BLOCKED"

    ACTIVATE_APP = "ACTIVATE_APP"
    SWITCH_WINDOW = "SWITCH_WINDOW"
    CLOSE_WINDOW = "CLOSE_WINDOW"
    MINIMIZE_WINDOW = "MINIMIZE_WINDOW"
    ZOOM_WINDOW = "ZOOM_WINDOW"
    OPEN_SEARCH = "OPEN_SEARCH"
    PRESS_ENTER = "PRESS_ENTER"
    PRESS_ESCAPE = "PRESS_ESCAPE"
    PRESS_TAB = "PRESS_TAB"


class TargetKind(StrEnum):
    NONE = "none"
    ELEMENT = "element"
    TEXT_FIELD = "text_field"
    OPTION = "option"
    TOGGLE = "toggle"
    VALUE_CONTROL = "value_control"
    SCROLL_CONTAINER = "scroll_container"
    WINDOW = "window"
    APPLICATION = "application"


class RiskLevel(StrEnum):
    SAFE = "safe"
    STATE_CHANGE = "state_change"
    DESTRUCTIVE = "destructive"


class ImplementationStatus(StrEnum):
    AX = "ax"
    SYSTEM_ADAPTER = "system_adapter"
    PLANNED = "planned"


@dataclass(frozen=True, slots=True)
class OperationSpec:
    operation: JEVOperation
    target_kind: TargetKind
    handler: str
    description: str
    risk: RiskLevel = RiskLevel.SAFE
    arguments: tuple[str, ...] = ()
    status: ImplementationStatus = ImplementationStatus.AX
    global_operation: bool = False
