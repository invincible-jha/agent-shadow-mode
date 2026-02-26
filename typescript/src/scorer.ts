// SPDX-License-Identifier: BSL-1.1
// Copyright (c) 2026 MuVeraAI Corporation

/**
 * ConfidenceScorer — aggregate comparison results into a human-readable report.
 *
 * Mirrors the Python ConfidenceScorer in python/src/shadow_mode/scorer.py.
 *
 * The recommendation field is ADVISORY ONLY — a plain string.
 * No API calls are made. No trust levels are changed automatically.
 */

import type { ComparisonResult, ConfidenceReport } from "./types.js";

/**
 * Aggregates comparison results into a ConfidenceReport.
 *
 * @example
 * ```typescript
 * const scorer = new ConfidenceScorer();
 * const report = scorer.score(comparisons);
 * console.log(report.agreementRate);   // 0.95
 * console.log(report.recommendation); // "Based on 95% agreement..."
 * ```
 */
export class ConfidenceScorer {
  private readonly strongAgreementThreshold: number;
  private readonly minimumSampleSize: number;

  /**
   * @param strongAgreementThreshold - Agreement rate at or above which a positive
   *   promotion advisory is issued. Defaults to 0.95.
   * @param minimumSampleSize - Minimum number of comparisons before a positive
   *   promotion advisory is issued. Defaults to 100.
   */
  constructor(strongAgreementThreshold = 0.95, minimumSampleSize = 100) {
    if (strongAgreementThreshold < 0 || strongAgreementThreshold > 1) {
      throw new RangeError("strongAgreementThreshold must be in [0.0, 1.0].");
    }
    if (minimumSampleSize < 1) {
      throw new RangeError("minimumSampleSize must be at least 1.");
    }
    this.strongAgreementThreshold = strongAgreementThreshold;
    this.minimumSampleSize = minimumSampleSize;
  }

  /**
   * Compute an aggregate confidence report from a list of comparison results.
   *
   * @param comparisons - List of ComparisonResult objects. May be empty.
   * @returns ConfidenceReport with aggregate statistics and a plain-text
   *   recommendation string. The recommendation is ADVISORY ONLY.
   */
  score(comparisons: readonly ComparisonResult[]): ConfidenceReport {
    if (comparisons.length === 0) {
      return {
        totalComparisons: 0,
        agreementCount: 0,
        disagreementCount: 0,
        agreementRate: 0,
        averageDeviation: 0,
        worstDeviation: 0,
        riskScore: 0,
        highRiskCount: 0,
        recommendation:
          "No comparison data available. Accumulate shadow decisions " +
          "before requesting a confidence report.",
      };
    }

    const total = comparisons.length;
    const agreementCount = comparisons.filter((c) => c.agreed).length;
    const disagreementCount = total - agreementCount;
    const agreementRate = agreementCount / total;

    const deviationScores = comparisons.map((c) => c.deviationScore);
    const averageDeviation = deviationScores.reduce((a, b) => a + b, 0) / total;
    const worstDeviation = Math.max(...deviationScores);

    const highRiskCount = comparisons.filter((c) => c.riskLevel === "high").length;
    const riskScore = highRiskCount / total;

    const recommendation = buildRecommendation(
      total,
      agreementRate,
      highRiskCount,
      worstDeviation,
      this.strongAgreementThreshold,
      this.minimumSampleSize
    );

    return {
      totalComparisons: total,
      agreementCount,
      disagreementCount,
      agreementRate: roundTo6(agreementRate),
      averageDeviation: roundTo6(averageDeviation),
      worstDeviation: roundTo6(worstDeviation),
      riskScore: roundTo6(riskScore),
      highRiskCount,
      recommendation,
    };
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function buildRecommendation(
  totalComparisons: number,
  agreementRate: number,
  highRiskCount: number,
  worstDeviation: number,
  strongAgreementThreshold: number,
  minimumSampleSize: number
): string {
  const agreementPct = `${(agreementRate * 100).toFixed(1)}%`;
  const base = `Based on ${agreementPct} agreement over ${totalComparisons} decision(s)`;

  if (totalComparisons < minimumSampleSize) {
    const needed = minimumSampleSize - totalComparisons;
    return (
      `${base}: sample size is below the recommended minimum of ` +
      `${minimumSampleSize}. Accumulate ${needed} more decision(s) ` +
      `before drawing conclusions.`
    );
  }

  if (highRiskCount > 0) {
    return (
      `${base}: ${highRiskCount} high-risk deviation(s) detected ` +
      `(worst deviation score: ${worstDeviation.toFixed(2)}). ` +
      `Review deviations before considering any promotion.`
    );
  }

  if (agreementRate >= strongAgreementThreshold) {
    return (
      `${base}: shadow performance is strong. A human operator may consider ` +
      `promoting this agent to a higher trust level.`
    );
  }

  const gap = ((strongAgreementThreshold - agreementRate) * 100).toFixed(1);
  return (
    `${base}: shadow performance is below the strong agreement threshold ` +
    `(${(strongAgreementThreshold * 100).toFixed(1)}%) by ${gap}%. ` +
    `Continue monitoring before considering any promotion.`
  );
}

function roundTo6(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}
