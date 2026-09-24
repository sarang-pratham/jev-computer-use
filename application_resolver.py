from __future__ import annotations

from dataclasses import dataclass

from goal_parser import GoalContext
from settings import Settings


class ApplicationResolutionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ApplicationResolution:
    name: str
    source: str
    capability: str | None = None


APPLICATION_ALIASES = {
    "ical": "Calendar",
    "chrome": "Google Chrome",
}


def resolve_application(
    context: GoalContext,
    settings: Settings | None = None,
) -> ApplicationResolution | None:
    if context.application_name:
        requested = context.application_name.strip()
        name = APPLICATION_ALIASES.get(requested.casefold(), requested)
        source = "alias" if name != requested else "explicit"
        return ApplicationResolution(name=name, source=source)

    if context.capability:
        settings = settings or Settings()
        defaults = {
            "web_browser": settings.default_browser,
            "camera": settings.default_camera,
            "calendar": settings.default_calendar,
        }
        name = defaults.get(context.capability)
        if name:
            return ApplicationResolution(
                name=name,
                source="configured default",
                capability=context.capability,
            )
        raise ApplicationResolutionError(
            f"No default application is configured for {context.capability}"
        )

    if context.application_required:
        raise ApplicationResolutionError(
            "The goal requires an application, but no application or capability was identified"
        )
    return None
