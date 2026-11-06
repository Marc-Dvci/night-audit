# Tasks: three-way match skeleton

Ordered implementation checklist. Each task is small (one module or one test file). Requirement
references are in brackets. Do not start implementation until this checklist is approved.

## Setup

- [x] **1. Project setup.** Create `skeleton/pyproject.toml`: package `nightaudit`, `src/` layout, Python
      3.12, deps `pydantic`, `pyyaml`, `fastapi`, `uvicorn`, `boto3` (dev: `pytest`, `hypothesis`,
      `ruff`, `mypy`). Configure `ruff` and `mypy --strict` for `skeleton/`. Add `pytest` markers:
      `property` in `pyproject.toml` (`[tool.pytest.ini_options] markers = ["property"]`). Create
      `skeleton/src/nightaudit/__init__.py` and `skeleton/tests/conftest.py`. Run `uv sync`.
      [tech]

- [x] **2. Casebook scorer scaffold.** Write `scripts/score_casebook.py` that loads
      `casebook/dev/cases.yaml`, and for each case builds a `ControlConfig` (cloud default, people
      default, per-case overrides), builds `LedgerSnapshot` objects from inline data (handling `null`
      as `missing=True`), runs `match()`, and compares results against `expect`. Accept `--set dev`
      and `--quiet` flags. This defines the acceptance contract and will fail until the matcher exists.
      [Req 3.6]

## Core data and configuration

- [x] **3. Data model.** Implement `skeleton/src/nightaudit/models.py`: `LedgerName` enum, `Record`,
      `LedgerSnapshot`, `UnkeyedRow`, `Finding`, `RegionSummary`, `RunResult`, and constants
      (`REGION_CODES`, `DEFAULT_REGION_NAMES`, `DEFAULT_REGION_MEANINGS`, `FINDING_REGIONS`,
      `INFORMATIONAL_REGIONS`). All money is `Decimal`. Records are frozen. [Req 2.4, 3.1, 3.4, 3.5]

- [x] **4. Normalisers.** Implement `skeleton/src/nightaudit/normalisers.py`: `NormaliserRegistry` with
      `register`, `get`, `names`. Built-in normalisers: `strip`, `lower`, `collapse_whitespace`,
      `email_canonical` (reads `alias_domains` from ctx), `arn_resource_id`. Chain application
      `normalise(raw_key, chain, ctx)`. `UnknownNormaliserError` for unregistered names. [Req 2.1–2.4]

- [x] **5. Control file.** Implement `skeleton/src/nightaudit/control.py`: `ScopeFilter`,
      `RegionOverride`, `ControlConfig`, `ConnectorConfig`, `LedgerConfig`, `ControlFile`. Validate
      exactly three ledgers named intended/observed/billed (Req 1.1). Validate normaliser names are
      registered (Req 1.2). Compute canonical hash as `SHA-256(canonical_json)` (Req 1.3). Resolve
      region names/meanings from overrides or defaults (Req 1.4). `ControlFile.to_config()` →
      `ControlConfig`. [Req 1.1–1.4]

- [x] **6. Scope filtering.** Implement `skeleton/src/nightaudit/scope.py`:
      `apply_scope(snapshots, scope)` drops records whose `attrs.get(scope.attr) != scope.equals`,
      returns filtered snapshots and dropped counts per ledger. [Req 4.2]

- [x] **7. Grace window.** Implement `skeleton/src/nightaudit/grace.py`:
      `find_pending(keys_in_observed, billed_keys, observed_records_by_key, grace_hours, run_time)`
      returns the set of keys to suppress. A key is pending when its most recent observed timestamp is
      within `grace_hours` of `run_time` and the key is absent from billed. [Req 4.1]

- [x] **8. Matcher.** Implement `skeleton/src/nightaudit/matcher.py`:
      `match(snapshots, control, run_time) → RunResult`. Steps per design §6: missing-ledger check,
      normalise keys, scope filter, group by key, grace window, compute regions, produce findings
      (with duplicate counts), compute region summaries, verify amount conservation. [Req 3.1–3.5,
      4.1, 4.2, 9.4]

- [x] **9. Scorer completion.** Complete `scripts/score_casebook.py` with case parsing, default control
      building (cloud + people), per-case override merging, snapshot building from inline data, and
      result comparison against all `expect` fields (regions, findings, informational, billed_total,
      billed_by_region, billed_unkeyed, pending, unkeyed, duplicates, dropped, complete,
      missing_ledgers). Run `uv run python scripts/score_casebook.py --set dev` and confirm all 18 dev
      cases pass. [Req 3.6]

## State, evidence, explanations, connectors

- [x] **10. Night-over-night state.** Implement `skeleton/src/nightaudit/state.py`: `StateStore` with
      `load(control_hash)` and `save(control_hash, state)`. `compare_findings(current, previous)` →
      statuses (new/persisting/resolved), first-seen carry-over, nights_persisted computation (date
      difference in UTC). State persisted as JSON in `runs/<control_hash>/state.json`, mapping
      `"{key}:{region_code}"` to `{"first_seen": ..., "region_code": ...}`. [Req 5.1–5.3]

- [x] **11. Evidence pack.** Implement `skeleton/src/nightaudit/evidence.py`:
      `write_evidence_pack(run_result, pack_dir)` writes `evidence.jsonl` (hash chain) and
      `manifest.json`. `verify_evidence_pack(pack_dir)` recomputes the chain and reports the first
      failing row or confirms. Canonical JSON for hashing (sorted keys, compact separators, Decimal
      as string, datetime as ISO-8601 UTC). Row order: intended → observed → billed, sorted by
      row_id. Manifest includes control_hash, per-ledger hash + count, chain_seed, final_chain_hash.
      [Req 6.1–6.3]

- [x] **12. Explanation guard.** Implement `skeleton/src/nightaudit/explain.py`:
      `explain_finding(finding, model_config)` calls Bedrock Converse with a 10-second timeout. Prompt
      contains only region, meaning, and evidence fields (quoted, truncated to 200 chars). Number
      guard: extract numbers from the response, check against evidence numbers (amounts, row_id
      integers, numeric attrs substrings, billed_amount, duplicate counts, nights_persisted), discard
      if mismatch (use template, record rejection). Template fallback on timeout/unavailable.
      [Req 7.1–7.4, audit rules 1–2, 4]

- [x] **13. Connectors.** Implement `skeleton/src/nightaudit/connectors.py`: `Connector` ABC with
      `ledger`, `read_only`, `fetch()`. `CSVConnector` (reads CSV, maps `key_field` column to
      `raw_key`, parses `amount` as `Decimal`, `ts`/`timestamp` as `datetime`). `JSONLConnector` (reads
      JSONL, maps `key_field`). Both `read_only = True`. [Req 9.1, 9.3]

- [x] **14. Runner.** Implement `skeleton/src/nightaudit/runner.py`:
      `run_control(control_path, runs_dir)` loads control, fetches ledgers via connectors, enforces
      read-only (refuse non-read-only, mark ledger missing), applies scope + normalisation + grace +
      matching, updates state, writes evidence pack, generates explanations, saves RunResult.
      [Req 1.3, 4.1–4.2, 5.1–5.2, 6.1, 7, 9.2, 9.4]

## API and UI

- [x] **15. API.** Implement `skeleton/src/nightaudit/api.py`: FastAPI app with `GET /api/runs`,
      `GET /api/runs/{id}`, `GET /api/runs/{id}/findings?region=`, `GET /api/runs/{id}/evidence.zip`.
      Mount static front-end from `web/dist/`. [Req 8.1]

- [x] **16. CLI.** Implement `skeleton/src/nightaudit/cli.py`: `nightaudit run <control>`,
      `nightaudit serve --app <name>`, `nightaudit verify <pack>`, `nightaudit score --set dev`. Uses
      argparse. [all]

- [ ] **17. UI kit.** Create `skeleton/web/` with Vite + TypeScript (no UI framework): `index.html`,
      `src/main.ts` (fetches `/api/runs/{id}`), `src/venn.ts` (three-circle SVG Venn with key counts,
      click-to-filter), `src/findings.ts` (green-bar rows with monster name in words, key, nights,
      amount, explanation), `styles.css` (palette from ui-identity: ink, ink-2, phosphor, bone,
      amber, moon, blood), self-hosted IBM Plex Mono + IBM Plex Sans fonts. Keyboard-accessible with
      visible phosphor focus rings, `prefers-reduced-motion` respected. [Req 8.2–8.4, ui-identity]

## Property-based tests

Each test uses `hypothesis` (100 examples, `derandomize` in CI), is marked `@pytest.mark.property`, and
its name starts with `test_property_`.

- [x] **18. Partition.** `tests/test_property_partition.py` — generate three random ledger snapshots,
      assert every key lands in exactly one region and the region matches the set of containing ledgers
      joined in I-O-B order. [Req 3.1]

- [x] **19. Order independence.** `tests/test_property_order_independence.py` — generate snapshots,
      shuffle records within each ledger, assert key→region assignments and per-region billed amounts
      are unchanged. [Req 3.2]

- [x] **20. Healthy control yields zero findings.** `tests/test_property_healthy_zero.py` — generate
      random keys, place the same set in all three ledgers, assert zero findings. [Req 3.3]

- [x] **21. Normaliser idempotence.** `tests/test_property_normaliser_idempotence.py` — for each
      built-in normaliser and random strings, assert `n(n(s, ctx), ctx) == n(s, ctx)`. [Req 2.3]

- [x] **22. Amount conservation.** `tests/test_property_amount_conservation.py` — generate random
      billed records (including unkeyed and duplicate-key), assert sum of region billed amounts +
      billed_unkeyed == billed_total. [Req 3.5]

- [x] **23. Grace window.** `tests/test_property_grace_window.py` — generate an observed record
      younger than grace_hours with no billed entry, assert the key is in `pending_keys` and produces
      no finding; generate one older than grace_hours, assert it gets its normal region. [Req 4.1]

- [x] **24. Evidence tamper detection.** `tests/test_property_evidence_tamper.py` — write a pack,
      flip a random byte in a random row of `evidence.jsonl`, assert `verify_evidence_pack` fails.
      [Req 6.3]

- [x] **25. Explanation guard.** `tests/test_property_explanation_guard.py` — generate a finding with
      known evidence numbers, supply a synthetic model response containing a number not in the
      evidence, assert the template is returned and the rejection is recorded. [Req 7.2]

- [x] **26. Injection does not change regions.** `tests/test_property_injection.py` — generate a
      record with an instruction-like attrs value, assert the region is the same as with an equal-length
      benign string. [Req 7.4]

- [x] **27. Repeat-run determinism.** `tests/test_property_repeat_run_determinism.py` — run
      `match()` twice with identical inputs at the same `run_time`, assert identical findings (keys,
      regions, amounts) and identical evidence chain hash. [Req 5.3]

## Verification

- [x] **28. Lint and types.** `uv run ruff check . && uv run mypy skeleton` passes clean. [tech]

- [x] **29. All tests pass.** `uv run pytest` passes (unit, integration, property).
      `uv run python scripts/score_casebook.py --set dev` reports all 18 dev cases passing. [all]
