# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation

"""A/B testing engine for governance configurations.

Runs the same sequence of agent actions through two distinct governance
configurations (Config A and Config B) and produces a side-by-side comparison
of their dry-run results.

This is read-only simulation. No governance state is modified. No side
effects are produced. The comparison is purely informational for human review.

Typical usage::

    from shadow_mode.ab_testing import ABTestEngine, GovernanceConfig

    config_a = GovernanceConfig(label="strict", trust_level=1, daily_budget=5.0)
    config_b = GovernanceConfig(label="permissive", trust_level=3, daily_budget=20.0)

    engine = ABTestEngine(config_a=config_a, config_b=config_b)
    result = engine.run(actions)
    print(result.summary_line)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .dry_run import DryRunAction, DryRunResult, GovernanceDryRun


@dataclass(frozen=True)
class GovernanceConfig:
    """A named governance configuration for use in A/B testing.

    Attributes:
        label: Short human-readable label identifying this configuration,
            e.g. ``"strict-l1"`` or ``"permissive-l3"``.
        trust_level: Static trust level to apply. Trust changes are NEVER
            automatic — this value is set by the operator.
        daily_budget: Daily spending ceiling in USD.
        require_consent: When ``True``, all sub-L3 actions require explicit
            consent. Passed directly to ``GovernanceDryRun``.
    """

    label: str
    trust_level: int = 2
    daily_budget: float = 10.0
    require_consent: bool = False


@dataclass(frozen=True)
class ABTestResult:
    """Side-by-side comparison of two governance configurations on the same actions.

    Attributes:
        config_a_label: Label from the first governance configuration.
        config_b_label: Label from the second governance configuration.
        result_a: Dry-run result for Config A.
        result_b: Dry-run result for Config B.
        additional_allowed_in_b: Number of actions allowed by B but denied by A
            (Config B is more permissive for these actions).
        additional_denied_in_b: Number of actions denied by B but allowed by A
            (Config B is more restrictive for these actions).
        cost_delta: Difference in estimated cost savings: ``savings_b - savings_a``.
            Positive means B saves more (blocks more costly actions).
        summary_line: Single-line human-readable comparison string.
    """

    config_a_label: str
    config_b_label: str
    result_a: DryRunResult
    result_b: DryRunResult
    additional_allowed_in_b: int
    additional_denied_in_b: int
    cost_delta: float
    summary_line: str


class ABTestEngine:
    """Run the same agent action trace through two governance configurations.

    Both configurations are evaluated independently using ``GovernanceDryRun``.
    The engine then produces a structured comparison so operators can understand
    the practical difference between configurations before making a manual
    trust-level or budget decision.

    Args:
        config_a: First governance configuration (treated as the baseline).
        config_b: Second governance configuration (treated as the candidate).

    Example::

        engine = ABTestEngine(
            config_a=GovernanceConfig("current", trust_level=2, daily_budget=10.0),
            config_b=GovernanceConfig("proposed", trust_level=3, daily_budget=15.0),
        )
        result = engine.run(actions)
        print(result.summary_line)
    """

    def __init__(
        self,
        config_a: GovernanceConfig,
        config_b: GovernanceConfig,
    ) -> None:
        self._config_a = config_a
        self._config_b = config_b

    def run(self, actions: Sequence[DryRunAction]) -> ABTestResult:
        """Evaluate actions under both configurations and return a comparison.

        Actions are evaluated independently under Config A and Config B.
        The results are then compared to surface net differences in allow/deny
        decisions and cost savings.

        Args:
            actions: Ordered sequence of ``DryRunAction`` objects representing
                the agent execution trace to evaluate.

        Returns:
            An ``ABTestResult`` containing both dry-run results and a
            structured comparison between them.
        """
        engine_a = GovernanceDryRun(
            trust_level=self._config_a.trust_level,
            daily_budget=self._config_a.daily_budget,
            require_consent=self._config_a.require_consent,
        )
        engine_b = GovernanceDryRun(
            trust_level=self._config_b.trust_level,
            daily_budget=self._config_b.daily_budget,
            require_consent=self._config_b.require_consent,
        )

        result_a = engine_a.evaluate(actions)
        result_b = engine_b.evaluate(actions)

        # Compute per-action diffs by building denial sets
        denied_ids_a: set[str] = {denial.action_id for denial in result_a.denial_reasons}
        denied_ids_b: set[str] = {denial.action_id for denial in result_b.denial_reasons}

        # Actions allowed by B that were denied by A (B is more permissive here)
        additional_allowed_in_b = len(denied_ids_a - denied_ids_b)
        # Actions denied by B that were allowed by A (B is more restrictive here)
        additional_denied_in_b = len(denied_ids_b - denied_ids_a)

        cost_delta = result_b.estimated_cost_savings - result_a.estimated_cost_savings

        summary_line = self._build_summary_line(
            result_a=result_a,
            result_b=result_b,
            additional_allowed_in_b=additional_allowed_in_b,
            additional_denied_in_b=additional_denied_in_b,
            cost_delta=cost_delta,
        )

        return ABTestResult(
            config_a_label=self._config_a.label,
            config_b_label=self._config_b.label,
            result_a=result_a,
            result_b=result_b,
            additional_allowed_in_b=additional_allowed_in_b,
            additional_denied_in_b=additional_denied_in_b,
            cost_delta=cost_delta,
            summary_line=summary_line,
        )

    def _build_summary_line(
        self,
        result_a: DryRunResult,
        result_b: DryRunResult,
        additional_allowed_in_b: int,
        additional_denied_in_b: int,
        cost_delta: float,
    ) -> str:
        """Construct a one-line human-readable comparison summary.

        Args:
            result_a: Dry-run result for Config A.
            result_b: Dry-run result for Config B.
            additional_allowed_in_b: Actions newly allowed under B.
            additional_denied_in_b: Actions newly denied under B.
            cost_delta: Difference in cost savings (B minus A).

        Returns:
            A single-line summary string suitable for log output or CI comments.
        """
        direction = "saves" if cost_delta >= 0 else "costs"
        delta_abs = abs(cost_delta)

        return (
            f"A({self._config_a.label}): "
            f"{result_a.allowed_count}/{result_a.total_actions} allowed, "
            f"block rate {result_a.estimated_block_rate:.1%} | "
            f"B({self._config_b.label}): "
            f"{result_b.allowed_count}/{result_b.total_actions} allowed, "
            f"block rate {result_b.estimated_block_rate:.1%} | "
            f"B vs A: +{additional_allowed_in_b} allowed, "
            f"+{additional_denied_in_b} denied, "
            f"{direction} ${delta_abs:.2f}"
        )
