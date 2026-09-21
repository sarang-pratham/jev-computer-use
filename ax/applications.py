from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

import ApplicationServices
from AppKit import NSDate, NSRunLoop, NSWorkspace


@dataclass(frozen=True, slots=True)
class ApplicationIdentity:
    name: str
    pid: int
    bundle_id: str | None
    active: bool


class ApplicationActivationError(RuntimeError):
    pass


def frontmost_application_name() -> str | None:
    application = frontmost_application()
    if application is None:
        return None
    return application.name


def frontmost_application() -> ApplicationIdentity | None:
    application = NSWorkspace.sharedWorkspace().frontmostApplication()
    return _identity(application)


def running_application(name: str) -> ApplicationIdentity | None:
    return _identity(_find_running_application(name))


def activate_application(name: str, timeout: float = 5.0) -> ApplicationIdentity:
    requested = name.removesuffix(".app").strip()
    running = _find_running_application(requested)
    result = subprocess.run(
        ["open", "-a", requested],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or (
            "running application could not be activated"
            if running is not None
            else "application was not found"
        )
        raise ApplicationActivationError(
            f"Could not open application '{requested}': {detail}"
        )

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = frontmost_application()
        target = _identity(_find_running_application(requested))
        if (
            current
            and target
            and current.pid == target.pid
            and _has_accessible_window(target.pid)
        ):
            return current
        _run_main_run_loop(0.1)

    current = frontmost_application()
    target = _identity(_find_running_application(requested))
    raise ApplicationActivationError(
        f"Application '{requested}' did not become frontmost "
        f"(target={_format_identity(target)}; "
        f"frontmost={_format_identity(current)}; "
        f"ax_window={str(_has_accessible_window(target.pid) if target else False).lower()}; "
        f"controller={controller_identity()})"
    )


def controller_identity() -> str:
    return f"{os.path.basename(sys.executable)} (pid={os.getpid()})"


def _run_main_run_loop(seconds: float) -> None:
    NSRunLoop.currentRunLoop().runUntilDate_(
        NSDate.dateWithTimeIntervalSinceNow_(seconds)
    )


def _has_accessible_window(pid: int) -> bool:
    root = ApplicationServices.AXUIElementCreateApplication(pid)
    error, windows = ApplicationServices.AXUIElementCopyAttributeValue(
        root, "AXWindows", None
    )
    return error == ApplicationServices.kAXErrorSuccess and bool(windows)


def _find_running_application(name: str) -> Any | None:
    for application in NSWorkspace.sharedWorkspace().runningApplications():
        current = application.localizedName()
        if current and _same_name(current, name):
            return application
    return None


def _identity(application: Any | None) -> ApplicationIdentity | None:
    if application is None:
        return None
    return ApplicationIdentity(
        name=application.localizedName() or "Unknown application",
        pid=int(application.processIdentifier()),
        bundle_id=application.bundleIdentifier(),
        active=bool(application.isActive()),
    )


def _format_identity(application: ApplicationIdentity | None) -> str:
    if application is None:
        return "none"
    return (
        f"{application.name} pid={application.pid}"
        f" active={str(application.active).lower()}"
    )


def _same_name(left: str, right: str) -> bool:
    return left.removesuffix(".app").casefold() == right.removesuffix(".app").casefold()
