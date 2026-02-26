# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""ShadowComparator — compare a shadow recommendation to an actual decision.

Comparison is pure computation — no external calls, no side effects, no state.
The comparator operates on structured dict outputs and computes:

- Agreement: whether the core decision matched
- Deviation score: quantified difference in [0.0, 1.0]
- Individual deviations: field-level diffs with path, shadow value, actual value
- Risk level: qualitative risk derived from deviation magnitude and field importance

High-priority fields (configurable) carry more weight in deviation scoring.
"""

from __future__ import annotations

from typing import Any

from .types import (
    ActualDecision,
    AgreementLevel,
    ComparisonResult,
    Deviation,
    RiskLevel,
    ShadowDecision,
)


# Default set of field paths considered high-priority for risk assessment.
# Differences in these fields are weighted more heavily in deviation scoring.
DEFAULT_HIGH_PRIORITY_FIELDS: frozenset[str] = frozenset(
    {
        "action",
        "decision",
        "approved",
        "blocked",
        "result",
        "status",
    }
)


class ShadowComparator:
    """Compares a shadow decision to an actual production decision.

    Produces a ``ComparisonResult`` for each pair. The comparison is
    synchronous and purely functional — it inspects the output dicts,
    computes field-level diffs, and calculates a deviation score.

    Args:
        high_priority_fields: Set of top-level field names that are treated
            as high-priority when computing the deviation score and risk level.
            Defaults to ``DEFAULT_HIGH_PRIORITY_FIELDS``.
        agreement_threshold: Deviation score at or below which the comparison
            is considered agreed. Defaults to 0.0 (exact match required for
            full agreement; partial agreement allows up to this threshold).

    Example::

        comparator = ShadowComparator()
        result = comparator.compare(shadow_decision, actual_decision)
        print(result.agreed, result.deviation_score, result.risk_level)
    """

    def __init__(
        self,
        high_priority_fields: frozenset[str] | None = None,
        agreement_threshold: float = 0.1,
    ) -> None:
        if not 0.0 <= agreement_threshold <= 1.0:
            raise ValueError("agreement_threshold must be in [0.0, 1.0].")
        self._high_priority_fields = high_priority_fields or DEFAULT_HIGH_PRIORITY_FIELDS
        self._agreement_threshold = agreement_threshold

    def compare(
        self,
        shadow: ShadowDecision,
        actual: ActualDecision,
    ) -> ComparisonResult:
        """Compare shadow output to actual output and return a scored result.

        Args:
            shadow: The shadow agent's decision (what it would have done).
            actual: The production agent's actual decision.

        Returns:
            ``ComparisonResult`` with agreement, deviation score, field-level
            diffs, and risk level.

        Raises:
            ValueError: If ``shadow.decision_id != actual.decision_id``.
        """
        if shadow.decision_id != actual.decision_id:
            raise ValueError(
                f"decision_id mismatch: shadow={shadow.decision_id!r} "
                f"actual={actual.decision_id!r}. Both must share the same ID."
            )

        deviations = _find_deviations(shadow.output, actual.output)
        deviation_score = _compute_deviation_score(deviations, self._high_priority_fields)
        agreed = deviation_score <= self._agreement_threshold
        agreement_level = _classify_agreement(deviation_score, self._agreement_threshold)
        risk_level = _assess_risk(deviations, deviation_score, self._high_priority_fields)

        return ComparisonResult(
            decision_id=shadow.decision_id,
            agreed=agreed,
            agreement_level=agreement_level,
            deviation_score=round(deviation_score, 6),
            deviations=deviations,
            risk_level=risk_level,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_deviations(
    shadow_output: dict[str, Any],
    actual_output: dict[str, Any],
    path_prefix: str = "",
) -> list[Deviation]:
    """Recursively find field-level deviations between two output dicts.

    Args:
        shadow_output: Shadow agent output (or nested sub-dict).
        actual_output: Actual agent output (or nested sub-dict).
        path_prefix: Dot-separated prefix for nested field paths.

    Returns:
        List of ``Deviation`` objects, one per differing field.
    """
    deviations: list[Deviation] = []
    all_keys = set(shadow_output.keys()) | set(actual_output.keys())

    for key in sorted(all_keys):
        field_path = f"{path_prefix}.{key}" if path_prefix else key
        shadow_value = shadow_output.get(key)
        actual_value = actual_output.get(key)

        if key not in shadow_output:
            deviations.append(
                Deviation(
                    field_path=field_path,
                    shadow_value=None,
                    actual_value=actual_value,
                    description=f"Field '{field_path}' present in actual but missing from shadow.",
                )
            )
        elif key not in actual_output:
            deviations.append(
                Deviation(
                    field_path=field_path,
                    shadow_value=shadow_value,
                    actual_value=None,
                    description=f"Field '{field_path}' present in shadow but missing from actual.",
                )
            )
        elif isinstance(shadow_value, dict) and isinstance(actual_value, dict):
            # Recurse into nested dicts.
            nested = _find_deviations(shadow_value, actual_value, path_prefix=field_path)
            deviations.extend(nested)
        elif shadow_value != actual_value:
            deviations.append(
                Deviation(
                    field_path=field_path,
                    shadow_value=shadow_value,
                    actual_value=actual_value,
                    description=(
                        f"Field '{field_path}' differs: "
                        f"shadow={shadow_value!r}, actual={actual_value!r}."
                    ),
                )
            )

    return deviations


def _compute_deviation_score(
    deviations: list[Deviation],
    high_priority_fields: frozenset[str],
) -> float:
    """Compute a normalised deviation score in [0.0, 1.0].

    High-priority field deviations are weighted at 2x compared to other fields.
    Score is capped at 1.0 regardless of the number of deviations.

    Args:
        deviations: List of field-level deviations.
        high_priority_fields: Set of top-level field names with higher weight.

    Returns:
        Float in [0.0, 1.0]. 0.0 = no deviations, 1.0 = maximum deviation.
    """
    if not deviations:
        return 0.0

    total_weight = 0.0
    for deviation in deviations:
        top_level_field = deviation.field_path.split(".")[0]
        weight = 2.0 if top_level_field in high_priority_fields else 1.0
        total_weight += weight

    # Normalise against expected weight for the number of deviations.
    # A single high-priority deviation in a 1-field output = score of 1.0.
    normaliser = max(total_weight, 1.0)
    raw_score = total_weight / normaliser

    return min(raw_score, 1.0)


def _classify_agreement(
    deviation_score: float,
    threshold: float,
) -> AgreementLevel:
    """Map a deviation score to a qualitative agreement level.

    Args:
        deviation_score: Float in [0.0, 1.0].
        threshold: Maximum score for full agreement.

    Returns:
        ``AgreementLevel.FULL``, ``PARTIAL``, or ``NONE``.
    """
    if deviation_score == 0.0:
        return AgreementLevel.FULL
    if deviation_score <= threshold:
        return AgreementLevel.PARTIAL
    return AgreementLevel.NONE


def _assess_risk(
    deviations: list[Deviation],
    deviation_score: float,
    high_priority_fields: frozenset[str],
) -> RiskLevel:
    """Assess risk level based on deviation score and high-priority field hits.

    Args:
        deviations: List of field-level deviations.
        deviation_score: Overall deviation score.
        high_priority_fields: High-priority field names.

    Returns:
        ``RiskLevel.LOW``, ``MEDIUM``, or ``HIGH``.
    """
    has_high_priority_deviation = any(
        deviation.field_path.split(".")[0] in high_priority_fields
        for deviation in deviations
    )

    if has_high_priority_deviation or deviation_score >= 0.5:
        return RiskLevel.HIGH
    if deviation_score > 0.0:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW
