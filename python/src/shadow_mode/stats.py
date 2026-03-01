# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""
Shadow mode comparison statistics.

Provides ``ShadowStats`` — an aggregated summary of shadow-vs-production
comparison outcomes — and ``ShadowStatsCollector``, which accumulates
``ComparisonResult`` instances and produces the summary on demand.

Includes an optional chi-squared test for detecting non-random divergence
patterns in categorical outputs (e.g., action types).

Example
-------
>>> collector = ShadowStatsCollector()
>>> for comparison in comparisons:
...     collector.add(comparison)
>>> stats = collector.compute()
>>> print(stats.divergence_rate)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Counter

from .types import ComparisonResult, RiskLevel

__all__ = ["ShadowStats", "ShadowStatsCollector", "chi_squared_divergence"]


@dataclass(frozen=True)
class ShadowStats:
    """Aggregated statistics over a set of shadow mode comparison results.

    Attributes:
        total_runs:         Total number of comparison results included.
        divergence_count:   Number of comparisons where shadow disagreed with production.
        avg_divergence_score: Mean deviation score across all comparisons.
        max_divergence_score: Maximum deviation score observed in any single run.
        min_divergence_score: Minimum deviation score observed.
        high_risk_count:    Number of comparisons rated as HIGH risk.
        medium_risk_count:  Number of comparisons rated as MEDIUM risk.
        low_risk_count:     Number of comparisons rated as LOW risk.
        agreement_rate:     Fraction of runs where shadow agreed with production.
        divergence_rate:    Fraction of runs where shadow diverged from production.
    """

    total_runs: int
    divergence_count: int
    avg_divergence_score: float
    max_divergence_score: float
    min_divergence_score: float
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int

    @property
    def agreement_rate(self) -> float:
        """Fraction of runs where shadow agreed with production.

        Returns 0.0 when no runs have been collected.
        """
        if self.total_runs == 0:
            return 0.0
        agreed = self.total_runs - self.divergence_count
        return agreed / self.total_runs

    @property
    def divergence_rate(self) -> float:
        """Fraction of runs where shadow diverged from production.

        Returns 0.0 when no runs have been collected.
        """
        if self.total_runs == 0:
            return 0.0
        return self.divergence_count / self.total_runs

    def __str__(self) -> str:
        return (
            f"ShadowStats("
            f"runs={self.total_runs}, "
            f"divergence_rate={self.divergence_rate:.1%}, "
            f"avg_score={self.avg_divergence_score:.3f}, "
            f"high_risk={self.high_risk_count})"
        )


class ShadowStatsCollector:
    """Accumulates comparison results and computes aggregate statistics.

    Thread-safe via simple list append. For concurrent use across threads,
    callers should synchronize externally or use one collector per thread
    and merge the results.

    Example
    -------
    >>> collector = ShadowStatsCollector()
    >>> collector.add(comparison_result)
    >>> stats = collector.compute()
    >>> stats.total_runs
    1
    """

    def __init__(self) -> None:
        self._results: list[ComparisonResult] = []

    def add(self, result: ComparisonResult) -> None:
        """Append a single comparison result to the collector.

        Parameters
        ----------
        result:
            A ``ComparisonResult`` from ``ShadowComparator.compare()``.
        """
        self._results.append(result)

    def add_many(self, results: list[ComparisonResult]) -> None:
        """Append multiple comparison results in one call.

        Parameters
        ----------
        results:
            A list of ``ComparisonResult`` instances.
        """
        self._results.extend(results)

    def reset(self) -> None:
        """Clear all accumulated results."""
        self._results.clear()

    @property
    def count(self) -> int:
        """Number of results currently in the collector."""
        return len(self._results)

    def compute(self) -> ShadowStats:
        """Compute and return aggregate statistics over all accumulated results.

        Returns
        -------
        ShadowStats:
            Summary statistics. When no results have been added, returns a
            zeroed-out ``ShadowStats`` instance.
        """
        if not self._results:
            return ShadowStats(
                total_runs=0,
                divergence_count=0,
                avg_divergence_score=0.0,
                max_divergence_score=0.0,
                min_divergence_score=0.0,
                high_risk_count=0,
                medium_risk_count=0,
                low_risk_count=0,
            )

        scores = [r.deviation_score for r in self._results]
        divergence_count = sum(1 for r in self._results if not r.agreed)
        high_risk = sum(1 for r in self._results if r.risk_level == RiskLevel.HIGH)
        medium_risk = sum(1 for r in self._results if r.risk_level == RiskLevel.MEDIUM)
        low_risk = sum(1 for r in self._results if r.risk_level == RiskLevel.LOW)

        return ShadowStats(
            total_runs=len(self._results),
            divergence_count=divergence_count,
            avg_divergence_score=sum(scores) / len(scores),
            max_divergence_score=max(scores),
            min_divergence_score=min(scores),
            high_risk_count=high_risk,
            medium_risk_count=medium_risk,
            low_risk_count=low_risk,
        )

    def deviation_scores(self) -> list[float]:
        """Return a list of all deviation scores in collection order."""
        return [r.deviation_score for r in self._results]


# ---------------------------------------------------------------------------
# Chi-squared test for categorical divergence
# ---------------------------------------------------------------------------


def chi_squared_divergence(
    shadow_counts: Counter[str],
    actual_counts: Counter[str],
) -> tuple[float, float]:
    """Compute chi-squared statistic for categorical divergence.

    Compares the distribution of output categories between shadow and
    production runs. A high chi-squared value indicates that the shadow
    agent's output distribution differs significantly from production.

    Uses a simplified Pearson chi-squared test assuming equal expected
    proportions from the production distribution.

    Parameters
    ----------
    shadow_counts:
        Counter mapping output category strings to counts from shadow runs.
    actual_counts:
        Counter mapping output category strings to counts from production runs.

    Returns
    -------
    tuple[float, float]:
        ``(chi_squared_statistic, degrees_of_freedom)`` where degrees of
        freedom = len(categories) - 1. Returns ``(0.0, 0.0)`` when there
        is insufficient data.

    Example
    -------
    >>> from collections import Counter
    >>> shadow = Counter({"approve": 80, "deny": 20})
    >>> actual = Counter({"approve": 90, "deny": 10})
    >>> chi_sq, dof = chi_squared_divergence(shadow, actual)
    """
    all_categories = set(shadow_counts.keys()) | set(actual_counts.keys())
    if len(all_categories) < 2:
        return 0.0, 0.0

    total_shadow = sum(shadow_counts.values())
    total_actual = sum(actual_counts.values())
    if total_shadow == 0 or total_actual == 0:
        return 0.0, 0.0

    chi_squared = 0.0
    for category in all_categories:
        observed = shadow_counts.get(category, 0)
        # Expected: proportion from actual scaled to shadow total
        actual_proportion = actual_counts.get(category, 0) / total_actual
        expected = total_shadow * actual_proportion
        if expected > 0:
            chi_squared += (observed - expected) ** 2 / expected

    degrees_of_freedom = float(len(all_categories) - 1)
    return chi_squared, degrees_of_freedom
