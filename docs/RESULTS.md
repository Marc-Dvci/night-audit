# Results

Every figure here comes from a command in this repository. Synthetic data is labelled as synthetic. Figures were
measured on 7 Nov 2026 at commit `a58b88b` plus the working changes that follow it.

## Tests

| Figure | Value | Command |
|---|---|---|
| All tests | 963 collected: 960 passed, 3 skipped | `uv run pytest -q` |
| Skipped | 3, all `-m lean` differential tests, which need the Lean toolchain (`lake`); the `lean` CI job runs them with `NIGHTAUDIT_REQUIRE_LEAN=1` | `uv run pytest -q -ra` |
| Property-based, integration, browser | 41, 250 and 46 tests (a test can carry more than one marker) | `uv run pytest -m property --collect-only -q`, `-m integration`, `-m e2e` |
| TypeScript | 138 tests in 4 files | `cd skeleton/web && npx vitest run --sequence.shuffle` |
| Decision core coverage | 96.8 % of lines and branches over `matcher`, `normalisers`, `grace`, `scope`, `state`, `evidence`, `explain`, `control`, `report` (floor 90 %) | `uv run pytest -q -m "not e2e and not live" --cov` |
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
The evidence of that night verifies (`uv run nightaudit verify <run>/evidence`: 224 rows, 8 findings).

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

`uv run python scripts/ui_check.py <url>` drives the demo UI in headless Chromium through eight states (overview and each
region filter, with a finding opened) and runs axe-core with the WCAG 2.0, 2.1 and 2.2 A and AA rules: 0 violations in all
eight on 7 Nov 2026, on the local build of this commit. The 46 browser tests (`uv run pytest -m e2e`) run the same axe
check on the screens of the apps, including a 390 px phone width.

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
| Audit | `kirocrew cron trigger e7757f1f` | Crew: `last_status: ok`, 4 runs. `nightaudit verify` OK on `c518e7f39e95c08e`, `910948837feacfbc`, `1e9e38e57a33f5c4`; on `41178d37bd0da182` (incomplete, observed ledger missing) after the verifier fix for incomplete runs |
| Notes | `kirocrew cron trigger 771fc3b9` | Crew: `last_status: ok`, `run 1e9e38e57a33f5c4: 5 accepted, 0 rejected, 0 unavailable, 0 skipped`. `nightaudit verify-notes`: `5 notes verify (5 accepted)` |
| Afterwards | `kirocrew cron pause e7757f1f`, `kirocrew cron pause 771fc3b9` | `Paused job: e7757f1f`, `Paused job: 771fc3b9` |

## Lean

`lean/` holds the partition theorem (`every_key_has_a_region`, `region_is_exact`, `order_independent`,
`partition_counts` and others, 17 theorems in `Partition.lean`) on Lean 4.28 with no Mathlib. CI builds it, fails on
`sorry`, `native_decide`, `admit` or `axiom`, prints what each theorem depends on (`propext` and `Quot.sound`), and runs a
differential test of the Lean model against the Python matcher
(`test_property_the_lean_model_and_the_python_matcher_give_every_key_the_same_region`).

## The third control: Night Audit audits its own build

`uv run python apps/own-build/snapshot.py` records the files git tracks at `HEAD` and the paths the specs promise;
`uv run python scripts/build_demos.py own-build` runs the night. Recorded commit `a58b88b`:

| Region | Files |
|---|---|
| `IOB` Spec'd and built with Kiro | 172 |
| `IO` Spec'd, no Kiro session | 118 |
| `O` Written by hand or generated | 56 |
| `OB` Built with Kiro, no spec names it or a folder holding it | 23 |
| `I` Promised by a spec, never built | 6 |
| `B` Kiro worked on it, no spec, it is gone | 5 |

369 files are tracked, 296 are promised, and Kiro worked on 200 in 17 sessions, for 679.1619 credits allocated across
files. The credits are an allocation chosen for this audit, not a measurement of what one file cost.

Before and after on the same night. The first run read a spec path as written and reported 32 files promised and never
built. 26 of those were the parser's mistakes: relative paths (`tests/test_x.py` for `skeleton/tests/test_x.py`), folders
(`apps/ghosts/`), build output (`skeleton/web/dist/**`, `node_modules/**`) and the files the power's design says it writes
into a user's own project. With the resolution rules in `apps/own-build/src/own_build/paths.py` the same night reports 6:

| Still promised and never built | Why |
|---|---|
| `apps/vampires/approved-changes.yaml` | The file is `apps/vampires/controls/approved-changes.yaml`. Spec text corrected |
| `src/findings.ts` | The file is `skeleton/web/src/render/rows.ts`. Spec text corrected |
| `src/venn.ts` | The file is `skeleton/web/src/render/venn.ts`. Spec text corrected |
| `demo/build.py` | Ends three tracked files, so it names none of them |
| `references/region-table.md` | Ends two tracked files |
| `assets/verify.js` | A path inside build output |

The three corrections were made in the spec text after the recorded commit, so the recorded night still shows them. The
resolution has 13 casebook cases (`apps/own-build/casebook/cases.yaml`, section `resolve`), six for folders and three
properties, run by `uv run pytest apps/own-build -q`.
