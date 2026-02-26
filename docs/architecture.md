# agent-shadow-mode — Architecture

## Overview

`agent-shadow-mode` is a standalone evaluation tool that runs a candidate AI agent
in parallel with a production agent, captures what the candidate *would have done*
without causing any real side effects, and produces a scored comparison report.
The report is advisory: it gives human operators evidence to inform their decisions,
but it never changes any agent configuration automatically.

---

## Package structure

```
agent-shadow-mode/
├── python/
│   └── src/shadow_mode/
│       ├── runner.py        ShadowRunner — executes shadow agent safely
│       ├── comparator.py    ShadowComparator — field-level diff + scoring
│       ├── scorer.py        ConfidenceScorer — aggregates comparisons
│       ├── recorder.py      ShadowRecorder — persists shadow decisions
│       ├── report.py        ShadowReporter — formats output (text/MD/JSON)
│       ├── types.py         Shared Pydantic v2 types
│       └── adapters/
│           ├── base.py      ShadowAdapter ABC
│           ├── generic.py   GenericAdapter (no-op)
│           ├── langchain.py LangChainAdapter (patches BaseTool)
│           └── crewai.py    CrewAIAdapter (patches Task + Crew)
├── typescript/src/          TypeScript port (@aumos/shadow-mode on npm)
├── examples/                Runnable usage examples
└── docs/                    Architecture and integration guides
```

---

## Component responsibilities

### ShadowRunner

`ShadowRunner` is the entry point. It wraps a shadow agent coroutine and runs it
inside the adapter's `intercept_side_effects()` context manager. It captures the
output as a `ShadowDecision` and ensures that:

- Raw input is never stored (only a SHA-256 hash is recorded).
- External calls, DB writes, and queue publishes are suppressed by the adapter.
- Exceptions from the shadow agent are wrapped in `ShadowExecutionError` and
  re-raised to the caller.

```python
runner = ShadowRunner(agent_fn=my_shadow_agent, adapter=LangChainAdapter())
shadow_decision = await runner.shadow_execute(input_data, decision_id="order-123")
```

### ShadowAdapter

`ShadowAdapter` is an abstract base class that defines the interception interface.
It exposes a single async context manager, `intercept_side_effects()`, which must
install and remove all interception hooks cleanly — even if the shadow agent raises.

The adapter also exposes `get_captured_metadata()` to return information about
intercepted calls (e.g., tool call counts). This metadata is stored on
`ShadowDecision.metadata` and is available for analysis in the report.

See [adapters.md](adapters.md) for the full adapter contract and framework-specific
implementations.

### ShadowComparator

`ShadowComparator.compare()` takes a `ShadowDecision` and an `ActualDecision` and
produces a `ComparisonResult`. It is synchronous and purely functional — no I/O, no
state, no external calls.

The comparator:

1. Recursively finds field-level deviations between `shadow.output` and `actual.output`.
2. Computes a deviation score in `[0.0, 1.0]`, weighting high-priority fields at 2x.
3. Classifies agreement as `FULL`, `PARTIAL`, or `NONE` based on the deviation score
   and a configurable threshold.
4. Assesses risk as `LOW`, `MEDIUM`, or `HIGH` based on deviation magnitude and
   whether any high-priority fields differ.

See [evaluation-criteria.md](evaluation-criteria.md) for how to interpret these values.

### ConfidenceScorer

`ConfidenceScorer.score()` aggregates a list of `ComparisonResult` objects into a
`ConfidenceReport`. It computes:

- Agreement rate (agreed comparisons / total)
- Average and worst deviation scores
- Risk score (proportion of HIGH-risk comparisons)
- `high_risk_count`
- A plain-text `recommendation` string

The `recommendation` is always a `str`. It is advisory only — it is never an API
call, flag, or state mutation. Trust levels are never changed by this component.

### ShadowRecorder

`ShadowRecorder` stores `ShadowDecision` objects. Two backends are available:

| Backend | Usage |
|---------|-------|
| In-memory (default) | Short evaluation sessions; data lost on process exit |
| JSONL file (opt-in) | Persistent recording across restarts |

Only the input hash and structured output are recorded. Raw input data is never
stored by design.

### ShadowReporter

`ShadowReporter` formats a `ConfidenceReport` (and optional `ComparisonResult` list)
into three output formats:

| Method | Format | Use case |
|--------|--------|----------|
| `to_text()` | Plain text | CLI output, log files |
| `to_markdown()` | Markdown | GitHub issues, PRs, wiki pages |
| `to_json()` | JSON | Machine-readable downstream tooling |

---

## Data flow

```
Input dict
    │
    ├──► shadow_agent_fn(input)      ← inside intercept_side_effects()
    │         │                         no real external calls escape
    │         ▼
    │    ShadowDecision
    │    { decision_id, input_hash, output, metadata }
    │
    ├──► production_agent_fn(input)  ← real execution, real side effects
    │         │
    │         ▼
    │    ActualDecision
    │    { decision_id, output }
    │
    ▼
ShadowComparator.compare(shadow, actual)
    │
    ▼
ComparisonResult
{ agreed, deviation_score, deviations, risk_level }
    │
    ▼  (accumulate many)
ConfidenceScorer.score(comparisons)
    │
    ▼
ConfidenceReport
{ agreement_rate, average_deviation, recommendation, ... }
    │
    ▼
ShadowReporter.to_markdown / to_json / to_text
```

---

## Decision IDs

Every shadow run must be tied to a `decision_id` that correlates the
`ShadowDecision` with the corresponding `ActualDecision`. The caller is responsible
for generating and tracking this ID. A common pattern is to use the production
agent's transaction ID, request ID, or order ID.

```python
# Caller generates the correlation ID
decision_id = f"order-{order.id}"

shadow_decision = await runner.shadow_execute(input_data, decision_id=decision_id)
actual_output = await production_agent(input_data)
actual_decision = ActualDecision(decision_id=decision_id, output=actual_output)
comparison = comparator.compare(shadow_decision, actual_decision)
```

---

## Invariants

These invariants are enforced throughout the codebase:

1. **No raw input storage.** `ShadowDecision.input_hash` is a SHA-256 hash of the
   serialised input. The input dict itself is never stored or logged.
2. **No automatic state changes.** `ConfidenceReport.recommendation` is a `str`.
   No trust level changes without a human operator acting on the report.
3. **No AumOS internals.** Shadow mode is a standalone package. It has no imports
   from AumOS trust ladder, PWM, or any governance pipeline.
4. **Side-effect isolation.** All shadow agent executions happen inside the
   adapter's context manager. A failed restore (exception during exit) is reported
   as an error to the caller, not silently swallowed.
5. **Comparator is pure.** `ShadowComparator.compare()` has no side effects and
   produces deterministic output for the same inputs.
