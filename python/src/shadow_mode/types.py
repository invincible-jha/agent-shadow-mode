# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""Shared Pydantic v2 types for agent-shadow-mode.

All data flowing through shadow mode uses these immutable, validated types.
No contextual user data or session state is stored here — only structured
decision outputs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class AgreementLevel(str, Enum):
    """Qualitative agreement level between shadow and actual decisions."""

    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"


class RiskLevel(str, Enum):
    """Risk level derived from comparison deviation."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ShadowDecision(BaseModel):
    """The output of a shadow agent execution.

    Captured by ``ShadowRunner.shadow_execute()``. The shadow agent ran
    without side effects; this is what it *would have* done.

    Attributes:
        decision_id: Unique identifier correlating shadow to actual decision.
        input_hash: SHA-256 hex digest of the serialised input (no raw input stored).
        output: Structured output from the shadow agent.
        timestamp: UTC timestamp of the shadow execution.
        adapter_name: Name of the adapter used to intercept side effects.
        metadata: Optional adapter-specific metadata (tool call counts, etc.).
    """

    decision_id: str = Field(description="Unique identifier correlating shadow to actual.")
    input_hash: str = Field(
        description="SHA-256 hex digest of the serialised input. Raw input is not stored."
    )
    output: dict[str, Any] = Field(description="Structured output from the shadow agent.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the shadow execution.",
    )
    adapter_name: str = Field(
        default="generic",
        description="Name of the adapter used to intercept side effects.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional adapter-specific metadata.",
    )


class ActualDecision(BaseModel):
    """The real decision made by the production agent.

    Recorded after the production agent has acted. Used as the ground truth
    when computing comparison results.

    Attributes:
        decision_id: Must match the corresponding ``ShadowDecision.decision_id``.
        output: Structured output from the production agent.
        timestamp: UTC timestamp of the actual decision.
        metadata: Optional production-side metadata.
    """

    decision_id: str = Field(description="Must match the corresponding ShadowDecision.decision_id.")
    output: dict[str, Any] = Field(description="Structured output from the production agent.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the actual decision.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional production-side metadata.",
    )


class Deviation(BaseModel):
    """A single field-level deviation between shadow and actual outputs.

    Attributes:
        field_path: Dot-separated path to the differing field, e.g. ``"action.type"``.
        shadow_value: Value produced by the shadow agent.
        actual_value: Value produced by the production agent.
        description: Human-readable summary of the difference.
    """

    field_path: str = Field(description="Dot-separated path to the differing field.")
    shadow_value: Any = Field(description="Value produced by the shadow agent.")
    actual_value: Any = Field(description="Value produced by the production agent.")
    description: str = Field(description="Human-readable summary of the difference.")


class ComparisonResult(BaseModel):
    """Result of comparing one shadow decision to one actual decision.

    Produced by ``ShadowComparator.compare()``.

    Attributes:
        decision_id: Shared identifier linking shadow and actual.
        agreed: True if shadow and actual outputs are considered equivalent.
        agreement_level: Qualitative agreement level.
        deviation_score: Float in [0.0, 1.0]. 0.0 = identical, 1.0 = completely different.
        deviations: List of individual field-level differences.
        risk_level: Risk level derived from deviation magnitude and field importance.
        notes: Optional free-text notes from the comparator.
    """

    decision_id: str
    agreed: bool = Field(description="True if shadow and actual outputs are considered equivalent.")
    agreement_level: AgreementLevel
    deviation_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Float in [0.0, 1.0]. 0.0 = identical, 1.0 = completely different.",
    )
    deviations: list[Deviation] = Field(default_factory=list)
    risk_level: RiskLevel
    notes: str | None = None

    @model_validator(mode="after")
    def validate_agreement_consistency(self) -> "ComparisonResult":
        """Ensure agreed flag is consistent with deviation_score."""
        if self.agreed and self.deviation_score > 0.0:
            # Partial agreement is acceptable — agreed means the core decision matched
            pass
        if not self.agreed and self.deviation_score == 0.0:
            raise ValueError(
                "deviation_score is 0.0 but agreed is False — outputs are identical."
            )
        return self


class ConfidenceReport(BaseModel):
    """Aggregated confidence report across many comparison results.

    Produced by ``ConfidenceScorer.score()``. The ``recommendation`` field
    is a plain human-readable string — it is never an API call or automatic
    state change.

    Attributes:
        total_comparisons: Total number of comparisons included.
        agreement_count: Number of comparisons where shadow agreed with actual.
        disagreement_count: Number of comparisons where shadow disagreed.
        agreement_rate: Float in [0.0, 1.0] — agreement_count / total_comparisons.
        average_deviation: Mean deviation_score across all comparisons.
        worst_deviation: Maximum deviation_score observed.
        risk_score: Float in [0.0, 1.0] — aggregate risk across all comparisons.
        high_risk_count: Number of HIGH risk comparisons.
        recommendation: Human-readable advisory string. NOT an API call.
    """

    total_comparisons: int = Field(ge=0)
    agreement_count: int = Field(ge=0)
    disagreement_count: int = Field(ge=0)
    agreement_rate: float = Field(ge=0.0, le=1.0)
    average_deviation: float = Field(ge=0.0, le=1.0)
    worst_deviation: float = Field(ge=0.0, le=1.0)
    risk_score: float = Field(ge=0.0, le=1.0)
    high_risk_count: int = Field(ge=0)
    recommendation: str = Field(
        description=(
            "Human-readable advisory string. "
            "Example: 'Based on 95% agreement over 200 decisions, consider promoting to L3.' "
            "This is NOT an API call and does NOT change any trust level automatically."
        )
    )

    @model_validator(mode="after")
    def validate_counts(self) -> "ConfidenceReport":
        if self.agreement_count + self.disagreement_count != self.total_comparisons:
            raise ValueError(
                "agreement_count + disagreement_count must equal total_comparisons."
            )
        return self
