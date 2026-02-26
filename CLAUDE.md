# CLAUDE.md — agent-shadow-mode

## Project Purpose

Standalone shadow mode evaluation tool for AI agents. Runs a candidate agent in
parallel with a production agent, captures what it *would have done*, compares
against actual decisions, and scores agreement over time. Humans review the report
and decide whether to promote the agent.

## Fire Line (Non-Negotiable)

- NO automatic trust level changes — recommendations are strings, never API calls
- NO AumOS Trust Ladder integration
- NO PWM, contextual user data, or session history in comparisons
- NO side effects during shadow execution
- Shadow mode is STANDALONE — it knows nothing about AumOS internals

## Package Structure

```
python/src/shadow_mode/     Python package (agent-shadow-mode on PyPI)
typescript/src/             TypeScript package (@aumos/shadow-mode on npm)
examples/                   Runnable usage examples
docs/                       Architecture and integration guides
```

## Forbidden Identifiers

These must NEVER appear in any source file:

```
progressLevel, promoteLevel, computeTrustScore, behavioralScore
adaptiveBudget, optimizeBudget, predictSpending
detectAnomaly, generateCounterfactual
PersonalWorldModel, MissionAlignment, SocialTrust
CognitiveLoop, AttentionFilter, GOVERNANCE_PIPELINE
```

## Code Standards

- Python 3.10+, Pydantic v2, ruff, mypy --strict
- TypeScript strict mode, tsup, Vitest
- License header on every source file (BSL-1.1)
- Type hints on all Python function signatures
- Descriptive variable names — no abbreviations

## Key Design Decisions

- `ShadowAdapter.intercept_side_effects()` is an async context manager that
  suppresses or mocks external calls (HTTP, DB, queues) during shadow execution.
- `ConfidenceReport.recommendation` is a plain `str` — never an enum, flag,
  or API payload.
- `ShadowRecorder` supports both in-memory and JSONL file backends.
- `ShadowComparator.compare()` is synchronous — comparison is pure computation.
- Deviation is computed as a float in [0.0, 1.0] — 0.0 means identical outputs.
