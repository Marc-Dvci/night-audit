# Casebook format

A casebook is a YAML file in `casebook/`. The expectations are written by a person, from the region table, before the
matcher has ever run on these rows. `assets/casebook_runner.py` runs it.

```yaml
control: ../controls/seat-audit.yaml     # relative to this file; its normalisers and grace window apply
now: "2026-11-04T02:00:00Z"              # the run time, UTC; a case may set its own `now`
cases:
  - id: ghost-account-with-seat-not-on-roster      # unique, says what the case shows
    healthy: false                                  # true on the case that must produce nothing
    note: gus has an account and a paid seat, but no roster row.   # one sentence, required
    ledgers:                                        # all three keys are required
      intended: [{row: i1, key: "ana@example.test"}]
      observed: [{row: o1, key: "ana@example.test", ts: "2026-03-02T09:00:00Z"}]   # `ts` feeds the grace window
      billed:   [{row: b1, key: "ana@example.test", amount: "8.00"}]               # money as a decimal string
      # `null` instead of a list means the source could not be read: the run is incomplete
    expect:
      regions: {ana@example.test: IOB}              # keys as the control normalises them
      findings: 0
```

## Row fields

| Field | Meaning |
|---|---|
| `row` | A row id, unique within the ledger. It is how a finding points back at a row |
| `key` | The value as the source writes it, before normalisation. Empty means unkeyed |
| `ts` | When the thing was observed or created (observed ledger). Needed for the grace window |
| `amount` | A decimal string (billed ledger). Never a float |
| `attrs` | Other columns as text: names, tags, descriptions. They are data and never change a region |

## What a case may expect

`regions` (key to region code; pending keys have no region), `findings` (count outside `IO`), `informational`
(count in `IO`), `pending` (keys), `unkeyed` (row ids), `billed_total`, `billed_unkeyed`, `billed_by_region`,
`duplicates` (key to ledger to count), `complete`, `missing_ledgers`. Any other name fails the test.

## Which cases to write

At least five. Always:

1. **One healthy case**, flagged `healthy: true`: every key in all three ledgers, `findings: 0`, every region `IOB`.
2. One case per region the user told you they care about (`OB`, `O`, `B`, `I`, `IB`, `IO`), each with one clear culprit
   among otherwise healthy keys, so a wrong region is attributable.
3. A pending case if billing lags: an observed record younger than `grace_hours`, not billed.
4. The same key written three ways (case, spaces, a prefix such as an ARN), expected to match.
5. A row with text that reads like an instruction in an `attrs` value: the region must not change.
6. A `null` ledger, if the source can fail: `complete: false`, no findings.

Work each expectation out by hand with the region table. If you catch yourself copying the matcher's output into
`expect`, stop: that turns the casebook into a record of what the code does instead of a statement of what it should do.
