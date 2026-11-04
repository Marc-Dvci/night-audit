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
