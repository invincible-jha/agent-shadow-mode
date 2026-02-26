# Fire Line — agent-shadow-mode

## What This Package IS

- A standalone evaluation tool for running AI agents in shadow mode
- A comparator that diffs shadow recommendations against actual production decisions
- A confidence scorer that produces human-readable summary strings
- A recorder that stores shadow decision history (in-memory or file-backed)
- Framework adapters for side-effect interception (LangChain, CrewAI, generic)

## What This Package IS NOT

- NOT an AumOS component or integrated with the AumOS Trust Ladder
- NOT a system that automatically changes, sets, or escalates trust levels
- NOT a behavioral scoring or adaptive learning system
- NOT a decision engine — it only observes and compares
- NOT connected to any external API for trust management

## Hard Rules

1. **No automatic trust changes.** The `ConfidenceReport.recommendation` is a plain
   human-readable string. It is never an API call, a state mutation, or a signal to
   any upstream system.

2. **No AumOS Trust Ladder integration.** Shadow mode has no knowledge of AumOS
   trust levels, APIs, or internal protocols. It is vendor-neutral.

3. **No contextual personal data in comparisons.** Comparisons operate on structured
   decision outputs only. No PWM, user profiles, or session context is stored.

4. **No side effects during shadow execution.** Adapters MUST intercept and suppress
   all external calls (HTTP, DB writes, queue publishes) made by the shadow agent.
   The shadow runs in a dry-run context manager.

5. **Recommendations are strings, not actions.** Example of an acceptable
   recommendation: `"Based on 95% agreement over 200 decisions, consider promoting
   to L3."` — the human operator reads this and decides what to do.

## Forbidden Identifiers

These must NEVER appear in source code:

```
progressLevel, promoteLevel, computeTrustScore, behavioralScore
adaptiveBudget, optimizeBudget, predictSpending
detectAnomaly, generateCounterfactual
PersonalWorldModel, MissionAlignment, SocialTrust
CognitiveLoop, AttentionFilter, GOVERNANCE_PIPELINE
```
