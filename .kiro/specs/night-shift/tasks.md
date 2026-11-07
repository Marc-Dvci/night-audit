# Tasks: the night shift

Requirements 2 (the Kiro power) and 3 (the partition proof). Requirement 1 gets tasks when it is taken up.

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
- [x] **10. Lint, types, tests, casebook.** `uv run ruff check .`, `uv run mypy skeleton`, `uv run pytest -q`,
      `uv run python scripts/score_casebook.py --set dev`. [tech]

## Requirement 3: the partition proof

Lean is not installed on the machine these were written on; CI's `lean` job is the only compiler. A task is ticked
when that job passes it. Tasks 11 to 16 were ticked on 7 Nov 2026 from CI run 42351134731 on commit `747eda1`: the
`lean` job and each of its steps (source grep, build, `sorry` in the build log, axiom audit, executable, differential
test) passed.

- [x] **11. Lake project.** `lean/` pinned to `leanprover/lean4:v4.28.0`, core library only; `lakefile.toml` with the
      `NightAudit` library and the `regions` executable. [Req 3.1]
- [x] **12. Model.** `lean/NightAudit/Region.lean`: `Region`, `regionOfFlags`, `regionOf`, with the `matcher.py` lines
      it models. [Req 3.1]
- [x] **13. Theorems.** `lean/NightAudit/Partition.lean`: `every_key_has_a_region`, `no_key_outside_has_a_region`,
      `region_is_exact`, `order_independent`, `duplicates_do_not_matter`, `partition_counts`; `Audit.lean` prints the
      axioms of each. [Req 3.1]
- [x] **14. Executable.** `lean/Main.lean` reads JSON Lines with `Lean.Json` and prints a region code or `none`.
      [Req 3.2]
- [x] **15. Differential test.** `skeleton/tests/test_lean_differential.py`, marker `lean`, 500 derandomised examples
      with hostile keys; skips without `lake`, fails without it in CI. [Req 3.2]
- [x] **16. CI.** `lean` job: forbidden-word grep, `leanprover/lean-action` build, `sorry` in the build log, axiom
      audit against `propext`, `Classical.choice`, `Quot.sound`, the executable, the differential test. [Req 3.3]

## The Crew app on Kiro Crew 0.13.0

Checked on Windows 11 on 7 Nov 2026; commands and output in `crew/README.md`.

- [x] **17. The audit as a script cron.** `crew/night-shift/crons/night_jobs.py:nightly` runs
      `uv run --directory <checkout> python scripts/nightly.py` as an argument list; the checkout comes from the job
      message as JSON. Tests: `test_the_audit_job_runs_nightly_py_through_uv_as_an_argument_list_and_reports_its_output`,
      the missing-checkout, non-zero-exit and timeout tests, and
      `test_regression_a_command_cron_is_rejected_on_windows_so_the_audit_is_a_script_cron`.
- [x] **18. The investigator's MCP servers.** Declared in the agent's own `mcpServers`, pinned
      (`awslabs.aws-api-mcp-server@1.6.0` with `READ_OPERATIONS_ONLY=true`, `awslabs.cloudtrail-mcp-server@0.1.1` with
      `lake_query` disabled), profile inherited from `AWS_PROFILE`. Tests:
      `test_the_investigator_servers_are_pinned_and_read_only`,
      `test_regression_the_investigator_tool_refs_name_servers_the_agent_declares`,
      `test_regression_the_agent_file_names_no_placeholder_crew_cannot_render`.
- [x] **19. Checked notes under Crew.** The 02:30 job is `night_jobs.py:notes`, which runs `scripts/night_shift.py` on
      the newest run; the agent stays registered with its skill for Crew chats. Test:
      `test_the_notes_job_runs_night_shift_py_with_its_limits_and_the_gateway_profile`.
- [x] **20. Manifest rules from the source.** Script path inside the bundle, a `.py` file, `file:function` naming a
      defined function, `timeout_secs` covering `timeout` plus 5 s, `command` and `script` exclusive, every `@server`
      ref declared. Tests: `test_the_validator_refuses_each_documented_mistake`,
      `test_the_validator_refuses_an_agent_crew_would_not_mount`.
- [x] **21. One real run in Crew.** Both jobs triggered from Crew: 4 runs written and verified, 5 accepted notes that
      verify on run `1e9e38e57a33f5c4`; both jobs paused afterwards. The incomplete run first failed `nightaudit verify`;
      the verifier was fixed (`test_regression_an_incomplete_run_whose_billed_ledger_was_read_verifies_against_its_page`).
- [x] **22. Both investigators read only.** The checkout's agent, which `scripts/night_shift.py` launches, lists only
      `read`, `@aws-api` and `@aws-cloudtrail` and denies `aws-cloudtrail/lake_query`; `.kiro/settings/mcp.json`
      disables `lake_query` and the billing server's `storage-lens`, `sp-purchase-analyzer` and `sp-recommendation`.
      `skeleton/tests/test_investigator_read_only.py`, 15 tests, reads each agent with the settings it loads; it
      failed on `lake_query`, then on the three billing tools, before the fixes. [audit rule 3]
- [x] **23. No local paths.** `test_no_tracked_text_file_names_a_drive_path_or_a_home_folder` scans every tracked text
      file. [audit rule 9]
- [x] **24. The Crew run with the final code.** Bundle reinstalled (ids `0af6390d`, `9d342b56`). The audit job:
      `last_status: ok`, 4 runs, each `nightaudit verify` OK (`847b2b2514c14574` incomplete, `ebd45fd5644e4159`,
      `4c3e32bf3ef8c9ab`, `6ad680fc05a50128`). The notes job with the read-only investigator: `last_status: ok`,
      `run 6ad680fc05a50128: 0 accepted, 0 rejected, 0 unavailable, 0 skipped`, `verify-notes`: `OK  no investigator's
      notes recorded` (its five `OB` and `O` findings persist from the night before). Both paused; `crew/README.md`.
- [ ] **25. A note from the read-only investigator inside Crew.** Needs a night with a new `OB` or `O` finding; the
      13:07 notes run had none, so kiro-cli was not started.
