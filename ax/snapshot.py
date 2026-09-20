from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

Scalar: TypeAlias = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class AXElementSnapshot:
    element_id: str
    role: str
    subrole: str | None = None
    title: str | None = None
    description: str | None = None
    value: Scalar = None
    enabled: bool = True
    hidden: bool = False
    focused: bool = False
    selected: bool | None = None
    expanded: bool | None = None
    actions: frozenset[str] = field(default_factory=frozenset)
    settable_attributes: frozenset[str] = field(default_factory=frozenset)
    parent_path: tuple[str, ...] = ()
    redacted: bool = False

    @property
    def label(self) -> str:
        for candidate in (self.title, self.description):
            if candidate:
                return candidate
        if isinstance(self.value, str) and self.value:
            return self.value
        return self.role

    def supports_action(self, action: str) -> bool:
        return action in self.actions

    def can_set(self, attribute: str) -> bool:
        return attribute in self.settable_attributes


@dataclass(frozen=True, slots=True)
class AXTreeSnapshot:
    elements: tuple[AXElementSnapshot, ...]
    pid: int | None = None
    bundle_id: str | None = None
    application_name: str | None = None
    window_title: str | None = None

    def by_id(self, element_id: str) -> AXElementSnapshot:
        for element in self.elements:
            if element.element_id == element_id:
                return element
        raise KeyError(f"Unknown AX element id: {element_id}")
