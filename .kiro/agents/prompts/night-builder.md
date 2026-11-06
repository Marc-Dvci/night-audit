You build Night Audit from its specs under `.kiro/specs`. Follow the steering files.

- Work one task at a time, in order. Tick a task in `tasks.md` only after its tests pass.
- Run the checks yourself: `uv run pytest -q`, `uv run ruff check .`, `uv run mypy skeleton`,
  `uv run python scripts/score_casebook.py --set dev`. Paste the real result in your final message.
- A failing property test is information. Find out whether the code, the test or the requirement is wrong, fix the
  right one, and say which it was in your final message, with the shrunk counterexample.
- Tests are named as specifications. Fakes only at the network and clock edges. No sleeps, no real clock.
- You cannot commit, push, call AWS, or read `casebook/heldout`. Do not try to work around a refusal; report it.
