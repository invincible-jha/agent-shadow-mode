# Contributing

Thank you for your interest in contributing to `agent-shadow-mode`.

This project is part of the AumOS open-source governance protocol suite maintained by
MuVeraAI Corporation. Contributions are welcome subject to the guidelines below.

## Before You Start

- Read [FIRE_LINE.md](FIRE_LINE.md). All contributions must respect the hard boundaries
  defined there. PRs that violate the fire line will be closed without review.
- Check open issues and the project roadmap before starting large changes.
- For non-trivial features, open an issue first to discuss the approach.

## Development Setup

```bash
cd python
pip install -e ".[dev]"
ruff check src/
mypy src/
pytest
```

For the TypeScript package:

```bash
cd typescript
npm install
npm run lint
npm run build
npm test
```

## Commit Convention

Follow the AumOS commit convention:

```
feat(agent-shadow-mode): add CrewAI adapter
fix(agent-shadow-mode): handle empty comparison list in scorer
docs(agent-shadow-mode): clarify fire line rules
test(agent-shadow-mode): add edge cases for deviation calculation
```

## Pull Request Process

1. Fork the repository and create a feature branch from `main`.
2. Ensure `ruff`, `mypy --strict`, and `pytest` all pass with zero warnings.
3. Add or update docstrings for any public API changes.
4. Update `CHANGELOG.md` under an `[Unreleased]` section.
5. Submit a PR targeting `main`.

## License

By contributing you agree that your contributions will be licensed under the
Business Source License 1.1. See [LICENSE](LICENSE).
