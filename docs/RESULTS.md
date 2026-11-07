# Results

Every figure here comes from a command in this repository. Synthetic data is labelled as synthetic. Figures were
measured on 7 Nov 2026 at commit `2035d42` plus the working changes that follow it.

## Tests

| Figure | Value | Command |
|---|---|---|
| All tests | 1046 collected: 1043 passed, 3 skipped | `uv run pytest -q` |
| Skipped | 3, all `-m lean` differential tests, which need the Lean toolchain (`lake`); the `lean` CI job runs them with `NIGHTAUDIT_REQUIRE_LEAN=1` | `uv run pytest -q -ra` |
| Property-based, integration, browser | 41, 252 and 46 tests (a test can carry more than one marker) | `uv run pytest -m property --collect-only -q`, `-m integration`, `-m e2e` |
| TypeScript | 261 tests in 4 files | `cd skeleton/web && npx vitest run --sequence.shuffle` |
| Decision core coverage | 96.85 % of lines and branches over `matcher`, `normalisers`, `grace`, `scope`, `state`, `evidence`, `explain`, `control`, `report` (floor 90 %) | `uv run pytest -q -m "not e2e and not live" --cov` |
| Lint, format, types | ruff, ruff format and `mypy --strict` clean | `uv run ruff check . && uv run ruff format --check . && uv run mypy` |

Tests run in random order (`pytest-randomly`), with a 30 s timeout each, no network and no real clock.

## Casebook (synthetic, labelled by hand before the matcher existed)

| Set | Cases | Passed | When | Command |
|---|---|---|---|---|
| Development | 18 | 18 | every commit (CI) | `uv run python scripts/score_casebook.py --set dev` |
| Held-out (sealed) | 6 | 6 | once, at tag `v0.1.0` (commit `77a2b64`), 4 Nov 2026 | `uv run python scripts/score_heldout.py` |

The held-out cases include a 40-key healthy account in shuffled order (zero findings expected), an instruction
planted in a billed tag, a duplicate phantom written two ways, and a leaver hidden behind an alias domain and a
`+tag`. The agent that wrote the matcher was blocked from reading them by the `seal-heldout-casebook` hook.

## The real lab night

`lab/expected.yaml` lists the four findings planted in the lab account. It was written on 4 Nov 2026 at 12:35 UTC,
after planting and before any audit ran.

| Night | Planted | Found | Phantoms | False Vampires | Vampires' cost |
|---|---|---|---|---|---|
| 7 Nov 2026, 02:00 UTC, live account | 4 | 4 | 0 | 0 | $0.7172 (the instance $0.4191, its volume $0.0455, its network interface $0.2526) |

The audit ran with the read-only profile: `uv run nightaudit run apps/vampires/controls/aws-account.yaml --runs runs/live`.
The evidence of that night verifies (`uv run nightaudit verify <run>/evidence`: 224 rows, 8 findings). Its pack was written
before the chain had a header row, and both verifiers still accept it against its page; the same page edited to say the
night was incomplete with no bill fails in both (checked on 7 Nov with the local pack of run `55e91b128f42ee31`; the
shape is pinned by `test_packs_written_before_completeness_was_recorded_still_verify_against_their_pages`). The headline
prints the Vampires' amount as $0.7172; the table, the page data and the evidence keep $0.7172358001.

The first bill taught three things, found by the read-only investigator through the AWS MCP server and written down as
Requirement 10 of the [vampires spec](../.kiro/specs/vampires-app/requirements.md): a public IPv4 address is billed on the
network interface; a stack's handler operations arrive as billed lines that name a stack; an Elastic IP is keyed by its
allocation id on the bill and the inventory.

## Property-based testing

Ten properties were first written as tests against the design. They found 7 bugs that 38 example tests, 18 of 18
development cases and 6 of 6 held-out cases had missed. Each is a `test_regression_` test, in
`skeleton/tests/test_property_*.py`:

| Bug | Test |
|---|---|
| `arn_resource_id` did not strip the id it extracted | `test_regression_arn_resource_id_strips_the_resource_id_it_extracts` |
| `email_canonical` copied an alias target as written | `test_regression_email_canonical_writes_the_alias_target_in_canonical_form` |
| A naive and an aware timestamp on one key crashed the run | `test_regression_a_naive_and_an_aware_timestamp_on_one_key_are_compared_as_utc` |
| Money was rounded at 28 digits: billed `1E-23` and `1E+5` lost a digit | `test_regression_a_tiny_and_a_large_amount_on_one_key_are_added_without_rounding` |
| The guard ignored minus signs: `-41.20` passed against evidence of `41.20`, so a charge could read as a refund | `test_regression_a_response_that_negates_an_evidence_number_is_rejected` |
| The template wrote `$1E-7` | `test_regression_the_template_writes_an_amount_without_an_exponent` |
| The template cut a date | `test_regression_the_template_cites_a_creation_date_only_when_it_starts_with_an_iso_date` |

Command: `uv run pytest -m property -q`.

## Standards run and independent review

The standards run (random order, coverage floor, CI summary, Docker, CodeQL) found 3 more bugs: a billed amount of
`1,234.50` was dropped while the run said complete; a timestamp of `yesterday` skipped the grace window; one instant
spelled two ways gave two run ids. Tests:
`test_regression_a_billed_amount_that_is_not_a_number_makes_the_ledger_missing`,
`test_regression_an_observed_timestamp_that_is_not_a_date_makes_the_ledger_missing`,
`test_every_spelling_of_one_utc_instant_gives_the_same_run`.

An independent review by an agent on a different model that cannot write files reported four things, all fixed: Cost and
Usage Report rounding below 1e-7, a pack's `run_id` that could change without failing verification
(`test_changing_the_run_id_in_the_manifest_fails_verification`), a fake finding on the page beside a passing verify (the page is
now compared with the chain), and attribute names reaching the prompt unquoted
(`test_a_hostile_attribute_name_is_quoted_and_cannot_forge_a_prompt_line`).

The release review found two more holes in the page check, both fixed in Python and TypeScript with the same verdicts
(`skeleton/web/test/fixtures/parity.json`):

| Hole | Test |
|---|---|
| Completeness came from the page: a complete night's page edited to `complete: false` with a billed total of 0, its findings still shown, verified. The header row and the manifest now record `complete` | `test_regression_a_page_that_says_incomplete_to_hide_the_bill_fails_verification` |
| The headline text was not compared with the chain, so it could print any amount. Each amount in it must now be a headline region's amount, exact or rounded half-even to four significant figures (`0.71725` prints `$0.7172`); every other figure must be exact | `test_regression_a_headline_that_rounds_its_amount_wrongly_fails_verification`, `test_a_page_that_rounds_any_amount_but_the_headline_fails_verification` |

A second independent review on another model, of `28a432b`, reported one tool that could start work in the account,
three holes in the evidence checks and two faults in the documentation. All are fixed in `2035d42`:

| Finding | Fix and test |
|---|---|
| The checkout's investigator, which the notes job launches, could call CloudTrail `lake_query` (`StartQuery`) | `lake_query` disabled in `.kiro/settings/mcp.json` and denied in the agent; `test_investigator_read_only.py` reads each agent with the settings it loads. That test then found three more: the billing server's `storage-lens` (Athena `StartQueryExecution`), `sp-purchase-analyzer` and `sp-recommendation` (both start an analysis). The investigator no longer lists the billing server, and the settings disable the three tools |
| A pack with no completeness field, a complete night holding only an unkeyed bill of $41.20, verified beside a page that said incomplete with every total 0 | Such a pack counts as complete: `test_regression_an_old_pack_cannot_hide_an_unkeyed_bill_behind_a_page_that_says_incomplete` |
| `One Vampire costs 0.7173 dollars.` verified: the headline check read only amounts written with `$` | Every number in the headline is read with the explanation guard's scanner: `test_regression_every_number_in_the_headline_must_be_its_own_count_or_amount` |
| A manifest without the `billed` ledger verified | Exactly three ledgers: `test_regression_a_manifest_that_omits_a_ledger_fails_verification` |
| A local checkout path in `crew/README.md`; a claim that tests pinned the Crew run | `test_no_tracked_text_file_names_a_drive_path_or_a_home_folder`; the claim split into a tested row and a recorded-run row |

## Self-attack

`skeleton/tests/test_self_attack.py`, run on every commit:

| Attack | Result |
|---|---|
| Five hostile payloads (instructions, JSON break-out, HTML, bidi override, 5,000 characters) in every attribute | No region changes |
| The same payloads in the explanation prompt | Quoted, cut to 200 characters |
| A Cyrillic lookalike of a declared instance id | Reported as its own Vampire, never matched to the declared one |
| A billed line and its negative twin with no resource id | Both stay visible as unkeyed evidence |
| A healthy account of 10,000 keys, ids in different case and order, ARNs on the bill | 0 findings |
| `<img src=x onerror=alert(1)>` in a demo resource name, opened in the browser | Shown as text, no dialog (`scripts/ui_check.py`) |

## Accessibility

`uv run python scripts/ui_check.py <url>` drives the UI in headless Chromium through eight states (overview and each
region filter, with a finding opened) and runs axe-core with the WCAG 2.0, 2.1 and 2.2 A and AA rules. Measured on
7 Nov 2026 at 13:13 local time against the deployed Lambda function URL:

| URL | Violations in the eight states | Script-payload check | Keyboard | Result |
|---|---|---|---|---|
| `https://o7hhjtbm3mydyatsvlz7t3teli0fqski.lambda-url.us-east-1.on.aws/?app=vampires-demo` (demo, synthetic) | 0 in each (axe passes 28 to 30 rules per state) | `payload in the data 2 time(s), shown as text in 1 place(s), no dialog` | Enter on the Vampire legend item shows `"VAMPIRE 2"` | `RESULT: PASS` |
| `https://o7hhjtbm3mydyatsvlz7t3teli0fqski.lambda-url.us-east-1.on.aws/` (the live lab night) | 0 in each (28 to 31 rules pass per state) | `not applicable, no payload on this night` | `"VAMPIRE 3"` | `RESULT: PASS` |

The first run on each URL also printed a Playwright traceback before `RESULT: PASS`: one JSON response on the deployed
URL is a redirect, and the script read its body. The script was wrong; it now skips redirects
(`test_regression_a_json_redirect_is_not_read_for_the_payload`), and the figures above are from the runs after the fix.
The line `third Tab lands on:` prints the focused element's class name, and printed nothing on both URLs; it is not
checked. The 46 browser tests (`uv run pytest -m e2e`) run the same axe check on the screens of the apps, including a
390 px phone width.

## Throughput

`uv run python scripts/bench.py 100000`: 298,000 records (100,000 keys across three ledgers, 1% declared-but-gone
and 1% never declared) matched in 1.49 s, 199,855 records a second, on a six-core desktop CPU (7 Nov 2026).

## Ghosts, the second app

Built by an agent with no write permission on `skeleton/`: 8 of 8 planted findings and nothing extra
(`apps/ghosts/planted.yaml`, written before the app; `uv run pytest apps/ghosts -q`). The skeleton is unchanged between
commits `b6f5e46` and `ec92469` (`git diff --stat b6f5e46 ec92469 -- skeleton` prints nothing). The agent then reported
five things the template could not do. They were fixed afterwards in the open (commit `9d73fe7`).

## Hooks

Two hook files were invalid JSON for three days and Kiro skipped them without a message. A test now fails on that
(`test_a_hook_file_kiro_would_skip_silently_fails_here_instead`). Hooks that fired during the build:
`seal-heldout-casebook`, `read-only-aws`, `no-harm-guard`, `casebook-score-on-stop`, `properties-on-save`,
`new-control-scaffold`. The steering held when the agent was told a read was authorised, and the seal blocked a command
that only mentioned the sealed path.

## The power

`power/night-audit` was installed in Kiro, then in an empty project a plain-English request that never named it
activated it. After one round of questions it produced a control, a 12-case casebook and tests, and found all the planted
mismatches: 124 s and 4.60 credits. The files it ships are checked by `skeleton/tests/test_power.py`, which also runs the
example control through `nightaudit` and finds each planted condition.

## Night shift

The investigator agent ran live through the AWS MCP server on the 7 Nov night. Its note passed the explanation guard and
verifies with the evidence: `uv run nightaudit verify-notes <run>/evidence` prints "1 notes verify (1 accepted)".
`crew/night-shift/` is checked by `skeleton/tests/test_crew_app.py` against the rules Kiro Crew 0.13.0's source
enforces; its install steps are in [`crew/README.md`](../crew/README.md).

### The Crew run, 7 Nov 2026

Kiro Crew 0.13.0 from a source checkout on Windows 11; gateway started with `AWS_PROFILE=night-audit` (read-only).

| Step | Command | Result |
|---|---|---|
| Apply the app | `kirocrew app disable`, `uninstall`, `install`, `enable` (`app update` printed "No running gateway answered" on Windows) | `Agents registered: 1`, `Skills registered: 1`, `registered 2 cron job(s) with scheduler`; no new gateway log line |
| Audit | `kirocrew cron trigger e7757f1f` | Crew: `last_status: ok`, 4 runs. `nightaudit verify` OK on `c518e7f39e95c08e`, `910948837feacfbc`, `1e9e38e57a33f5c4`; on `41178d37bd0da182` (incomplete, observed ledger missing) after the verifier fix for incomplete runs, and again after completeness was recorded in the chain (`OK  verified 545 rows, 0 findings`) |
| Notes | `kirocrew cron trigger 771fc3b9` | Crew: `last_status: ok`, `run 1e9e38e57a33f5c4: 5 accepted, 0 rejected, 0 unavailable, 0 skipped`; superseded by the 13:07 run below |
| Afterwards | `kirocrew cron pause e7757f1f`, `kirocrew cron pause 771fc3b9` | `Paused job: e7757f1f`, `Paused job: 771fc3b9` |

`41178d37bd0da182` no longer verifies: it was written before the chain recorded completeness, and such a pack is now
taken as complete (`complete: the page shows false, the evidence records no completeness, so the night is taken as
complete; billed total: the page shows $0.00, the evidence has $6,683.00; ...`). It should be removed.

### The Crew run again, with the final code, 7 Nov 2026

| Step | Command | Result |
|---|---|---|
| Apply the app | `kirocrew app disable night-shift`, `uninstall`, `install <checkout>\crew\night-shift`; trust set back to `["night-shift"]` in `agent.apps_trusted` and `agent.apps_trusted_local`; `enable` | `Agents registered: 1`, `Skills registered: 1`, `registered 2 cron job(s) with scheduler`; new ids `0af6390d` (audit), `9d342b56` (notes) |
| Audit, before the message was set | `kirocrew cron trigger 0af6390d` | Crew: `last_status: error`, `checkout 'REPLACE_WITH_NIGHT_AUDIT_CHECKOUT' is not an absolute path`; nothing run |
| Audit | `kirocrew cron update 0af6390d --message '{"checkout": "<checkout>"}'`, `kirocrew cron trigger 0af6390d` | Crew: `last_status: ok`, 4 runs. `nightaudit verify`: `847b2b2514c14574` (incomplete, observed missing) `OK  verified 545 rows, 0 findings`; `ebd45fd5644e4159` `OK  verified 742 rows, 12 findings`; `4c3e32bf3ef8c9ab` `OK  verified 1119 rows, 211 findings`; `6ad680fc05a50128` `OK  verified 226 rows, 8 findings`; each `header matches the manifest; the page matches the evidence` |
| Notes | `kirocrew cron trigger 9d342b56` at 13:07:02, after `@aws-billing` was removed from the investigator; message already `{"checkout": "<checkout>"}` | Crew: `"trigger": "manual"`, `"duration_ms": 1553`, `"status": "success"`, `last_status: ok`, `run 6ad680fc05a50128: 0 accepted, 0 rejected, 0 unavailable, 0 skipped`. `nightaudit verify-notes runs/6ad680fc05a50128/evidence`: `OK  no investigator's notes recorded`. No finding was asked about: the five `OB` and `O` findings are `persisting` from `1e9e38e57a33f5c4`, and the job opens only `new` ones |
| Afterwards | `kirocrew cron pause 0af6390d`, `kirocrew cron pause 9d342b56`, `kirocrew cron list` | `Paused job: 0af6390d`, `Paused job: 9d342b56`; both listed as `⏸` with the checkout message |

The five notes the page shows for the lab account are still those on `1e9e38e57a33f5c4`, written by the earlier
investigator, which then also listed `@aws-billing` (`verify-notes`: `OK  evidence verifies; 5 notes verify (5
accepted)`). The read-only investigator has not yet written a note inside Crew.

## Lean

`lean/` holds the partition theorem (`every_key_has_a_region`, `region_is_exact`, `order_independent`,
`partition_counts` and others, 17 theorems in `Partition.lean`) on Lean 4.28 with no Mathlib. CI builds it, fails on
`sorry`, `native_decide`, `admit` or `axiom`, prints what each theorem depends on (`propext` and `Quot.sound`), and runs a
differential test of the Lean model against the Python matcher
(`test_property_the_lean_model_and_the_python_matcher_give_every_key_the_same_region`).

## The third control: Night Audit audits its own build

`uv run python apps/own-build/snapshot.py` records the files git tracks at `HEAD` and the paths the specs promise;
`uv run python scripts/build_demos.py own-build` runs the night. Recorded first at commit `a58b88b`, then at `05f013d`
and at `2035d42`, each time after `export_build_ledger.py` refreshed Kiro's export with the later sessions (the Crew
sessions among them). The export at `2035d42` holds 46 sessions, 24 of them with a credit figure, and 403
session-file rows over 234 files.

| Region | `a58b88b` | `05f013d` (before) | `2035d42` (after) | Change |
|---|---|---|---|---|
| `IOB` Spec'd and built with Kiro | 172 | 176 | 180 | +4 |
| `IO` Spec'd, no Kiro session | 118 | 119 | 119 | 0 |
| `O` Written by hand or generated | 56 | 36 | 42 | +6 |
| `OB` Built with Kiro, no spec names it or a folder holding it | 23 | 45 | 49 | +4 |
| `I` Promised by a spec, never built | 6 | 3 | 3 | 0 |
| `B` Kiro worked on it, no spec, it is gone | 5 | 8 | 5 | -3 |
| Tracked / promised / worked on by Kiro | 369 / 296 / 200 | 376 / 298 / 229 | 390 / 302 / 234 | +14 / +4 / +5 |
| Findings, informational among them | | 211, 119 | 218, 119 | +7, 0 |
| Sessions that touched a file / credits allocated to files | 17 / 679.1619 | 21 / 929.1727 | 23 / 1072.7314 | +2 / +143.5587 |

21 files moved from `O` to `OB` between the first two: Kiro sessions in the newer export touched them. Between
`05f013d` and `2035d42`:

| Move | Files |
|---|---|
| new, `IOB` | `skeleton/tests/test_investigator_read_only.py`, `skeleton/tests/test_no_local_paths.py`, `skeleton/tests/test_ui_check.py` |
| new, `O` | `SECURITY.md` and the seven files of `examples/vampires-night/` (generated by `scripts/build_examples.py`) |
| `B` to `IOB` | `skeleton/tests/test_examples.py` |
| `B` to `OB` | `examples/README.md`, `scripts/build_examples.py` |
| `O` to `OB` | `.kiro/specs/ui-kit/requirements.md`, `scripts/ui_check.py` |

The three `B` files had been worked on by Kiro before they were committed. A file the newer export credits more than
before carries more: `.devcontainer/devcontainer.json` held 3.2145 credits, and holds 7.2952 now that its second
session reports 4.0807. The credits are an allocation chosen for this audit, not a measurement of what one file cost.

Before and after on the same night. The first run read a spec path as written and reported 32 files promised and never
built. 26 of those were the parser's mistakes: relative paths (`tests/test_x.py` for `skeleton/tests/test_x.py`), folders
(`apps/ghosts/`), build output (`skeleton/web/dist/**`, `node_modules/**`) and the files the power's design says it writes
into a user's own project. With the resolution rules in `apps/own-build/src/own_build/paths.py` the `a58b88b` night
reports 6, and the `05f013d` night 3:

| Promised and never built at `a58b88b` | Why | At `05f013d` |
|---|---|---|
| `apps/vampires/approved-changes.yaml` | The file is `apps/vampires/controls/approved-changes.yaml` | Spec text corrected, gone |
| `src/findings.ts` | The file is `skeleton/web/src/render/rows.ts` | Spec text corrected, gone |
| `src/venn.ts` | The file is `skeleton/web/src/render/venn.ts` | Spec text corrected, gone |
| `demo/build.py` | Ends three tracked files, so it names none of them | Remains |
| `references/region-table.md` | Ends two tracked files | Remains |
| `assets/verify.js` | A path inside build output | Remains |

The resolution has 13 casebook cases (`apps/own-build/casebook/cases.yaml`, section `resolve`), six for folders and three
properties, run by `uv run pytest apps/own-build -q`.
