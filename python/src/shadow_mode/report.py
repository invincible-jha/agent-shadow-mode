# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""ShadowReporter — generate evaluation reports from confidence reports.

Produces human-readable output in three formats:

- **Markdown**: suitable for GitHub issues, PRs, or documentation
- **JSON**: machine-readable for downstream tooling
- **Plain text**: for CLI output or log files

The reporter operates on a ``ConfidenceReport`` and an optional list of
``ComparisonResult`` objects for per-decision breakdowns.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .types import ComparisonResult, ConfidenceReport, RiskLevel


class ShadowReporter:
    """Generate evaluation reports from shadow mode confidence data.

    Example::

        reporter = ShadowReporter()

        markdown_text = reporter.to_markdown(report, comparisons)
        json_text = reporter.to_json(report, comparisons)
        plain_text = reporter.to_text(report)
    """

    def to_markdown(
        self,
        report: ConfidenceReport,
        comparisons: list[ComparisonResult] | None = None,
        agent_label: str = "Shadow Agent",
    ) -> str:
        """Generate a Markdown evaluation report.

        Args:
            report: The ``ConfidenceReport`` to render.
            comparisons: Optional list of comparison results for the per-decision table.
            agent_label: Display name for the shadow agent. Defaults to ``"Shadow Agent"``.

        Returns:
            Markdown string.
        """
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines: list[str] = []

        lines.append(f"# Shadow Mode Evaluation Report — {agent_label}")
        lines.append(f"\n_Generated: {generated_at}_\n")

        lines.append("## Summary\n")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Total Decisions Evaluated | {report.total_comparisons} |")
        lines.append(f"| Agreement Count | {report.agreement_count} |")
        lines.append(f"| Disagreement Count | {report.disagreement_count} |")
        lines.append(f"| Agreement Rate | {report.agreement_rate * 100:.1f}% |")
        lines.append(f"| Average Deviation | {report.average_deviation:.4f} |")
        lines.append(f"| Worst Deviation | {report.worst_deviation:.4f} |")
        lines.append(f"| Risk Score | {report.risk_score:.4f} |")
        lines.append(f"| High-Risk Decisions | {report.high_risk_count} |")

        lines.append("\n## Recommendation\n")
        lines.append(f"> {report.recommendation}")

        if comparisons:
            lines.append("\n## Per-Decision Breakdown\n")
            lines.append("| Decision ID | Agreed | Deviation | Risk | Deviations |")
            lines.append("|-------------|--------|-----------|------|------------|")
            for comparison in comparisons:
                agreed_str = "Yes" if comparison.agreed else "No"
                deviation_count = len(comparison.deviations)
                lines.append(
                    f"| `{comparison.decision_id[:16]}...` "
                    f"| {agreed_str} "
                    f"| {comparison.deviation_score:.4f} "
                    f"| {comparison.risk_level.value} "
                    f"| {deviation_count} |"
                )

            high_risk = [c for c in comparisons if c.risk_level == RiskLevel.HIGH]
            if high_risk:
                lines.append("\n## High-Risk Deviations\n")
                for comparison in high_risk:
                    lines.append(f"### Decision `{comparison.decision_id}`\n")
                    for deviation in comparison.deviations:
                        lines.append(f"- **`{deviation.field_path}`**: {deviation.description}")
                    lines.append("")

        return "\n".join(lines)

    def to_json(
        self,
        report: ConfidenceReport,
        comparisons: list[ComparisonResult] | None = None,
        agent_label: str = "Shadow Agent",
    ) -> str:
        """Generate a JSON evaluation report.

        Args:
            report: The ``ConfidenceReport`` to serialise.
            comparisons: Optional list of comparison results to include.
            agent_label: Display name for the shadow agent.

        Returns:
            Pretty-printed JSON string.
        """
        payload: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "agent_label": agent_label,
            "summary": report.model_dump(),
            "comparisons": (
                [c.model_dump() for c in comparisons] if comparisons else None
            ),
        }
        return json.dumps(payload, indent=2, default=str)

    def to_text(
        self,
        report: ConfidenceReport,
        agent_label: str = "Shadow Agent",
    ) -> str:
        """Generate a plain-text evaluation report for CLI/log output.

        Args:
            report: The ``ConfidenceReport`` to render.
            agent_label: Display name for the shadow agent.

        Returns:
            Plain-text string.
        """
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        separator = "=" * 60
        lines: list[str] = [
            separator,
            f"SHADOW MODE EVALUATION REPORT — {agent_label.upper()}",
            f"Generated: {generated_at}",
            separator,
            "",
            f"Total decisions evaluated : {report.total_comparisons}",
            f"Agreement count           : {report.agreement_count}",
            f"Disagreement count        : {report.disagreement_count}",
            f"Agreement rate            : {report.agreement_rate * 100:.1f}%",
            f"Average deviation         : {report.average_deviation:.4f}",
            f"Worst deviation           : {report.worst_deviation:.4f}",
            f"Risk score                : {report.risk_score:.4f}",
            f"High-risk decisions       : {report.high_risk_count}",
            "",
            "RECOMMENDATION:",
            report.recommendation,
            "",
            separator,
        ]
        return "\n".join(lines)
