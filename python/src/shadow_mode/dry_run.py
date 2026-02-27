# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation

"""GovernanceDryRun — evaluate actions against governance rules without enforcing them.

Replays a sequence of agent actions through a governance configuration and
reports what would have been allowed or denied, along with estimated cost
savings from the denied actions.

This is a read-only simulation. No governance state is modified. No side
effects are produced. Results are purely informational for human review.

Typical usage::

    from shadow_mode.dry_run import DryRunAction, GovernanceDryRun

    engine = GovernanceDryRun(trust_level=2, daily_budget=10.0)

    actions = [
        DryRunAction("a1", "tool_call", "web_search", estimated_cost=0.50, required_trust_level=1),
        DryRunAction("a2", "tool_call", "send_email", estimated_cost=1.00, required_trust_level=3),
    ]

    result = engine.evaluate(actions)
    print(f"Block rate: {result.estimated_block_rate:.1%}")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class DryRunAction:
    """A single agent action submitted for dry-run evaluation.

    Attributes:
        action_id: Unique identifier for this action within the trace.
        action_type: Category of action (e.g. ``"tool_call"``, ``"api_request"``).
        tool_name: Name of the tool or capability being invoked.
        estimated_cost: Estimated monetary cost in USD for this action.
        required_trust_level: Minimum trust level required to execute this action.
    """

    action_id: str
    action_type: str
    tool_name: str
    estimated_cost: float
    required_trust_level: int


@dataclass(frozen=True)
class DryRunDenial:
    """Record of a single action that would have been denied by governance.

    Attributes:
        action_id: Identifier of the denied action.
        reason: Human-readable explanation of why the action was denied.
        category: Denial category — one of ``"trust"``, ``"budget"``,
            ``"consent"``, or ``"policy"``.
    """

    action_id: str
    reason: str
    category: str  # "trust" | "budget" | "consent" | "policy"


@dataclass(frozen=True)
class DryRunResult:
    """Aggregated result of a governance dry-run evaluation.

    Attributes:
        total_actions: Total number of actions evaluated.
        allowed_count: Number of actions that would have been allowed.
        denied_count: Number of actions that would have been denied.
        denial_reasons: Ordered sequence of denial records.
        estimated_block_rate: Fraction of actions denied, in [0.0, 1.0].
        estimated_cost_savings: Total USD cost of denied actions (not incurred).
    """

    total_actions: int
    allowed_count: int
    denied_count: int
    denial_reasons: Sequence[DryRunDenial]
    estimated_block_rate: float
    estimated_cost_savings: float


class GovernanceDryRun:
    """Evaluate a sequence of actions against governance rules without enforcement.

    The engine applies trust-level gating and budget ceiling checks in the
    order actions arrive, mirroring how a live governance layer would process
    them sequentially.

    Trust changes are NEVER automatic. The ``trust_level`` is a static value
    set by the operator for simulation purposes.

    Args:
        trust_level: Current trust level assigned to the agent being evaluated.
            Actions requiring a higher level will be denied with category
            ``"trust"``. Defaults to ``2``.
        daily_budget: Maximum cumulative spend (USD) allowed in one day.
            Once exceeded, further actions are denied with category
            ``"budget"``. Defaults to ``10.0``.
        require_consent: When ``True``, all actions are flagged as denied with
            category ``"consent"`` unless trust_level is sufficiently high to
            waive consent. Currently a placeholder for consent-gate evaluation.
            Defaults to ``False``.

    Example::

        engine = GovernanceDryRun(trust_level=2, daily_budget=5.0)
        result = engine.evaluate(actions)
        print(result.denied_count, "actions would be blocked")
    """

    def __init__(
        self,
        trust_level: int = 2,
        daily_budget: float = 10.0,
        require_consent: bool = False,
    ) -> None:
        self._trust_level = trust_level
        self._daily_budget = daily_budget
        self._require_consent = require_consent

    def evaluate(self, actions: Sequence[DryRunAction]) -> DryRunResult:
        """Evaluate a sequence of actions without enforcing governance.

        Processes each action in order. Trust-level violations are checked
        first; budget overflow is checked second. Denied actions do not
        accumulate against the running budget total (their cost is saved,
        not spent).

        Args:
            actions: Ordered sequence of ``DryRunAction`` objects representing
                an agent execution trace.

        Returns:
            A ``DryRunResult`` summarising what would have been allowed,
            denied, and the estimated cost savings from blocked actions.
        """
        denials: list[DryRunDenial] = []
        running_cost: float = 0.0
        cost_savings: float = 0.0

        for action in actions:
            # Trust-level gate — checked before spending budget
            if action.required_trust_level > self._trust_level:
                denials.append(
                    DryRunDenial(
                        action_id=action.action_id,
                        reason=(
                            f"Requires trust L{action.required_trust_level}, "
                            f"agent is L{self._trust_level}"
                        ),
                        category="trust",
                    )
                )
                cost_savings += action.estimated_cost
                continue

            # Consent gate — placeholder; all non-trusted actions flagged
            if self._require_consent and self._trust_level < 3:
                denials.append(
                    DryRunDenial(
                        action_id=action.action_id,
                        reason=(
                            f"Consent required for trust L{self._trust_level}; "
                            "operator has not granted consent waiver"
                        ),
                        category="consent",
                    )
                )
                cost_savings += action.estimated_cost
                continue

            # Budget ceiling gate — accumulate cost, deny if over limit
            running_cost += action.estimated_cost
            if running_cost > self._daily_budget:
                denials.append(
                    DryRunDenial(
                        action_id=action.action_id,
                        reason=(
                            f"Daily budget exceeded: "
                            f"${running_cost:.2f} > ${self._daily_budget:.2f}"
                        ),
                        category="budget",
                    )
                )
                cost_savings += action.estimated_cost
                # Revert the spend so subsequent actions see accurate cumulative total
                running_cost -= action.estimated_cost
                continue

        total_actions = len(actions)
        denied_count = len(denials)
        allowed_count = total_actions - denied_count
        block_rate = denied_count / total_actions if total_actions > 0 else 0.0

        return DryRunResult(
            total_actions=total_actions,
            allowed_count=allowed_count,
            denied_count=denied_count,
            denial_reasons=tuple(denials),
            estimated_block_rate=block_rate,
            estimated_cost_savings=cost_savings,
        )
