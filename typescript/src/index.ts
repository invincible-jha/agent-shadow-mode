// SPDX-License-Identifier: BSL-1.1
// Copyright (c) 2026 MuVeraAI Corporation

/**
 * @aumos/shadow-mode — run AI agents in shadow mode to build a trust track record.
 *
 * @example
 * ```typescript
 * import { ShadowRunner, ShadowComparator, ConfidenceScorer } from "@aumos/shadow-mode";
 *
 * const runner = new ShadowRunner(async (input) => {
 *   return { action: "approve" };
 * });
 *
 * const shadow = await runner.shadowExecute({ amount: 500 });
 * const actual = {
 *   decisionId: shadow.decisionId,
 *   output: { action: "approve" },
 *   timestamp: new Date().toISOString(),
 *   metadata: {},
 * };
 *
 * const comparator = new ShadowComparator();
 * const comparison = comparator.compare(shadow, actual);
 *
 * const scorer = new ConfidenceScorer();
 * const report = scorer.score([comparison]);
 * console.log(report.recommendation);
 * ```
 */

export { ShadowRunner, ShadowExecutionError } from "./runner.js";
export type { AgentFn } from "./runner.js";

export { ShadowComparator } from "./comparator.js";

export { ConfidenceScorer } from "./scorer.js";

export type {
  ShadowDecision,
  ActualDecision,
  ComparisonResult,
  ConfidenceReport,
  Deviation,
  AgreementLevel,
  RiskLevel,
} from "./types.js";
