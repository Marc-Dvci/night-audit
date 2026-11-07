# Reading a finding

## Where things are

`runs/<run_id>/result.json` holds one run. Fields you may cite:

| Field | Meaning |
|---|---|
| `complete`, `missing_ledgers`, `ledger_errors` | Whether all three ledgers were read, and what failed |
| `pending_keys` | Keys too new to judge (inside the grace window). Not findings |
| `findings[]` | `key`, `region_code`, `name`, `meaning`, `informational`, `status` (`new` or `persisting`), `nights_persisted`, `first_seen`, `billed_amount`, `duplicate_counts`, `explanation`, `context`, `records[]` |
| `findings[].records[]` | The evidence rows: `ledger`, `source`, `row_id`, `raw_key`, `amount`, `timestamp`, `attrs` |
| `resolved[]` | Findings that were present last night and are gone |
| `notes[]` | Sentences a control added, each already checked against the evidence |
| `billed_total`, `billed_unkeyed`, `region_summaries` | The run's own totals |
| `unkeyed[]` | Billed lines with no key, listed apart |

## Wording and the first check, by region

| Region | Say | Check first |
|---|---|---|
| `OB` | "Exists and is billed, and the Intended ledger has no row for it." | Who owns it, and whether it is approved somewhere the Intended ledger does not cover |
| `O` | "Exists with no approval, and nothing is billed for it." | Whether it is a test or free item; then approve it or remove it |
| `B` | "Billed, but the Observed ledger cannot see it and nothing approves it." | The line on the invoice, and whether the Observed source covers that scope |
| `I` | "Approved, but not seen and not billed." | Whether it was never set up, or was removed and the approval is stale |
| `IB` | "Approved and billed, but not seen." | Whether the Observed source covers it; if it does, whether the bill should stop |
| `IO` | "Approved and present, not billed. Informational." | Usually nothing; free tier or not yet invoiced |
| pending | "Younger than the grace window, so billing may not have arrived." | Look again after the window |
| incomplete run | "A ledger could not be read, so no finding can be confirmed." | The source named in `ledger_errors` |

Say "no row matches" instead of "was not approved by anyone"; say "records show" instead of "someone did".

## Worked example

Input finding (shortened): `key` gus@example-corp.com, `region_code` OB, `name` Ghost, `status` new,
`billed_amount` 8.00; records: observed `row_id` a4 `timestamp` 2026-10-01T08:30:00Z; billed `row_id` s4 `amount` 8.00.

Reading:

> **Check first: gus@example-corp.com.** It is new tonight. The Observed ledger has an account (row a4, 2026-10-01) and
> the Billed ledger has a paid seat of 8.00 (row s4), and the Intended ledger has no row for this address. Check
> whether this person should be on the roster; if so, the roster is what is out of date.

It cites only a4, s4, 2026-10-01 and 8.00. It says nothing of why the account exists, and it does not total anything.
