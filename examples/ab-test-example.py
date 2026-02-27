# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation

"""ab-test-example.py — Compare two governance configurations side by side.

Demonstrates the A/B testing workflow:

1. Define an agent action trace (the same trace is used for both configs).
2. Define two governance configurations — a "strict" baseline and a "relaxed"
   candidate — both with statically assigned trust levels set by the operator.
3. Run the ABTestEngine to produce a side-by-side comparison.
4. Render the comparison report in Markdown and JSON using ImpactReporter.

Trust changes are MANUAL ONLY. This example shows how an operator might
preview the effect of raising a trust level before actually doing so.

Run:
    cd python
    pip install -e .
    python ../examples/ab-test-example.py
"""

from __future__ import annotations

from shadow_mode.ab_testing import ABTestEngine, GovernanceConfig
from shadow_mode.dry_run import DryRunAction
from shadow_mode.impact_report import ImpactReporter


# ---------------------------------------------------------------------------
# Shared agent action trace
# ---------------------------------------------------------------------------

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
        required_trust_level=3,
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
        required_trust_level=3,
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
        required_trust_level=2,
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
    # Config A: current production config — L2 trust, $5 daily budget
    # Config B: proposed promotion config — L3 trust, $10 daily budget
    # Both trust levels are MANUALLY set by the operator; nothing is automatic.
    config_a = GovernanceConfig(
        label="current-L2-$5",
        trust_level=2,
        daily_budget=5.00,
        require_consent=False,
    )
    config_b = GovernanceConfig(
        label="proposed-L3-$10",
        trust_level=3,
        daily_budget=10.00,
        require_consent=False,
    )

    print("Running A/B governance comparison:")
    print(f"  Config A : {config_a.label}")
    print(f"  Config B : {config_b.label}")
    print()

    engine = ABTestEngine(config_a=config_a, config_b=config_b)
    result = engine.run(ACTIONS)

    reporter = ImpactReporter()

    # One-line comparison to terminal
    print("Summary:")
    print(f"  {result.summary_line}")
    print()

    # Full Markdown comparison report
    print("--- A/B Markdown Report ---\n")
    print(reporter.ab_to_markdown(result))

    # JSON comparison for downstream tooling
    print("\n--- A/B JSON Report ---\n")
    print(reporter.ab_to_json(result))

    # Also show individual reports for each config
    print("\n--- Config A Individual Report ---\n")
    print(reporter.to_text(result.result_a, config_label=config_a.label))

    print("\n--- Config B Individual Report ---\n")
    print(reporter.to_text(result.result_b, config_label=config_b.label))


if __name__ == "__main__":
    main()
