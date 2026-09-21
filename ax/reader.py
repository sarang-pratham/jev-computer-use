from __future__ import annotations

import subprocess
from typing import Any

import ApplicationServices
from AppKit import NSWorkspace

from .applications import controller_identity as _controller_identity
from .backend import AXBackendError, PyObjCAXBackend
from .constants import (
    AX_CHILDREN,
    AX_DESCRIPTION,
    AX_ENABLED,
    AX_EXPANDED,
    AX_FOCUSED,
    AX_FOCUSED_WINDOW,
    AX_HIDDEN,
    AX_ROLE,
    AX_SELECTED,
    AX_SUBROLE,
    AX_TITLE,
    AX_VALUE,
    AX_WINDOWS,
)
from .snapshot import AXElementSnapshot, AXTreeSnapshot, Scalar

ACCESSIBILITY_SETTINGS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
)


class AXReaderError(RuntimeError):
    pass


class AXPermissionError(AXReaderError):
    pass


def open_accessibility_settings() -> bool:
    result = subprocess.run(
        ["open", ACCESSIBILITY_SETTINGS_URL],
        check=False,
    )
    return result.returncode == 0


def controller_identity() -> str:
    return _controller_identity()


class AXReader:
    def __init__(
        self,
        backend: PyObjCAXBackend | Any | None = None,
        max_depth: int = 8,
        max_elements: int = 250,
    ) -> None:
        self.backend = backend or PyObjCAXBackend()
        self.max_depth = max_depth
        self.max_elements = max_elements
        self._elements: list[AXElementSnapshot] = []

    def read_frontmost(self) -> AXTreeSnapshot:
        trusted = ApplicationServices.AXIsProcessTrustedWithOptions(
            {ApplicationServices.kAXTrustedCheckOptionPrompt: True}
        )
        if not trusted:
            raise AXPermissionError(
                "Accessibility permission is required in System Settings > Privacy & Security > Accessibility"
            )

        application = NSWorkspace.sharedWorkspace().frontmostApplication()
        if application is None:
            raise AXReaderError("Could not find the frontmost application")

        pid = int(application.processIdentifier())
        root = ApplicationServices.AXUIElementCreateApplication(pid)
        return self.read_root(
            root,
            pid=pid,
            bundle_id=application.bundleIdentifier(),
            application_name=application.localizedName(),
        )

    def read_root(
        self,
        root: Any,
        *,
        pid: int | None = None,
        bundle_id: str | None = None,
        application_name: str | None = None,
    ) -> AXTreeSnapshot:
        self.backend.clear()
        self._elements = []
        root_id = f"app:{pid}" if pid is not None else "app"
        self._read_element(root_id, root, (), 0)
        return AXTreeSnapshot(
            elements=tuple(self._elements),
            pid=pid,
            bundle_id=bundle_id,
            application_name=application_name,
        )

    def _read_element(
        self,
        element_id: str,
        element: Any,
        parent_path: tuple[str, ...],
        depth: int,
    ) -> None:
        if len(self._elements) >= self.max_elements:
            return

        self.backend.bind(element_id, element)
        role = self._string(element_id, AX_ROLE) or "AXUnknown"
        subrole = self._string(element_id, AX_SUBROLE)
        title = self._string(element_id, AX_TITLE)
        description = self._string(element_id, AX_DESCRIPTION)
        value = self._scalar(element_id, AX_VALUE)
        redacted = subrole == "AXSecureTextField"
        if redacted:
            value = None

        snapshot = AXElementSnapshot(
            element_id=element_id,
            role=role,
            subrole=subrole,
            title=title,
            description=description,
            value=value,
            enabled=self._boolean(element_id, AX_ENABLED, True),
            hidden=self._boolean(element_id, AX_HIDDEN, False),
            focused=self._boolean(element_id, AX_FOCUSED, False),
            selected=self._optional_boolean(element_id, AX_SELECTED),
            expanded=self._optional_boolean(element_id, AX_EXPANDED),
            actions=frozenset(self._actions(element_id)),
            settable_attributes=frozenset(
                attribute
                for attribute in (AX_VALUE, AX_FOCUSED)
                if self._settable(element_id, attribute)
            ),
            parent_path=parent_path,
            redacted=redacted,
        )
        self._elements.append(snapshot)

        if depth >= self.max_depth:
            return

        if role == "AXApplication":
            windows = self._items(self._attribute(element_id, AX_WINDOWS))
            if windows:
                child_groups = [windows]
            else:
                focused_window = self._attribute(element_id, AX_FOCUSED_WINDOW)
                if focused_window is not None:
                    child_groups = [[focused_window]]
                else:
                    child_groups = [
                        self._items(self._attribute(element_id, AX_CHILDREN))
                    ]
        else:
            child_groups = [self._items(self._attribute(element_id, AX_CHILDREN))]

        next_path = parent_path + (snapshot.label,)
        seen_children: set[int] = set()
        child_index = 0
        for children in child_groups:
            for child in children:
                if len(self._elements) >= self.max_elements:
                    return
                child_key = id(child)
                if child_key in seen_children:
                    continue
                seen_children.add(child_key)
                self._read_element(
                    f"{element_id}/{child_index}",
                    child,
                    next_path,
                    depth + 1,
                )
                child_index += 1

    @staticmethod
    def _items(value: Any) -> tuple[Any, ...]:
        if value is None or isinstance(value, (str, bytes)):
            return ()
        try:
            return tuple(value)
        except TypeError:
            return ()

    def _attribute(self, element_id: str, attribute: str) -> Any:
        try:
            return self.backend.copy_attribute(element_id, attribute)
        except AXBackendError:
            return None

    def _string(self, element_id: str, attribute: str) -> str | None:
        value = self._attribute(element_id, attribute)
        return value if isinstance(value, str) and value else None

    def _scalar(self, element_id: str, attribute: str) -> Scalar:
        value = self._attribute(element_id, attribute)
        return value if isinstance(value, (str, int, float, bool)) else None

    def _boolean(self, element_id: str, attribute: str, default: bool) -> bool:
        value = self._attribute(element_id, attribute)
        return value if isinstance(value, bool) else default

    def _optional_boolean(self, element_id: str, attribute: str) -> bool | None:
        value = self._attribute(element_id, attribute)
        return value if isinstance(value, bool) else None

    def _actions(self, element_id: str) -> tuple[str, ...]:
        try:
            return self.backend.copy_actions(element_id)
        except AXBackendError:
            return ()

    def _settable(self, element_id: str, attribute: str) -> bool:
        try:
            return self.backend.is_attribute_settable(element_id, attribute)
        except AXBackendError:
            return False
