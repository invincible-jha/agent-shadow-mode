# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""ConfidenceScorer — aggregate comparison results into a human-readable report.

The scorer takes a list of ``ComparisonResult`` objects (produced by
``ShadowComparator``) and computes aggregate statistics:

- Agreement rate (fraction of comparisons where shadow agreed with actual)
- Average and worst deviation scores
- Risk score (proportion of HIGH-risk comparisons)
- A plain human-readable recommendation string

The recommendation is ADVISORY ONLY. It is a string like::

    "Based on 87% agreement over 150 decisions, shadow performance needs
    improvement before promotion. Investigate the 19 high-risk deviations."

No API calls are made. No trust levels are changed automatically.
"""

from __future__ import annotations

from .types import ComparisonResult, ConfidenceReport, RiskLevel


class ConfidenceScorer:
    """Aggregates comparison results into a ``ConfidenceReport``.

    Example::

        scorer = ConfidenceScorer()
        report = scorer.score(comparisons)
        print(report.agreement_rate)      # 0.95
        print(report.recommendation)     # "Based on 95% agreement..."

    Args:
        strong_agreement_threshold: Agreement rate at or above which a positive
            promotion advisory is issued. Defaults to 0.95 (95%).
        minimum_sample_size: Minimum number of comparisons before a positive
            promotion advisory is issued. Defaults to 100.
    """

    def __init__(
        self,
        strong_agreement_threshold: float = 0.95,
        minimum_sample_size: int = 100,
    ) -> None:
        if not 0.0 <= strong_agreement_threshold <= 1.0:
            raise ValueError("strong_agreement_threshold must be in [0.0, 1.0].")
        if minimum_sample_size < 1:
            raise ValueError("minimum_sample_size must be at least 1.")
        self._strong_agreement_threshold = strong_agreement_threshold
        self._minimum_sample_size = minimum_sample_size

    def score(self, comparisons: list[ComparisonResult]) -> ConfidenceReport:
        """Compute an aggregate confidence report from a list of comparison results.

        Args:
            comparisons: List of ``ComparisonResult`` objects. May be empty,
                in which case a zero-state report is returned.

        Returns:
            ``ConfidenceReport`` with aggregate statistics and a plain-text
            recommendation string. The recommendation is ADVISORY ONLY —
            no automatic actions are taken.

        Example::

            report = scorer.score([result1, result2, result3])
            print(report.total_comparisons)  # 3
            print(report.recommendation)     # human-readable string
        """
        if not comparisons:
            return ConfidenceReport(
                total_comparisons=0,
                agreement_count=0,
                disagreement_count=0,
                agreement_rate=0.0,
                average_deviation=0.0,
                worst_deviation=0.0,
                risk_score=0.0,
                high_risk_count=0,
                recommendation=(
                    "No comparison data available. Accumulate shadow decisions "
                    "before requesting a confidence report."
                ),
            )

        total = len(comparisons)
        agreed_count = sum(1 for c in comparisons if c.agreed)
        disagreed_count = total - agreed_count
        agreement_rate = agreed_count / total

        deviation_scores = [c.deviation_score for c in comparisons]
        average_deviation = sum(deviation_scores) / total
        worst_deviation = max(deviation_scores)

        high_risk_count = sum(1 for c in comparisons if c.risk_level == RiskLevel.HIGH)
        risk_score = high_risk_count / total

        recommendation = _build_recommendation(
            total_comparisons=total,
            agreement_rate=agreement_rate,
            high_risk_count=high_risk_count,
            worst_deviation=worst_deviation,
            strong_agreement_threshold=self._strong_agreement_threshold,
            minimum_sample_size=self._minimum_sample_size,
        )

        return ConfidenceReport(
            total_comparisons=total,
            agreement_count=agreed_count,
            disagreement_count=disagreed_count,
            agreement_rate=round(agreement_rate, 6),
            average_deviation=round(average_deviation, 6),
            worst_deviation=round(worst_deviation, 6),
            risk_score=round(risk_score, 6),
            high_risk_count=high_risk_count,
            recommendation=recommendation,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_recommendation(
    total_comparisons: int,
    agreement_rate: float,
    high_risk_count: int,
    worst_deviation: float,
    strong_agreement_threshold: float,
    minimum_sample_size: int,
) -> str:
    """Build a plain human-readable advisory string.

    The string describes the current shadow mode performance and makes an
    advisory suggestion — it is NOT an API call, NOT a state mutation, and
    does NOT change any trust level.

    Args:
        total_comparisons: Total number of comparisons evaluated.
        agreement_rate: Fraction of comparisons where shadow agreed with actual.
        high_risk_count: Number of HIGH-risk comparisons.
        worst_deviation: Maximum observed deviation score.
        strong_agreement_threshold: Threshold for a positive advisory.
        minimum_sample_size: Minimum comparisons needed for a positive advisory.

    Returns:
        Human-readable advisory string.
    """
    agreement_pct = f"{agreement_rate * 100:.1f}%"
    base = f"Based on {agreement_pct} agreement over {total_comparisons} decision(s)"

    if total_comparisons < minimum_sample_size:
        needed = minimum_sample_size - total_comparisons
        return (
            f"{base}: sample size is below the recommended minimum of "
            f"{minimum_sample_size}. Accumulate {needed} more decision(s) "
            f"before drawing conclusions."
        )

    if high_risk_count > 0:
        return (
            f"{base}: {high_risk_count} high-risk deviation(s) detected "
            f"(worst deviation score: {worst_deviation:.2f}). "
            f"Review deviations before considering any promotion."
        )

    if agreement_rate >= strong_agreement_threshold:
        return (
            f"{base}: shadow performance is strong. A human operator may consider "
            f"promoting this agent to a higher trust level."
        )

    gap = f"{(strong_agreement_threshold - agreement_rate) * 100:.1f}%"
    return (
        f"{base}: shadow performance is below the strong agreement threshold "
        f"({strong_agreement_threshold * 100:.1f}%) by {gap}. "
        f"Continue monitoring before considering any promotion."
    )
