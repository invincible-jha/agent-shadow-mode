// SPDX-License-Identifier: BSL-1.1
// Copyright (c) 2026 MuVeraAI Corporation

/**
 * ShadowComparator — compare a shadow recommendation to an actual decision.
 *
 * Comparison is pure computation — no external calls, no side effects, no state.
 * Mirrors the Python ShadowComparator in python/src/shadow_mode/comparator.py.
 */

import type {
  ActualDecision,
  AgreementLevel,
  ComparisonResult,
  Deviation,
  RiskLevel,
  ShadowDecision,
} from "./types.js";

/** Default set of top-level field names treated as high-priority for risk assessment. */
const DEFAULT_HIGH_PRIORITY_FIELDS: ReadonlySet<string> = new Set([
  "action",
  "decision",
  "approved",
  "blocked",
  "result",
  "status",
]);

/**
 * Compares shadow decisions to actual decisions and produces ComparisonResult objects.
 *
 * @example
 * ```typescript
 * const comparator = new ShadowComparator();
 * const result = comparator.compare(shadowDecision, actualDecision);
 * console.log(result.agreed, result.deviationScore, result.riskLevel);
 * ```
 */
export class ShadowComparator {
  private readonly highPriorityFields: ReadonlySet<string>;
  private readonly agreementThreshold: number;

  /**
   * @param highPriorityFields - Top-level field names weighted more heavily
   *   in deviation scoring. Defaults to DEFAULT_HIGH_PRIORITY_FIELDS.
   * @param agreementThreshold - Deviation score at or below which the comparison
   *   is considered agreed. Defaults to 0.1.
   */
  constructor(
    highPriorityFields?: ReadonlySet<string>,
    agreementThreshold = 0.1
  ) {
    if (agreementThreshold < 0 || agreementThreshold > 1) {
      throw new RangeError("agreementThreshold must be in [0.0, 1.0].");
    }
    this.highPriorityFields = highPriorityFields ?? DEFAULT_HIGH_PRIORITY_FIELDS;
    this.agreementThreshold = agreementThreshold;
  }

  /**
   * Compare shadow output to actual output and return a scored result.
   *
   * @param shadow - The shadow agent's decision (what it would have done).
   * @param actual - The production agent's actual decision.
   * @returns ComparisonResult with agreement, deviation score, field-level diffs,
   *   and risk level.
   * @throws Error if shadow.decisionId !== actual.decisionId.
   */
  compare(shadow: ShadowDecision, actual: ActualDecision): ComparisonResult {
    if (shadow.decisionId !== actual.decisionId) {
      throw new Error(
        `decisionId mismatch: shadow="${shadow.decisionId}" actual="${actual.decisionId}". ` +
          "Both must share the same ID."
      );
    }

    const deviations = findDeviations(shadow.output, actual.output);
    const deviationScore = computeDeviationScore(deviations, this.highPriorityFields);
    const agreed = deviationScore <= this.agreementThreshold;
    const agreementLevel = classifyAgreement(deviationScore, this.agreementThreshold);
    const riskLevel = assessRisk(deviations, deviationScore, this.highPriorityFields);

    return {
      decisionId: shadow.decisionId,
      agreed,
      agreementLevel,
      deviationScore: roundTo6(deviationScore),
      deviations,
      riskLevel,
    };
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function findDeviations(
  shadowOutput: Record<string, unknown>,
  actualOutput: Record<string, unknown>,
  pathPrefix = ""
): Deviation[] {
  const deviations: Deviation[] = [];
  const allKeys = new Set([...Object.keys(shadowOutput), ...Object.keys(actualOutput)]);

  for (const key of [...allKeys].sort()) {
    const fieldPath = pathPrefix ? `${pathPrefix}.${key}` : key;
    const shadowValue = shadowOutput[key];
    const actualValue = actualOutput[key];

    if (!(key in shadowOutput)) {
      deviations.push({
        fieldPath,
        shadowValue: undefined,
        actualValue,
        description: `Field '${fieldPath}' present in actual but missing from shadow.`,
      });
    } else if (!(key in actualOutput)) {
      deviations.push({
        fieldPath,
        shadowValue,
        actualValue: undefined,
        description: `Field '${fieldPath}' present in shadow but missing from actual.`,
      });
    } else if (isPlainObject(shadowValue) && isPlainObject(actualValue)) {
      const nested = findDeviations(
        shadowValue as Record<string, unknown>,
        actualValue as Record<string, unknown>,
        fieldPath
      );
      deviations.push(...nested);
    } else if (!deepEqual(shadowValue, actualValue)) {
      deviations.push({
        fieldPath,
        shadowValue,
        actualValue,
        description:
          `Field '${fieldPath}' differs: ` +
          `shadow=${JSON.stringify(shadowValue)}, actual=${JSON.stringify(actualValue)}.`,
      });
    }
  }

  return deviations;
}

function computeDeviationScore(
  deviations: Deviation[],
  highPriorityFields: ReadonlySet<string>
): number {
  if (deviations.length === 0) return 0;

  let totalWeight = 0;
  for (const deviation of deviations) {
    const topLevelField = deviation.fieldPath.split(".")[0] ?? deviation.fieldPath;
    const weight = highPriorityFields.has(topLevelField) ? 2.0 : 1.0;
    totalWeight += weight;
  }

  const normaliser = Math.max(totalWeight, 1);
  return Math.min(totalWeight / normaliser, 1.0);
}

function classifyAgreement(deviationScore: number, threshold: number): AgreementLevel {
  if (deviationScore === 0) return "full";
  if (deviationScore <= threshold) return "partial";
  return "none";
}

function assessRisk(
  deviations: Deviation[],
  deviationScore: number,
  highPriorityFields: ReadonlySet<string>
): RiskLevel {
  const hasHighPriorityDeviation = deviations.some((d) =>
    highPriorityFields.has(d.fieldPath.split(".")[0] ?? d.fieldPath)
  );

  if (hasHighPriorityDeviation || deviationScore >= 0.5) return "high";
  if (deviationScore > 0) return "medium";
  return "low";
}

function isPlainObject(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function deepEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function roundTo6(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}
