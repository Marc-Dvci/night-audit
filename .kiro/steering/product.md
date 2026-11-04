---
inclusion: always
---

# Product: Night Audit

Night Audit is a three-way match for things an organisation pays for. Accounts-payable teams release an invoice only when
the purchase order, the goods receipt and the invoice agree. Night Audit runs the same control every night over three
independent ledgers of the same reality:

| Ledger | Question it answers |
|---|---|
| Intended | What did we approve? |
| Observed | What actually exists? |
| Billed | What are we paying for? |

A key present in all three ledgers is matched. Every other combination is a finding, and each combination has one
fixed meaning. The Halloween names are the control's taxonomy, so a reader learns the meaning once and reads every
screen with it.

| Present in | Region code | Default name | Meaning |
|---|---|---|---|
| I, O, B | `IOB` | Living | Matched. No finding |
| O, B | `OB` | Vampire (cloud) / Ghost (people) | Exists and is paid for, but nobody approved it |
| O | `O` | Poltergeist | Exists, unapproved, not billed (free resources, keys, test accounts) |
| B | `B` | Phantom | Billed for something nobody approved and nobody can see |
| I | `I` | Skeleton | Approved, but absent and unbilled (a missing control or an unprovisioned joiner) |
| I, B | `IB` | Wraith | Approved and paid for, but not observed |
| I, O | `IO` | Familiar | Approved and present, not billed. Informational |

The repository is a Skeleton Crew entry: one reusable skeleton and two applications built on it.

- `skeleton/` is the template: ledgers, normalisers, the matcher, night-over-night state, the evidence pack, the
  explanation guard, and the night-ledger UI kit.
- `apps/vampires/` reconciles an AWS account: CloudFormation and approved changes (intended), live inventory
  (observed), Cost and Usage Report 2.0 line items (billed).
- `apps/ghosts/` reconciles staff access: an HR roster (intended), identity and SaaS user lists (observed), SaaS
  licence assignments and invoices (billed).

## Users and moments

- A startup CTO at 08:30 opening the morning report, before anyone has looked at the bill.
- An IT manager preparing a quarterly access review that an auditor will test.

## Product rules

- The control decides with code. A language model may only explain a finding that code already produced.
- Findings are stated as conditions with evidence ("account j.marsh is active in two systems; HR records a leaving date
  of 12 Sep 2026"), never as accusations.
- A healthy account must produce zero findings.
- Billing data arrives late. Records younger than the control's grace window are pending, never findings.
