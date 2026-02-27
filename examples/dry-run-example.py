# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation

"""dry-run-example.py — Evaluate an agent action trace without enforcement.

Demonstrates the governance dry-run workflow:

1. Define a sequence of agent actions with varying trust requirements and costs.
2. Create a GovernanceDryRun engine with specific trust level and budget limits.
3. Evaluate the actions — nothing is enforced, this is read-only simulation.
4. Render the results using ImpactReporter in both Markdown and plain text.

Run:
    cd python
    pip install -e .
    python ../examples/dry-run-example.py
"""

from __future__ import annotations

from shadow_mode.dry_run import DryRunAction, GovernanceDryRun
from shadow_mode.impact_report import ImpactReporter


# ---------------------------------------------------------------------------
# Simulated agent action trace
# ---------------------------------------------------------------------------

# These represent what an AI agent "would have done" in a real session.
# The trust levels and costs are illustrative only.
ACTIONS: list[DryRunAction] = [
    DryRunAction(
        action_id="act-001",
        action_type="tool_call",
        tool_name="web_search",
        estimated_cost=0.10,
        required_trust_level=1,
    ),
    DryRunAction(
        action_id="act-002",
        action_type="tool_call",
        tool_name="read_file",
        estimated_cost=0.05,
        required_trust_level=1,
    ),
    DryRunAction(
        action_id="act-003",
        action_type="tool_call",
        tool_name="write_file",
        estimated_cost=0.20,
        required_trust_level=2,
    ),
    DryRunAction(
        action_id="act-004",
        action_type="api_request",
        tool_name="send_email",
        estimated_cost=0.50,
        required_trust_level=3,  # Requires higher trust — will be denied at L2
    ),
    DryRunAction(
        action_id="act-005",
        action_type="api_request",
        tool_name="database_write",
        estimated_cost=0.30,
        required_trust_level=2,
    ),
    DryRunAction(
        action_id="act-006",
        action_type="api_request",
        tool_name="external_api_post",
        estimated_cost=0.75,
        required_trust_level=3,  # Requires higher trust — will be denied at L2
    ),
    DryRunAction(
        action_id="act-007",
        action_type="tool_call",
        tool_name="summarise_document",
        estimated_cost=0.15,
        required_trust_level=1,
    ),
    DryRunAction(
        action_id="act-008",
        action_type="api_request",
        tool_name="schedule_task",
        estimated_cost=0.40,
        required_trust_level=2,
    ),
    DryRunAction(
        action_id="act-009",
        action_type="tool_call",
        tool_name="code_execute",
        estimated_cost=2.50,
        required_trust_level=2,  # Will be denied — pushes over the $5 budget
    ),
    DryRunAction(
        action_id="act-010",
        action_type="tool_call",
        tool_name="web_search",
        estimated_cost=0.10,
        required_trust_level=1,
    ),
]


def main() -> None:
    # Trust level is set MANUALLY by the operator — never automatic
    engine = GovernanceDryRun(
        trust_level=2,
        daily_budget=5.00,
        require_consent=False,
    )

    print("Evaluating 10-action agent trace against governance config:")
    print(f"  Trust level  : L{engine._trust_level}")
    print(f"  Daily budget : ${engine._daily_budget:.2f}")
    print()

    result = engine.evaluate(ACTIONS)

    reporter = ImpactReporter()

    # Plain text to terminal
    print(reporter.to_text(result, config_label="L2 — $5 daily budget"))

    # Markdown (useful for piping to a file or CI step)
    print("\n--- Markdown Report ---\n")
    print(reporter.to_markdown(result, config_label="L2 — $5 daily budget"))

    # JSON (machine-readable)
    print("\n--- JSON Report ---\n")
    print(reporter.to_json(result, config_label="L2 — $5 daily budget"))


if __name__ == "__main__":
    main()
