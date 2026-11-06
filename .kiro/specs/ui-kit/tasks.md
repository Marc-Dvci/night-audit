# Tasks: the night ledger UI kit

Ordered implementation checklist. Each task is small and ends with its own tests passing. Requirement references are in
brackets; `P11`–`P15` are the properties in `design.md` §9. This spec supersedes task 17 of
`.kiro/specs/three-way-match/tasks.md`.

Open interpretation, flagged for review: Req 1.1 names one headline template per region. The design accepts a
`{one, other}` pair (a plain string is shorthand for both) because the singular-noun boundary needs singular verbs too.
Amounts are shown with a `$` sign for every control; a currency field is not in Req 1 and is not added.

Status: every task but 28 is ticked. Task 28 waits on `uv run ruff check .`, which reports five line-length errors in `scripts/hooks/no_harm_guard.py`, a hook file outside this spec that is left for its owner.

## Setup

- [x] **1. Tooling.** `uv add --dev playwright` at the workspace root and `uv run playwright install chromium`. Add the
      `e2e` marker to `[tool.pytest.ini_options]`. In `skeleton/web`, add `vitest` as a dev dependency, a `test` script,
      `vitest.config.ts` (node environment, `test/**/*.test.ts`), and keep `build` as `tsc --noEmit && vite build`.
      Confirm `npm run build`, `npx vitest run` (no tests yet: passes with `--passWithNoTests` only for this task) and
      `uv run pytest -q` all run. [Req 12, tech]

## Control and run data

- [x] **2. `ui` schema.** In `control.py`: `NounUi`, `LedgerUi`, `ColumnUi` (alias `from`, validated forms),
      `HeadlineUi` (plain string accepted), `UiConfig`; `ControlFile.ui: UiConfig | None`; template slot validation.
      Tests in `test_ui_config.py`: full section loads, bad `from` rejected, unknown slot rejected, template without
      `{count}` rejected, `ui` changes the control hash. [Req 1.1, 1.3]

- [x] **3. Defaults and run copy.** `resolve_ui(control_file)` with the neutral defaults of design §3;
      `RunResult.ui: UiConfig` (default neutral, so old runs load); the runner stores the resolved ui. Tests: a control
      with no `ui` gets every default; renamed regions flow into default headlines; an old `result.json` without `ui`
      loads. [Req 1.2, 1.3]

- [x] **4. Ship the words.** Add the `ui` section to `apps/vampires/controls/aws-account.yaml` and to the three
      `apps/vampires/demo/night-*/control.yaml` files. Test: each file loads and its columns name existing attributes of
      the demo data. [Req 1.4, 8.2]

## Report module

- [x] **5. `money_text`.** In new `report.py`: exact decimal display (design §4). Unit tests for `0`, `-0`, `0E-12`,
      `1E+5`, `0.5`, `41.200`, `0.000000001`, `-3.10`, `1234567.891`. Property test
      `test_property_money_text.py`. [Req 3.1–3.3, P13]

- [x] **6. Ledger key counts.** `ledger_key_counts(run)`. Unit tests: duplicates and unkeyed rows do not count, missing
      ledger is `None`. Property test `test_property_ledger_keys.py`. [Req 2.4, 2.5, P12]

- [x] **7. Headline.** `headline(run)` with the missing-ledger, calm and per-region forms. Unit tests in `test_report.py`:
      zero findings, one finding (singular noun and verb), a run with a missing ledger, many decimals, negative unkeyed
      total not in the headline, region order, empty regions omitted, `IO` never mentioned. Property test
      `test_property_headline_numbers.py` (headline part). [Req 2.2, 2.3, P11]

- [x] **8. Run view.** `run_view(run)` and `run_numbers(run)`; conservation assert; money lines with the credit note for a
      negative unkeyed total. Unit tests for the lines and the note. [Req 3.1–3.3]

- [x] **9. Morning report.** `report_html(run, recorded)`: self-contained, A4 print rules, green bars, new first, nights,
      laid to rest, chain hash, every value escaped. Unit tests: no `http`, `src=` or `<script` in output; planted
      payload appears escaped. Extend P11 to the report headline and table; property test
      `test_property_report_escaping.py`. [Req 7.1, 7.3, 7.4, P11, P14]

## Evidence and API

- [x] **10. Structured verify result.** `evidence.py`: public `canonical_json`; `VerifyResult.failed_row`, `rows`,
      `findings`, `final_hash`. Existing tests unchanged; new tests assert `failed_row` for a changed byte and for a
      broken link. [Req 6.2, 6.4]

- [x] **11. API routes and CSP.** `api.py`: `view` in the run JSON, `new_findings` in `run_summary`, routes
      `evidence.jsonl`, `manifest.json`, `report.html`; CSP, `nosniff` and `no-referrer` middleware; the report's own
      hashed style policy. Tests in `test_api_ui.py`: routes, 404s, headers on JSON, static and report responses.
      [Req 4.1, 6.5, 7.2, 11.2]

## Front end

- [x] **12. Split the kit.** Move `main.ts` into `api.ts`, `state.ts`, `format.ts`, `render/*.ts` with no change in
      behaviour other than reading `view` and `ui`; `types.ts` gains `UiConfig`, `RunView`, `AppEntry`. `moneyText` is
      string-only. `npm run build` clean. [Req 1, tech]

- [x] **13. Canonical JSON and verify in TypeScript.** `canonical.ts`, `verify.ts` (WebCrypto, `onRow` callback),
      stable chunk `assets/verify.js`. `scripts/write_parity_fixture.py` writes `test/fixtures/parity.json` (canonical
      cases, money cases, a hostile pack and tampered variants with Python verdicts); `test_parity_fixture.py` checks it
      is current. Vitest suites `canonical.test.ts`, `verify.test.ts`, `format.test.ts`. [Req 6.1, 6.4, P13]

- [x] **14. Delivery shell.** `index.html`: title, description, OG and Twitter tags, `favicon.svg`, CSP meta (added to
      the built page only, after `<meta charset>`), skip link. Fonts self-hosted from `@fontsource` through
      `src/fonts.css` (latin subset, `font-display: block`); `main.ts` draws the page only after `document.fonts.load`
      of the four faces. No inline styles anywhere. Test: `test_web_shell.py`. `og.png` itself is task 23.
      [Req 9.1, 9.2, 11.2]

- [x] **15. Style rewrite.** `style.css` for the printout direction: bands and hairlines only, no borders around
      blocks, no radius, no gradient except the scan line; headline the largest text after the masthead; phosphor focus
      ring; reduced motion; 360 px single column; tables scroll in their own container; summary lines wrap only at
      spaces. [Req 2.1, 3.4, 10.2–10.4, ui-identity]

- [x] **16. Masthead and lede.** Brand, app switch from `apps.json`, recorded-run notice in words, night picker, morning
      report link; tagline, headline, money lines. [Req 2.1, 3.1, 3.2, 7.2, 8.1, 8.3]

- [x] **17. Ledgers and Venn.** Ledger label, source sentence and distinct-key count beside the Venn; calm state without
      zero labels; legend as the keyboard path; filter note with name and meaning. [Req 2.3–2.6]

- [x] **18. Rows and laid to rest.** Rows from `ui.columns`; status with first-seen date and nights; amber for new, blood
      only above 3 nights; evidence table in a scroll container; "Laid to rest" with region, key, first seen, nights.
      [Req 4.2, 4.3, 8.2, 10.3]

- [x] **19. Nights strip.** Up to 30 marks for the control, height classes, text counts, selection loads the night.
      [Req 4.1]

- [x] **20. Deep links.** `state.ts` reads and writes `app`, `run`, `region`, `open`; ignores unknown values; opens and
      scrolls to the named finding. [Req 5.1, 5.2]

- [x] **21. Verify screen.** Line-printer output on animation frames, one final line under reduced motion, live region
      for the verdict; change one byte and restore. [Req 6.1–6.3, 10.4]

## Demo and capture

- [x] **22. Demo build.** `apps/vampires/demo/build.py` also writes `demo/<id>/evidence.jsonl`, `manifest.json`,
      `report.html`, run JSON with `view`, `runs.json` with `new_findings`, and `public/apps.json`. Run
      `uv run python apps/vampires/demo/build.py`. Test: every run listed in `runs.json` has its four files and its
      evidence verifies. [Req 6.5, 7.2, 8.1]

- [x] **23. Capture.** `scripts/capture_card.py` writes `public/og.png` (1200×630) and, with `--review`, screenshots at
      1440 and 390 px into `build/screens/`. Read the screenshots and fix what they show. [Req 9.1]

## Browser tests

- [x] **24. E2E harness.** `skeleton/tests/e2e/conftest.py`: dist check, demo runs plus a clean night and a hostile night
      in a temp folder, uvicorn on a free port in a thread, headless Chromium per session, `assert_axe_clean` with the
      WCAG 2.0/2.1/2.2 A and AA tags. [Req 10.1, 12.1, 12.2]

- [x] **25. Screen states.** `test_screens.py`: overview, each region filter, opened finding, deep link, nights strip,
      verify (and reduced motion), change one byte, report, clean night, phone, hostile name, keyboard and focus ring;
      axe on each. [Req 2, 4, 5, 6.2, 6.3, 7.2, 8, 10.1, 10.2, 11.1, 12.1]

- [x] **26. Layout.** `test_layout.py`: no horizontal scroll at 360 and 390 px; no word in a summary line split across
      lines at 360–1440 px; layout-shift sum 0; report prints on one A4 page with 12 findings; no request leaves the
      origin. [Req 3.4, 7.1, 9.2, 10.3]

- [x] **27. Verify parity property.** `test_property_verify_parity.py`: hostile packs, untouched or with one changed
      character, compared between `assets/verify.js` in Chromium and `verify_evidence_pack`. [Req 6.4, P15]

## Verification

- [ ] **28. All checks.** `uv run ruff check .`, `uv run mypy skeleton apps/vampires/src`, `uv run pytest -q`,
      `uv run python scripts/score_casebook.py --set dev`, `npm run build` and `npx vitest run` in `skeleton/web`. Tick
      task 17 of `.kiro/specs/three-way-match/tasks.md`. [all]
