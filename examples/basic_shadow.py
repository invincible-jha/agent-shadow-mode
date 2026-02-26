# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""basic_shadow.py — Shadow a simple function.

Demonstrates the minimal shadow mode workflow:

1. Define a production agent function and a shadow agent function.
2. Run the shadow agent on real input (no side effects).
3. Record what the production agent actually did.
4. Compare the two outputs.
5. Accumulate comparisons and score them.

Run:
    cd python
    pip install -e .
    python ../examples/basic_shadow.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from shadow_mode import (
    ActualDecision,
    ConfidenceScorer,
    ComparisonResult,
    ShadowComparator,
    ShadowDecision,
    ShadowRecorder,
    ShadowReporter,
    ShadowRunner,
)
from shadow_mode.adapters import GenericAdapter


# ---------------------------------------------------------------------------
# Simulated agents
# ---------------------------------------------------------------------------

async def production_agent(input_data: dict[str, Any]) -> dict[str, Any]:
    """Simulated production agent — makes real decisions."""
    amount = input_data.get("amount", 0)
    if amount <= 1000:
        return {"action": "approve", "reason": "within_policy"}
    return {"action": "escalate", "reason": "exceeds_limit"}


async def shadow_agent(input_data: dict[str, Any]) -> dict[str, Any]:
    """Candidate shadow agent — under evaluation.

    In a real scenario this would be a different model, new logic, or a
    different configuration of the same model. Here it intentionally deviates
    on one edge case to illustrate disagreement.
    """
    amount = input_data.get("amount", 0)
    if amount <= 1000:
        return {"action": "approve", "reason": "within_policy"}
    # Shadow agent uses "review" instead of "escalate" — disagreement!
    return {"action": "review", "reason": "exceeds_limit"}


# ---------------------------------------------------------------------------
# Shadow run
# ---------------------------------------------------------------------------

async def main() -> None:
    adapter = GenericAdapter()
    runner = ShadowRunner(agent_fn=shadow_agent, adapter=adapter)
    comparator = ShadowComparator()
    scorer = ConfidenceScorer(strong_agreement_threshold=0.95, minimum_sample_size=5)
    recorder = ShadowRecorder()
    reporter = ShadowReporter()

    test_cases: list[dict[str, Any]] = [
        {"amount": 100, "user": "alice"},
        {"amount": 500, "user": "bob"},
        {"amount": 800, "user": "carol"},
        {"amount": 1500, "user": "dave"},   # This will cause a disagreement
        {"amount": 2000, "user": "eve"},    # This will cause a disagreement
        {"amount": 300, "user": "frank"},
    ]

    comparisons: list[ComparisonResult] = []

    print("Running shadow evaluation...\n")
    for test_input in test_cases:
        decision_id = f"order-{test_input['user']}"

        # 1. Run shadow agent (no side effects)
        shadow_decision: ShadowDecision = await runner.shadow_execute(
            test_input, decision_id=decision_id
        )
        recorder.record(shadow_decision)

        # 2. Run production agent (real execution)
        actual_output = await production_agent(test_input)

        # 3. Record actual decision
        actual_decision = ActualDecision(
            decision_id=decision_id,
            output=actual_output,
            timestamp=datetime.now(timezone.utc),
        )

        # 4. Compare
        comparison = comparator.compare(shadow_decision, actual_decision)
        comparisons.append(comparison)

        status = "AGREE" if comparison.agreed else "DISAGREE"
        print(
            f"  [{status}] {decision_id}: "
            f"shadow={shadow_decision.output.get('action')!r}, "
            f"actual={actual_output.get('action')!r}, "
            f"deviation={comparison.deviation_score:.2f}, "
            f"risk={comparison.risk_level.value}"
        )

    # 5. Score
    print()
    report = scorer.score(comparisons)
    print(reporter.to_text(report, agent_label="Basic Shadow Agent"))

    # Also show Markdown output
    print("\n--- Markdown Report ---\n")
    print(reporter.to_markdown(report, comparisons, agent_label="Basic Shadow Agent"))


if __name__ == "__main__":
    asyncio.run(main())
