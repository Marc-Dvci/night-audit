# A finished night, without running anything

`vampires-night/` is the third night of the Vampires demo: a demo AWS account audited at 02:00 UTC on 6 Nov 2026
(run `75b641467552e35a`). The files are copied byte for byte from the committed demo by
`uv run python scripts/build_examples.py`, and `skeleton/tests/test_examples.py` fails if they ever differ.

| File | What it is |
|---|---|
| [`vampires-night/report.html`](vampires-night/report.html) | The morning report: 8 findings, 2 of them Vampires billed $42.56 together |
| [`vampires-night/evidence.jsonl`](vampires-night/evidence.jsonl) | The evidence chain: a header row, every ledger record, then one row per finding, each row carrying the SHA-256 of the row before it |
| [`vampires-night/manifest.json`](vampires-night/manifest.json) | The pack's manifest: the control hash, each ledger's hash and count, the final chain hash |
| [`vampires-night/run.json`](vampires-night/run.json) | The run as the page shows it. `verify` compares it with the chain |
| [`vampires-night/ledgers/intended.csv`](vampires-night/ledgers/intended.csv) | Intended: what the account's stacks and approved changes declare |
| [`vampires-night/ledgers/observed.csv`](vampires-night/ledgers/observed.csv) | Observed: the live inventory |
| [`vampires-night/ledgers/billed.csv`](vampires-night/ledgers/billed.csv) | Billed: the Cost and Usage Report line items |

The control that read these ledgers is `apps/vampires/demo/night-3/control.yaml`. Nights 1 and 2 are in the same
folder; they are why some findings on this night are persisting rather than new.

## Verify it

```bash
uv sync
uv run nightaudit verify examples/vampires-night
```

It prints `OK  verified 36 rows, 8 findings, header matches the manifest; the page matches the evidence`. Change one
character in `evidence.jsonl`, or one amount in `run.json`, and it prints `FAIL` with the row or the figure that differs.
