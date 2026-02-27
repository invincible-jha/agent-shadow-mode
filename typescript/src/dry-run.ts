// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 MuVeraAI Corporation

/**
 * GovernanceDryRun — evaluate actions against governance rules without enforcing them.
 *
 * TypeScript mirror of `python/src/shadow_mode/dry_run.py`.
 *
 * Replays a sequence of agent actions through a governance configuration and
 * reports what would have been allowed or denied, along with estimated cost
 * savings from denied actions.
 *
 * This is a read-only simulation. No governance state is modified. No side
 * effects are produced.
 *
 * @example
 * ```typescript
 * import { GovernanceDryRun } from "@aumos/shadow-mode/dry-run";
 *
 * const engine = new GovernanceDryRun({ trustLevel: 2, dailyBudget: 10.0 });
 *
 * const actions: DryRunAction[] = [
 *   { actionId: "a1", actionType: "tool_call", toolName: "web_search", estimatedCost: 0.50, requiredTrustLevel: 1 },
 *   { actionId: "a2", actionType: "tool_call", toolName: "send_email", estimatedCost: 1.00, requiredTrustLevel: 3 },
 * ];
 *
 * const result = engine.evaluate(actions);
 * console.log(`Block rate: ${(result.estimatedBlockRate * 100).toFixed(1)}%`);
 * ```
 */

/** Denial category produced by the dry-run engine. */
export type DenialCategory = "trust" | "budget" | "consent" | "policy";

/**
 * A single agent action submitted for dry-run evaluation.
 *
 * All properties are readonly — actions are treated as immutable records
 * of an agent execution trace.
 */
export interface DryRunAction {
  /** Unique identifier for this action within the trace. */
  readonly actionId: string;
  /** Category of action, e.g. `"tool_call"` or `"api_request"`. */
  readonly actionType: string;
  /** Name of the tool or capability being invoked. */
  readonly toolName: string;
  /** Estimated monetary cost in USD for this action. */
  readonly estimatedCost: number;
  /** Minimum trust level required to execute this action. */
  readonly requiredTrustLevel: number;
}

/**
 * Record of a single action that would have been denied by governance.
 */
export interface DryRunDenial {
  /** Identifier of the denied action. */
  readonly actionId: string;
  /** Human-readable explanation of why the action was denied. */
  readonly reason: string;
  /** Denial category. */
  readonly category: DenialCategory;
}

/**
 * Aggregated result of a governance dry-run evaluation.
 *
 * Produced by `GovernanceDryRun.evaluate()`.
 */
export interface DryRunResult {
  /** Total number of actions evaluated. */
  readonly totalActions: number;
  /** Number of actions that would have been allowed. */
  readonly allowedCount: number;
  /** Number of actions that would have been denied. */
  readonly deniedCount: number;
  /** Ordered array of denial records. */
  readonly denialReasons: readonly DryRunDenial[];
  /** Fraction of actions denied, in [0.0, 1.0]. */
  readonly estimatedBlockRate: number;
  /** Total USD cost of denied actions (not incurred). */
  readonly estimatedCostSavings: number;
}

/** Constructor options for `GovernanceDryRun`. */
export interface GovernanceDryRunOptions {
  /**
   * Current trust level assigned to the agent being evaluated.
   * Actions requiring a higher level will be denied with category `"trust"`.
   * Trust changes are NEVER automatic — this is a static operator-set value.
   *
   * @default 2
   */
  readonly trustLevel?: number;
  /**
   * Maximum cumulative spend (USD) allowed in one day.
   * Once exceeded, further actions are denied with category `"budget"`.
   *
   * @default 10.0
   */
  readonly dailyBudget?: number;
  /**
   * When `true`, all sub-L3 actions are flagged as denied with category
   * `"consent"` unless the trust level provides a consent waiver.
   *
   * @default false
   */
  readonly requireConsent?: boolean;
}

/**
 * Evaluate a sequence of actions against governance rules without enforcement.
 *
 * The engine applies trust-level gating and budget ceiling checks in the
 * order actions arrive, mirroring how a live governance layer would process
 * them sequentially. Trust changes are NEVER automatic.
 */
export class GovernanceDryRun {
  private readonly trustLevel: number;
  private readonly dailyBudget: number;
  private readonly requireConsent: boolean;

  constructor(options: GovernanceDryRunOptions = {}) {
    this.trustLevel = options.trustLevel ?? 2;
    this.dailyBudget = options.dailyBudget ?? 10.0;
    this.requireConsent = options.requireConsent ?? false;
  }

  /**
   * Evaluate a sequence of actions without enforcing governance.
   *
   * Processes each action in order. Trust-level violations are checked
   * first; budget overflow is checked second. Denied actions do not
   * accumulate against the running budget total.
   *
   * @param actions - Ordered array of `DryRunAction` objects representing
   *   an agent execution trace.
   * @returns A `DryRunResult` summarising what would have been allowed,
   *   denied, and the estimated cost savings from blocked actions.
   */
  evaluate(actions: readonly DryRunAction[]): DryRunResult {
    const denials: DryRunDenial[] = [];
    let runningCost = 0;
    let costSavings = 0;

    for (const action of actions) {
      // Trust-level gate — checked before spending budget
      if (action.requiredTrustLevel > this.trustLevel) {
        denials.push({
          actionId: action.actionId,
          reason: `Requires trust L${action.requiredTrustLevel}, agent is L${this.trustLevel}`,
          category: "trust",
        });
        costSavings += action.estimatedCost;
        continue;
      }

      // Consent gate — all sub-L3 actions flagged when consent is required
      if (this.requireConsent && this.trustLevel < 3) {
        denials.push({
          actionId: action.actionId,
          reason: `Consent required for trust L${this.trustLevel}; operator has not granted consent waiver`,
          category: "consent",
        });
        costSavings += action.estimatedCost;
        continue;
      }

      // Budget ceiling gate — accumulate cost, deny if over limit
      const prospectiveCost = runningCost + action.estimatedCost;
      if (prospectiveCost > this.dailyBudget) {
        denials.push({
          actionId: action.actionId,
          reason: `Daily budget exceeded: $${prospectiveCost.toFixed(2)} > $${this.dailyBudget.toFixed(2)}`,
          category: "budget",
        });
        costSavings += action.estimatedCost;
        continue;
      }

      runningCost = prospectiveCost;
    }

    const totalActions = actions.length;
    const deniedCount = denials.length;
    const allowedCount = totalActions - deniedCount;
    const estimatedBlockRate = totalActions > 0 ? deniedCount / totalActions : 0;

    return {
      totalActions,
      allowedCount,
      deniedCount,
      denialReasons: denials,
      estimatedBlockRate,
      estimatedCostSavings: costSavings,
    };
  }
}
