# agent-shadow-mode

Run an AI agent in shadow mode — observe real decisions, generate parallel recommendations, compare outcomes. Build a trust track record before going live.

[![PyPI](https://img.shields.io/pypi/v/agent-shadow-mode)](https://pypi.org/project/agent-shadow-mode/)
[![npm](https://img.shields.io/npm/v/@aumos/shadow-mode)](https://www.npmjs.com/package/@aumos/shadow-mode)
[![License: BSL-1.1](https://img.shields.io/badge/License-BSL%201.1-blue)](LICENSE)
[![Governance Score](https://img.shields.io/badge/governance-self--assessed-blue)](https://github.com/aumos-ai/agent-shadow-mode)

---

## What Is Shadow Mode?

Shadow mode lets you run a new AI agent or decision system in parallel with an existing (production) system, without exposing its outputs to end users or triggering side effects. You capture what the shadow agent *would have done*, compare it to what the production agent *actually did*, and accumulate a scored track record.

Only a human operator reviews the track record and decides whether to promote the agent. The tool never changes trust levels automatically.

```
User Request
     │
     ├──► Production Agent ──► Actual Decision (recorded)
     │
     └──► Shadow Agent ──► Shadow Recommendation (no side effects)

ShadowComparator ──► ComparisonResult
ConfidenceScorer ──► ConfidenceReport ──► Human-readable recommendation string
```

---

## Installation

**Python**

```bash
pip install agent-shadow-mode
```

**TypeScript / Node.js**

```bash
npm install @aumos/shadow-mode
```

---

## Quick Start (Python)

```python
import asyncio
from shadow_mode import ShadowRunner, ShadowComparator, ConfidenceScorer
from shadow_mode.adapters import GenericAdapter

async def my_production_agent(input_data: dict) -> dict:
    # your existing agent logic
    return {"action": "approve", "reason": "within_policy"}

async def my_shadow_agent(input_data: dict) -> dict:
    # new agent being evaluated
    return {"action": "approve", "reason": "within_policy"}

async def main() -> None:
    adapter = GenericAdapter()
    runner = ShadowRunner(agent_fn=my_shadow_agent, adapter=adapter)

    # Run shadow execution — no side effects
    shadow_decision = await runner.shadow_execute({"amount": 500, "user": "alice"})

    # Capture what production actually did
    from shadow_mode.types import ActualDecision
    actual = ActualDecision(
        decision_id=shadow_decision.decision_id,
        output={"action": "approve", "reason": "within_policy"},
        timestamp=shadow_decision.timestamp,
    )

    comparator = ShadowComparator()
    comparison = comparator.compare(shadow_decision, actual)
    print(f"Agreement: {comparison.agreed}")

    scorer = ConfidenceScorer()
    report = scorer.score([comparison])
    print(report.recommendation)

asyncio.run(main())
```

---

## Quick Start (TypeScript)

```typescript
import { ShadowRunner, ShadowComparator, ConfidenceScorer } from "@aumos/shadow-mode";

const runner = new ShadowRunner(async (input) => {
  return { action: "approve", reason: "within_policy" };
});

const shadowDecision = await runner.shadowExecute({ amount: 500, user: "alice" });

const actual = {
  decisionId: shadowDecision.decisionId,
  output: { action: "approve", reason: "within_policy" },
  timestamp: new Date().toISOString(),
};

const comparator = new ShadowComparator();
const comparison = comparator.compare(shadowDecision, actual);

const scorer = new ConfidenceScorer();
const report = scorer.score([comparison]);
console.log(report.recommendation);
```

---

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full design.

### Core Components

| Component | Role |
|---|---|
| `ShadowRunner` | Executes agent without side effects via adapter context manager |
| `ShadowComparator` | Compares shadow recommendation to actual production decision |
| `ConfidenceScorer` | Aggregates comparison results into a human-readable confidence report |
| `ShadowRecorder` | In-memory and persistent history of shadow decisions |
| Adapters | Framework-specific side-effect interception (Generic, LangChain, CrewAI) |

### Adapters

| Adapter | Use Case |
|---|---|
| `GenericAdapter` | Wraps any Python callable |
| `LangChainAdapter` | Intercepts LangChain tool calls |
| `CrewAIAdapter` | Intercepts CrewAI task execution |

---

## Fire Line

This project has strict boundaries. See [FIRE_LINE.md](FIRE_LINE.md).

**Shadow mode never automatically changes trust levels.** The `ConfidenceReport.recommendation` field is a plain string like `"Based on 95% agreement over 200 decisions, consider promoting to L3."` — it is advisory only. No API calls are made.

---

## Examples

- [`examples/basic_shadow.py`](examples/basic_shadow.py) — Shadow a simple function
- [`examples/langchain_shadow.py`](examples/langchain_shadow.py) — Shadow a LangChain agent
- [`examples/evaluation_report.py`](examples/evaluation_report.py) — Generate a full trust-building report

---

## License

Business Source License 1.1. See [LICENSE](LICENSE) and https://mariadb.com/bsl11/.

Copyright (c) 2026 MuVeraAI Corporation.
