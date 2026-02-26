// SPDX-License-Identifier: BSL-1.1
// Copyright (c) 2026 MuVeraAI Corporation

/**
 * ShadowRunner — execute an agent without side effects and capture its output.
 *
 * The runner is the TypeScript entry point for shadow mode. It wraps the
 * shadow agent function and executes it, capturing the output as a
 * ShadowDecision. Raw input is never stored — only a SHA-256 hash.
 *
 * Note: The TypeScript runner does not implement an adapter context manager
 * pattern (as in Python). Side-effect interception in TypeScript is expected
 * to be handled by the caller wrapping the agentFn with appropriate mocks,
 * or by injecting dependency-injected mock services into the agent.
 */

import { createHash, randomUUID } from "node:crypto";

import type { ShadowDecision } from "./types.js";

/** Agent function signature — accepts a dict and returns a dict asynchronously. */
export type AgentFn = (
  input: Record<string, unknown>
) => Promise<Record<string, unknown>>;

/**
 * Executes a shadow agent without side effects.
 *
 * @example
 * ```typescript
 * const runner = new ShadowRunner(async (input) => {
 *   return { action: "approve", confidence: 0.92 };
 * });
 *
 * const decision = await runner.shadowExecute({ amount: 500 });
 * console.log(decision.output); // { action: "approve", confidence: 0.92 }
 * ```
 */
export class ShadowRunner {
  private readonly agentFn: AgentFn;
  private readonly adapterName: string;

  /**
   * @param agentFn - The shadow agent coroutine. Must accept and return
   *   Record<string, unknown>.
   * @param adapterName - Optional label for the adapter used. Defaults to "generic".
   */
  constructor(agentFn: AgentFn, adapterName = "generic") {
    this.agentFn = agentFn;
    this.adapterName = adapterName;
  }

  /**
   * Execute the shadow agent and capture its output as a ShadowDecision.
   *
   * @param inputData - The input dict passed to both production and shadow agents.
   * @param decisionId - Optional explicit ID to correlate with the matching
   *   ActualDecision. If omitted, a new UUID v4 is generated.
   * @returns ShadowDecision with output, timestamp, adapter name, and metadata.
   * @throws ShadowExecutionError if the shadow agent throws.
   */
  async shadowExecute(
    inputData: Record<string, unknown>,
    decisionId?: string
  ): Promise<ShadowDecision> {
    const resolvedId = decisionId ?? randomUUID();
    const inputHash = hashInput(inputData);
    const timestamp = new Date().toISOString();

    let output: Record<string, unknown>;
    try {
      output = await this.agentFn(inputData);
    } catch (error) {
      throw new ShadowExecutionError(
        `Shadow agent threw an exception: ${String(error)}`,
        { cause: error }
      );
    }

    return {
      decisionId: resolvedId,
      inputHash,
      output,
      timestamp,
      adapterName: this.adapterName,
      metadata: {},
    };
  }
}

/** Thrown when the shadow agent function raises an exception during execution. */
export class ShadowExecutionError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ShadowExecutionError";
  }
}

/** Compute a SHA-256 hex digest of a deterministically serialised input dict. */
function hashInput(inputData: Record<string, unknown>): string {
  const serialised = JSON.stringify(inputData, Object.keys(inputData).sort());
  return createHash("sha256").update(serialised, "utf8").digest("hex");
}
