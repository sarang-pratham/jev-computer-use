from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import httpx

from ax.operations.candidates import ActionCandidate
from ax.operations.models import JEVOperation, TargetKind
from ax.operations.registry import operation_spec
from ax.snapshot import AXTreeSnapshot
from settings import Settings


class JEVError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class JEVDecision:
    operation: JEVOperation
    candidate: ActionCandidate
    confidence: float
    probabilities: dict[str, float]
    operation_probabilities: dict[str, float]
    target_confidence: float | None = None
    raw_answers: dict[str, Any] = field(default_factory=dict)
    arguments: dict[str, Any] = field(default_factory=dict)


def validate_choice(answer: Any, choices: Iterable[str]) -> dict[str, Any]:
    choice_ids = set(choices)
    try:
        probabilities = answer["probabilities"]
        confidence = answer["confidence"]
        selected = answer["choice"]
        numbers = [*probabilities.values(), confidence]
        valid = (
            selected in choice_ids
            and set(probabilities) == choice_ids
            and all(
                type(number) in (int, float)
                and math.isfinite(number)
                and 0 <= number <= 1
                for number in numbers
            )
            and abs(sum(probabilities.values()) - 1) < 0.02
            and probabilities[selected] >= max(probabilities.values()) - 1e-6
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise JEVError("Invalid JEV choice; no action executed")
    return answer


def _element_payload(
    snapshot: AXTreeSnapshot, candidates: Iterable[ActionCandidate]
) -> list[dict[str, Any]]:
    operations: dict[str, list[str]] = defaultdict(list)
    for candidate in candidates:
        if candidate.element_id is not None:
            operations[candidate.element_id].append(candidate.operation.value)

    return [
        {
            "id": element.element_id,
            "label": element.label,
            "role": element.role,
            "subrole": element.subrole,
            "value": None if element.redacted else element.value,
            "enabled": element.enabled,
            "focused": element.focused,
            "selected": element.selected,
            "expanded": element.expanded,
            "context": list(element.parent_path),
            "operations": operations.get(element.element_id, []),
        }
        for element in snapshot.elements
    ]


def _target_payload(candidate: ActionCandidate) -> dict[str, Any]:
    return {
        "element": f"{candidate.label or candidate.element_id} [{candidate.role}]",
        "id": candidate.element_id,
        "label": candidate.label,
        "role": candidate.role,
        "value": None if candidate.redacted else candidate.value,
        "focused": candidate.focused,
        "state": candidate.state,
        "context": list(candidate.parent_path),
    }


def build_request(
    goal: str,
    snapshot: AXTreeSnapshot,
    candidates: Iterable[ActionCandidate],
    history: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, ActionCandidate]]]:
    candidate_list = tuple(candidates)
    operation_criteria: dict[str, str] = {}
    targets: dict[str, dict[str, ActionCandidate]] = defaultdict(dict)
    for candidate in candidate_list:
        operation = candidate.operation.value
        operation_criteria.setdefault(
            operation,
            operation_spec(candidate.operation).description,
        )
        if candidate.element_id is not None:
            targets[operation][candidate.element_id] = candidate

    for operation in (JEVOperation.WAIT, JEVOperation.DONE, JEVOperation.BLOCKED):
        operation_criteria.setdefault(
            operation.value,
            operation_spec(operation).description,
        )

    questions: dict[str, Any] = {
        "operation": {
            "type": "choice",
            "criteria": operation_criteria,
            "instructions": {
                "goal": goal,
                "rules": [
                    "Choose one operation that advances the goal.",
                    "Use only operations and targets present in this observation.",
                    "Choose DONE only when the goal is visibly satisfied.",
                    "Choose BLOCKED only when no available operation can progress.",
                ],
            },
        }
    }

    for operation, operation_targets in targets.items():
        questions[f"{operation.lower()}_target"] = {
            "type": "choice",
            "criteria": {
                element_id: _target_payload(candidate)
                for element_id, candidate in operation_targets.items()
            },
            "instructions": {
                "goal": goal,
                "operation": operation,
                "rules": [
                    "Choose one target from the current observation.",
                    "Do not invent an element id or target.",
                ],
            },
        }

    body = {
        "state": {
            "goal": goal,
            "application": {
                "name": snapshot.application_name,
                "bundle_id": snapshot.bundle_id,
                "pid": snapshot.pid,
                "window_title": snapshot.window_title,
            },
            "elements": _element_payload(snapshot, candidate_list),
            "recent_actions": list(history)[-10:],
        },
        "questions": questions,
    }
    return body, dict(targets)


class JEVClient:
    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.client = client or httpx.Client(timeout=25)
        self._owns_client = client is None

    def choose(
        self,
        goal: str,
        snapshot: AXTreeSnapshot,
        candidates: Iterable[ActionCandidate],
        history: Iterable[Mapping[str, Any]],
    ) -> JEVDecision:
        body, targets = build_request(goal, snapshot, candidates, history)
        try:
            response = self.client.post(
                self.settings.typesafe_url,
                json={"model": self.settings.typesafe_model, **body},
                headers={
                    "Authorization": f"Bearer {self.settings.typesafe_api_key.get_secret_value()}"
                },
            )
        except httpx.HTTPError as error:
            raise JEVError("JEV connection failed; no action executed") from error
        if response.status_code >= 400:
            raise JEVError(f"JEV returned HTTP {response.status_code}")
        try:
            payload = response.json()
            answers = payload["answers"]
        except (TypeError, ValueError, KeyError) as error:
            raise JEVError("JEV returned an invalid response") from error

        operation_ids = body["questions"]["operation"]["criteria"]
        operation_answer = validate_choice(answers.get("operation"), operation_ids)
        try:
            operation = JEVOperation(operation_answer["choice"])
        except ValueError as error:
            raise JEVError("JEV selected an unknown operation") from error

        target_answer = None
        if operation.value in targets:
            target_key = f"{operation.value.lower()}_target"
            operation_targets = targets[operation.value]
            target_answer = validate_choice(answers.get(target_key), operation_targets)
            candidate = operation_targets[target_answer["choice"]]
        else:
            candidate = ActionCandidate(
                operation=operation,
                element_id=None,
                target_kind=TargetKind.NONE,
            )

        return JEVDecision(
            operation=operation,
            candidate=candidate,
            confidence=operation_answer["confidence"],
            probabilities=target_answer["probabilities"] if target_answer else {},
            operation_probabilities=operation_answer["probabilities"],
            target_confidence=target_answer["confidence"] if target_answer else None,
            raw_answers=answers,
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
