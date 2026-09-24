from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from application_resolver import (
    ApplicationResolutionError,
    resolve_application,
)
from ax.executor import ExecutionError, OperationExecutor
from ax.applications import (
    ApplicationActivationError,
    ApplicationIdentity,
    activate_application,
    controller_identity,
    frontmost_application,
    running_application,
)
from ax.operations.candidates import ActionCandidate, build_candidates
from ax.operations.models import JEVOperation
from ax.reader import AXPermissionError, AXReader
from ax.snapshot import AXTreeSnapshot
from goal_parser import GoalContext, GoalParserError, OpenRouterGoalParser
from jev import JEVClient, JEVDecision
from text_provider import OpenRouterTextProvider, TextProviderError


class AgentStatus(StrEnum):
    IDLE = "idle"
    OBSERVING = "observing"
    READY = "ready"
    DECIDING = "deciding"
    VALIDATING = "validating"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    WAITING_PERMISSION = "waiting_permission"
    DONE = "done"
    BLOCKED = "blocked"


@dataclass(slots=True)
class AgentState:
    goal: str
    status: AgentStatus = AgentStatus.IDLE
    snapshot: AXTreeSnapshot | None = None
    candidates: tuple[ActionCandidate, ...] = ()
    fingerprint: str | None = None
    decision: JEVDecision | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    step_count: int = 0
    last_error: str | None = None


class AgentError(RuntimeError):
    pass


def snapshot_fingerprint(snapshot: AXTreeSnapshot) -> str:
    state = [
        {
            "id": element.element_id,
            "role": element.role,
            "subrole": element.subrole,
            "label": element.label,
            "value": None if element.redacted else element.value,
            "enabled": element.enabled,
            "hidden": element.hidden,
            "focused": element.focused,
            "selected": element.selected,
            "expanded": element.expanded,
            "actions": sorted(element.actions),
            "settable": sorted(element.settable_attributes),
            "context": element.parent_path,
        }
        for element in snapshot.elements
    ]
    return hashlib.sha256(
        json.dumps(
            {
                "application": snapshot.application_name,
                "bundle_id": snapshot.bundle_id,
                "pid": snapshot.pid,
                "elements": state,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


class ComputerUseAgent:
    def __init__(
        self,
        goal: str,
        *,
        reader: AXReader | Any | None = None,
        decision_client: JEVClient | Any | None = None,
        executor: OperationExecutor | Any | None = None,
        text_provider: Callable[[str, ActionCandidate, list[dict[str, Any]]], str]
        | None = None,
        goal_parser: Callable[[str], GoalContext] | None = None,
        event_handler: Callable[[str], None] | None = None,
        max_steps: int = 20,
        wait_seconds: float = 0.2,
    ) -> None:
        goal = goal.strip()
        if not goal:
            raise ValueError("Supply a goal")
        self.reader = reader or AXReader()
        self.decision_client = decision_client or JEVClient()
        self.executor = executor or OperationExecutor(self.reader.backend)
        self.text_provider = text_provider
        self._default_text_provider: OpenRouterTextProvider | None = None
        self.goal_parser = goal_parser
        self._default_goal_parser: OpenRouterGoalParser | None = None
        self._goal_context_resolved = False
        self.event_handler = event_handler
        self.max_steps = max_steps
        self.wait_seconds = wait_seconds
        self.target_application: str | None = None
        self.target_application_pid: int | None = None
        self.state = AgentState(goal=goal)

    def tick(self) -> dict[str, Any]:
        if self.state.status in {AgentStatus.DONE, AgentStatus.BLOCKED}:
            return self.snapshot()
        if self.state.step_count >= self.max_steps:
            return self._block(f"Reached the {self.max_steps}-step limit")

        if not self._resolve_goal_context():
            return self.snapshot()
        self._observe()
        if self.state.status == AgentStatus.BLOCKED:
            return self.snapshot()
        self._event("deciding: asking JEV to choose the next action")
        self.state.status = AgentStatus.DECIDING
        decision = self.decision_client.choose(
            self.state.goal,
            self.state.snapshot,
            self.state.candidates,
            self.state.history,
        )
        self.state.decision = decision
        target = decision.candidate.label or decision.candidate.element_id or "none"
        probabilities = sorted(
            decision.operation_probabilities.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:3]
        probability_summary = ", ".join(
            f"{operation}={probability:.2f}" for operation, probability in probabilities
        )
        self._event(
            f"JEV selected {decision.operation.value} target={target}"
            f" confidence={decision.confidence:.2f}"
            f" probabilities=[{probability_summary}]"
        )

        if decision.operation == JEVOperation.DONE:
            self.state.status = AgentStatus.DONE
            self.state.decision = None
            self._event("goal complete")
            return self.snapshot()
        if decision.operation == JEVOperation.BLOCKED:
            return self._block(
                "JEV selected BLOCKED because no actionable operation was chosen"
            )

        self.state.status = AgentStatus.VALIDATING
        self._event("validating the selected target against a fresh observation")
        current = self.reader.read_frontmost()
        if self.target_application and not self._is_target_snapshot(current):
            self._event(
                f"target application is no longer frontmost; reactivating "
                f"{self.target_application}"
            )
            if not self._activate_target_application():
                return self.snapshot()
            current = self.reader.read_frontmost()
        current_candidates = build_candidates(current.elements)
        if snapshot_fingerprint(current) != self.state.fingerprint:
            self._set_observation(current, current_candidates)
            self.state.decision = None
            self.state.last_error = "Observation changed before execution"
            self._event("observation changed before execution; replanning")
            return self.snapshot()

        candidate = self._matching_candidate(decision.candidate, current_candidates)
        if candidate is None:
            return self._block("JEV selected a target that is no longer available")

        arguments = dict(decision.arguments)
        if decision.operation == JEVOperation.TYPE_TEXT and "text" not in arguments:
            self._event("generating text with OpenRouter")
            if self.text_provider is None:
                if self._default_text_provider is None:
                    self._default_text_provider = OpenRouterTextProvider()
                provider = self._default_text_provider
            else:
                provider = self.text_provider
            try:
                arguments["text"] = provider(
                    self.state.goal,
                    candidate,
                    self.state.history,
                )
            except TextProviderError as error:
                return self._block(str(error))

        self.state.status = AgentStatus.EXECUTING
        self.state.decision = None
        target = candidate.label or candidate.element_id or "none"
        self._event(f"executing {decision.operation.value} on {target}")
        try:
            result = self.executor.execute(candidate, arguments)
        except ExecutionError as error:
            return self._block(str(error))

        if decision.operation == JEVOperation.WAIT:
            time.sleep(self.wait_seconds)

        self.state.status = AgentStatus.VERIFYING
        self._event("verifying the result")
        after = self.reader.read_frontmost()
        after_candidates = build_candidates(after.elements)
        after_fingerprint = snapshot_fingerprint(after)
        changed = after_fingerprint != self.state.fingerprint
        self.state.history.append(
            {
                "step": self.state.step_count + 1,
                "operation": decision.operation.value,
                "target": candidate.element_id,
                "label": candidate.label,
                "pre_fingerprint": self.state.fingerprint,
                "post_fingerprint": after_fingerprint,
                "changed": changed,
                "dispatch": result.dispatch,
            }
        )
        self.state.step_count += 1
        self._set_observation(after, after_candidates)
        self._event(f"step {self.state.step_count} complete; changed={changed}")
        return self.snapshot()

    def run(self):
        while self.state.status not in {AgentStatus.DONE, AgentStatus.BLOCKED}:
            yield self.tick()

    def snapshot(self) -> dict[str, Any]:
        current = self.state.snapshot
        return {
            "goal": self.state.goal,
            "status": self.state.status.value,
            "application": {
                "name": current.application_name if current else None,
                "bundle_id": current.bundle_id if current else None,
                "pid": current.pid if current else None,
            },
            "elements": [
                {
                    "id": element.element_id,
                    "label": element.label,
                    "role": element.role,
                    "value": None if element.redacted else element.value,
                }
                for element in current.elements
            ]
            if current
            else [],
            "candidates": [
                candidate.to_jev(index)
                for index, candidate in enumerate(self.state.candidates)
            ],
            "history": self.state.history[-10:],
            "step_count": self.state.step_count,
            "error": self.state.last_error,
        }

    def _resolve_goal_context(self) -> bool:
        if self._goal_context_resolved:
            return True
        self._event("interpreting goal to identify the target application")
        if self.goal_parser is None:
            if self._default_goal_parser is None:
                self._default_goal_parser = OpenRouterGoalParser()
            parser = self._default_goal_parser
        else:
            parser = self.goal_parser
        try:
            context = parser(self.state.goal)
        except GoalParserError as error:
            self._block(str(error))
            return False
        self._event(
            f"goal parser result: application={context.application_name or 'none'}"
            f" capability={context.capability or 'none'}"
            f" required={context.application_required}"
        )
        try:
            resolution = resolve_application(context)
        except ApplicationResolutionError as error:
            self._block(str(error))
            return False
        self.target_application = resolution.name if resolution else None
        self._goal_context_resolved = True
        if resolution:
            self._event(
                f"application resolved: {resolution.name}"
                f" (source={resolution.source})"
            )
        else:
            self._event("no target application identified; using the frontmost app")
        return True

    def _observe(self) -> None:
        self.state.status = AgentStatus.OBSERVING
        if not self._activate_target_application():
            return
        try:
            snapshot = self.reader.read_frontmost()
        except AXPermissionError:
            self.state.status = AgentStatus.WAITING_PERMISSION
            self._event("waiting for Accessibility permission")
            raise
        self._set_observation(snapshot, build_candidates(snapshot.elements))
        self._event(
            f"observed {snapshot.application_name or 'unknown application'}"
            f" (pid={snapshot.pid}); elements={len(snapshot.elements)}"
            f" candidates={len(self.state.candidates)}"
        )
        self._event(
            f"available actions: {self._candidate_summary(self.state.candidates)}"
        )

    def _activate_target_application(self) -> bool:
        if self.target_application is None:
            return True
        current = frontmost_application()
        target = running_application(self.target_application)
        if current and target and current.pid == target.pid:
            self.target_application_pid = target.pid
            return True
        self._event(
            f"activating {self.target_application}"
            f" (target={_format_application(target)}"
            f"; frontmost={_format_application(current)}"
            f"; controller={controller_identity()})"
        )
        try:
            active = activate_application(self.target_application)
        except ApplicationActivationError as error:
            self._block(str(error))
            return False
        self.target_application_pid = active.pid
        self._event(f"application active: {_format_application(active)}")
        return True

    def _is_target_snapshot(self, snapshot: AXTreeSnapshot) -> bool:
        if self.target_application is None:
            return True
        if self.target_application_pid is not None and snapshot.pid is not None:
            return snapshot.pid == self.target_application_pid
        return _same_application(snapshot.application_name, self.target_application)

    def _set_observation(
        self,
        snapshot: AXTreeSnapshot,
        candidates: tuple[ActionCandidate, ...],
    ) -> None:
        self.state.snapshot = snapshot
        self.state.candidates = candidates
        self.state.fingerprint = snapshot_fingerprint(snapshot)
        self.state.status = AgentStatus.READY

    @staticmethod
    def _matching_candidate(
        selected: ActionCandidate,
        candidates: tuple[ActionCandidate, ...],
    ) -> ActionCandidate | None:
        return next(
            (
                candidate
                for candidate in candidates
                if candidate.operation == selected.operation
                and candidate.element_id == selected.element_id
            ),
            None,
        )

    @staticmethod
    def _candidate_summary(candidates: tuple[ActionCandidate, ...]) -> str:
        summary = []
        for candidate in candidates[:20]:
            if candidate.element_id is None:
                summary.append(candidate.operation.value)
            else:
                target = candidate.label or candidate.element_id
                summary.append(f"{candidate.operation.value}({target})")
        if len(candidates) > 20:
            summary.append(f"+{len(candidates) - 20} more")
        return ", ".join(summary) or "none"

    def _block(self, message: str) -> dict[str, Any]:
        self.state.status = AgentStatus.BLOCKED
        self.state.decision = None
        self.state.last_error = message
        self._event(f"blocked: {message}")
        return self.snapshot()

    def _event(self, message: str) -> None:
        if self.event_handler is not None:
            self.event_handler(message)

    def close(self) -> None:
        close = getattr(self.decision_client, "close", None)
        if close:
            close()
        if self._default_text_provider is not None:
            self._default_text_provider.close()
        if self._default_goal_parser is not None:
            self._default_goal_parser.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def _same_application(left: str | None, right: str) -> bool:
    if left is None:
        return False
    return left.casefold() == right.casefold()


def _format_application(application: ApplicationIdentity | None) -> str:
    if application is None:
        return "none"
    return (
        f"{application.name} pid={application.pid}"
        f" active={str(application.active).lower()}"
    )
