# The three ledgers and the seven regions

Night Audit is a three-way match over three independent ledgers of the same reality.

| Ledger | Initial | Question it answers |
|---|---|---|
| Intended | I | What did we approve? |
| Observed | O | What actually exists? |
| Billed | B | What are we paying for? |

A key present in all three ledgers is matched. Every other combination is a finding, and each combination has one
fixed meaning. The code assigns the region from which ledgers hold the key, never from any text in a record.
The region code always lists the initials in I-O-B order.

| Present in | Region code | Default name | Meaning |
|---|---|---|---|
| I, O, B | `IOB` | Living | Matched. No finding |
| O, B | `OB` | Vampire (cloud) / Ghost (people) | Exists and is paid for, but nobody approved it |
| O | `O` | Poltergeist | Exists, unapproved, not billed (free resources, keys, test accounts) |
| B | `B` | Phantom | Billed for something nobody approved and nobody can see |
| I | `I` | Skeleton | Approved, but absent and unbilled (a missing control or an unprovisioned joiner) |
| I, B | `IB` | Wraith | Approved and paid for, but not observed |
| I, O | `IO` | Familiar | Approved and present, not billed. Informational |

Two more outcomes are not regions:

- **Pending.** An observed record younger than the control's grace window, with no billed record yet. Billing data
  arrives late, so a young record is pending, never a finding.
- **Unkeyed.** A record whose key is empty after normalisation (a tax line, a blank cell). It is listed apart, never
  matched, and still counted in the billed total.

The names are a default. A control may rename any region (`regions:` in the control file) so that a reader sees
the words of their own domain; the code and the meaning stay the same.