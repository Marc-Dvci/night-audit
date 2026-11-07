# Design: the three-way match skeleton

## 1. Overview

The `nightaudit` package in `skeleton/` is the reusable core of the Night Audit product. An application
supplies three connectors (one per ledger) and a control file; the skeleton handles normalisation,
matching, night-over-night state, the evidence pack, the explanation guard, and the API that the UI
reads.

The control is a three-way match over three independent ledgers of the same reality:

| Ledger | Question it answers |
|---|---|
| intended | What did we approve? |
| observed | What actually exists? |
| billed | What are we paying for? |

A key present in all three ledgers is matched (`IOB`). Every other combination is a finding
with a fixed meaning drawn from the product taxonomy. The code decides regions, amounts, counts, dates
and owners; a language model may only explain a finding the code already produced (audit rule 1).

The seven non-empty subsets of {I, O, B} map to region codes, always written in I-O-B order. This is the
spec's one region table; everywhere else a region is called by its meaning or its code. The Halloween name is
the default tag shown beside the meaning.

| Meaning | Code | Finding? | Halloween name (default tag) |
|---|---|---|---|
| Matched | `IOB` | No | Living |
| Approved and present, not billed | `IO` | Informational | Familiar |
| Approved and paid for, but not observed | `IB` | Yes | Wraith |
| Exists and is paid for, but nobody approved it | `OB` | Yes | Vampire (cloud) / Ghost (people) |
| Approved, but absent and unbilled | `I` | Yes | Skeleton |
| Exists, unapproved, not billed | `O` | Yes | Poltergeist |
| Billed for something nobody approved and nobody can see | `B` | Yes | Phantom |

## 2. Module map

```
skeleton/
  pyproject.toml
  src/nightaudit/
    __init__.py        public API exports
    models.py          pydantic v2 data model
    normalisers.py      normaliser registry + built-in chain normalisers
    control.py          control file schema, loading, validation, canonical hash
    scope.py            scope filter: drop out-of-scope records before matching
    grace.py            grace window: mark young unbilled keys as pending
    matcher.py          matching engine: partition keys into regions, produce findings
    state.py            night-over-night state: new / persisting / resolved
    evidence.py         evidence pack: JSONL hash chain, manifest, verify
    explain.py          explanation guard: Bedrock call, number guard, template fallback
    connectors.py       connector interface, CSV / JSONL connectors, read-only enforcement
    runner.py           orchestrates one run end to end
    api.py              FastAPI app + endpoints
    cli.py              nightaudit CLI (run, serve, verify, score)
    web/                static front-end (TypeScript, Vite, SVG Venn diagram)
  tests/
    conftest.py
    test_property_*.py  one file per correctness property
    test_*.py           unit and integration tests
```

### Responsibilities

| Module | Responsibility | Key requirements |
|---|---|---|
| models | Immutable pydantic v2 types and region constants | Req 2.4, 3.1, 3.4, 3.5 |
| normalisers | Registry + built-in normalisers, chain application, idempotence | Req 2.1–2.4 |
| control | Control file parsing, schema validation, canonical hash, region defaults | Req 1.1–1.4 |
| scope | Drop out-of-scope records before matching, count dropped | Req 4.2 |
| grace | Suppress young unbilled keys as pending | Req 4.1 |
| matcher | Partition keys into regions, produce findings, verify amount conservation | Req 3.1–3.5 |
| state | Compare with previous run, track first-seen and nights | Req 5.1–5.3 |
| evidence | Hash chain, manifest, verify, tamper detection | Req 6.1–6.3 |
| explain | Bedrock Converse call, number guard, template fallback, injection safety | Req 7.1–7.4 |
| connectors | Connector interface, CSV / JSONL, read-only enforcement, failure handling | Req 9.1–9.4 |
| runner | End-to-end orchestration | all |
| api | REST endpoints + static front-end | Req 8.1 |
| cli | Command-line entry points | all |
| web | Venn diagram, findings list, green-bar UI kit | Req 8.2–8.4 |

## 3. Data model

All models are pydantic v2 `BaseModel` subclasses. Money is `decimal.Decimal`, never float. Records are
immutable (`model_config = ConfigDict(frozen=True)`).

### Constants

**`REGION_CODES`** — `("IOB", "IO", "IB", "OB", "I", "O", "B")`, the seven non-empty subsets of {I, O, B}
in I-O-B order.

**`DEFAULT_REGION_NAMES`** — maps each code to its default Halloween tag, the last column of the region table
in §1 (the cloud tag for `OB`).

**`DEFAULT_REGION_MEANINGS`** — maps each code to its one-sentence meaning from the product glossary.

**`FINDING_REGIONS`** — `frozenset({"OB", "O", "B", "I", "IB"})`. Keys in these regions are findings.

**`INFORMATIONAL_REGIONS`** — `frozenset({"IO"})`. Keys in this region are informational (approved and present, not billed):
shown in the UI and counted separately, but not actionable findings.

### LedgerName

`str` enum with values `intended`, `observed`, `billed`.

### Record

One row from one ledger.

| Field | Type | Notes |
|---|---|---|
| `ledger` | `LedgerName` | which ledger this row came from |
| `source` | `str` | connector name or file path |
| `row_id` | `str` | row identifier within the source |
| `raw_key` | `str` | the key before normalisation |
| `key` | `str \| None` | normalised key; `None` if empty after normalisation (unkeyed) |
| `attrs` | `dict[str, str]` | free-form attributes (tags, names, scope markers) |
| `amount` | `Decimal \| None` | billed amount; `None` for non-billed ledgers |
| `timestamp` | `datetime \| None` | creation/observation time; observed records only |

`key` is set during matching by applying the control's normaliser chain to `raw_key`.

### LedgerSnapshot

The result of fetching one ledger.

| Field | Type | Notes |
|---|---|---|
| `name` | `LedgerName` | |
| `source` | `str` | connector name or file path |
| `records` | `list[Record]` | in-scope records after filtering |
| `dropped` | `int` | count of records removed by scope filter |
| `missing` | `bool` | `True` when the connector failed or the ledger was not provided |

### UnkeyedRow

A record whose normalised key is empty (Req 2.4), reported separately.

| Field | Type |
|---|---|
| `row_id` | `str` |
| `ledger` | `LedgerName` |
| `source` | `str` |
| `amount` | `Decimal \| None` |

### Finding

One key that does not match (non-IOB), with all its evidence.

| Field | Type | Notes |
|---|---|---|
| `key` | `str` | normalised key |
| `region_code` | `str` | one of the 7 codes |
| `name` | `str` | Halloween tag from control override or default (Req 1.4) |
| `severity` | `str` | from control override or default |
| `meaning` | `str` | from control override or default |
| `informational` | `bool` | `True` for `IO` (approved and present, not billed); `False` for finding regions |
| `records` | `list[Record]` | every record for this key across all three ledgers |
| `billed_amount` | `Decimal` | sum of amounts in billed records for this key (zero if none) |
| `duplicate_counts` | `dict[str, int]` | ledger name → count when > 1 (Req 3.4) |
| `status` | `str` | `"new"` \| `"persisting"` \| `"resolved"` (Req 5.1) |
| `nights_persisted` | `int \| None` | nights since first_seen (Req 5.2) |
| `first_seen` | `datetime \| None` | first time this finding appeared (Req 5.2) |
| `explanation` | `str \| None` | model or template explanation |

### RegionSummary

Aggregated stats for one region (Req 3.5).

| Field | Type |
|---|---|
| `code` | `str` |
| `key_count` | `int` |
| `billed_amount` | `Decimal` |

### RunResult

The complete output of one run.

| Field | Type | Notes |
|---|---|---|
| `run_id` | `str` | deterministic: derived from run_time + control_hash |
| `run_time` | `datetime` | |
| `control_hash` | `str` | SHA-256 of canonical control (Req 1.3) |
| `complete` | `bool` | `False` when any ledger is missing (Req 9.4) |
| `missing_ledgers` | `list[str]` | names of failed ledgers |
| `snapshots` | `list[LedgerSnapshot]` | |
| `regions` | `dict[str, str]` | key → region code; empty when incomplete |
| `pending_keys` | `list[str]` | keys suppressed by the grace window (Req 4.1) |
| `unkeyed` | `list[UnkeyedRow]` | records with empty normalised keys (Req 2.4) |
| `findings` | `list[Finding]` | actionable findings + informational items; empty when incomplete |
| `region_summaries` | `dict[str, RegionSummary]` | per region: key count + billed amount (Req 3.5) |
| `duplicates` | `dict[str, dict[str, int]]` | key → {ledger: count} (Req 3.4) |
| `billed_total` | `Decimal` | sum of all in-scope billed amounts |
| `billed_unkeyed` | `Decimal` | sum of unkeyed billed amounts |
| `dropped` | `dict[str, int]` | per-ledger scope drop count (Req 4.2) |
| `evidence_chain_hash` | `str \| None` | final hash of the evidence chain |

The `findings` list contains both actionable findings (`informational=False`) and informational items
(`informational=True` for `IO`). The casebook and UI count them separately. The API can filter by
region code, which includes `IO`.

## 4. Control file schema

### ControlConfig

The subset of a control file that the matcher needs (no connector details). The scorer builds this
directly from casebook data.

| Field | Type | Default | Notes |
|---|---|---|---|
| `normalisers` | `dict[str, list[str]]` | — | per-ledger normaliser chain |
| `grace_hours` | `int` | 24 | grace window in hours |
| `scope` | `ScopeFilter \| None` | `None` | optional scope filter |
| `alias_domains` | `dict[str, str]` | `{}` | used by `email_canonical` |
| `regions` | `dict[str, RegionOverride]` | `{}` | overrides for name, severity, meaning, template |

### ScopeFilter

| Field | Type |
|---|---|
| `attr` | `str` |
| `equals` | `str` |

A record is in scope when `record.attrs.get(attr) == equals`. Records missing the attribute are out
of scope.

### RegionOverride

| Field | Type | Notes |
|---|---|---|
| `name` | `str \| None` | override the default monster name |
| `severity` | `str \| None` | override severity |
| `meaning` | `str \| None` | override the one-sentence meaning |
| `template` | `str \| None` | deterministic explanation template |

### ControlFile (production)

Extends `ControlConfig` with connector configuration per ledger. Example:

```yaml
ledgers:
  intended:
    connector: {type: csv, path: "approved.csv"}
    key_field: resource_id
    normalisers: [strip, lower]
  observed:
    connector: {type: jsonl, path: "inventory.jsonl"}
    key_field: resource_id
    normalisers: [strip, lower]
  billed:
    connector: {type: csv, path: "cur.csv"}
    key_field: line_item_resource_id
    normalisers: [arn_resource_id, strip, lower]
grace_hours: 24
scope: {attr: project, equals: lab}
alias_domains: {hollowpines.org: hollowpines.com}
regions:
  OB: {name: Ghost, severity: high, meaning: "Active and paid for, but HR has no record"}
```

`ControlFile.to_config()` extracts a `ControlConfig` (normalisers pulled from each ledger config) for
the matcher and scorer.

### Validation rules

- **Req 1.1** — the `ledgers` dict must contain exactly three keys: `intended`, `observed`, `billed`.
  Any other set is rejected with a message naming the missing or extra ledgers.
- **Req 1.2** — every normaliser name in every ledger's chain must be in the normaliser registry. An
  unknown name is rejected with the name and the ledger it appeared in.
- **Req 1.3** — the canonical form is the control's configuration serialised as JSON with sorted keys and
  compact separators (`separators=(",", ":")`), so comments and formatting variance do not affect the
  hash. The control hash is `SHA-256(canonical_json)` and is attached to every run.
- **Req 1.4** — when a region code has no override in the control file, the default name and meaning
  from `DEFAULT_REGION_NAMES` / `DEFAULT_REGION_MEANINGS` are used.

## 5. Normalisers

### Normaliser registry

A class-level registry maps normaliser names to functions. Each function has the signature
`(value: str, ctx: dict) -> str`. The `ctx` dict carries control-level parameters such as
`alias_domains` (used by `email_canonical`).

Registration happens at import time via a `@register("name")` decorator. The registry exposes:

- `get(name)` — returns the function, raises `UnknownNormaliserError` if absent.
- `names()` — returns the set of registered names.

The control file loader calls `get` for every normaliser name in the file to validate early (Req 1.2).

### Built-in normalisers

| Name | Behaviour | Idempotent because |
|---|---|---|
| `strip` | `s.strip()` | stripping an already-stripped string is a no-op |
| `lower` | `s.lower()` | lowercasing an already-lower string is a no-op |
| `collapse_whitespace` | replace every run of whitespace with a single space | an already-collapsed string has no runs longer than one |
| `email_canonical` | strip, lower, remove `+tag` from the local part, map alias domains | a canonicalised email has no `+` and the domain is already mapped, so a second pass is a no-op |
| `arn_resource_id` | if the string starts with `arn:`, extract the resource id; otherwise return as-is | a bare resource id does not start with `arn:`, so a second pass returns it unchanged |

#### email_canonical detail

Input `Li.Wei+admin@hollowpines.org` with `alias_domains = {"hollowpines.org": "hollowpines.com"}`:

1. Lower-case the whole string → `li.wei+admin@hollowpines.org`
2. Split at `@`: local=`li.wei+admin`, domain=`hollowpines.org`
3. Remove the `+tag`: local=`li.wei`
4. Map alias domain: domain=`hollowpines.com`
5. Result: `li.wei@hollowpines.com`

A second pass: no `+` in the local part, `hollowpines.com` is not an alias key, so the result is
unchanged.

#### arn_resource_id detail

Input `arn:aws:ec2:us-east-1:111122223333:instance/i-0aa1`:

1. Split on `:` with `maxsplit=5` → `["arn", "aws", "ec2", "us-east-1", "111122223333", "instance/i-0aa1"]`
2. Resource = `instance/i-0aa1`
3. Contains `/` → take the last `/` segment → `i-0aa1`

Input `arn:aws:rds:eu-west-3:111122223333:db:db-reporting`:

1. Split on `:` with `maxsplit=5` → `["arn", "aws", "rds", "eu-west-3", "111122223333", "db:db-reporting"]`
2. Resource = `db:db-reporting`
3. No `/`, contains `:` → take the last `:` segment → `db-reporting`

Input `lab-logs-bucket` (not an ARN): return as-is. Input `i-0aa1` (already a resource id): does not
start with `arn:`, return as-is.

### Chain application

The chain is applied in order (Req 2.1):

```python
def normalise(raw_key: str, chain: list[str], ctx: dict) -> str:
    result = raw_key
    for name in chain:
        result = NormaliserRegistry.get(name)(result, ctx)
    return result
```

If the result is an empty string, the record is unkeyed (Req 2.4): it is excluded from matching and
reported in the `unkeyed` list with its `row_id`.

## 6. Matcher algorithm

`match(snapshots, control, run_time)` takes three `LedgerSnapshot` objects, a `ControlConfig`, and a
`datetime` run time. It returns a `RunResult`.

### Step 0 — Missing-ledger check

If any snapshot has `missing=True`, return an incomplete `RunResult` immediately:

- `complete = False`
- `missing_ledgers` = names of missing snapshots
- `findings = []`, `regions = {}`
- all amounts are zero

Every finding claims a discrepancy between ledgers, and a discrepancy cannot be confirmed without
every ledger. This satisfies Req 9.4: "produce no findings that depend on the missing ledger." Since
every finding depends on all three ledgers, an incomplete run produces no findings at all.

### Step 1 — Normalise keys

For each record in each snapshot:

- Build `ctx = {"alias_domains": control.alias_domains}`.
- Apply the ledger's normaliser chain to `raw_key` (Req 2.1).
- If the result is empty → add an `UnkeyedRow` to the `unkeyed` list, set `record.key = None`.
- Otherwise → set `record.key = result`.

### Step 2 — Scope filtering

If `control.scope` is set, drop records whose `attrs.get(scope.attr)` does not equal `scope.equals`
(records missing the attribute are also dropped). Record the count of dropped records per ledger
(Req 4.2). This happens before matching so dropped records never enter a region or the amount
conservation check.

### Step 3 — Group by key

For each ledger, group surviving records by `record.key`. Build:

- `keys_in_ledger: dict[LedgerName, set[str]]` — normalised keys present in each ledger.
- `records_by_key: dict[str, list[Record]]` — all records for a key across all three ledgers.

### Step 4 — Grace window

For each key that appears in the observed ledger but not in the billed ledger:

- Find the most recent observed record for the key (maximum `timestamp`).
- If `run_time - max_timestamp < grace_hours` → add the key to `pending_keys` and remove it from
  `keys_in_ledger[observed]` and from `records_by_key`.

This prevents false findings for resources whose billing has not arrived yet (Req 4.1). See §7 for
details.

### Step 5 — Compute regions

Collect the union of all keys across all three ledgers. For each key:

- Build the set of ledgers that contain it.
- The region code is the join of the present ledger initials in I-O-B order:

  | Present in | Code |
  |---|---|
  | I, O, B | `IOB` |
  | I, O | `IO` |
  | I, B | `IB` |
  | O, B | `OB` |
  | I | `I` |
  | O | `O` |
  | B | `B` |

- Store in `regions[key] = code`.

This is a pure set computation: it does not depend on record order (Req 3.2) or record count.

### Step 6 — Produce findings

For each key whose region is not `IOB`:

- Collect all records for the key from `records_by_key`.
- `billed_amount` = sum of `record.amount` for billed records (default `Decimal("0")` if none).
- `duplicate_counts` = `{ledger_name: count}` for each ledger where the record count is > 1 (Req 3.4).
- `informational` = `True` if region is `IO`, `False` otherwise.
- Resolve `name`, `severity`, `meaning` from control file overrides or defaults (Req 1.4).
- Create a `Finding` with `status="new"`, `nights_persisted=None`, `first_seen=run_time`. The state
  module (§9) updates `status`, `nights_persisted`, and `first_seen` after the run.

### Step 7 — Compute summaries

For each region code that has at least one key (Req 3.5):

- `key_count` = number of keys in that region.
- `billed_amount` = sum of `billed_amount` over all keys in that region.

Store in `region_summaries[code]`.

### Step 8 — Amount conservation

- `billed_total` = sum of `amount` over all surviving billed records (after scope filtering).
- `billed_unkeyed` = sum of `amount` over unkeyed billed records.
- Assert: `sum(region_summaries[r].billed_amount for all r) + billed_unkeyed == billed_total`.

Every billed record with a key contributes to exactly one region's `billed_amount`. Every billed
record without a key contributes to `billed_unkeyed`. The two sets are disjoint and exhaustive, so the
sum is exact (Req 3.5). Pending keys have no billed records (that is a precondition for pending), so
they do not affect the conservation.

### Step 9 — Assemble RunResult

Combine all the above into a `RunResult` with `complete=True`.

## 7. Grace window

The grace window prevents false findings for resources whose billing data has not arrived yet
(Req 4.1).

A key is **pending** when all of the following hold:

1. The key has at least one observed record (a `timestamp` is present).
2. The most recent observed record's timestamp is within `grace_hours` of `run_time`:
   `run_time - max(timestamps) < timedelta(hours=grace_hours)`.
3. The key does not appear in the billed ledger.

Pending keys are removed from the region assignment entirely. They appear in `pending_keys` and do
not produce findings. Their observed records are not included in any finding's evidence.

When the observed record ages past the grace window, the key gets its normal region:

- In intended + observed, not billed → `IO` (approved and present, not billed; informational).
- In observed only, not billed → `O` (exists, unapproved, not billed; a finding).

The grace window does not apply to:

- Keys that appear in the billed ledger (billing has arrived).
- Keys that have no observed record (no recent creation to explain; these get `I`, `B`, or `IB`).

## 8. Scope filtering

Scope filtering drops records outside the audit's scope before matching (Req 4.2).

A `ScopeFilter` declares an attribute name (`attr`) and a required value (`equals`). A record is in
scope when `record.attrs.get(attr) == equals`. Records missing the attribute are out of scope.

Dropped records are counted per ledger and reported in `RunResult.dropped` (e.g.
`{"intended": 0, "observed": 1, "billed": 1}`). Their amounts (if any) are excluded from `billed_total`
and the amount conservation check. The conservation property holds over the filtered set.

Scope filtering is applied after key normalisation but before grouping, so dropped records never enter
a region. (The attribute check is independent of the key, so the order relative to normalisation does
not affect correctness, but filtering first keeps the grouping step clean.)

## 9. Night-over-night state

The state module compares the current run's findings with the previous run of the same control and
marks each finding (Req 5.1).

### Status assignment

| Current run | Previous run | Status |
|---|---|---|
| key + region present now | not present before | `new` |
| key + region present now | present before (same key + same region) | `persisting` |
| not present now | present before | `resolved` |

A finding is identified by the pair `(key, region_code)`. If a key changes region between runs, the old
finding is `resolved` and the new one is `new`.

### First-seen and nights persisted

For `persisting` findings, `first_seen` is carried over from the previous run (Req 5.2).
`nights_persisted` is the number of midnights between `first_seen` and `run_time` (computed as the date
difference in UTC: `run_time.date() - first_seen.date()`).

For `new` findings, `first_seen = run_time` and `nights_persisted = 0`.

### State storage

State is persisted per control (keyed by `control_hash`) as a JSON file at
`runs/<control_hash>/state.json`. The file maps `"{key}:{region_code}"` to
`{"first_seen": "<iso-8601>", "region_code": "<code>"}`. The `runs/` directory is gitignored.

### Determinism

Re-running with identical inputs at the same `run_time` produces identical findings, identical status
assignments, and identical evidence hashes (Req 5.3). The state comparison depends only on the previous
state file and the current findings, both of which are deterministic given the same inputs. The
deterministic `run_id` (derived from `run_time` + `control_hash`) ensures the same storage path.

## 10. Evidence chain

### Evidence rows

The evidence pack is a directory containing `evidence.jsonl` (one JSON object per line) and
`manifest.json`.

Each evidence row is one record from one ledger. The row is serialised as canonical JSON (sorted keys,
compact separators, `Decimal` as `str()`, `datetime` as ISO-8601 UTC):

```
{"index": 0, "ledger": "intended", "row_id": "i1", "raw_key": "i-0aa1", "key": "i-0aa1",
 "attrs": {}, "amount": null, "timestamp": null,
 "prev_hash": "0000...0000", "row_hash": "abc..."}
```

### Hash chain

- `chain_seed` = 64 hex zeros (`"0" * 64`).
- Row 0: `prev_hash = chain_seed`, `row_hash = SHA-256(prev_hash + canonical_json(row_without_row_hash))`.
- Row N (N > 0): `prev_hash = row_hash of row N-1`,
  `row_hash = SHA-256(prev_hash + canonical_json(row_without_row_hash))`.
- `final_chain_hash = row_hash of the last row`.

`canonical_json` sorts keys, uses `separators=(",", ":")`, serialises `Decimal` as `str()`, and
serialises `datetime` as ISO-8601 UTC. This makes the hash deterministic (Req 5.3).

### Row ordering

Rows are ordered by ledger (intended → observed → billed), then by `row_id` within each ledger. This
order is deterministic given the same records.

### Manifest

```json
{
  "control_hash": "...",
  "ledgers": {
    "intended": {"source": "...", "hash": "...", "count": 3},
    "observed": {"source": "...", "hash": "...", "count": 3},
    "billed": {"source": "...", "hash": "...", "count": 2}
  },
  "chain_seed": "0000...0000",
  "final_chain_hash": "...",
  "row_count": 8,
  "run_id": "...",
  "run_time": "2026-11-04T02:00:00Z"
}
```

Each ledger hash is `SHA-256(canonical_json(sorted_records))` — the hash of the canonical serialisation
of that ledger's records in `row_id` order.

### Verification (Req 6.2)

`nightaudit verify <pack>`:

1. Load `manifest.json`.
2. Read `evidence.jsonl` line by line.
3. For each row: recompute `row_hash` from `prev_hash` and the row content (excluding `row_hash`).
   Compare with the stored `row_hash`. If mismatch → report the row index and stop.
4. Compare the final `row_hash` with `manifest.final_chain_hash`.
5. Recompute each ledger hash from the rows and compare with the manifest.
6. If all checks pass → confirm the pack.

### Tamper detection (Req 6.3)

Changing any byte of an evidence row changes its content, so the recomputed `row_hash` will not match
the stored value. If an attacker also updates the stored `row_hash`, the next row's `prev_hash` will
not match the tampered row's actual hash, so verification fails at the next row. If every `row_hash` is
recomputed after tampering, the `final_chain_hash` changes and will not match the manifest (unless the
manifest is also tampered, but the manifest's `control_hash` can be independently recomputed from the
control file).

## 11. Explanation guard

The explanation module produces a one- or two-sentence explanation for each finding (Req 7). It is
deterministic-first, model-last: the finding's region and evidence are already decided by code; the
model may only explain (audit rule 1).

### Prompt construction (Req 7.1)

The model receives only:

- The region code and its meaning.
- The finding's evidence fields (`row_id`, `key`, `amount`, `timestamp`, `attrs` values), each placed
  inside a quoted string and truncated to 200 characters.

No unquoted ledger text reaches the model. Tag values, names and descriptions are data, never
instructions (audit rule 4).

### Number guard (Req 7.2)

1. Collect the set of numbers that appear in the finding's evidence: every `amount` (as a Decimal
   string), every integer in every `row_id`, every numeric substring of every `attrs` value, plus the
   finding's `billed_amount`, `duplicate_counts` values, and `nights_persisted`.
2. Extract all numbers from the model's response text (integers and decimals, including currency
   amounts).
3. If any extracted number is not in the evidence set → discard the response, use the deterministic
   template, and record the rejection.

Every number in an explanation must exist in an evidence row (audit rule 2).

### Template fallback (Req 7.3)

If the model is unavailable or the call times out after 10 seconds, the deterministic template is used.
The template is a fixed string with slots filled from the finding's evidence fields (e.g.
`"{key} is active in {region_name} with a billed amount of {billed_amount}."`). The template only uses
numbers from the evidence, so it always passes the number guard.

### Injection handling (Req 7.4)

Evidence fields that contain text resembling an instruction (`"IGNORE PREVIOUS INSTRUCTIONS..."`) are
treated as data. They are placed in quoted, truncated fields in the prompt and cannot change the
region. The region is computed by the matcher from ledger membership, not from any text content.

### Testing

No network access in unit and property tests (tech rule). The Bedrock call is tested with a mock or
the template fallback. The number guard is tested with scripted model responses.

## 12. Connector interface

### Connector protocol (Req 9.1)

```
class Connector(ABC):
    @property
    @abstractmethod
    def ledger(self) -> LedgerName: ...

    @property
    @abstractmethod
    def read_only(self) -> bool: ...

    @abstractmethod
    def fetch(self) -> list[Record]: ...
```

A connector returns records for one ledger and declares whether it is read-only.

### Read-only enforcement (Req 9.2)

Before calling `fetch()`, the runner checks `connector.read_only`. If `False`, the runner refuses to
execute the connector and marks the ledger as missing. This enforces audit rule 3 (read-only).

### Built-in connectors (Req 9.3)

**CSVConnector** — reads a CSV file, maps a `key_field` column to `raw_key`, and maps other columns to
`attrs`. The `amount` column (if present) is parsed as `Decimal`. The `ts` or `timestamp` column (if
present) is parsed as `datetime`.

**JSONLConnector** — reads a JSON Lines file, maps a `key_field` to `raw_key`, and maps other fields to
`attrs`, `amount`, and `timestamp`.

Both declare `read_only = True`.

### Failure handling (Req 9.4)

If `fetch()` raises an exception, the runner catches it, creates a `LedgerSnapshot` with
`missing=True`, names the failed ledger in `missing_ledgers`, and the matcher produces no findings.

### Testing

Connectors are tested against recorded fixtures (CSV / JSONL files under `tests/fixtures/`), never
against live sources (tech rule: no network in tests).

## 13. Runner

The runner orchestrates one run end to end:

1. **Load control** — parse the YAML, validate (Req 1.1–1.2), compute the control hash (Req 1.3),
   extract `ControlConfig` via `to_config()`.
2. **Fetch ledgers** — instantiate connectors from the control file, enforce read-only (Req 9.2), call
   `fetch()` for each, handle failures (Req 9.4).
3. **Scope filter** — drop out-of-scope records (Req 4.2).
4. **Normalise** — apply each ledger's normaliser chain (Req 2.1), separate unkeyed records (Req 2.4).
5. **Grace window** — mark young unbilled keys as pending (Req 4.1).
6. **Match** — partition keys into regions, produce findings (Req 3.1–3.5).
7. **State** — load previous state, assign new/persisting/resolved, update first-seen and nights
   (Req 5.1–5.2).
8. **Evidence** — write the evidence pack with hash chain and manifest (Req 6.1).
9. **Explain** — generate explanations for each finding (Req 7).
10. **Save** — write the `RunResult` and updated state to `runs/<run_id>/`.

## 14. API

FastAPI app serving JSON endpoints and a static front end.

### Endpoints (Req 8.1)

| Method | Path | Returns |
|---|---|---|
| GET | `/api/runs` | list of run summaries (`run_id`, `run_time`, `control_hash`, `complete`, finding count, informational count) |
| GET | `/api/runs/{id}` | full `RunResult` as JSON |
| GET | `/api/runs/{id}/findings?region=` | findings filtered by region code; if `region` is omitted, all findings |
| GET | `/api/runs/{id}/evidence.zip` | the evidence pack as a zip file |

### Static files

The app mounts `skeleton/web/dist/` (Vite build output) at `/` so the UI is served from the same origin.

## 15. UI kit

The web front-end lives in `skeleton/web/` and uses TypeScript, Vite, no UI framework, and SVG for the
Venn diagram (tech rule). It is shared by both apps.

### Structure

```
skeleton/web/
  package.json
  vite.config.ts
  tsconfig.json
  index.html
  src/
    main.ts          entry point, fetches /api/runs/{id}
    venn.ts          three-circle SVG Venn diagram with key counts
    findings.ts      findings list, filterable by region
    styles.css       green-bar palette, printout rows
  fonts/             self-hosted IBM Plex Mono + IBM Plex Sans
```

### Venn diagram (Req 8.2)

A three-circle SVG Venn diagram. Each of the seven regions shows its key count. Clicking a region
filters the findings list to that region. The circles use the `moon` colour (`#C9D3FF`) for outlines
and `phosphor` (`#7CFFB2`) for matched counts.

### Findings list (Req 8.3)

Each finding is a row on alternating green-bar bands (`ink` `#0B1020` / `ink-2` `#141B33`), never
cards or bordered boxes. Each row shows:

- The monster name in words (not just the icon).
- The key.
- Nights persisted.
- Billed amount.
- The explanation.

`amber` (`#FFB347`) highlights new findings tonight; `blood` (`#FF5A6E`) highlights findings
persisting more than 3 nights. Body text is `bone` (`#EDEAE0`).

### Accessibility (Req 8.4)

- Every interactive element is keyboard-reachable with a visible `phosphor` focus ring.
- The Venn diagram has ARIA labels for each region.
- All text/background pairs meet WCAG 2.2 AA (4.5:1 for body text).
- `prefers-reduced-motion` disables the scan-line animation.
- An automated WCAG 2.2 AA scan (e.g. axe-core) passes on every screen.

Full WCAG validation requires manual testing with assistive technologies and expert accessibility
review; the automated scan is a necessary but not sufficient check.

## 16. Casebook format and scorer

### Case structure

Each case in `casebook/dev/cases.yaml` has:

| Field | Type | Notes |
|---|---|---|
| `id` | `str` | unique case identifier |
| `note` | `str` | human description |
| `now` | `datetime` | the run time for this case |
| `ledgers` | `dict` | inline ledger data (see below) |
| `control` | `dict \| omitted` | per-case overrides (`normalisers`, `scope`, `grace_hours`) |
| `people` | `bool \| omitted` | when true, use the people default control |
| `expect` | `dict` | expected results to compare against |

Each ledger in `ledgers` is either:

- A list of row dicts: `[{row: ..., key: ..., ts: ..., amount: ..., attrs: {...}}]`
- `null` — the ledger is missing (connector failed)

Row dict fields map to `Record` fields: `row` → `row_id`, `key` → `raw_key`, `ts` → `timestamp`,
`amount` → `Decimal`, `attrs` → `attrs`.

### Default controls

**Cloud default** (when `people` is absent or false):

- normalisers: intended `[strip, lower]`, observed `[strip, lower]`, billed `[arn_resource_id, strip, lower]`
- grace_hours: 24

**People default** (when `people: true`):

- normalisers: all three `[email_canonical]`
- alias_domains: `{hollowpines.org: hollowpines.com}`
- grace_hours: 24

Per-case `control` overrides merge on top of the default: each field in the override replaces the
corresponding field in the default (shallow merge, not deep). For example, a `normalisers` override
replaces the entire per-ledger normaliser dict.

### Scorer (scripts/score_casebook.py)

For each case:

1. Build a `ControlConfig` from the default (cloud or people) + per-case overrides.
2. Build `LedgerSnapshot` objects from the inline ledger data. A `null` ledger becomes a snapshot with
   `missing=True`.
3. Run the matcher with the snapshots, control config, and `now` as `run_time`.
4. Compare the `RunResult` against `expect`:
   - `regions`: dict key → code (when present)
   - `findings`: int count of finding-region keys (informational=False)
   - `informational`: int count of `IO` keys (when present)
   - `billed_total`: Decimal string
   - `billed_by_region`: dict code → Decimal string (when present); extracted from `region_summaries`
   - `billed_unkeyed`: Decimal string (when present)
   - `pending`: list of keys (when present)
   - `unkeyed`: list of `row_id`s (when present)
   - `duplicates`: dict key → {ledger: count} (when present)
   - `dropped`: dict ledger → count (when present)
   - `complete`: bool (when present)
   - `missing_ledgers`: list (when present)
5. Report pass/fail per case and per field, plus an overall summary.

### CLI

```
python scripts/score_casebook.py --set dev [--quiet]
```

`--set` selects the casebook set (`dev` or `heldout`). `--quiet` suppresses per-case detail and prints
only the summary. The heldout set is sealed (audit rule 7) and scored only by
`scripts/score_heldout.py` on tagged releases; this design does not cover that script.

## 17. Correctness properties

Each property is a hypothesis property-based test (100 examples, `derandomize` in CI), marked
`@pytest.mark.property`, with a name starting with `test_property_`.

### P1 — Partition (validates Req 3.1)

For any three ledger snapshots and any control config, every key that appears in at least one ledger
after normalisation is assigned to exactly one region, and that region is the set of ledger initials
that contain the key joined in I-O-B order. No key is assigned to more than one region and no key is
lost.

### P2 — Order independence (validates Req 3.2)

For any three ledger snapshots, the set of key→region assignments and the billed amount per region are
identical regardless of the order of records within each ledger.

### P3 — Healthy control yields zero findings (validates Req 3.3)

For any set of records where the intended, observed and billed ledgers contain the same set of
normalised keys, the matcher produces zero findings.

### P4 — Normaliser idempotence (validates Req 2.3)

For any string `s` and any registered normaliser `n`, `n(n(s, ctx), ctx) == n(s, ctx)`.

### P5 — Amount conservation including unkeyed lines (validates Req 3.5)

For any run with at least one billed record, the sum of billed amounts over all regions plus the
unkeyed billed amount equals the total billed amount, where the total is the sum of every surviving
billed record's amount.

### P6 — Grace window (validates Req 4.1)

For any observed record whose age is less than the grace window and whose key does not appear in the
billed ledger, the key is reported in `pending_keys` and no finding is produced for it.

### P7 — Evidence tamper detection (validates Req 6.3)

For any evidence pack that passes verification, modifying any single byte of any row in
`evidence.jsonl` causes `verify` to report a failure.

### P8 — Explanation guard (validates Req 7.2)

For any model response text that contains a number not present in the finding's evidence, the
explanation guard discards the response and returns the deterministic template.

### P9 — Injection does not change regions (validates Req 7.4)

For any record whose attribute value contains text that resembles an instruction, the region assigned
to that record's key is the same as when the attribute value is replaced with an equal-length string
of benign characters.

### P10 — Repeat-run determinism (validates Req 5.3)

For any control config and set of ledger inputs, running the matcher twice with identical inputs at
the same run time produces identical findings (same keys, regions, amounts) and an identical evidence
chain hash.

## 18. What the second app taught (Req 10)

The staff access app (`apps/ghosts/`) was built without write access to `skeleton/`. Its design (§10 there) lists what it had to work around. Each
item below is the skeleton's answer. A control that uses none of them hashes, runs and verifies exactly as before:
new control fields that are empty are left out of the canonical hash, and a run with no notes writes the same
evidence rows as before.

### 18.1 Run time for connectors (Req 10.1)

`Connector` gains a concrete `bind_run_time(when)` and a `run_time` property (`None` until bound). The runner calls
`bind_run_time(now)` on each connector just before `fetch()`. Nothing is abstract, so an existing connector needs no
change. `nightaudit run --at` therefore moves the date of every connector that reads `self.run_time`.

### 18.2 Run notes (Req 10.2)

A control may declare `summarisers`, each `{entry: "package.module:function", options: {...}}`, the same shape as an
enricher without `regions`. A summariser is called after enrichers and explanations as
`func(result, options[, control=ControlContext])` and returns a list of plain sentences.

- At most 12 notes per summariser and 300 characters per note; whitespace is collapsed to single spaces.
- Each note becomes `RunNote(text, numbers, source)`, where `numbers` are the numbers the guard extracts from the text.
- The run's evidence numbers are every number the explanation guard would accept for any finding plus every number in
  every in-scope record (amount, row id, raw key, key, attribute values, timestamp). IF any number of any note is
  outside that set THEN all notes of that summariser are dropped and `ledger_errors["summariser:<entry>"]` names the
  numbers. A summariser that raises is reported the same way.
- Accepted notes are appended to the evidence chain after the finding rows as
  `{"type": "note", "row_id": "note:<n>", "source", "text", "numbers"}`.
- The page prints the notes under the headline; the report prints them under its headline. `run_numbers` includes
  note numbers.

### 18.3 Control context (Req 10.3)

`ControlContext(folder, alias_domains, control_id, run_time)` is a frozen dataclass. The runner passes it as the
keyword argument `control` to an enricher or summariser whose signature has a parameter named `control`. An enricher
written as `(findings, options)` is called as before.

### 18.4 Words for lines with no key (Req 10.4)

`ui.unkeyed: {singular, plural, explanation}`. Defaults: "line with no resource id", "lines with no resource id",
"Tax, credits and support lines carry no resource id, so they are kept apart." The negative-total sentence about
credits is kept only while the default words are in use, because it describes a cloud bill.

### 18.5 Context and attribute slots (Req 10.5)

A region `template` may use `{context:<name>}` and `{attr:<name>}` beside the existing slots. They are replaced first,
with braces in values doubled, and then the template is formatted with the existing safe mapping. An absent value is
empty text. The rendered text then passes the number guard against `evidence_numbers(finding)`; if it fails, the
default template is used. A date from context is evidence, so it passes.

### 18.6 Downloads (Req 10.6)

`ui.downloads: [{label, file}]`. `file` must match `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.(csv|html|json|txt)$`: no
separator, no `..`, no hidden file, no other type. The API serves `GET /api/runs/{id}/files/{file}` only when `file`
is listed in that run's stored `ui.downloads`, matches the pattern and resolves to a regular file whose parent is the
run's folder; it is sent as an attachment with `default-src 'none'; sandbox`. `run_document(result, run_dir)` lists the
downloads that exist; the static demo copies them beside `run.json`.

### 18.7 Review decisions on the page (Req 10.7)

`nightaudit.decisions.verify_decision_chain(run_dir, result, allowed)` is the decision chain check the staff access app wrote (§7.3
of its design), moved into the skeleton: the evidence pack verifies, the first `prev_hash` is the run's final chain
hash, each row hash, index and link holds, and each key and region code is a finding of the run. `run_document`
includes `decisions: {ok, detail, rows}` when the file exists, with rows only when the chain verifies. The page shows a
decision line on the finding row and in its evidence.

### 18.8 Demos per application (Req 10.8)

Each application's `demo/build.py` exposes `build(target, runs)` and `APP_ENTRIES`. `scripts/build_demos.py` calls each
with `skeleton/web/public/demo/<app>/` and writes `apps.json` from the entries, live first. A builder removes only its
own target folder.

### P11 — Notes cite only evidence (validates Req 10.2)

For any run and any sentence, a summariser returning that sentence produces a note if and only if every number in the
sentence is one of the run's evidence numbers; otherwise the run has no note from it and names it in its errors.

### P12 — Template slots never fail and never invent a number (validates Req 10.5)

For any template text built from literal words and `{context:*}`, `{attr:*}` and existing slots, and any finding,
`resolve_template` returns a string without raising, and every number in it is in the finding's evidence.

### P13 — No download escapes the run folder (validates Req 10.6)

For any requested file name, the API returns a file only when the name is listed in the run's downloads and matches the
allow-list, and the bytes returned are those of that file in the run's folder.
