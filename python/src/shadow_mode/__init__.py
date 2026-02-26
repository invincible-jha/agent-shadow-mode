# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""agent-shadow-mode — run AI agents in shadow mode to build a trust track record.

Run a candidate agent in parallel with a production agent without side effects.
Capture what it *would have done*, compare to actual decisions, score agreement
over time, and generate human-readable evaluation reports.

Quick start::

    import asyncio
    from shadow_mode import ShadowRunner, ShadowComparator, ConfidenceScorer
    from shadow_mode.types import ActualDecision

    async def my_shadow_agent(input_data: dict) -> dict:
        return {"action": "approve"}

    async def main() -> None:
        runner = ShadowRunner(agent_fn=my_shadow_agent)
        shadow = await runner.shadow_execute({"amount": 500})

        actual = ActualDecision(
            decision_id=shadow.decision_id,
            output={"action": "approve"},
        )

        comparator = ShadowComparator()
        comparison = comparator.compare(shadow, actual)

        scorer = ConfidenceScorer()
        report = scorer.score([comparison])
        print(report.recommendation)

    asyncio.run(main())
"""

from .comparator import ShadowComparator
from .recorder import ShadowRecorder
from .report import ShadowReporter
from .runner import ShadowExecutionError, ShadowRunner
from .scorer import ConfidenceScorer
from .types import (
    ActualDecision,
    AgreementLevel,
    ComparisonResult,
    ConfidenceReport,
    Deviation,
    RiskLevel,
    ShadowDecision,
)

__all__ = [
    # Core
    "ShadowRunner",
    "ShadowComparator",
    "ConfidenceScorer",
    "ShadowRecorder",
    "ShadowReporter",
    # Errors
    "ShadowExecutionError",
    # Types
    "ShadowDecision",
    "ActualDecision",
    "ComparisonResult",
    "ConfidenceReport",
    "Deviation",
    "AgreementLevel",
    "RiskLevel",
]

__version__ = "0.1.0"
