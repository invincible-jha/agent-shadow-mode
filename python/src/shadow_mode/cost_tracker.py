# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""
Cost tracking for shadow mode runs.

Tracks token usage and estimated monetary cost for both shadow and production
agent runs. Allows operators to assess whether running shadow mode is cost-
justified relative to the divergence rate it surfaces.

Pricing is provided by the caller at construction time — this module makes no
assumptions about specific model providers or current pricing. Operators supply
a ``ModelPricing`` entry for each model they use.

Example
-------
>>> tracker = CostTracker()
>>> tracker.add_model_pricing("gpt-4o", input_cost_per_1k=0.005, output_cost_per_1k=0.015)
>>> tracker.record_shadow_run("gpt-4o", input_tokens=1200, output_tokens=300)
>>> tracker.record_production_run("gpt-4o", input_tokens=1100, output_tokens=280)
>>> report = tracker.generate_report(divergence_pct=12.0)
>>> print(report)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

__all__ = ["ModelPricing", "TokenUsage", "CostTracker", "CostReport"]


class ModelPricing(NamedTuple):
    """Per-model token pricing configuration.

    Attributes:
        model_name:            Identifier for this model.
        input_cost_per_1k:     Cost in USD per 1,000 input (prompt) tokens.
        output_cost_per_1k:    Cost in USD per 1,000 output (completion) tokens.
    """

    model_name: str
    input_cost_per_1k: float
    output_cost_per_1k: float


@dataclass
class TokenUsage:
    """Accumulated token usage for a run type.

    Attributes:
        input_tokens:  Total input (prompt) tokens consumed.
        output_tokens: Total output (completion) tokens consumed.
        run_count:     Number of runs contributing to these totals.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    run_count: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        """Accumulate usage from a single run."""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.run_count += 1

    def cost(self, pricing: ModelPricing) -> float:
        """Compute estimated cost in USD using *pricing*.

        Parameters
        ----------
        pricing:
            The ``ModelPricing`` for the model that produced this usage.

        Returns
        -------
        float:
            Estimated cost in USD.
        """
        input_cost = (self.input_tokens / 1000) * pricing.input_cost_per_1k
        output_cost = (self.output_tokens / 1000) * pricing.output_cost_per_1k
        return input_cost + output_cost


@dataclass(frozen=True)
class CostReport:
    """Cost comparison report between shadow and production runs.

    Attributes:
        shadow_tokens_total:      Total tokens consumed by all shadow runs.
        production_tokens_total:  Total tokens consumed by production runs.
        shadow_cost_usd:          Estimated USD cost of shadow runs.
        production_cost_usd:      Estimated USD cost of production runs.
        shadow_run_count:         Number of shadow runs recorded.
        production_run_count:     Number of production runs recorded.
        divergence_pct:           Divergence rate as a percentage (0–100).
        summary:                  Human-readable summary string.
    """

    shadow_tokens_total: int
    production_tokens_total: int
    shadow_cost_usd: float
    production_cost_usd: float
    shadow_run_count: int
    production_run_count: int
    divergence_pct: float
    summary: str

    @property
    def total_overhead_usd(self) -> float:
        """Additional cost of shadow mode (shadow - production)."""
        return self.shadow_cost_usd - self.production_cost_usd

    @property
    def cost_multiplier(self) -> float:
        """Ratio of shadow cost to production cost.

        Returns 0.0 when production cost is zero (avoids divide-by-zero).
        """
        if self.production_cost_usd == 0.0:
            return 0.0
        return self.shadow_cost_usd / self.production_cost_usd


class CostTracker:
    """Tracks token usage and estimated cost for shadow and production runs.

    Pricing is registered per model. If a run uses a model that has no
    registered pricing, the cost is recorded as 0.0 USD.

    Parameters
    ----------
    default_model:
        Optional default model name used when recording runs without an
        explicit model name.

    Example
    -------
    >>> tracker = CostTracker(default_model="gpt-4o")
    >>> tracker.add_model_pricing("gpt-4o", input_cost_per_1k=0.005, output_cost_per_1k=0.015)
    >>> tracker.record_shadow_run(input_tokens=1000, output_tokens=200)
    >>> tracker.record_production_run(input_tokens=950, output_tokens=190)
    >>> report = tracker.generate_report(divergence_pct=8.0)
    >>> print(report.summary)
    """

    def __init__(self, default_model: str = "unknown") -> None:
        self._default_model = default_model
        self._pricing: dict[str, ModelPricing] = {}
        # Per-model usage: model_name -> (shadow_usage, production_usage)
        self._shadow_usage: dict[str, TokenUsage] = {}
        self._production_usage: dict[str, TokenUsage] = {}

    def add_model_pricing(
        self,
        model_name: str,
        input_cost_per_1k: float,
        output_cost_per_1k: float,
    ) -> None:
        """Register pricing for a model.

        Parameters
        ----------
        model_name:
            Model identifier (e.g. ``"gpt-4o"``, ``"claude-3-haiku"``).
        input_cost_per_1k:
            USD cost per 1,000 input tokens.
        output_cost_per_1k:
            USD cost per 1,000 output tokens.
        """
        self._pricing[model_name] = ModelPricing(
            model_name=model_name,
            input_cost_per_1k=input_cost_per_1k,
            output_cost_per_1k=output_cost_per_1k,
        )

    def record_shadow_run(
        self,
        input_tokens: int,
        output_tokens: int,
        model_name: str | None = None,
    ) -> None:
        """Record token usage from one shadow agent run.

        Parameters
        ----------
        input_tokens:
            Number of input tokens consumed by the shadow agent.
        output_tokens:
            Number of output tokens produced by the shadow agent.
        model_name:
            Model used. Defaults to the tracker's ``default_model``.
        """
        model = model_name or self._default_model
        if model not in self._shadow_usage:
            self._shadow_usage[model] = TokenUsage()
        self._shadow_usage[model].add(input_tokens, output_tokens)

    def record_production_run(
        self,
        input_tokens: int,
        output_tokens: int,
        model_name: str | None = None,
    ) -> None:
        """Record token usage from one production agent run.

        Parameters
        ----------
        input_tokens:
            Number of input tokens consumed by the production agent.
        output_tokens:
            Number of output tokens produced by the production agent.
        model_name:
            Model used. Defaults to the tracker's ``default_model``.
        """
        model = model_name or self._default_model
        if model not in self._production_usage:
            self._production_usage[model] = TokenUsage()
        self._production_usage[model].add(input_tokens, output_tokens)

    def total_shadow_cost_usd(self) -> float:
        """Return total estimated USD cost of all shadow runs."""
        total = 0.0
        for model, usage in self._shadow_usage.items():
            pricing = self._pricing.get(model)
            if pricing:
                total += usage.cost(pricing)
        return total

    def total_production_cost_usd(self) -> float:
        """Return total estimated USD cost of all production runs."""
        total = 0.0
        for model, usage in self._production_usage.items():
            pricing = self._pricing.get(model)
            if pricing:
                total += usage.cost(pricing)
        return total

    def total_shadow_tokens(self) -> int:
        """Return total tokens (input + output) across all shadow runs."""
        return sum(
            u.input_tokens + u.output_tokens for u in self._shadow_usage.values()
        )

    def total_production_tokens(self) -> int:
        """Return total tokens (input + output) across all production runs."""
        return sum(
            u.input_tokens + u.output_tokens for u in self._production_usage.values()
        )

    def shadow_run_count(self) -> int:
        """Return total number of shadow runs recorded."""
        return sum(u.run_count for u in self._shadow_usage.values())

    def production_run_count(self) -> int:
        """Return total number of production runs recorded."""
        return sum(u.run_count for u in self._production_usage.values())

    def generate_report(self, divergence_pct: float = 0.0) -> CostReport:
        """Generate a cost comparison report.

        Parameters
        ----------
        divergence_pct:
            The observed divergence percentage between shadow and production
            (0.0–100.0). Included in the summary string for context.

        Returns
        -------
        CostReport:
            Full structured cost comparison.
        """
        shadow_cost = self.total_shadow_cost_usd()
        production_cost = self.total_production_cost_usd()
        shadow_runs = self.shadow_run_count()
        production_runs = self.production_run_count()

        summary = (
            f"Shadow run cost ${shadow_cost:.4f} "
            f"vs production ${production_cost:.4f}, "
            f"divergence: {divergence_pct:.1f}%"
        )

        return CostReport(
            shadow_tokens_total=self.total_shadow_tokens(),
            production_tokens_total=self.total_production_tokens(),
            shadow_cost_usd=shadow_cost,
            production_cost_usd=production_cost,
            shadow_run_count=shadow_runs,
            production_run_count=production_runs,
            divergence_pct=divergence_pct,
            summary=summary,
        )
