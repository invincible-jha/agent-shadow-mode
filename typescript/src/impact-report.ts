// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 MuVeraAI Corporation

/**
 * ImpactReporter — render governance dry-run results as markdown or JSON.
 *
 * TypeScript mirror of `python/src/shadow_mode/impact_report.py`.
 *
 * Produces formatted reports from `DryRunResult` and `ABTestResult` objects
 * suitable for:
 *
 * - CI pipeline comments (Markdown)
 * - Downstream tooling and dashboards (JSON)
 * - Terminal output (plain text)
 *
 * This module is output-only. It does not modify any governance state.
 *
 * @example
 * ```typescript
 * import { ImpactReporter } from "@aumos/shadow-mode/impact-report";
 * import { GovernanceDryRun } from "@aumos/shadow-mode/dry-run";
 *
 * const engine = new GovernanceDryRun({ trustLevel: 2, dailyBudget: 10.0 });
 * const result = engine.evaluate(actions);
 *
 * const reporter = new ImpactReporter();
 * console.log(reporter.toMarkdown(result, "current"));
 * console.log(reporter.toJson(result, "current"));
 * ```
 */

import { DryRunResult } from "./dry-run.js";
import { ABTestResult } from "./ab-testing.js";

/** Serialisable JSON shape for a single dry-run report. */
export interface DryRunReportJson {
  readonly generatedAt: string;
  readonly configLabel: string;
  readonly summary: {
    readonly totalActions: number;
    readonly allowedCount: number;
    readonly deniedCount: number;
    readonly estimatedBlockRate: number;
    readonly estimatedCostSavings: number;
  };
  readonly denials: ReadonlyArray<{
    readonly actionId: string;
    readonly category: string;
    readonly reason: string;
  }>;
}

/** Serialisable JSON shape for an A/B comparison report. */
export interface ABReportJson {
  readonly generatedAt: string;
  readonly configALabel: string;
  readonly configBLabel: string;
  readonly resultA: DryRunReportJson["summary"] & {
    readonly denials: DryRunReportJson["denials"];
  };
  readonly resultB: DryRunReportJson["summary"] & {
    readonly denials: DryRunReportJson["denials"];
  };
  readonly delta: {
    readonly additionalAllowedInB: number;
    readonly additionalDeniedInB: number;
    readonly costDelta: number;
  };
  readonly summaryLine: string;
}

/**
 * Generate formatted impact reports from governance dry-run results.
 *
 * Supports single-config dry-run reports and A/B comparison reports.
 * All output methods return strings — no files are written by this class.
 */
export class ImpactReporter {
  // ------------------------------------------------------------------
  // Single dry-run reports
  // ------------------------------------------------------------------

  /**
   * Render a single dry-run result as a Markdown report.
   *
   * Suitable for GitHub PR comments, issue bodies, or documentation.
   *
   * @param result - The `DryRunResult` to render.
   * @param configLabel - Human-readable name for the governance configuration.
   * @returns Markdown string.
   */
  toMarkdown(
    result: DryRunResult,
    configLabel = "governance config",
  ): string {
    const generatedAt = utcTimestamp();
    const lines: string[] = [];

    lines.push(`# Governance Dry-Run Impact Report — ${configLabel}`);
    lines.push(`\n_Generated: ${generatedAt}_\n`);

    lines.push("## Summary\n");
    lines.push("| Metric | Value |");
    lines.push("|--------|-------|");
    lines.push(`| Total Actions | ${result.totalActions} |`);
    lines.push(`| Allowed | ${result.allowedCount} |`);
    lines.push(`| Denied | ${result.deniedCount} |`);
    lines.push(
      `| Block Rate | ${(result.estimatedBlockRate * 100).toFixed(1)}% |`,
    );
    lines.push(
      `| Estimated Cost Savings | $${result.estimatedCostSavings.toFixed(2)} |`,
    );

    if (result.denialReasons.length > 0) {
      // Category breakdown
      const categoryCounts = new Map<string, number>();
      for (const denial of result.denialReasons) {
        categoryCounts.set(
          denial.category,
          (categoryCounts.get(denial.category) ?? 0) + 1,
        );
      }

      lines.push("\n## Denial Breakdown\n");
      lines.push("| Category | Count |");
      lines.push("|----------|-------|");
      for (const [category, count] of [...categoryCounts.entries()].sort()) {
        lines.push(`| ${category} | ${count} |`);
      }

      lines.push("\n## Denied Actions\n");
      lines.push("| Action ID | Category | Reason |");
      lines.push("|-----------|----------|--------|");
      for (const denial of result.denialReasons) {
        const safeReason = denial.reason.replace(/\|/g, "\\|");
        lines.push(
          `| \`${denial.actionId}\` | ${denial.category} | ${safeReason} |`,
        );
      }
    } else {
      lines.push(
        "\n> All actions would be allowed under this configuration.\n",
      );
    }

    return lines.join("\n");
  }

  /**
   * Render a single dry-run result as a structured JSON object.
   *
   * Returns the typed `DryRunReportJson` object. Call `JSON.stringify()`
   * on the result if you need a string.
   *
   * @param result - The `DryRunResult` to serialise.
   * @param configLabel - Human-readable name for the governance configuration.
   * @returns A `DryRunReportJson` object.
   */
  toJsonObject(
    result: DryRunResult,
    configLabel = "governance config",
  ): DryRunReportJson {
    return {
      generatedAt: new Date().toISOString(),
      configLabel,
      summary: {
        totalActions: result.totalActions,
        allowedCount: result.allowedCount,
        deniedCount: result.deniedCount,
        estimatedBlockRate: result.estimatedBlockRate,
        estimatedCostSavings: result.estimatedCostSavings,
      },
      denials: result.denialReasons.map((denial) => ({
        actionId: denial.actionId,
        category: denial.category,
        reason: denial.reason,
      })),
    };
  }

  /**
   * Render a single dry-run result as a pretty-printed JSON string.
   *
   * @param result - The `DryRunResult` to serialise.
   * @param configLabel - Human-readable name for the governance configuration.
   * @returns Pretty-printed JSON string.
   */
  toJson(result: DryRunResult, configLabel = "governance config"): string {
    return JSON.stringify(this.toJsonObject(result, configLabel), null, 2);
  }

  /**
   * Render a single dry-run result as plain text for CLI/log output.
   *
   * @param result - The `DryRunResult` to render.
   * @param configLabel - Human-readable name for the governance configuration.
   * @returns Plain-text string.
   */
  toText(result: DryRunResult, configLabel = "governance config"): string {
    const separator = "=".repeat(60);
    const lines: string[] = [
      separator,
      `GOVERNANCE DRY-RUN IMPACT REPORT — ${configLabel.toUpperCase()}`,
      `Generated: ${utcTimestamp()}`,
      separator,
      "",
      `Total actions evaluated : ${result.totalActions}`,
      `Allowed                 : ${result.allowedCount}`,
      `Denied                  : ${result.deniedCount}`,
      `Block rate              : ${(result.estimatedBlockRate * 100).toFixed(1)}%`,
      `Estimated cost savings  : $${result.estimatedCostSavings.toFixed(2)}`,
      "",
    ];

    if (result.denialReasons.length > 0) {
      lines.push("DENIED ACTIONS:");
      for (const denial of result.denialReasons) {
        lines.push(
          `  [${denial.category.toUpperCase()}] ${denial.actionId}: ${denial.reason}`,
        );
      }
    } else {
      lines.push("All actions would be allowed under this configuration.");
    }

    lines.push("");
    lines.push(separator);
    return lines.join("\n");
  }

  // ------------------------------------------------------------------
  // A/B comparison reports
  // ------------------------------------------------------------------

  /**
   * Render an A/B test result as a Markdown comparison report.
   *
   * @param result - The `ABTestResult` to render.
   * @returns Markdown string with side-by-side comparison tables.
   */
  abToMarkdown(result: ABTestResult): string {
    const generatedAt = utcTimestamp();
    const lines: string[] = [];

    lines.push(
      `# Governance A/B Comparison Report — ${result.configALabel} vs ${result.configBLabel}`,
    );
    lines.push(`\n_Generated: ${generatedAt}_\n`);

    lines.push("## Configuration Comparison\n");
    lines.push(
      `| Metric | ${result.configALabel} | ${result.configBLabel} |`,
    );
    lines.push("|--------|" + "--------|".repeat(2));
    lines.push(
      `| Total Actions | ${result.resultA.totalActions} | ${result.resultB.totalActions} |`,
    );
    lines.push(
      `| Allowed | ${result.resultA.allowedCount} | ${result.resultB.allowedCount} |`,
    );
    lines.push(
      `| Denied | ${result.resultA.deniedCount} | ${result.resultB.deniedCount} |`,
    );
    lines.push(
      `| Block Rate | ${(result.resultA.estimatedBlockRate * 100).toFixed(1)}% | ${(result.resultB.estimatedBlockRate * 100).toFixed(1)}% |`,
    );
    lines.push(
      `| Cost Savings | $${result.resultA.estimatedCostSavings.toFixed(2)} | $${result.resultB.estimatedCostSavings.toFixed(2)} |`,
    );

    lines.push("\n## Delta (B vs A)\n");
    lines.push("| Delta Metric | Value |");
    lines.push("|--------------|-------|");
    lines.push(
      `| Additional Allowed in B | ${result.additionalAllowedInB} |`,
    );
    lines.push(
      `| Additional Denied in B | ${result.additionalDeniedInB} |`,
    );
    const costDirection =
      result.costDelta >= 0 ? "saves more" : "costs more";
    const costSign = result.costDelta >= 0 ? "+" : "";
    lines.push(
      `| Cost Delta (B - A) | ${costSign}$${result.costDelta.toFixed(2)} (B ${costDirection}) |`,
    );

    lines.push("\n## Summary\n");
    lines.push(`> ${result.summaryLine}`);

    return lines.join("\n");
  }

  /**
   * Render an A/B test result as a structured JSON object.
   *
   * @param result - The `ABTestResult` to serialise.
   * @returns An `ABReportJson` object.
   */
  abToJsonObject(result: ABTestResult): ABReportJson {
    const buildResultSection = (r: DryRunResult) => ({
      totalActions: r.totalActions,
      allowedCount: r.allowedCount,
      deniedCount: r.deniedCount,
      estimatedBlockRate: r.estimatedBlockRate,
      estimatedCostSavings: r.estimatedCostSavings,
      denials: r.denialReasons.map((d) => ({
        actionId: d.actionId,
        category: d.category,
        reason: d.reason,
      })),
    });

    return {
      generatedAt: new Date().toISOString(),
      configALabel: result.configALabel,
      configBLabel: result.configBLabel,
      resultA: buildResultSection(result.resultA),
      resultB: buildResultSection(result.resultB),
      delta: {
        additionalAllowedInB: result.additionalAllowedInB,
        additionalDeniedInB: result.additionalDeniedInB,
        costDelta: result.costDelta,
      },
      summaryLine: result.summaryLine,
    };
  }

  /**
   * Render an A/B test result as a pretty-printed JSON string.
   *
   * @param result - The `ABTestResult` to serialise.
   * @returns Pretty-printed JSON string.
   */
  abToJson(result: ABTestResult): string {
    return JSON.stringify(this.abToJsonObject(result), null, 2);
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Return the current UTC time formatted as `YYYY-MM-DD HH:MM UTC`. */
function utcTimestamp(): string {
  const now = new Date();
  const year = now.getUTCFullYear();
  const month = String(now.getUTCMonth() + 1).padStart(2, "0");
  const day = String(now.getUTCDate()).padStart(2, "0");
  const hours = String(now.getUTCHours()).padStart(2, "0");
  const minutes = String(now.getUTCMinutes()).padStart(2, "0");
  return `${year}-${month}-${day} ${hours}:${minutes} UTC`;
}
