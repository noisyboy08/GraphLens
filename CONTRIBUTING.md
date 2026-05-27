# Contributing

Thanks for improving GraphLens.

## Development Setup

```bash
pip install -e ".[dev]"
pytest -q
```

## Before Opening A PR

Run:

```bash
pytest -q
graphlens doctor
graphlens benchmark tests/fixtures/sample_python
```

## Code Style

- Keep changes focused.
- Prefer typed functions.
- Add tests for behavior changes.
- Keep parser failures graceful; parsing one bad file should not stop a repository build.
- Do not require cloud services for core functionality.

## Useful Areas To Improve

- More precise Tree-sitter queries.
- Better language-specific import resolution.
- Better blast radius ranking.
- More MCP client examples.
