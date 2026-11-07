# Tasks: the night shift

Requirement 2 (the Kiro power) only. Requirements 1 and 3 get tasks when they are taken up.

## Requirement 2: the Kiro power

- [x] **1. Manifest and MCP config.** `power/night-audit/plugin.json` and `mcp.json` as designed in §1. [Req 2.1]
- [x] **2. Shared references.** `region-table.md` and `audit-rules.md` for both skills, copied from the product table and
      the steering file. [Req 2.1]
- [x] **3. Worked example.** `example-control.yaml`, `example-fixtures/`, `example-casebook.yaml` in `add-control`. The
      example runs through `nightaudit` and through the casebook runner. [Req 2.2]
- [x] **4. Templates.** `contract_tests.py`, `casebook_runner.py`, `connector_template.py` in `add-control/assets/`.
      [Req 2.2, 2.4]
- [x] **5. `add-control` skill.** `SKILL.md` and `casebook-format.md`. [Req 2.2, 2.4]
- [x] **6. `read-a-night` skill.** `SKILL.md` and `reading-a-finding.md`. [Req 2.3]
- [x] **7. README for a stranger.** `power/night-audit/README.md`. [Req 2.4]
- [x] **8. Checks.** `skeleton/tests/test_power.py` per design §4. [Req 2.1-2.4]
- [ ] **9. Empty-project trial.** Build a project with no Night Audit files, install `nightaudit` from the local path,
      copy the templates and the example, and run the contract tests, the casebook and `nightaudit run`. [Req 2.4]
      NOT DONE: `uv init --bare` and `uv add` hung behind the shared `power` lock. The copied templates were run in a
      temp project inside this repository's environment (`test_the_copied_templates_pass_on_the_example_in_a_project_
      with_no_other_night_audit_files`), which does not exercise `uv add` or the git URL.
- [ ] **10. Lint, types, tests, casebook.** `uv run ruff check .`, `uv run mypy skeleton`, `uv run pytest -q`,
      `uv run python scripts/score_casebook.py --set dev`. [tech]
