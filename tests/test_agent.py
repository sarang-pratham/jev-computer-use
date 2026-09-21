from __future__ import annotations

import unittest

from agent import AgentStatus, ComputerUseAgent
from ax.constants import AX_PRESS, ROLE_BUTTON
from ax.executor import OperationExecutor
from ax.operations.candidates import build_candidates
from ax.operations.models import JEVOperation
from ax.snapshot import AXElementSnapshot, AXTreeSnapshot
from goal_parser import GoalContext
from jev import JEVClient, JEVDecision, build_request
from settings import Settings


class FakeBackend:
    def __init__(self) -> None:
        self.actions: list[tuple[str, str]] = []

    def perform_action(self, element_id: str, action: str) -> None:
        self.actions.append((element_id, action))

    def set_attribute(self, element_id: str, attribute: str, value: object) -> None:
        pass


class FakeReader:
    def __init__(self) -> None:
        self.backend = FakeBackend()
        self.snapshot = AXTreeSnapshot(
            elements=(
                AXElementSnapshot(
                    element_id="search",
                    role=ROLE_BUTTON,
                    title="Search",
                    actions=frozenset({AX_PRESS}),
                ),
            ),
            pid=1,
            application_name="Test App",
        )

    def read_frontmost(self) -> AXTreeSnapshot:
        return self.snapshot


class FakeDecisionClient:
    def choose(self, goal, snapshot, candidates, history) -> JEVDecision:
        candidate = next(
            candidate
            for candidate in candidates
            if candidate.operation == JEVOperation.CLICK
        )
        return JEVDecision(
            operation=JEVOperation.CLICK,
            candidate=candidate,
            confidence=1.0,
            probabilities={candidate.element_id: 1.0},
            operation_probabilities={JEVOperation.CLICK.value: 1.0},
        )


class FakeGoalParser:
    def __call__(self, goal: str) -> GoalContext:
        return GoalContext()


class FakeResponse:
    def __init__(self, payload) -> None:
        self.status_code = 200
        self.payload = payload

    def json(self):
        return self.payload


class FakeHTTPClient:
    def __init__(self) -> None:
        self.calls = []

    def post(self, url, json, headers):
        self.calls.append((url, json, headers))
        operations = json["questions"]["operation"]["criteria"]
        targets = json["questions"]["click_target"]["criteria"]
        return FakeResponse(
            {
                "answers": {
                    "operation": {
                        "choice": "CLICK",
                        "confidence": 1.0,
                        "probabilities": {
                            operation: float(operation == "CLICK")
                            for operation in operations
                        },
                    },
                    "click_target": {
                        "choice": "search",
                        "confidence": 1.0,
                        "probabilities": {
                            target: float(target == "search") for target in targets
                        },
                    },
                }
            }
        )

    def close(self) -> None:
        pass


class AgentIntegrationTests(unittest.TestCase):
    def test_request_contains_goal_state_history_and_target_head(self) -> None:
        reader = FakeReader()
        candidates = build_candidates(reader.snapshot.elements)
        body, _ = build_request(
            "Click Search",
            reader.snapshot,
            candidates,
            [{"operation": "WAIT"}],
        )

        self.assertEqual(body["state"]["goal"], "Click Search")
        self.assertEqual(body["state"]["recent_actions"], [{"operation": "WAIT"}])
        self.assertIn("operation", body["questions"])
        self.assertIn("click_target", body["questions"])

    def test_jev_client_chooses_operation_and_target_in_one_request(self) -> None:
        reader = FakeReader()
        client = FakeHTTPClient()
        decision_client = JEVClient(
            Settings(typesafe_api_key="test"),
            client=client,
        )

        decision = decision_client.choose(
            "Click Search",
            reader.snapshot,
            build_candidates(reader.snapshot.elements),
            [],
        )

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(decision.operation, JEVOperation.CLICK)
        self.assertEqual(decision.candidate.element_id, "search")

    def test_agent_executes_one_decision_and_records_history(self) -> None:
        reader = FakeReader()
        agent = ComputerUseAgent(
            "Click Search",
            reader=reader,
            decision_client=FakeDecisionClient(),
            executor=OperationExecutor(reader.backend),
            goal_parser=FakeGoalParser(),
        )

        result = agent.tick()

        self.assertEqual(result["status"], AgentStatus.READY.value)
        self.assertEqual(reader.backend.actions, [("search", AX_PRESS)])
        self.assertEqual(result["history"][0]["operation"], JEVOperation.CLICK.value)

    def test_agent_reports_decision_and_execution_events(self) -> None:
        reader = FakeReader()
        events: list[str] = []
        agent = ComputerUseAgent(
            "Click Search",
            reader=reader,
            decision_client=FakeDecisionClient(),
            executor=OperationExecutor(reader.backend),
            goal_parser=FakeGoalParser(),
            event_handler=events.append,
        )

        agent.tick()

        self.assertTrue(any("JEV selected CLICK" in event for event in events))
        self.assertTrue(any("executing CLICK" in event for event in events))
        self.assertTrue(any("verifying" in event for event in events))


if __name__ == "__main__":
    unittest.main()
