from __future__ import annotations

import argparse
import sys

from pydantic import ValidationError

from agent import AgentError, ComputerUseAgent
from ax.operations.candidates import build_candidates
from ax.reader import (
    AXPermissionError,
    AXReader,
    AXReaderError,
    controller_identity,
    open_accessibility_settings,
)
from jev import JEVError


def permission_error(error: AXPermissionError, open_settings: bool) -> int:
    print(f"Unable to inspect frontmost application: {error}", file=sys.stderr)
    print(f"Controller needing permission: {controller_identity()}", file=sys.stderr)
    print(
        "When running from a terminal or IDE, grant permission to that host application.",
        file=sys.stderr,
    )
    if open_settings:
        if open_accessibility_settings():
            print("Opened Accessibility settings. Enable access, then run again.")
        else:
            print("Could not open Accessibility settings.", file=sys.stderr)
    return 1


def inspect_frontmost(open_settings: bool = False) -> int:
    try:
        snapshot = AXReader().read_frontmost()
    except AXPermissionError as error:
        return permission_error(error, open_settings)
    except AXReaderError as error:
        print(f"Unable to inspect frontmost application: {error}", file=sys.stderr)
        return 1

    print(f"Controller: {controller_identity()}")
    print(
        f"Target: {snapshot.application_name or 'Unknown application'}"
        f" (pid={snapshot.pid}, elements={len(snapshot.elements)})"
    )
    candidates = build_candidates(snapshot.elements, include_global_operations=False)
    candidate_ids = {candidate.element_id for candidate in candidates}
    for element in snapshot.elements:
        if element.element_id not in candidate_ids and element.role not in {
            "AXApplication",
            "AXWindow",
        }:
            continue
        operations = sorted(
            candidate.operation.value
            for candidate in candidates
            if candidate.element_id == element.element_id
        )
        indent = "  " * len(element.parent_path)
        print(f"{indent}{element.role}: {element.label} [{', '.join(operations)}]")
    return 0


def run_goal(goal: str, open_settings: bool = False) -> int:
    try:
        agent = ComputerUseAgent(
            goal,
            event_handler=lambda message: print(f"[agent] {message}", flush=True),
        )
    except ValidationError as error:
        print(f"Invalid settings: {error}", file=sys.stderr)
        return 1

    try:
        for state in agent.run():
            if state["error"]:
                print(f"[agent] error: {state['error']}", file=sys.stderr)
        status = agent.state.status.value
        print(f"[agent] finished status={status} steps={agent.state.step_count}")
        return 0 if status == "done" else 1
    except AXPermissionError as error:
        return permission_error(error, open_settings)
    except (AgentError, JEVError) as error:
        print(f"Agent stopped: {error}", file=sys.stderr)
        return 1
    finally:
        agent.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("inspect", "run"))
    parser.add_argument("goal", nargs="?")
    parser.add_argument("--open-settings", action="store_true")
    args = parser.parse_args()
    if args.command == "inspect":
        return inspect_frontmost(args.open_settings)
    if not args.goal:
        parser.error("run requires a goal")
    return run_goal(args.goal, args.open_settings)


if __name__ == "__main__":
    raise SystemExit(main())
