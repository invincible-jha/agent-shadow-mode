// SPDX-License-Identifier: BSL-1.1
// Copyright (c) 2026 MuVeraAI Corporation

/**
 * Shared TypeScript types for @aumos/shadow-mode.
 *
 * Mirrors the Python Pydantic models in python/src/shadow_mode/types.py.
 * All types are immutable-by-convention (readonly properties).
 */

/** Qualitative agreement level between shadow and actual decisions. */
export type AgreementLevel = "full" | "partial" | "none";

/** Risk level derived from comparison deviation. */
export type RiskLevel = "low" | "medium" | "high";

/**
 * The output of a shadow agent execution.
 * Captured by ShadowRunner.shadowExecute(). Raw input is never stored.
 */
export interface ShadowDecision {
  readonly decisionId: string;
  /** SHA-256 hex digest of the serialised input. Raw input is not stored. */
  readonly inputHash: string;
  readonly output: Record<string, unknown>;
  readonly timestamp: string; // ISO 8601 UTC
  readonly adapterName: string;
  readonly metadata: Record<string, unknown>;
}

/**
 * The real decision made by the production agent.
 * Used as ground truth when computing comparison results.
 */
export interface ActualDecision {
  /** Must match the corresponding ShadowDecision.decisionId. */
  readonly decisionId: string;
  readonly output: Record<string, unknown>;
  readonly timestamp: string; // ISO 8601 UTC
  readonly metadata: Record<string, unknown>;
}

/** A single field-level deviation between shadow and actual outputs. */
export interface Deviation {
  /** Dot-separated path to the differing field, e.g. "action.type". */
  readonly fieldPath: string;
  readonly shadowValue: unknown;
  readonly actualValue: unknown;
  readonly description: string;
}

/**
 * Result of comparing one shadow decision to one actual decision.
 * Produced by ShadowComparator.compare().
 */
export interface ComparisonResult {
  readonly decisionId: string;
  /** True if shadow and actual outputs are considered equivalent. */
  readonly agreed: boolean;
  readonly agreementLevel: AgreementLevel;
  /** Float in [0.0, 1.0]. 0.0 = identical, 1.0 = completely different. */
  readonly deviationScore: number;
  readonly deviations: readonly Deviation[];
  readonly riskLevel: RiskLevel;
  readonly notes?: string;
}

/**
 * Aggregated confidence report across many comparison results.
 * Produced by ConfidenceScorer.score().
 *
 * The recommendation field is a plain human-readable string.
 * It is NEVER an API call and does NOT change any trust level.
 */
export interface ConfidenceReport {
  readonly totalComparisons: number;
  readonly agreementCount: number;
  readonly disagreementCount: number;
  /** Float in [0.0, 1.0]. */
  readonly agreementRate: number;
  readonly averageDeviation: number;
  readonly worstDeviation: number;
  readonly riskScore: number;
  readonly highRiskCount: number;
  /**
   * Human-readable advisory string. NOT an API call.
   * Example: "Based on 95% agreement over 200 decisions, consider promoting to L3."
   */
  readonly recommendation: string;
}
