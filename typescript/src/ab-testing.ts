// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 MuVeraAI Corporation

/**
 * ABTestEngine — compare two governance configurations on the same action trace.
 *
 * TypeScript mirror of `python/src/shadow_mode/ab_testing.py`.
 *
 * Runs the same sequence of agent actions through two distinct governance
 * configurations (Config A and Config B) and produces a side-by-side comparison
 * of their dry-run results.
 *
 * This is read-only simulation. No governance state is modified. No side
 * effects are produced.
 *
 * @example
 * ```typescript
 * import { ABTestEngine } from "@aumos/shadow-mode/ab-testing";
 *
 * const engine = new ABTestEngine(
 *   { label: "current", trustLevel: 2, dailyBudget: 10.0 },
 *   { label: "proposed", trustLevel: 3, dailyBudget: 15.0 },
 * );
 *
 * const result = engine.run(actions);
 * console.log(result.summaryLine);
 * ```
 */

import { GovernanceDryRun, DryRunAction, DryRunResult } from "./dry-run.js";

/**
 * A named governance configuration for use in A/B testing.
 *
 * Trust changes are NEVER automatic — all values here are static and
 * set by the operator for simulation purposes.
 */
export interface GovernanceConfig {
  /** Short human-readable label, e.g. `"strict-l1"` or `"permissive-l3"`. */
  readonly label: string;
  /**
   * Static trust level to apply.
   * @default 2
   */
  readonly trustLevel?: number;
  /**
   * Daily spending ceiling in USD.
   * @default 10.0
   */
  readonly dailyBudget?: number;
  /**
   * When `true`, all sub-L3 actions require explicit consent.
   * @default false
   */
  readonly requireConsent?: boolean;
}

/**
 * Side-by-side comparison of two governance configurations on the same actions.
 *
 * Produced by `ABTestEngine.run()`.
 */
export interface ABTestResult {
  /** Label from the first governance configuration. */
  readonly configALabel: string;
  /** Label from the second governance configuration. */
  readonly configBLabel: string;
  /** Dry-run result for Config A. */
  readonly resultA: DryRunResult;
  /** Dry-run result for Config B. */
  readonly resultB: DryRunResult;
  /**
   * Number of actions allowed by B but denied by A
   * (Config B is more permissive for these actions).
   */
  readonly additionalAllowedInB: number;
  /**
   * Number of actions denied by B but allowed by A
   * (Config B is more restrictive for these actions).
   */
  readonly additionalDeniedInB: number;
  /**
   * Difference in estimated cost savings: `savingsB - savingsA`.
   * Positive means B saves more (blocks more costly actions).
   */
  readonly costDelta: number;
  /** Single-line human-readable comparison string. */
  readonly summaryLine: string;
}

/**
 * Run the same agent action trace through two governance configurations.
 *
 * Both configurations are evaluated independently using `GovernanceDryRun`.
 * The engine then produces a structured comparison so operators can understand
 * the practical difference between configurations before making a manual
 * trust-level or budget decision.
 */
export class ABTestEngine {
  private readonly configA: Required<GovernanceConfig>;
  private readonly configB: Required<GovernanceConfig>;

  constructor(configA: GovernanceConfig, configB: GovernanceConfig) {
    this.configA = {
      label: configA.label,
      trustLevel: configA.trustLevel ?? 2,
      dailyBudget: configA.dailyBudget ?? 10.0,
      requireConsent: configA.requireConsent ?? false,
    };
    this.configB = {
      label: configB.label,
      trustLevel: configB.trustLevel ?? 2,
      dailyBudget: configB.dailyBudget ?? 10.0,
      requireConsent: configB.requireConsent ?? false,
    };
  }

  /**
   * Evaluate actions under both configurations and return a comparison.
   *
   * Actions are evaluated independently under Config A and Config B.
   * The results are then compared to surface net differences in allow/deny
   * decisions and cost savings.
   *
   * @param actions - Ordered array of `DryRunAction` objects representing
   *   the agent execution trace to evaluate.
   * @returns An `ABTestResult` containing both dry-run results and a
   *   structured comparison between them.
   */
  run(actions: readonly DryRunAction[]): ABTestResult {
    const engineA = new GovernanceDryRun({
      trustLevel: this.configA.trustLevel,
      dailyBudget: this.configA.dailyBudget,
      requireConsent: this.configA.requireConsent,
    });
    const engineB = new GovernanceDryRun({
      trustLevel: this.configB.trustLevel,
      dailyBudget: this.configB.dailyBudget,
      requireConsent: this.configB.requireConsent,
    });

    const resultA = engineA.evaluate(actions);
    const resultB = engineB.evaluate(actions);

    // Compute per-action diffs by building denial ID sets
    const deniedIdsA = new Set(resultA.denialReasons.map((d) => d.actionId));
    const deniedIdsB = new Set(resultB.denialReasons.map((d) => d.actionId));

    // Actions allowed by B that were denied by A (B is more permissive here)
    const additionalAllowedInB = [...deniedIdsA].filter(
      (id) => !deniedIdsB.has(id),
    ).length;

    // Actions denied by B that were allowed by A (B is more restrictive here)
    const additionalDeniedInB = [...deniedIdsB].filter(
      (id) => !deniedIdsA.has(id),
    ).length;

    const costDelta =
      resultB.estimatedCostSavings - resultA.estimatedCostSavings;

    const summaryLine = this.buildSummaryLine(
      resultA,
      resultB,
      additionalAllowedInB,
      additionalDeniedInB,
      costDelta,
    );

    return {
      configALabel: this.configA.label,
      configBLabel: this.configB.label,
      resultA,
      resultB,
      additionalAllowedInB,
      additionalDeniedInB,
      costDelta,
      summaryLine,
    };
  }

  private buildSummaryLine(
    resultA: DryRunResult,
    resultB: DryRunResult,
    additionalAllowedInB: number,
    additionalDeniedInB: number,
    costDelta: number,
  ): string {
    const direction = costDelta >= 0 ? "saves" : "costs";
    const deltaAbs = Math.abs(costDelta).toFixed(2);

    return (
      `A(${this.configA.label}): ` +
      `${resultA.allowedCount}/${resultA.totalActions} allowed, ` +
      `block rate ${(resultA.estimatedBlockRate * 100).toFixed(1)}% | ` +
      `B(${this.configB.label}): ` +
      `${resultB.allowedCount}/${resultB.totalActions} allowed, ` +
      `block rate ${(resultB.estimatedBlockRate * 100).toFixed(1)}% | ` +
      `B vs A: +${additionalAllowedInB} allowed, ` +
      `+${additionalDeniedInB} denied, ` +
      `${direction} $${deltaAbs}`
    );
  }
}
