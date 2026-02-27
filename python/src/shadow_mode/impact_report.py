# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation

"""ImpactReporter — render governance dry-run results as markdown or JSON.

Produces formatted reports from ``DryRunResult`` and ``ABTestResult`` objects
suitable for:

- CI pipeline comments (Markdown)
- Downstream tooling and dashboards (JSON)
- Terminal output (plain text)

This module is output-only. It does not modify any governance state.

Typical usage::

    from shadow_mode.impact_report import ImpactReporter
    from shadow_mode.dry_run import GovernanceDryRun, DryRunAction

    engine = GovernanceDryRun(trust_level=2, daily_budget=10.0)
    result = engine.evaluate(actions)

    reporter = ImpactReporter()
    print(reporter.to_markdown(result, config_label="current"))
    print(reporter.to_json(result, config_label="current"))
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .ab_testing import ABTestResult
from .dry_run import DryRunResult


class ImpactReporter:
    """Generate formatted impact reports from governance dry-run results.

    Supports single-config dry-run reports and A/B comparison reports.
    All output methods return strings — no files are written by this class.

    Example::

        reporter = ImpactReporter()
        markdown = reporter.to_markdown(dry_run_result, config_label="strict-l1")
        ab_markdown = reporter.ab_to_markdown(ab_result)
    """

    # ------------------------------------------------------------------
    # Single dry-run reports
    # ------------------------------------------------------------------

    def to_markdown(
        self,
        result: DryRunResult,
        config_label: str = "governance config",
    ) -> str:
        """Render a single dry-run result as a Markdown report.

        Suitable for GitHub PR comments, issue bodies, or documentation.

        Args:
            result: The ``DryRunResult`` to render.
            config_label: Human-readable name for the governance configuration.

        Returns:
            Markdown string.
        """
        generated_at = _utc_timestamp()
        lines: list[str] = []

        lines.append(f"# Governance Dry-Run Impact Report — {config_label}")
        lines.append(f"\n_Generated: {generated_at}_\n")

        lines.append("## Summary\n")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Actions | {result.total_actions} |")
        lines.append(f"| Allowed | {result.allowed_count} |")
        lines.append(f"| Denied | {result.denied_count} |")
        lines.append(
            f"| Block Rate | {result.estimated_block_rate * 100:.1f}% |"
        )
        lines.append(
            f"| Estimated Cost Savings | ${result.estimated_cost_savings:.2f} |"
        )

        if result.denial_reasons:
            lines.append("\n## Denial Breakdown\n")
            category_counts: dict[str, int] = {}
            for denial in result.denial_reasons:
                category_counts[denial.category] = (
                    category_counts.get(denial.category, 0) + 1
                )

            lines.append("| Category | Count |")
            lines.append("|----------|-------|")
            for category, count in sorted(category_counts.items()):
                lines.append(f"| {category} | {count} |")

            lines.append("\n## Denied Actions\n")
            lines.append("| Action ID | Category | Reason |")
            lines.append("|-----------|----------|--------|")
            for denial in result.denial_reasons:
                safe_reason = denial.reason.replace("|", "\\|")
                lines.append(
                    f"| `{denial.action_id}` | {denial.category} | {safe_reason} |"
                )
        else:
            lines.append("\n> All actions would be allowed under this configuration.\n")

        return "\n".join(lines)

    def to_json(
        self,
        result: DryRunResult,
        config_label: str = "governance config",
    ) -> str:
        """Render a single dry-run result as a pretty-printed JSON string.

        Args:
            result: The ``DryRunResult`` to serialise.
            config_label: Human-readable name for the governance configuration.

        Returns:
            Pretty-printed JSON string.
        """
        payload: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "config_label": config_label,
            "summary": {
                "total_actions": result.total_actions,
                "allowed_count": result.allowed_count,
                "denied_count": result.denied_count,
                "estimated_block_rate": result.estimated_block_rate,
                "estimated_cost_savings": result.estimated_cost_savings,
            },
            "denials": [
                {
                    "action_id": denial.action_id,
                    "category": denial.category,
                    "reason": denial.reason,
                }
                for denial in result.denial_reasons
            ],
        }
        return json.dumps(payload, indent=2)

    def to_text(
        self,
        result: DryRunResult,
        config_label: str = "governance config",
    ) -> str:
        """Render a single dry-run result as plain text for CLI/log output.

        Args:
            result: The ``DryRunResult`` to render.
            config_label: Human-readable name for the governance configuration.

        Returns:
            Plain-text string.
        """
        separator = "=" * 60
        lines: list[str] = [
            separator,
            f"GOVERNANCE DRY-RUN IMPACT REPORT — {config_label.upper()}",
            f"Generated: {_utc_timestamp()}",
            separator,
            "",
            f"Total actions evaluated : {result.total_actions}",
            f"Allowed                 : {result.allowed_count}",
            f"Denied                  : {result.denied_count}",
            f"Block rate              : {result.estimated_block_rate * 100:.1f}%",
            f"Estimated cost savings  : ${result.estimated_cost_savings:.2f}",
            "",
        ]

        if result.denial_reasons:
            lines.append("DENIED ACTIONS:")
            for denial in result.denial_reasons:
                lines.append(
                    f"  [{denial.category.upper()}] {denial.action_id}: {denial.reason}"
                )
        else:
            lines.append("All actions would be allowed under this configuration.")

        lines.append("")
        lines.append(separator)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # A/B comparison reports
    # ------------------------------------------------------------------

    def ab_to_markdown(self, result: ABTestResult) -> str:
        """Render an A/B test result as a Markdown comparison report.

        Args:
            result: The ``ABTestResult`` to render.

        Returns:
            Markdown string with side-by-side comparison tables.
        """
        generated_at = _utc_timestamp()
        lines: list[str] = []

        lines.append(
            f"# Governance A/B Comparison Report — "
            f"{result.config_a_label} vs {result.config_b_label}"
        )
        lines.append(f"\n_Generated: {generated_at}_\n")

        lines.append("## Configuration Comparison\n")
        lines.append(f"| Metric | {result.config_a_label} | {result.config_b_label} |")
        lines.append("|--------|" + "--------|" * 2)
        lines.append(
            f"| Total Actions | {result.result_a.total_actions} "
            f"| {result.result_b.total_actions} |"
        )
        lines.append(
            f"| Allowed | {result.result_a.allowed_count} "
            f"| {result.result_b.allowed_count} |"
        )
        lines.append(
            f"| Denied | {result.result_a.denied_count} "
            f"| {result.result_b.denied_count} |"
        )
        lines.append(
            f"| Block Rate | {result.result_a.estimated_block_rate * 100:.1f}% "
            f"| {result.result_b.estimated_block_rate * 100:.1f}% |"
        )
        lines.append(
            f"| Cost Savings | ${result.result_a.estimated_cost_savings:.2f} "
            f"| ${result.result_b.estimated_cost_savings:.2f} |"
        )

        lines.append("\n## Delta (B vs A)\n")
        lines.append("| Delta Metric | Value |")
        lines.append("|--------------|-------|")
        lines.append(
            f"| Additional Allowed in B | {result.additional_allowed_in_b} |"
        )
        lines.append(
            f"| Additional Denied in B | {result.additional_denied_in_b} |"
        )
        cost_direction = "saves more" if result.cost_delta >= 0 else "costs more"
        lines.append(
            f"| Cost Delta (B - A) | ${result.cost_delta:+.2f} "
            f"(B {cost_direction}) |"
        )

        lines.append("\n## Summary\n")
        lines.append(f"> {result.summary_line}")

        return "\n".join(lines)

    def ab_to_json(self, result: ABTestResult) -> str:
        """Render an A/B test result as a pretty-printed JSON string.

        Args:
            result: The ``ABTestResult`` to serialise.

        Returns:
            Pretty-printed JSON string.
        """
        payload: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "config_a_label": result.config_a_label,
            "config_b_label": result.config_b_label,
            "result_a": {
                "total_actions": result.result_a.total_actions,
                "allowed_count": result.result_a.allowed_count,
                "denied_count": result.result_a.denied_count,
                "estimated_block_rate": result.result_a.estimated_block_rate,
                "estimated_cost_savings": result.result_a.estimated_cost_savings,
                "denials": [
                    {
                        "action_id": denial.action_id,
                        "category": denial.category,
                        "reason": denial.reason,
                    }
                    for denial in result.result_a.denial_reasons
                ],
            },
            "result_b": {
                "total_actions": result.result_b.total_actions,
                "allowed_count": result.result_b.allowed_count,
                "denied_count": result.result_b.denied_count,
                "estimated_block_rate": result.result_b.estimated_block_rate,
                "estimated_cost_savings": result.result_b.estimated_cost_savings,
                "denials": [
                    {
                        "action_id": denial.action_id,
                        "category": denial.category,
                        "reason": denial.reason,
                    }
                    for denial in result.result_b.denial_reasons
                ],
            },
            "delta": {
                "additional_allowed_in_b": result.additional_allowed_in_b,
                "additional_denied_in_b": result.additional_denied_in_b,
                "cost_delta": result.cost_delta,
            },
            "summary_line": result.summary_line,
        }
        return json.dumps(payload, indent=2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_timestamp() -> str:
    """Return the current UTC time formatted as ``YYYY-MM-DD HH:MM UTC``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
