# Evaluation Criteria

This document explains how to interpret the numbers produced by
`ShadowComparator` and `ConfidenceScorer`, and what actions they warrant.

---

## ComparisonResult — per-decision fields

Each `ComparisonResult` covers a single shadow / actual decision pair.

### `agreed` (bool)

`True` when the overall `deviation_score` is at or below the comparator's
`agreement_threshold` (default `0.1`). This is a coarse signal:

- `True` — the shadow and actual outputs were close enough to be considered
  equivalent for the purposes of this evaluation run.
- `False` — there was a meaningful difference. Read `deviations` for details.

`agreed=True` does not mean the outputs were identical. It means the deviation
was below the configured tolerance. Set a lower `agreement_threshold` to require
closer matches.

### `agreement_level` (AgreementLevel)

A qualitative label derived from `deviation_score`:

| Value | Meaning |
|-------|---------|
| `FULL` | `deviation_score == 0.0` — outputs are byte-for-byte identical |
| `PARTIAL` | `0.0 < deviation_score <= agreement_threshold` — minor differences |
| `NONE` | `deviation_score > agreement_threshold` — significant differences |

### `deviation_score` (float, 0.0–1.0)

A normalised measure of how different the shadow output was from the actual
output.

- `0.0` — outputs are identical in all compared fields.
- `1.0` — maximum measured deviation (all fields differ, all weighted as high-priority).

The score is computed by summing field weights across all deviations and
normalising. High-priority fields (configurable via `ShadowComparator`) carry 2x
the weight of other fields. The score is capped at `1.0`.

Practical interpretation:

| Range | Interpretation |
|-------|----------------|
| `0.00` | Exact match |
| `0.01–0.10` | Minor differences, typically in metadata or secondary fields |
| `0.11–0.30` | Moderate differences — investigate the specific deviations |
| `0.31–0.60` | Significant differences — high likelihood of consequential divergence |
| `0.61–1.00` | Severe divergence — shadow agent behaves substantially differently |

These ranges are guidelines; calibrate thresholds based on your domain.

### `deviations` (list[Deviation])

The list of individual field-level differences. Each `Deviation` contains:

- `field_path` — dot-separated path to the differing field (e.g., `"action.type"`)
- `shadow_value` — the value the shadow agent produced
- `actual_value` — the value the production agent produced
- `description` — a human-readable summary of the difference

Use `deviations` to pinpoint exactly where the shadow agent diverges. Common
patterns:

- Differences only in `metadata.*` fields — usually not consequential; consider
  excluding these paths from high-priority weighting.
- Differences in `action` or `approved` — usually consequential; keep these
  in `high_priority_fields`.
- Missing fields (shadow produced a key that actual did not, or vice versa) —
  indicates a schema mismatch between the candidate and production agents.

### `risk_level` (RiskLevel)

| Value | Conditions |
|-------|-----------|
| `HIGH` | Any high-priority field differs, OR `deviation_score >= 0.5` |
| `MEDIUM` | `deviation_score > 0.0` and no high-priority field differs |
| `LOW` | `deviation_score == 0.0` (no deviations) |

`HIGH` risk comparisons are counted in `ConfidenceReport.high_risk_count` and
contribute to `risk_score`. They are the primary signal for whether a shadow agent
is safe for promotion consideration.

---

## ConfidenceReport — aggregate fields

`ConfidenceScorer.score()` aggregates all `ComparisonResult` objects into a
`ConfidenceReport`.

### `agreement_rate` (float, 0.0–1.0)

```
agreement_rate = agreement_count / total_comparisons
```

The fraction of comparisons where the shadow agreed with production. This is the
headline metric. Practical thresholds depend on domain risk:

| Domain | Suggested minimum agreement rate |
|--------|----------------------------------|
| Low-stakes classification | ~0.80 |
| Customer-facing approvals | ~0.90 |
| Financial or safety-critical | ~0.95 |

These are starting points, not hard rules. Set your own threshold in
`ConfidenceScorer(strong_agreement_threshold=...)`.

### `average_deviation` (float, 0.0–1.0)

The mean `deviation_score` across all comparisons. Use this alongside
`agreement_rate`:

- High `agreement_rate` but high `average_deviation` — the shadow often agrees
  on the core decision but diverges significantly on secondary fields. Investigate
  what those secondary fields represent.
- Low `agreement_rate` and low `average_deviation` on disagreements — the shadow
  disagrees frequently but on small differences. May indicate a threshold issue.

### `worst_deviation` (float, 0.0–1.0)

The maximum `deviation_score` observed across all comparisons. A single very high
`worst_deviation` (e.g., `1.0`) warrants investigation even if the aggregate
`agreement_rate` is strong.

### `risk_score` (float, 0.0–1.0)

```
risk_score = high_risk_count / total_comparisons
```

The proportion of comparisons rated `HIGH` risk. A `risk_score` of `0.0` means no
high-risk comparisons were observed. Any non-zero `risk_score` warrants review of
the specific `HIGH` risk cases.

### `high_risk_count` (int)

The raw count of `HIGH` risk comparisons. Use this alongside `total_comparisons`
to assess absolute exposure, not just the fraction.

### `recommendation` (str)

A plain human-readable advisory string. Its format is:

```
"Based on X% agreement over N decision(s): <advisory text>"
```

Possible advisory scenarios:

| Scenario | Advisory text |
|----------|---------------|
| Sample too small | "sample size is below the recommended minimum of N. Accumulate M more..." |
| High-risk deviations present | "X high-risk deviation(s) detected (worst deviation score: Y). Review before considering any promotion." |
| Agreement rate strong, no high-risk | "shadow performance is strong. A human operator may consider promoting this agent to a higher trust level." |
| Agreement rate below threshold | "shadow performance is below the strong agreement threshold (X%) by Y%. Continue monitoring..." |

**The recommendation is advisory only.** It is a `str`. It does not trigger any API
call, state change, or trust level update. A human operator reads it and decides
what to do.

---

## Configuring the comparator

### `high_priority_fields`

The set of top-level field names whose deviations are weighted at 2x. Default:

```python
frozenset({"action", "decision", "approved", "blocked", "result", "status"})
```

Customise this for your agent's output schema. Fields that represent the core
decision (approve / deny / escalate) should be high-priority. Fields that carry
metadata, explanatory text, or internal state should not.

```python
comparator = ShadowComparator(
    high_priority_fields=frozenset({"approved", "tier", "action"}),
)
```

### `agreement_threshold`

The maximum `deviation_score` at which a comparison is still considered agreed.
Default: `0.1`.

- Set lower (e.g., `0.0`) to require exact output matches.
- Set higher (e.g., `0.2`) to tolerate minor secondary-field differences.

---

## Interpreting tool-call metadata (LangChain / CrewAI)

When using `LangChainAdapter` or `CrewAIAdapter`, the shadow agent's tool calls
are intercepted and stubbed. `ShadowDecision.metadata` contains:

| Key | Description |
|-----|-------------|
| `intercepted_tool_calls` | List of intercepted call records |
| `total_tool_calls` | Total number of tool calls attempted by the shadow agent |

A shadow agent that attempts zero tool calls when the production agent would have
used several may produce a different output not because of a logic change but
because it lacked the tool data. Factor this into your deviation analysis:
deviations in fields that depend on tool responses are less meaningful than
deviations in fields that reflect the agent's core routing logic.

---

## What the report does not tell you

- Whether the shadow agent would perform correctly with real tool responses.
  Shadow tool calls always return stub values, so output fields that depend on
  real tool data will differ from production.
- Whether the shadow agent is faster or slower than production.
- Whether the shadow agent's outputs are correct in an absolute sense — only
  whether they match production's outputs.
- Whether the agent should be promoted. That decision belongs to a human operator,
  not to the report.
