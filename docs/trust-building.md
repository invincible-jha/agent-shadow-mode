# Trust Building with Shadow Mode

Shadow mode produces evidence. What you do with that evidence is a human decision.
This document explains how to interpret shadow evaluation reports in the context of
deciding whether to adjust an agent's trust configuration, and what the workflow
looks like in practice.

---

## The core principle

Shadow mode does not promote agents. It observes them.

`ConfidenceReport.recommendation` is a plain string. It is never an API call, a
configuration write, or a signal to any governance system. The string describes the
observed data and suggests what a human might consider doing. Acting on it requires
a deliberate operator decision followed by a deliberate configuration change.

---

## What shadow mode measures

Shadow mode compares an agent's proposed outputs against production outputs on the
same inputs, under side-effect isolation. After accumulating enough comparisons, it
reports:

| Metric | What it tells you |
|--------|-------------------|
| Agreement rate | How often the shadow agent would have made the same decision as production |
| Average deviation | How different the shadow outputs were, on average |
| Worst deviation | The single largest divergence observed |
| High-risk count | How many comparisons involved differences in critical output fields |
| Recommendation | Plain-text advisory based on the above |

What it does **not** measure:

- Correctness — whether production's decisions were right.
- Speed or throughput.
- Behaviour on unseen input distributions.
- Long-term stability after a configuration change.

---

## Building an evidence base

Shadow evaluation reports are more useful as evidence accumulates over time. A
meaningful evidence base has:

1. **Sufficient sample size.** The `ConfidenceScorer` default is 100 comparisons
   before a positive advisory is issued. For safety-critical domains consider 500 or
   more.

2. **Representative inputs.** If the test cases you shadow are not representative of
   the production distribution, the agreement rate may not generalise. Cover normal
   cases, edge cases, and boundary inputs.

3. **Stable production behaviour.** If the production agent's behaviour is itself
   changing (e.g., due to model updates), the shadow comparisons may reflect that
   instability rather than a property of the shadow agent.

4. **Multiple evaluation windows.** Run shadow evaluations across different time
   periods and input conditions. A single batch may reflect a narrow slice of
   behaviour.

---

## Interpreting the recommendation string

The recommendation string follows four patterns:

### Pattern 1 — Insufficient data

```
"Based on 72.0% agreement over 50 decision(s): sample size is below the
recommended minimum of 100. Accumulate 50 more decision(s) before drawing
conclusions."
```

Action: Continue shadow evaluation. Do not draw conclusions from this batch.

### Pattern 2 — High-risk deviations present

```
"Based on 89.0% agreement over 120 decision(s): 14 high-risk deviation(s)
detected (worst deviation score: 0.82). Review deviations before considering
any promotion."
```

Action: Read the per-decision breakdown in the report. Identify which inputs
trigger high-risk deviations. Determine whether the deviations reflect a genuine
behavioural difference or an artefact of the evaluation setup (e.g., stub tool
responses causing downstream differences). If genuine, the shadow agent is not
ready for a higher trust assignment.

### Pattern 3 — Strong performance, ready for consideration

```
"Based on 96.1% agreement over 200 decision(s): shadow performance is strong.
A human operator may consider promoting this agent to a higher trust level."
```

Action: Review the report. Verify that the test inputs were representative. If
the evidence is satisfactory, an operator may choose to update the agent's trust
configuration. This is a manual step — see the workflow below.

### Pattern 4 — Below threshold, keep monitoring

```
"Based on 91.3% agreement over 150 decision(s): shadow performance is below
the strong agreement threshold (95.0%) by 3.7%. Continue monitoring before
considering any promotion."
```

Action: Continue shadow evaluation. Review recent disagreements to understand
whether the gap is closing or stable.

---

## Adjusting trust configuration (manual workflow)

If you decide to act on a shadow evaluation report, the change to an agent's trust
level is made by an operator through a deliberate configuration update. Shadow mode
plays no part in that update.

Using `aumos-edge-runtime` as the governance layer:

1. Review the evaluation report and confirm the evidence meets your threshold.
2. Open the agent's governance configuration file (`edge-config.toml`).
3. Update the `level` field for the agent in the `[[agents]]` table:

   ```toml
   [[agents]]
   agent_id = "my-agent-001"
   level = "elevated"   # changed from "standard" after review
   ```

4. Push the updated config via your deployment pipeline or via the sync server.
5. Optionally call `EdgeGovernanceEngine.reload_config()` if the engine is running
   as a long-lived process.
6. Record the change with a rationale: who made it, which report supported it, and
   when it was made. Keep this as part of your audit trail.

Trust levels are: `restricted`, `standard`, `elevated`, `system`. A human operator
sets these values. They are not inferred or incremented automatically.

---

## Choosing evaluation parameters

### Agreement threshold in ConfidenceScorer

```python
scorer = ConfidenceScorer(
    strong_agreement_threshold=0.95,  # positive advisory requires >= 95% agreement
    minimum_sample_size=100,           # positive advisory requires >= 100 decisions
)
```

Set these based on the consequences of the agent's actions:

| Domain | Suggested strong_agreement_threshold | Suggested minimum_sample_size |
|--------|--------------------------------------|-------------------------------|
| Internal tooling | 0.85 | 50 |
| Customer-facing | 0.90 | 100 |
| Financial approvals | 0.95 | 200 |
| Safety-critical | 0.98 | 500 |

### High-priority fields in ShadowComparator

Set `high_priority_fields` to the fields that represent the agent's core decision:

```python
comparator = ShadowComparator(
    high_priority_fields=frozenset({"approved", "action", "tier"}),
    agreement_threshold=0.1,
)
```

Excluding non-critical fields (e.g., internal trace IDs, timestamps, explanatory
text) from high-priority weighting prevents them from inflating the risk score.

---

## Limitations of shadow-based evidence

Shadow evaluation is one input to a promotion decision, not the only input.
Consider also:

- **Correctness audits.** Shadow mode compares shadow to production — it does not
  assess whether production is correct. If production has known errors, high
  agreement with production may not be a positive signal.
- **Distribution shift.** Test inputs used during shadow evaluation may not match
  future production inputs. Evaluate across multiple time periods.
- **Tool stub artefacts.** When using `LangChainAdapter` or `CrewAIAdapter`,
  shadow agent outputs may differ from what the agent would produce with real tool
  responses. High-deviation cases in tool-dependent fields should be examined
  carefully.
- **Single-model evaluations.** If shadow and production use the same underlying
  model with the same configuration, high agreement is expected. The evidence is
  more meaningful when the shadow agent uses a different model version, different
  prompting, or different logic.

---

## Keeping the loop closed

After adjusting a trust configuration based on shadow evidence:

1. Continue running shadow evaluations on the agent at its new trust level.
2. Monitor for regressions — an agent that performs well at a lower trust level
   may behave differently when it has access to higher-privilege actions.
3. Archive the shadow evaluation reports as part of your governance audit trail.
   They are the documented basis for the configuration change.

Shadow mode provides continuous observability, not a one-time gate. Running it
persistently gives you an ongoing signal about whether an agent's behaviour remains
consistent with expectations.
