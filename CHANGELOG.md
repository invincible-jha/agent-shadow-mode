# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - 2026-02-26

### Added

- `ShadowRunner` — executes shadow agent without side effects via adapter context manager
- `ShadowComparator` — compares shadow recommendation to actual production decision, computes agreement and deviation
- `ConfidenceScorer` — aggregates comparison list into `ConfidenceReport` with human-readable recommendation string
- `ShadowRecorder` — in-memory and JSONL file-backed history of shadow decisions
- `ShadowReporter` — generates Markdown, JSON, and plain-text evaluation reports
- Adapters: `GenericAdapter`, `LangChainAdapter`, `CrewAIAdapter`
- Full Pydantic v2 type definitions: `ShadowDecision`, `ActualDecision`, `ComparisonResult`, `ConfidenceReport`
- TypeScript mirror: `ShadowRunner`, `ShadowComparator`, `ConfidenceScorer` with matching types
- Examples: basic shadow, LangChain shadow, evaluation report generation
- Docs: architecture, evaluation criteria, adapters guide, trust-building guide
