# Night Audit

![Night Audit, night of 6 Nov 2026 on the demo account](docs/figures/ui-night-3.png)

**Night Audit checks every night that what you approved, what is running and what you pay for are the same three
lists, and names whatever appears in only one or two of them.**

I test access and change-management controls in IT audits at a bank's technology practice. The control I trust most
is the oldest one in accounts payable: an invoice is paid only when the purchase order, the goods receipt and the
invoice agree. Night Audit runs that three-way match on a cloud account.

| | |
|---|---|
| Live app, no login | https://o7hhjtbm3mydyatsvlz7t3teli0fqski.lambda-url.us-east-1.on.aws/ (`?demo=1` for the demo account) |
| Category | Kiroween 2026, Skeleton Crew |
| Built with | Kiro (specs, hooks, steering, MCP), Python 3.12, FastAPI, TypeScript, AWS Lambda, EventBridge Scheduler, S3, CUR 2.0 |
| Headline | Held-out casebook 6 of 6, scored once at tag `v0.1.0`; development casebook 18 of 18 on every commit |

## For judges

| Criterion | Where to look |
|---|---|
| Potential impact | [The problem](#the-problem), [the lab](lab/expected.yaml) |
| Technological implementation | [How Kiro is used](#how-kiro-is-used), [`.kiro/`](.kiro) |
| Design | [See it work](#see-it-work), [`.kiro/steering/ui-identity.md`](.kiro/steering/ui-identity.md) |
| Innovation | [How it works](#how-it-works) |
| Evidence | [docs/RESULTS.md](docs/RESULTS.md) |

## See it work

![The Vampire finding opened: the billed line, the inventory line and an instruction planted in the Name tag, shown as data](docs/figures/ui-vampire-evidence.png)

The Venn diagram is the navigation: click a region, or use the legend with the keyboard, to filter the rows. Each row
opens to the ledger lines it came from.

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

## How it works

![Architecture](docs/figures/architecture.png)

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
that cites a number absent from the evidence is replaced by a fixed template.

The repository is a Skeleton Crew entry: `skeleton/` is the reusable template (package `nightaudit`) and each app under
`apps/` supplies only a control file and connectors.

| Folder | What it is |
|---|---|
| `skeleton/` | Normalisers, matcher, grace window, night-over-night state, evidence chain, explanation guard, API, CLI, web UI kit |
| `apps/vampires/` | AWS account: declared stacks and approvals, live inventory in every enabled region, CUR 2.0 |
| `apps/ghosts/` | Staff access: HR roster, identity exports, SaaS licences ([spec](.kiro/specs/ghosts-app/requirements.md)) |

## How Kiro is used

| Kiro feature | In this repository |
|---|---|
| Specs | [`three-way-match`](.kiro/specs/three-way-match): requirements in EARS, Kiro's design with ten correctness properties, Kiro's 29-task plan. App specs for [vampires](.kiro/specs/vampires-app) and [ghosts](.kiro/specs/ghosts-app) |
| Kiro CLI | Kiro wrote the design and implemented tasks 1 to 16 headless (`kiro-cli chat --v3 --no-interactive`), with file tools only |
| Hooks | [`seal-heldout`](.kiro/hooks/seal-heldout.json) blocks any read of the held-out casebook; [`read-only-aws`](.kiro/hooks/read-only-aws.json) refuses any AWS write from MCP or the shell; [`properties-on-save`](.kiro/hooks/properties-on-save.json); [`new-control-scaffold`](.kiro/hooks/new-control-scaffold.json); [`score-on-stop`](.kiro/hooks/score-on-stop.json) |
| Steering | [product](.kiro/steering/product.md), [tech](.kiro/steering/tech.md), [audit rules](.kiro/steering/audit-rules.md), [UI identity](.kiro/steering/ui-identity.md) (loaded only for web files) |
| MCP | [`.kiro/settings/mcp.json`](.kiro/settings/mcp.json): the AWS API server in read-only mode, billing and CloudTrail servers, all on a read-only profile |

## What it will not do

- Write to the account. Every connector is read-only, the deployed role is `ReadOnlyAccess`, and a Kiro hook refuses
  write calls during development.
- Accuse anyone. Findings state a condition and its evidence.
- Report billing it cannot see yet. Resources younger than the grace window (36 hours) are pending.

## Evidence

| Claim | Command |
|---|---|
| Held-out casebook 6/6, scored once at `v0.1.0` | `uv run python scripts/score_heldout.py` |
| Development casebook 18/18 | `uv run python scripts/score_casebook.py --set dev` |
| Injection, lookalike keys, laundering through unkeyed lines | `uv run pytest skeleton/tests/test_self_attack.py` |
| Evidence pack fails on a single added space | `uv run pytest skeleton/tests/test_end_to_end.py` |
| 298,000 records in 1.49 s | `uv run python scripts/bench.py 100000` |
| 0 axe-core WCAG 2.2 AA violations on 8 screen states | `python scripts/ui_check.py <url>` |

Real and synthetic: the live account is a real AWS account with a planted lab ([`lab/`](lab)); the demo account and
both casebooks are synthetic.

## Quickstart (no credentials)

```bash
uv sync
uv run python apps/vampires/demo/build.py          # three demo nights
(cd skeleton/web && npm ci && npm run build)
uv run nightaudit serve --app vampires --runs runs/demo
# open http://127.0.0.1:8000/
```

Or with Docker: `docker build -t night-audit . && docker run --rm -p 8000:8000 night-audit`.

Run it on your own account with a read-only profile: edit `apps/vampires/controls/aws-account.yaml`, then
`uv run nightaudit run apps/vampires/controls/aws-account.yaml --runs runs/live`.

## Licence

Apache 2.0.
