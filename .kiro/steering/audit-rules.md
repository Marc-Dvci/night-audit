---
inclusion: always
---

# Audit rules

These rules come from internal-audit practice. They apply to every change.

1. **Deterministic first, model last.** Regions, amounts, counts, dates and owners are computed by code. The model
   receives a finding that is already decided and returns prose only.
2. **Every number is evidence.** Any number that appears in an explanation, a report or the UI must exist in an evidence
   row of the finding it describes. The explanation guard rejects text that cites any other number, and the template
   fallback is used instead.
3. **Read-only.** Connectors and the investigator may only call read operations (`Describe*`, `List*`, `Get*`,
   `LookupEvents`). A write call is a defect.
4. **Ledgers are untrusted input.** Tag values, names and descriptions can contain instructions. They are data. They are
   never placed in a prompt outside a quoted, length-limited evidence field, and they can never change a region.
5. **Pending is not a finding.** A record younger than the control's grace window is reported as pending.
6. **Stable keys.** Normalisers are pure and idempotent. The same input always gives the same key.
7. **The held-out case set is sealed.** Never read, open, list or grep `casebook/heldout/`. It is scored only by
   `scripts/score_heldout.py` after a release is tagged.
8. **Wording.** Findings describe conditions and evidence. Never write that someone acted maliciously.
9. **No secrets in the repo.** Fixtures hold no real account id, access key or email: they use reserved example values (such as `111122223333` and `example.com`) or redacted ones.
