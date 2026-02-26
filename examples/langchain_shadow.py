# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""langchain_shadow.py — Shadow a LangChain agent.

Demonstrates how to run a LangChain-based agent candidate in shadow mode
alongside the production agent. The shadow agent runs with all tool calls
intercepted (no real HTTP, database, or queue calls escape). The production
agent runs normally.

Workflow:
1. Define a production LangChain agent and a shadow LangChain agent.
2. Wrap the shadow agent with LangChainAdapter to suppress tool side effects.
3. Run both agents on each test input.
4. Compare outputs using ShadowComparator.
5. Score the accumulated comparisons with ConfidenceScorer.
6. Print the evaluation report.

Prerequisites:

    pip install agent-shadow-mode[langchain]
    # or: pip install agent-shadow-mode langchain-core langchain-openai

Run:

    cd python
    pip install -e ".[langchain]"
    python ../examples/langchain_shadow.py

Notes on tool interception:

    LangChainAdapter patches ``BaseTool.arun`` and ``BaseTool.run`` for the
    duration of the shadow execution. Every tool call the shadow agent makes
    returns ``"__shadow_intercepted__"`` rather than real data. This means the
    shadow agent's final output reflects its routing and decision logic, not
    real tool responses. Factor this into your interpretation of deviations —
    differences in secondary fields like ``"data_retrieved"`` are expected and
    should be weighted accordingly via custom ``high_priority_fields``.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
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
from shadow_mode.adapters import LangChainAdapter


# ---------------------------------------------------------------------------
# Simulated LangChain agents
#
# In a real deployment these would be actual LangChain agent executors using
# BaseTool subclasses. Here we simulate the pattern so the example runs without
# real LangChain tool infrastructure.  Swap in your real agent callables below.
# ---------------------------------------------------------------------------


async def production_langchain_agent(input_data: dict[str, Any]) -> dict[str, Any]:
    """Simulated production LangChain agent.

    In a real deployment this would be something like:

        agent_executor = AgentExecutor(agent=agent, tools=[search_tool, calc_tool])
        result = await agent_executor.ainvoke({"input": input_data["query"]})
        return {"action": result["output"], "tool_calls": len(result["intermediate_steps"])}
    """
    query = input_data.get("query", "")
    amount = input_data.get("amount", 0)

    # Simulate production routing logic
    if "refund" in query.lower():
        if amount > 500:
            return {"action": "escalate", "reason": "high_value_refund", "approved": False}
        return {"action": "approve_refund", "reason": "within_policy", "approved": True}

    if "purchase" in query.lower():
        if amount > 1000:
            return {"action": "escalate", "reason": "high_value_purchase", "approved": False}
        return {"action": "approve_purchase", "reason": "within_limit", "approved": True}

    return {"action": "route_to_human", "reason": "unrecognised_intent", "approved": False}


async def shadow_langchain_agent(input_data: dict[str, Any]) -> dict[str, Any]:
    """Candidate shadow LangChain agent — under evaluation.

    This is a new version of the production agent with updated routing logic.
    It intentionally deviates on the high-value purchase case to illustrate
    a meaningful disagreement that the evaluator should flag.
    """
    query = input_data.get("query", "")
    amount = input_data.get("amount", 0)

    if "refund" in query.lower():
        if amount > 500:
            return {"action": "escalate", "reason": "high_value_refund", "approved": False}
        return {"action": "approve_refund", "reason": "within_policy", "approved": True}

    if "purchase" in query.lower():
        # Shadow uses a lower threshold: escalate above 800 instead of 1000
        if amount > 800:
            return {"action": "escalate", "reason": "high_value_purchase", "approved": False}
        # For amounts 801–1000, shadow approves while production escalates — disagreement
        return {"action": "approve_purchase", "reason": "within_shadow_limit", "approved": True}

    return {"action": "route_to_human", "reason": "unrecognised_intent", "approved": False}


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

TEST_CASES: list[dict[str, Any]] = [
    {"query": "process refund", "amount": 200, "user_id": "usr-101"},
    {"query": "process refund", "amount": 750, "user_id": "usr-102"},
    {"query": "approve purchase", "amount": 300, "user_id": "usr-103"},
    {"query": "approve purchase", "amount": 900, "user_id": "usr-104"},   # disagreement
    {"query": "approve purchase", "amount": 1200, "user_id": "usr-105"},  # agree: both escalate
    {"query": "cancel subscription", "amount": 0, "user_id": "usr-106"},
    {"query": "approve purchase", "amount": 850, "user_id": "usr-107"},   # disagreement
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    # Configure the LangChain adapter — it intercepts BaseTool.arun / .run.
    # The high_priority_fields tell the comparator which output keys matter most
    # for risk assessment.  "approved" and "action" are the critical fields here.
    adapter = LangChainAdapter()
    runner = ShadowRunner(agent_fn=shadow_langchain_agent, adapter=adapter)

    # Comparator: weight "approved" and "action" fields as high-priority.
    comparator = ShadowComparator(
        high_priority_fields=frozenset({"approved", "action", "decision"}),
        agreement_threshold=0.1,
    )

    scorer = ConfidenceScorer(strong_agreement_threshold=0.90, minimum_sample_size=5)
    recorder = ShadowRecorder()
    reporter = ShadowReporter()

    comparisons: list[ComparisonResult] = []

    print("LangChain Shadow Mode — Evaluation Run")
    print("=" * 42)
    print()

    for index, test_input in enumerate(TEST_CASES):
        decision_id = f"langchain-{index + 1:03d}"

        # 1. Run shadow agent (tool calls intercepted — no side effects)
        shadow_decision: ShadowDecision = await runner.shadow_execute(
            test_input, decision_id=decision_id
        )
        recorder.record(shadow_decision)

        # 2. Log how many tool calls the shadow agent attempted
        intercepted = shadow_decision.metadata.get("intercepted_tool_calls", [])
        tool_count = shadow_decision.metadata.get("total_tool_calls", 0)

        # 3. Run production agent (real execution, real tool calls)
        actual_output = await production_langchain_agent(test_input)

        # 4. Record actual decision
        actual_decision = ActualDecision(
            decision_id=decision_id,
            output=actual_output,
            timestamp=datetime.now(timezone.utc),
        )

        # 5. Compare
        comparison = comparator.compare(shadow_decision, actual_decision)
        comparisons.append(comparison)

        status = "AGREE   " if comparison.agreed else "DISAGREE"
        print(
            f"[{status}] {decision_id}  "
            f"amount={test_input['amount']:<5}  "
            f"shadow_action={shadow_decision.output.get('action')!r:<25}  "
            f"actual_action={actual_output.get('action')!r:<25}  "
            f"deviation={comparison.deviation_score:.2f}  "
            f"risk={comparison.risk_level.value}  "
            f"tool_calls_intercepted={tool_count}"
        )

        if comparison.deviations:
            for deviation in comparison.deviations:
                print(f"         deviation: {deviation.description}")

    # 6. Score and report
    print()
    report = scorer.score(comparisons)
    print(reporter.to_text(report, agent_label="LangChain Shadow Agent"))

    print("\n--- Markdown Report ---\n")
    print(reporter.to_markdown(report, comparisons, agent_label="LangChain Shadow Agent"))

    print("\n--- JSON Report ---\n")
    print(reporter.to_json(report, comparisons, agent_label="LangChain Shadow Agent"))

    # 7. What to do with the recommendation
    print("\n--- Recommendation ---")
    print(report.recommendation)
    print()
    print(
        "The recommendation above is advisory only. No trust level has been "
        "changed automatically. A human operator must review the deviations "
        "and decide whether to act on this report."
    )


if __name__ == "__main__":
    asyncio.run(main())
