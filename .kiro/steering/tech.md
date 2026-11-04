---
inclusion: always
---

# Technology

- Python 3.12. Package manager: `uv`. Layout: `skeleton/` is an installable package named `nightaudit`; each app is its
  own package that depends on it.
- Data model: `pydantic` v2 models. Money is `decimal.Decimal`, never float.
- Tests: `pytest`. Property-based tests use `hypothesis` (default 100 examples, `derandomize` in CI). Every property in a
  design document gets one test whose name starts with `test_property_`.
- Web: FastAPI serving JSON plus a static front end in `skeleton/web/` (TypeScript, Vite, no UI framework, SVG for the
  Venn diagram). The UI kit is shared by both apps.
- AWS access: `boto3`, read-only calls only. The deployed audit runs on AWS Lambda with a read-only IAM role.
- Explanations: Amazon Bedrock Converse API, model id from configuration. A deterministic template runs when the model is
  unavailable, and the output must still pass the explanation guard.
- Evidence: JSON Lines with a SHA-256 hash chain and a manifest that records the control spec hash and each ledger
  snapshot hash.
- Lint and types: `ruff` and `mypy --strict` on `skeleton/`.
- No network access in unit and property tests. Connectors are tested against recorded fixtures.

## Commands

| Task | Command |
|---|---|
| Install | `uv sync` |
| All tests | `uv run pytest` |
| Properties only | `uv run pytest -m property` |
| Lint | `uv run ruff check . && uv run mypy skeleton` |
| Run an app locally | `uv run nightaudit serve --app vampires` |
