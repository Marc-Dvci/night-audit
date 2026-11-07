# Night Audit

[![CI](https://github.com/Marc-Dvci/night-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/Marc-Dvci/night-audit/actions/workflows/ci.yml)
[![CodeQL](https://github.com/Marc-Dvci/night-audit/actions/workflows/codeql.yml/badge.svg)](https://github.com/Marc-Dvci/night-audit/actions/workflows/codeql.yml)
[![Licence: Apache 2.0](https://img.shields.io/badge/licence-Apache%202.0-blue.svg)](LICENSE)
![Tests: 1046](https://img.shields.io/badge/tests-1046-brightgreen)
![Decision core coverage: 96.85%](https://img.shields.io/badge/decision%20core%20coverage-96.85%25-brightgreen)
![Casebook: 18 of 18](https://img.shields.io/badge/casebook-18%20of%2018-brightgreen)

![Night Audit on the demo account, night of 6 Nov 2026: the headline, the bill, the three-circle Venn diagram of declared, running and billed resources, and the list of regions](docs/figures/ui-night-3.png)

**Night Audit checks every night that what you approved, what is running and what you pay for are the same three
lists, and names whatever appears in only one or two of them.**

I test access and change-management controls in IT audits at a bank's technology practice. The control I trust most
is the oldest one in accounts payable: an invoice is paid only when the purchase order, the goods receipt and the
invoice agree. Night Audit runs that three-way match on a cloud account.

| | |
|---|---|
| Live app, no login | [The real lab account, audited every night](https://o7hhjtbm3mydyatsvlz7t3teli0fqski.lambda-url.us-east-1.on.aws/) · [Vampires demo account](https://o7hhjtbm3mydyatsvlz7t3teli0fqski.lambda-url.us-east-1.on.aws/?app=vampires-demo) · [Ghosts demo company](https://o7hhjtbm3mydyatsvlz7t3teli0fqski.lambda-url.us-east-1.on.aws/?app=ghosts-demo) · [This repository's own build](https://o7hhjtbm3mydyatsvlz7t3teli0fqski.lambda-url.us-east-1.on.aws/?app=own-build-demo) |
| Category | Kiroween 2026, Skeleton Crew |
| Built with | Kiro CLI (specs, custom agents, hooks, steering, MCP, a power, a Crew app), Python 3.12, FastAPI, TypeScript, Lean 4, AWS Lambda, EventBridge Scheduler, S3, Cost and Usage Report 2.0 |
| Headline | Real lab night: 4 planted findings, 4 found, 0 Phantoms, 0 false Vampires. Casebooks: development 18 of 18, held-out 6 of 6 |

Menu: [For judges](#for-judges) · [See it work](#see-it-work) · [Quickstart](#quickstart-no-credentials) ·
[How it works](#how-it-works) · [How Kiro is used](#how-kiro-is-used) · [Claims](#claims-and-the-tests-that-pin-them) ·
[Evidence](#evidence) · [Two apps and a third control](#two-apps-and-a-third-control)

## For judges

Code links point at lines in the release tag `v1.0.0`.

| Criterion | Where to look |
|---|---|
| Potential Impact | [The problem](#the-problem). The real lab night: [`lab/expected.yaml`](lab/expected.yaml) was written before any audit; the findings are in [Evidence](#evidence). Region rules a reader learns once: [`_region_code`](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/skeleton/src/nightaudit/matcher.py#L35-L44) |
| Technological Implementation | [How Kiro is used](#how-kiro-is-used) and [`.kiro/`](.kiro). The matcher: [`_match`](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/skeleton/src/nightaudit/matcher.py#L110-L315). The number guard: [`numbers_are_safe`](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/skeleton/src/nightaudit/explain.py#L162-L167) and [`explain_finding`](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/skeleton/src/nightaudit/explain.py#L339-L375). The evidence chain: [`write_evidence_pack`](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/skeleton/src/nightaudit/evidence.py#L148-L220) and [`verify_evidence_pack`](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/skeleton/src/nightaudit/evidence.py#L516-L633). The partition theorem: [`Partition.lean`](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/lean/NightAudit/Partition.lean#L166-L173) |
| Design | [See it work](#see-it-work). The identity: [`ui-identity.md`](.kiro/steering/ui-identity.md). The Venn diagram: [`vennSvg`](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/skeleton/web/src/render/venn.ts#L68-L119). Accessibility: [Evidence](#evidence) |
| Innovation / Idea | [How it works](#how-it-works). One skeleton, three controls: [vampires](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/apps/vampires/controls/aws-account.yaml#L1-L95), [ghosts](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/apps/ghosts/controls/staff-access.yaml#L1-L72) and [this repository's own build](apps/own-build/README.md) |
| Presentation | The three GIFs and the figures in [See it work](#see-it-work), the [architecture](#how-it-works), the [claims table](#claims-and-the-tests-that-pin-them) |

## See it work

**Click the Vampire.** The Venn diagram is the navigation: a click on a region filters the rows, and a row opens to the
ledger lines it came from.

![Clicking the Vampire region of the Venn diagram filters the rows to the two Vampires; the first opens to its billed line and its inventory line](docs/figures/venn-click.gif)

**Verify this night, then change one byte.** The page re-computes the evidence chain in the browser. One changed byte
fails it.

![The evidence footer: Verify this night shows every row OK; Change one byte makes the verdict fail](docs/figures/verify-then-change-one-byte.gif)

**Ghosts, with a decision.** The second app, on staff access. A reviewer's decision shows next to the finding it
settles, and only when its own chain verifies.

![The Ghosts demo company: three Ghosts with active accounts and paid seats, and the first opened with its decision, revoke, by the reviewer](docs/figures/ghosts-decision.gif)

An opened Vampire. The tag value that reads like an instruction is shown as data and changes no region:

![The Vampire row opened: the billed line, the inventory line and an instruction planted in the Name tag, shown as data](docs/figures/ui-vampire-evidence.png)

## The problem

In 1986 Cliff Stoll, then a systems administrator at Lawrence Berkeley Laboratory, found a 75-cent difference between two
accounting systems. It led to an intruder selling what he found to the KGB. Two ledgers that should agree, and did not.

Cloud accounts still produce ledgers that nobody compares:

- what the team declared (infrastructure as code, approved changes),
- what exists (the inventory),
- what is billed (the Cost and Usage Report).

AWS's Cloud Financial Management blog ([27 Apr 2026](https://aws.amazon.com/blogs/aws-cloud-financial-management/identifying-security-risks-using-aws-cost-and-usage-report-data/)) publishes Athena queries over the Cost and Usage Report and tells readers to "cross-reference findings with CloudTrail logs to identify who created these resources". Night Audit runs that cross-reference every night, adds the third ledger, and keeps the evidence.
Stolen keys used to run models or miners show up on the bill before anyone looks; an access key nobody declared costs
nothing, which is why nobody looks for it.

It is for two people. A startup CTO at 08:30, opening the morning report before anyone has looked at the bill. An IT
manager preparing a quarterly access review that an auditor will test.

## How it works

![Architecture: three read-only ledgers feed the skeleton, where code decides every region; below a dashed line the model only explains a decided finding, and a guard checks every number in its text before it is shown](docs/figures/architecture.png)

Source: [`docs/figures/architecture.html`](docs/figures/architecture.html), rendered by `scripts/render_figure.py`.

Every key lands in exactly one of seven regions. The Halloween names are the taxonomy:

| Present in | Name | Meaning |
|---|---|---|
| observed, billed | **Vampire** | Running and paid for, but nobody declared it |
| observed | **Poltergeist** | Exists, undeclared, costs nothing |
| billed | **Phantom** | On the bill, invisible to the inventory, undeclared |
| intended | **Skeleton** | Declared, but gone |
| intended, billed | **Wraith** | Declared and billed, but not observed |
| intended, observed | Familiar | Declared and present, not billed yet (informational) |
| all three | Living | Matched |

Code decides every region, amount and date. A language model may only explain a decided finding, and any explanation
that cites a number absent from the evidence is replaced by a fixed template. Ledger text (tags, names, descriptions) is
data: it enters a prompt only as a quoted field cut to 200 characters, and it cannot change a region.

The repository is a Skeleton Crew entry: `skeleton/` is the reusable template (package `nightaudit`) and each app under
`apps/` supplies only a control file and connectors.

| Folder | What it is |
|---|---|
| `skeleton/` | Normalisers, matcher, grace window, night-over-night state, evidence chain, explanation guard, API, CLI, web UI kit |
| `apps/vampires/` | AWS account: declared stacks and approvals, live inventory in every enabled region, CUR 2.0 |
| `apps/ghosts/` | Staff access: HR roster, identity exports, SaaS licences ([spec](.kiro/specs/ghosts-app/requirements.md)) |
| `apps/own-build/` | This repository: the specs, the tracked files and Kiro's work ([README](apps/own-build/README.md)) |
| `power/`, `crew/` | The Kiro power `night-audit` and the Crew app `night-shift` |
| `lean/` | The partition theorem and the Lean model checked against the Python matcher |
| `deploy/`, `lab/` | The Lambda stack, and the lab account's declared stack with its planted findings |

## How Kiro is used

The build used Kiro CLI, in headless mode (`kiro-cli chat --no-interactive`), with custom agents.

| Kiro surface | In this repository |
|---|---|
| Specs | Five spec folders in [`.kiro/specs`](.kiro/specs): [`three-way-match`](.kiro/specs/three-way-match) (EARS requirements, a design with 13 correctness properties, 40 tasks), [`ui-kit`](.kiro/specs/ui-kit), [`vampires-app`](.kiro/specs/vampires-app), [`ghosts-app`](.kiro/specs/ghosts-app), [`night-shift`](.kiro/specs/night-shift). Tasks are ticked only after their tests pass |
| Custom agents | [`night-builder`](.kiro/agents/night-builder.json) (cannot read the sealed cases, edit its own hooks or commit), [`night-app-builder`](.kiro/agents/night-app-builder.json) (no write permission on `skeleton/`), [`night-reviewer`](.kiro/agents/night-reviewer.json) (a different model, cannot change a file), [`night-investigator`](.kiro/agents/night-investigator.json) (read-only AWS tools) |
| Hooks | [`seal-heldout-casebook`](.kiro/hooks/seal-heldout.json), [`read-only-aws`](.kiro/hooks/read-only-aws.json), [`no-harm-guard`](.kiro/hooks/no-harm.json), [`casebook-score-on-stop`](.kiro/hooks/score-on-stop.json), [`properties-on-save`](.kiro/hooks/properties-on-save.json), [`new-control-scaffold`](.kiro/hooks/new-control-scaffold.json) |
| Steering | [product](.kiro/steering/product.md), [tech](.kiro/steering/tech.md), [audit rules](.kiro/steering/audit-rules.md), [UI identity](.kiro/steering/ui-identity.md) (loaded only for web files) |
| MCP | [`.kiro/settings/mcp.json`](.kiro/settings/mcp.json) mounts three pinned servers on the read-only `night-audit` profile: `aws-api` (`awslabs.aws-api-mcp-server@1.6.0`, `READ_OPERATIONS_ONLY=true`), `aws-cloudtrail` (`@0.1.1`, `lake_query` disabled) and `aws-billing` (`awslabs.billing-cost-management-mcp-server@0.0.44`, `storage-lens`, `sp-purchase-analyzer` and `sp-recommendation` disabled). The [`night-investigator`](.kiro/agents/night-investigator.json) may call only `aws-api` and `aws-cloudtrail`, and denies `aws-cloudtrail/lake_query`; the builder, app-builder and reviewer agents load no MCP settings. [`test_investigator_read_only.py`](skeleton/tests/test_investigator_read_only.py) fails if either investigator can call a tool that is not a read |
| Property-based testing | 41 property-based tests (marker `property`) for the properties in the design. Seven bugs the example tests, the development casebook and the held-out casebook had missed, each kept as a `test_regression_` test |
| Power | [`power/night-audit`](power/night-audit): the `add-control` and `read-a-night` skills and a pinned read-only MCP server |
| Crew | [`crew/night-shift`](crew/night-shift): a Kiro Crew app with two daily script crons (the audit at 02:00 UTC, checked notes at 02:30), an investigator agent with two pinned read-only MCP servers, and a skill. Installed on Kiro Crew 0.13.0 on Windows 11 and triggered from Crew against the lab account on 7 Nov 2026 (the audit job and the notes job); what was checked and what was not is in [`crew/README.md`](crew/README.md) |

What Kiro did in this repository, from its own session export (the own-build demo page lists it file by file): 23 sessions
worked on 234 files, 229 of the 390 files tracked at the recorded commit, `2035d42`. The credits reported for those
files add up to 1072.7314 (an allocation, see [the third control](#two-apps-and-a-third-control)).

## What it will not do

- Write to the account. The connectors make no write call. The deployed role is `ReadOnlyAccess` plus `s3:PutObject` on its
  own runs bucket and log writes to its own log groups ([`NightlyRole`](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/deploy/stack.yaml#L32-L58)).
  A Kiro hook refuses write calls during development.
- Accuse anyone. Findings state a condition and its evidence.
- Report billing it cannot see yet. Resources younger than the grace window (36 hours) are pending.

What the deployed roles can and cannot do, and how to report a security problem: [`SECURITY.md`](SECURITY.md).

## Claims and the tests that pin them

| Claim | Code | Test |
|---|---|---|
| Every key lands in exactly one of the seven regions | [`_region_code`](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/skeleton/src/nightaudit/matcher.py#L35-L44) | `test_property_every_key_lands_in_exactly_one_region_named_by_its_ledgers` |
| The same holds for every list of keys, proved | [`Partition.lean`](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/lean/NightAudit/Partition.lean#L166-L173) | `test_property_the_lean_model_and_the_python_matcher_give_every_key_the_same_region` |
| A healthy account gives zero findings | `_match` | `test_property_same_keys_in_all_three_ledgers_produce_zero_findings`, `test_healthy_account_of_ten_thousand_keys_is_silent` |
| A record younger than the grace window is pending | [`find_pending`](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/skeleton/src/nightaudit/grace.py#L16-L35) | `test_property_a_young_unbilled_observed_key_is_pending_and_produces_no_finding` |
| Ledger text never changes a region | `_match` | `test_property_an_instruction_in_an_attribute_assigns_the_same_regions_as_benign_text_of_equal_length` |
| Ledger text enters a prompt quoted and cut | [`build_prompt`](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/skeleton/src/nightaudit/explain.py#L89-L109) | `test_injected_text_is_quoted_and_truncated_in_the_prompt` |
| A number outside the evidence is replaced by the template | [`numbers_are_safe`](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/skeleton/src/nightaudit/explain.py#L162-L167) | `test_property_a_response_citing_a_number_outside_the_evidence_is_replaced_by_the_template` |
| A minus sign counts: a charge cannot read as a refund | `numbers_are_safe` | `test_regression_a_response_that_negates_an_evidence_number_is_rejected` |
| One changed byte in any evidence row fails verification | [`verify_evidence_pack`](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/skeleton/src/nightaudit/evidence.py#L516-L633) | `test_property_flipping_any_byte_of_any_evidence_row_fails_verification` |
| Region amounts plus unkeyed lines equal the billed total | `_match` | `test_property_region_billed_amounts_plus_unkeyed_equal_the_billed_total` |
| The same inputs give the same findings and evidence hash | `write_evidence_pack` | `test_property_repeating_a_run_with_identical_inputs_gives_identical_findings_and_evidence_hash` |
| Connectors make no write call; the role writes only its own runs and logs | [`stack.yaml`](deploy/stack.yaml) | `test_a_connector_module_calls_no_aws_operation_that_is_not_a_read`, `test_a_role_can_write_only_what_the_claim_names` |
| A hook file Kiro would skip fails a test | [`.kiro/hooks`](.kiro/hooks) | `test_a_hook_file_kiro_would_skip_silently_fails_here_instead` |
| The sealed casebook is unreadable in every spelling | [`seal_heldout.py`](scripts/hooks/seal_heldout.py) | `test_seal_blocks_every_spelling_of_the_heldout_folder` |
| Ghosts finds exactly its 8 planted findings | [`planted.yaml`](apps/ghosts/planted.yaml) | `test_the_run_finds_exactly_the_planted_findings` |
| A spec path resolves to the one tracked file it ends | [`promised_files`](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/apps/own-build/src/own_build/paths.py#L144-L157) | `test_a_spec_promises_exactly_the_files_the_casebook_says_given_the_tracked_files` |
| The power finds each planted condition in an empty project | [`power/night-audit`](power/night-audit) | `test_the_example_control_finds_each_planted_condition_through_nightaudit` |
| The Crew manifest passes the rules Crew 0.13.0 enforces | [`crew/night-shift/app.json`](crew/night-shift/app.json) | `test_the_manifest_follows_the_documented_rules`, `test_regression_a_command_cron_is_rejected_on_windows_so_the_audit_is_a_script_cron`, `test_regression_the_investigator_tool_refs_name_servers_the_agent_declares` |
| Both investigator agents (the checkout's, which the notes job launches, and the Crew app's) can call only reads, from pinned servers | [`.kiro/agents/night-investigator.json`](.kiro/agents/night-investigator.json), [`.kiro/settings/mcp.json`](.kiro/settings/mcp.json) | `test_the_checkout_investigator_can_call_no_tool_that_is_not_a_read`, `test_every_server_the_checkout_investigator_mounts_is_pinned_and_aws_api_reads_only`, `test_the_crew_investigator_can_call_no_tool_that_is_not_a_read_and_its_servers_are_pinned` |
| Recorded run, not a test: the Crew jobs wrote runs and notes that verify | [`docs/RESULTS.md`](docs/RESULTS.md#night-shift) | the `kirocrew cron trigger` commands and their output, recorded there |
| A Venn click filters the rows | [`vennSvg`](https://github.com/Marc-Dvci/night-audit/blob/v1.0.0/skeleton/web/src/render/venn.ts#L68-L119) | `test_a_venn_region_click_filters_the_rows` |

## Evidence

Every figure comes from a command in this repository. Synthetic data is labelled as synthetic. More in
[`docs/RESULTS.md`](docs/RESULTS.md).

| Figure | Command |
|---|---|
| 1046 tests: 1043 pass, 3 are the Lean differential tests, which run where `lake` is installed (CI) | `uv run pytest -q` |
| 41 property-based tests, 252 integration tests, 46 browser tests, 261 TypeScript tests | `uv run pytest -m property`, `-m integration`, `-m e2e`; `cd skeleton/web && npx vitest run` |
| Decision core coverage 96.85 % (lines and branches, nine modules) | `uv run pytest -q -m "not e2e and not live" --cov` |
| Development casebook 18 of 18 | `uv run python scripts/score_casebook.py --set dev` |
| Held-out casebook 6 of 6, scored once at tag `v0.1.0` | `uv run python scripts/score_heldout.py` |
| Real lab night, 7 Nov 02:00 UTC: 4 planted, 4 found, 0 Phantoms, 0 false Vampires. The instance, its volume and its network interface cost $0.7172 together, as Vampires | `uv run nightaudit run apps/vampires/controls/aws-account.yaml --runs runs/live` (read-only profile on the lab account); expected findings in `lab/expected.yaml` |
| Property-based testing found 7 bugs that 38 example tests, 18 of 18 development cases and 6 of 6 held-out cases had missed | `uv run pytest -m property`; the `test_regression_` tests |
| 0 axe-core violations (WCAG 2.0, 2.1, 2.2 A and AA) in 8 screen states, on the deployed demo (`?app=vampires-demo`) and on the live lab night, 7 Nov 2026; hostile tag text shown as text on the demo | `uv run python scripts/ui_check.py <url>`; both URLs and results in [`docs/RESULTS.md`](docs/RESULTS.md#accessibility) |
| 298,000 records matched in 1.49 s (199,855 a second) | `uv run python scripts/bench.py 100000` |
| Evidence of the live night verifies; the investigator's note passed the guard | `uv run nightaudit verify <run>/evidence`, `uv run nightaudit verify-notes <run>/evidence` |
| Kiro Crew 0.13.0 on Windows 11, 7 Nov, with the final code: the `night-audit` cron (`0af6390d`) wrote 4 runs and all 4 verify (`847b2b2514c14574`, `ebd45fd5644e4159`, `4c3e32bf3ef8c9ab`, `6ad680fc05a50128`). The `night-notes` cron (`9d342b56`), run with the read-only investigator, picked `6ad680fc05a50128` and asked nothing, since its five `OB` and `O` findings persist from the night before: `0 accepted, 0 rejected, 0 unavailable, 0 skipped`. The 5 notes on that earlier night, `1e9e38e57a33f5c4`, verify (`5 notes verify (5 accepted)`). Both jobs paused | `kirocrew cron trigger <id>`; `uv run nightaudit verify runs/<run>/evidence`; `uv run nightaudit verify-notes runs/<run>/evidence`; details in [`crew/README.md`](crew/README.md) |

**Real and synthetic.** The lab night is a real AWS account with a planted lab ([`lab/`](lab)); the Vampires and Ghosts
demos, both casebooks and the benchmark are synthetic; the third control reads this repository itself.

## Quickstart (no credentials)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/Marc-Dvci/night-audit?quickstart=1)
builds the same three demos and serves them on the forwarded port 8000: add `?app=vampires-demo`, `?app=ghosts-demo`
or `?app=own-build-demo`.

Python 3.12 with [`uv`](https://docs.astral.sh/uv/), and Node 22 for the web build.

```bash
uv sync
uv run python scripts/build_demos.py               # the recorded demo nights of all three apps
(cd skeleton/web && npm ci && npm run build)
uv run nightaudit serve --app vampires --runs runs/demo
# open http://127.0.0.1:8000/?app=vampires-demo
```

Or with Docker: `docker build -t night-audit . && docker run --rm -p 8000:8000 night-audit`.

To read a finished night without running anything, open [`examples/`](examples/README.md): one Vampires demo night's
report, its evidence pack and the three ledgers it read.

Run it on your own account with a read-only profile: edit `apps/vampires/controls/aws-account.yaml`, then
`uv run nightaudit run apps/vampires/controls/aws-account.yaml --runs runs/live`.

## Two apps and a third control

The same skeleton runs both submitted apps unchanged. [`apps/vampires`](apps/vampires) reconciles an AWS account.
[`apps/ghosts`](apps/ghosts) reconciles staff access: an HR roster, identity and SaaS user lists, and licence seats. It
was built by an agent with no write permission on `skeleton/` and found its 8 planted findings with nothing extra; the
skeleton is unchanged between commits `b6f5e46` and `ec92469`. The agent then reported five things the template could not
do. They were fixed afterwards in the open ([`git log`](https://github.com/Marc-Dvci/night-audit/commits/main)).

The third control, [`apps/own-build`](apps/own-build/README.md), audits this repository. Intended is the file paths the
specs promise. Observed is the files git tracks. Billed is the files Kiro worked on, in Kiro credits. It was written in
one control file through the `new-control-scaffold` hook, and no skeleton source file changed.

It reads the files git tracks at one commit. Recorded first at `a58b88b`, then at `05f013d` and at `2035d42`, each time
after the later Kiro sessions (the Crew sessions among them) were added to Kiro's export:

| Region | `a58b88b` | `05f013d` | `2035d42` |
|---|---|---|---|
| Spec'd and built with Kiro (`IOB`) | 172 | 176 | 180 |
| Spec'd, no Kiro session (`IO`, informational) | 118 | 119 | 119 |
| Written by hand or generated (`O`) | 56 | 36 | 42 |
| Built with Kiro, no spec names it or a folder holding it (`OB`) | 23 | 45 | 49 |
| Promised by a spec, never built (`I`) | 6 | 3 | 3 |
| Kiro worked on it, no spec, it is gone (`B`) | 5 | 8 | 5 |
| Tracked files | 369 | 376 | 390 |

The first run reported 32 files promised and never built. Reading them showed that 26 were the control's own parser
mistakes: a path written relative to a folder, a folder, or build output. The parser now resolves a relative path to the
one tracked file it ends, reads a folder as every tracked file under it, and drops `dist` and `node_modules` paths and
the files a spec says the power writes into a user's own project. At `a58b88b` that left 6 real findings. Three were
paths in the spec text that no longer existed (`apps/vampires/approved-changes.yaml`, `src/findings.ts`, `src/venn.ts`);
the spec text was corrected, and at `05f013d` they are gone. Three remain because they name no single file:
`demo/build.py` ends three tracked files, `references/region-table.md` ends two, `assets/verify.js` is a path inside
build output. Between the first two, 21 files moved from `O` to `OB`: Kiro sessions in the newer export touched them.
Between `05f013d` and `2035d42`, 14 more files are tracked: 11 new ones (3 in `IOB`, 8 in `O`) and 3 that were in `B`
because Kiro had worked on them before they were committed (`examples/README.md` and `scripts/build_examples.py` are
now `OB`, `skeleton/tests/test_examples.py` is `IOB`); 2 more files moved from `O` to `OB`.

The snapshot is one commit: `uv run python apps/own-build/snapshot.py` records the files git tracks at `HEAD` and the
paths its specs promise, and a change after that commit enters at the next snapshot. The credits are an allocation: a
session reports one figure and the export splits it equally across the files the session touched, so a file's credits
are not what it cost.

## Limits

Both casebooks are synthetic and small (18 and 6 cases). Findings are conditions with evidence, and a person decides what
each means. Billing data arrives late, so a resource younger than the grace window is pending until its bill lands.

## Layout and licence

`skeleton/` the template · `apps/` the three controls · `.kiro/` specs, agents, hooks, steering, MCP · `power/` and `crew/`
· `lean/` the proof · `deploy/` the Lambda stack · `lab/` the planted lab · `casebook/` the development cases ·
`scripts/` the scorers, the benchmark and the figure tools · `docs/` the results and figures.

Apache 2.0, see [`LICENSE`](LICENSE).
