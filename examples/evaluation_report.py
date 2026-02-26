# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""evaluation_report.py — Generate a trust-building evaluation report.

Demonstrates how to accumulate a large batch of shadow comparisons, score them
with ConfidenceScorer, and produce a complete evaluation report in three formats
(plain text, Markdown, JSON) that a human operator can use as evidence when
deciding whether to adjust an agent's trust assignment.

Key concepts illustrated:

- Persistent JSONL recording of shadow decisions across sessions.
- Loading historical decisions from a JSONL file for batch evaluation.
- Using ShadowComparator with custom high-priority fields.
- Generating a ConfidenceReport with explicit sample-size thresholds.
- Exporting the report in all three output formats.
- Understanding what the recommendation string means (advisory only).

Run:

    cd python
    pip install -e .
    python ../examples/evaluation_report.py

The example creates a temporary JSONL file, populates it with simulated
decisions, and then generates a report. The JSONL file is removed at the end.
"""

from __future__ import annotations

import asyncio
import json
import random
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shadow_mode import (
    ActualDecision,
    ComparisonResult,
    ConfidenceScorer,
    ShadowComparator,
    ShadowDecision,
    ShadowRecorder,
    ShadowReporter,
    ShadowRunner,
)
from shadow_mode.adapters import GenericAdapter


# ---------------------------------------------------------------------------
# Simulated agents
#
# These stand in for a real production agent and its shadow candidate.  The
# shadow agent has a deliberately higher approval rate to generate some
# disagreements for the report.
# ---------------------------------------------------------------------------

_RNG = random.Random(42)  # Fixed seed for reproducible output


async def production_agent(input_data: dict[str, Any]) -> dict[str, Any]:
    """Simulated production agent with well-established routing logic."""
    amount = input_data.get("amount", 0)
    category = input_data.get("category", "general")

    if category == "medical":
        return {"approved": True, "tier": "priority", "reason": "medical_exemption"}

    if amount <= 200:
        return {"approved": True, "tier": "standard", "reason": "within_limit"}
    if amount <= 800:
        return {"approved": True, "tier": "enhanced", "reason": "within_enhanced_limit"}

    return {"approved": False, "tier": "escalation", "reason": "exceeds_limit"}


async def shadow_agent_candidate(input_data: dict[str, Any]) -> dict[str, Any]:
    """Candidate shadow agent — under evaluation.

    This agent uses a slightly different approval boundary.  It approves
    requests up to 850 (versus the production threshold of 800), which causes
    a disagreement on requests in the 801–850 range.
    """
    amount = input_data.get("amount", 0)
    category = input_data.get("category", "general")

    if category == "medical":
        return {"approved": True, "tier": "priority", "reason": "medical_exemption"}

    if amount <= 200:
        return {"approved": True, "tier": "standard", "reason": "within_limit"}
    if amount <= 850:
        # Shadow agent approves 801–850; production escalates these
        return {"approved": True, "tier": "enhanced", "reason": "within_enhanced_limit"}

    return {"approved": False, "tier": "escalation", "reason": "exceeds_limit"}


# ---------------------------------------------------------------------------
# Generate a diverse set of test inputs to get statistically meaningful results
# ---------------------------------------------------------------------------

def generate_test_inputs(count: int) -> list[dict[str, Any]]:
    """Generate a list of varied test inputs."""
    categories = ["general", "general", "general", "medical"]  # weighted
    inputs = []
    for index in range(count):
        category = _RNG.choice(categories)
        # Amounts spread across threshold boundaries
        amount = _RNG.choice([
            _RNG.randint(10, 200),     # always approved by both
            _RNG.randint(201, 800),    # approved by both (enhanced tier)
            _RNG.randint(801, 850),    # shadow approves, production escalates
            _RNG.randint(851, 1500),   # both escalate
        ])
        inputs.append({
            "case_id": f"eval-{index + 1:04d}",
            "amount": amount,
            "category": category,
        })
    return inputs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    # ── Configuration ─────────────────────────────────────────────────────────

    # Number of decisions to evaluate — use at least 100 for meaningful stats.
    total_decisions = 150

    # High-priority fields: deviations in "approved" carry double weight.
    high_priority_fields = frozenset({"approved", "tier"})

    # Scorer thresholds: a positive advisory only if agreement rate >= 92%
    # and at least 100 comparisons have been accumulated.
    scorer = ConfidenceScorer(
        strong_agreement_threshold=0.92,
        minimum_sample_size=100,
    )

    # ── Setup ─────────────────────────────────────────────────────────────────
    jsonl_path = Path(tempfile.mktemp(suffix=".jsonl"))

    adapter = GenericAdapter()
    runner = ShadowRunner(agent_fn=shadow_agent_candidate, adapter=adapter)
    comparator = ShadowComparator(
        high_priority_fields=high_priority_fields,
        agreement_threshold=0.1,
    )
    recorder = ShadowRecorder(storage_path=jsonl_path, max_memory_records=None)
    reporter = ShadowReporter()

    comparisons: list[ComparisonResult] = []
    test_inputs = generate_test_inputs(total_decisions)

    print("Shadow Mode — Batch Evaluation")
    print("=" * 40)
    print(f"Total decisions to evaluate: {total_decisions}")
    print(f"JSONL recording path: {jsonl_path}")
    print()

    # ── Evaluation loop ───────────────────────────────────────────────────────
    for test_input in test_inputs:
        decision_id = test_input["case_id"]

        # Run shadow agent (no side effects — GenericAdapter is a no-op)
        shadow_decision: ShadowDecision = await runner.shadow_execute(
            test_input, decision_id=decision_id
        )
        recorder.record(shadow_decision)

        # Run production agent (real execution)
        actual_output = await production_agent(test_input)

        # Record actual decision
        actual_decision = ActualDecision(
            decision_id=decision_id,
            output=actual_output,
            timestamp=datetime.now(timezone.utc),
        )

        # Compare
        comparison = comparator.compare(shadow_decision, actual_decision)
        comparisons.append(comparison)

    print(f"Evaluation complete: {len(comparisons)} comparisons recorded.")
    print(f"JSONL file size: {jsonl_path.stat().st_size:,} bytes\n")

    # ── Score ─────────────────────────────────────────────────────────────────
    report = scorer.score(comparisons)

    # ── Report — plain text ───────────────────────────────────────────────────
    print(reporter.to_text(report, agent_label="Approval Agent v2"))

    # ── Report — Markdown ─────────────────────────────────────────────────────
    markdown_output = reporter.to_markdown(
        report,
        comparisons,
        agent_label="Approval Agent v2",
    )
    markdown_path = jsonl_path.with_suffix(".md")
    markdown_path.write_text(markdown_output, encoding="utf-8")
    print(f"\nMarkdown report written to: {markdown_path}")

    # ── Report — JSON ─────────────────────────────────────────────────────────
    json_output = reporter.to_json(
        report,
        comparisons,
        agent_label="Approval Agent v2",
    )
    json_path = jsonl_path.with_suffix(".json")
    json_path.write_text(json_output, encoding="utf-8")
    print(f"JSON report written to: {json_path}")

    # ── Key metrics ───────────────────────────────────────────────────────────
    print("\n--- Key Metrics ---")
    print(f"  Agreement rate   : {report.agreement_rate * 100:.1f}%")
    print(f"  Average deviation: {report.average_deviation:.4f}")
    print(f"  Worst deviation  : {report.worst_deviation:.4f}")
    print(f"  High-risk count  : {report.high_risk_count}")
    print(f"  Risk score       : {report.risk_score:.4f}")

    # ── Breakdown of disagreements ─────────────────────────────────────────
    disagreements = [c for c in comparisons if not c.agreed]
    print(f"\n--- Disagreement Summary ({len(disagreements)} total) ---")
    for disagreement in disagreements[:10]:  # show first 10
        fields = [deviation.field_path for deviation in disagreement.deviations]
        print(f"  {disagreement.decision_id}: fields={fields}, risk={disagreement.risk_level.value}")
    if len(disagreements) > 10:
        print(f"  ... and {len(disagreements) - 10} more")

    # ── Recommendation ────────────────────────────────────────────────────────
    print("\n--- Recommendation (advisory only) ---")
    print(report.recommendation)
    print()
    print(
        "IMPORTANT: This recommendation is a human-readable advisory string.\n"
        "No trust level has changed and no API call has been made.\n"
        "A human operator must review this report and decide whether to act.\n"
        "To adjust an agent's trust level, update the governance configuration\n"
        "directly and redeploy or reload the configuration."
    )

    # ── Load and verify from JSONL ─────────────────────────────────────────
    print("\n--- Verifying JSONL persistence ---")
    loaded_decisions = recorder.load_from_file()
    print(f"  Decisions in JSONL file: {len(loaded_decisions)}")
    first_loaded = loaded_decisions[0]
    print(f"  First decision_id: {first_loaded.decision_id}")
    print(f"  First input_hash: {first_loaded.input_hash[:16]}...")

    # ── Cleanup ───────────────────────────────────────────────────────────────
    jsonl_path.unlink(missing_ok=True)
    markdown_path.unlink(missing_ok=True)
    json_path.unlink(missing_ok=True)
    print("\nTemporary files cleaned up. Done.")


if __name__ == "__main__":
    asyncio.run(main())
