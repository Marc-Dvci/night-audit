# Results

Every figure here comes from a command in this repository. Synthetic data is labelled as synthetic.

## Casebook (synthetic, labelled by hand before the matcher existed)

| Set | Cases | Passed | When | Command |
|---|---|---|---|---|
| Development | 18 | 18 | every commit (CI) | `uv run python scripts/score_casebook.py --set dev` |
| Held-out (sealed) | 6 | 6 | once, at tag `v0.1.0` (commit `f1efcbd`), 4 Nov 2026 | `uv run python scripts/score_heldout.py` |

The held-out cases include a 40-key healthy account in shuffled order (zero findings expected), an instruction
planted in a billed tag, a duplicate phantom written two ways, and a leaver hidden behind an alias domain and a
`+tag`. The agent that wrote the matcher was blocked from reading them by the `seal-heldout-casebook` hook.

## Accessibility

`python scripts/ui_check.py <url>` drives the UI in headless Chromium through eight states (overview and each
region filter, with a finding opened) and runs axe-core with the WCAG 2.0, 2.1 and 2.2 A/AA rules: 0 violations on
4 Nov 2026, locally and on the live function URL.

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

## Throughput

`uv run python scripts/bench.py 100000`: 298,000 records (100,000 keys across three ledgers, 1% declared-but-gone
and 1% never declared) matched in 1.49 s, about 199,000 records a second, on a six-core desktop CPU (4 Nov 2026).
