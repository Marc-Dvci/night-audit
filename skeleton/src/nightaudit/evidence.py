"""Evidence pack: JSONL hash chain, manifest, and verification (Req 6.1-6.3).

The evidence pack is a directory containing ``evidence.jsonl`` (one JSON object
per line, each row carrying the SHA-256 of the previous row) and
``manifest.json`` (control hash, per-ledger hash + count, chain seed and final
chain hash).

Hashing uses canonical JSON: sorted keys, compact separators, ``Decimal`` as
``str()``, ``datetime`` as ISO-8601 UTC.  Rows are ordered by ledger
(intended -> observed -> billed) then by ``row_id``, so the chain is
deterministic given the same records (Req 5.3).
"""

from __future__ import annotations

import decimal
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .explain import extract_numbers, number_literals
from .models import Finding, Record, RunResult
from .report import HEADLINE_ORDER, headline_money_text, money_text
from .textfile import write_text_exact

CHAIN_SEED = "0" * 64

#: Fields that make up a record's content (used for the ledger hash and rows).
_CONTENT_FIELDS: tuple[str, ...] = (
    "ledger",
    "row_id",
    "raw_key",
    "key",
    "attrs",
    "amount",
    "timestamp",
)

_LEDGER_ORDER: dict[str, int] = {
    "intended": 0,
    "observed": 1,
    "billed": 2,
}


def _to_utc_iso(dt: datetime | None) -> str | None:
    """Serialise a datetime as ISO-8601 UTC (``Z`` suffix); ``None`` stays ``None``."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.isoformat() + "Z"


def _canonical_json(obj: object) -> str:
    """Canonical JSON: sorted keys, compact separators, non-ASCII escaped as ``\\uXXXX``."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


#: Public name: the browser verifier (``skeleton/web/src/canonical.ts``) reproduces exactly this serialisation.
canonical_json = _canonical_json


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _content_from_record(record: Record) -> dict[str, object]:
    """Build the content dict for a record (Decimal->str, datetime->iso)."""
    return {
        "ledger": record.ledger.value,
        "row_id": record.row_id,
        "raw_key": record.raw_key,
        "key": record.key,
        "attrs": dict(record.attrs),
        "amount": str(record.amount) if record.amount is not None else None,
        "timestamp": _to_utc_iso(record.timestamp),
    }


def _content_from_row(row: dict[str, object]) -> dict[str, object]:
    """Build the content dict from a parsed evidence row."""
    result: dict[str, object] = {}
    for field in _CONTENT_FIELDS:
        result[field] = row.get(field)
    return result


def _finding_row(finding: Finding) -> dict[str, object]:
    """The decided part of a finding: what code concluded and from which rows (no prose)."""
    return {
        "type": "finding",
        "key": finding.key,
        "region_code": finding.region_code,
        "name": finding.name,
        "status": finding.status,
        "first_seen": _to_utc_iso(finding.first_seen),
        "billed_amount": str(finding.billed_amount),
        "evidence_rows": [f"{r.ledger.value}:{r.row_id}" for r in finding.records],
        "context": dict(sorted(finding.context.items())),
    }


#: The manifest fields that the header row repeats. A verifier requires each to be equal in both.
HEADER_FIELDS: tuple[str, ...] = ("run_id", "run_time", "control_hash", "row_count", "finding_count", "complete")

#: The three ledgers. A night that could not read one of them writes no record row for it.
_LEDGERS: tuple[str, ...] = ("intended", "observed", "billed")


def _header_row(result: RunResult, row_count: int) -> dict[str, object]:
    """The first chain row: which run this pack is. ``row_count`` counts every row of the chain, this one included.

    ``complete`` says whether every ledger was read. A page takes its billed figures from it (Req 9.4), so it is hashed
    with the rest of the chain rather than read from the page.
    """
    return {
        "type": "header",
        "run_id": result.run_id,
        "run_time": _to_utc_iso(result.run_time),
        "control_hash": result.control_hash,
        "row_count": row_count,
        "finding_count": len(result.findings),
        "complete": result.complete,
    }


def _ordered_records(result: RunResult) -> list[Record]:
    """All in-scope records ordered by ledger then ``row_id``."""
    records: list[Record] = []
    for snapshot in result.snapshots:
        records.extend(snapshot.records)
    records.sort(key=lambda r: (_LEDGER_ORDER.get(r.ledger.value, 99), r.row_id))
    return records


def _ledger_hash(records: list[Record]) -> tuple[str, int]:
    """SHA-256 of the canonical serialisation of a ledger's records (row_id order)."""
    ordered = sorted(records, key=lambda r: r.row_id)
    contents = [_content_from_record(r) for r in ordered]
    return _sha(_canonical_json(contents)), len(ordered)


def write_evidence_pack(result: RunResult, pack_dir: Path) -> str:
    """Write ``evidence.jsonl`` and ``manifest.json`` into *pack_dir*.

    Returns the final chain hash and sets ``result.evidence_chain_hash``.
    """
    pack_dir.mkdir(parents=True, exist_ok=True)

    records = _ordered_records(result)

    # Build content dicts (ledger order, row_id order), then one row per finding, then the chain.
    contents: list[dict[str, object]] = [{"type": "record", **_content_from_record(r)} for r in records]
    contents.extend(_finding_row(f) for f in result.findings)
    # Notes come last, so a run without notes writes the same rows as before Req 10.2.
    contents.extend(
        {"type": "note", "row_id": f"note:{n}", "source": note.source, "text": note.text, "numbers": list(note.numbers)}
        for n, note in enumerate(result.notes, start=1)
    )
    # The header is the first row of the chain, so the run it names is hashed with everything else. The manifest repeats
    # these values and a verifier requires the two to agree (Req 6.5).
    contents.insert(0, _header_row(result, row_count=len(contents) + 1))
    rows: list[dict[str, object]] = []
    prev_hash = CHAIN_SEED
    for index, content in enumerate(contents):
        row: dict[str, object] = {
            "index": index,
            "prev_hash": prev_hash,
            **content,
        }
        row_hash = _sha(prev_hash + _canonical_json(row))
        row["row_hash"] = row_hash
        rows.append(row)
        prev_hash = row_hash

    final_chain_hash = prev_hash if rows else CHAIN_SEED
    result.evidence_chain_hash = final_chain_hash

    evidence_path = pack_dir / "evidence.jsonl"
    with evidence_path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(_canonical_json(row))
            f.write("\n")

    # Per-ledger hashes and counts, in ledger order.
    ledgers_manifest: dict[str, dict[str, object]] = {}
    for snapshot in sorted(result.snapshots, key=lambda s: _LEDGER_ORDER.get(s.name.value, 99)):
        if snapshot.missing:
            ledgers_manifest[snapshot.name.value] = {
                "source": snapshot.source,
                "hash": _sha(_canonical_json([])),
                "count": 0,
            }
            continue
        h, count = _ledger_hash(snapshot.records)
        ledgers_manifest[snapshot.name.value] = {
            "source": snapshot.source,
            "hash": h,
            "count": count,
        }

    manifest: dict[str, object] = {
        "control_hash": result.control_hash,
        "ledgers": ledgers_manifest,
        "chain_seed": CHAIN_SEED,
        "final_chain_hash": final_chain_hash,
        "row_count": len(rows),
        "finding_count": len(result.findings),
        "run_id": result.run_id,
        "run_time": _to_utc_iso(result.run_time),
        "complete": result.complete,
    }
    write_text_exact(pack_dir / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True))

    return final_chain_hash


@dataclass
class VerifyResult:
    """Outcome of verifying an evidence pack.

    ``failed_row`` is the 0-based index of the first row that fails, or ``None`` when the pack verifies or the failure
    is in the manifest as a whole. ``has_header`` is true when the chain starts with a header row that names the run;
    a pack written before that row existed verifies without it. The browser verifier returns the same fields (ui-kit
    Req 6.4).
    """

    ok: bool
    detail: str
    failed_row: int | None = None
    rows: int = 0
    findings: int = 0
    final_hash: str | None = None
    has_header: bool = False


# --- What the page displays, against what the chain holds (Req 6.6) ---------------------------------------------------

#: A decimal as the API sends it. The browser verifier uses the same pattern, so both accept the same strings.
_DECIMAL_TEXT = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_EXACT = decimal.Context(
    prec=decimal.MAX_PREC,
    Emax=decimal.MAX_EMAX,
    Emin=decimal.MIN_EMIN,
    traps=[decimal.InvalidOperation, decimal.Inexact, decimal.Overflow],
)
#: Regions whose findings are informational: the page counts them apart from the headline.
_INFORMATIONAL = frozenset({"IO"})
_MAX_PROBLEMS = 8


def _decimal(value: object) -> Decimal | None:
    """A JSON value as an exact decimal, or ``None`` when it is not a plain decimal number."""
    if isinstance(value, bool) or not isinstance(value, str | int | float | Decimal):
        return None
    text = str(value)
    return Decimal(text) if _DECIMAL_TEXT.fullmatch(text) else None


def _amount_text(value: object) -> str:
    number = _decimal(value)
    return money_text(number) if number is not None else canonical_json(value)


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _same_instant(a: object, b: object) -> bool:
    if canonical_json(a) == canonical_json(b):
        return True
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    try:
        left, right = datetime.fromisoformat(a), datetime.fromisoformat(b)
    except ValueError:
        return False
    if left.tzinfo is None or right.tzinfo is None:
        return False
    return left == right


def compare_displayed(
    displayed: dict[str, Any], manifest: dict[str, Any], rows: list[dict[str, object]], final_hash: str
) -> list[str]:
    """Every difference between what a page shows of a run and what the verified chain holds.

    *displayed* is the run as the page reads it (``result.json``, or ``run.json`` with its ``view``). It is compared
    with the chain's own rows: each finding's key, region, status and billed amount, the figures the headline is built
    from (the count and billed amount of each region), the billed total and the unkeyed amount, the run's identity and
    the final chain hash. The result is a list of plain sentences, empty when they agree. The browser verifier writes
    the same sentences for the same input.
    """
    q = canonical_json
    problems: list[str] = []

    for field in ("run_id", "run_time", "control_hash"):
        if field in manifest:
            shown = displayed.get(field)
            same = _same_instant(shown, manifest[field]) if field == "run_time" else q(shown) == q(manifest[field])
            if not same:
                problems.append(f"{field}: the page shows {q(shown)}, the evidence has {q(manifest[field])}")
    shown_hash = displayed.get("evidence_chain_hash")
    if q(shown_hash) != q(final_hash):
        problems.append(f"evidence chain hash: the page shows {q(shown_hash)}, the chain ends {q(final_hash)}")

    chain_findings = [r for r in rows if r.get("type") == "finding"]
    chain_by_key: dict[str, dict[str, object]] = {}
    for row in chain_findings:
        chain_by_key.setdefault(str(row.get("key")), row)
    shown_list = displayed.get("findings")
    shown_findings = [f for f in shown_list if isinstance(f, dict)] if isinstance(shown_list, list) else []
    if not isinstance(shown_list, list) or len(shown_findings) != len(shown_list):
        problems.append("findings: the page does not hold a list of findings")
    seen: set[str] = set()
    for finding in shown_findings:
        key = finding.get("key")
        name = q(key)
        if not isinstance(key, str) or key not in chain_by_key:
            problems.append(f"finding {name} is shown but is not in the evidence")
            continue
        if key in seen:
            problems.append(f"finding {name} is shown more than once")
            continue
        seen.add(key)
        row = chain_by_key[key]
        if q(finding.get("region_code")) != q(row.get("region_code")):
            problems.append(
                f"finding {name}: the page shows region {q(finding.get('region_code'))}, "
                f"the evidence has {q(row.get('region_code'))}"
            )
        if q(finding.get("status")) != q(row.get("status")):
            problems.append(
                f"finding {name}: the page shows status {q(finding.get('status'))}, "
                f"the evidence has {q(row.get('status'))}"
            )
        shown_amount, chain_amount = _decimal(finding.get("billed_amount")), _decimal(row.get("billed_amount"))
        if shown_amount is None or chain_amount is None or shown_amount != chain_amount:
            problems.append(
                f"finding {name}: the page shows billed amount {_amount_text(finding.get('billed_amount'))}, "
                f"the evidence has {_amount_text(row.get('billed_amount'))}"
            )
    shown_keys = {f.get("key") for f in shown_findings}
    for key in chain_by_key:
        if key not in shown_keys:
            problems.append(f"finding {q(key)} is in the evidence but is not shown")

    counts: dict[str, int] = {}
    amounts: dict[str, Decimal] = {}
    for row in chain_findings:
        code = str(row.get("region_code"))
        counts[code] = counts.get(code, 0) + 1
        amounts[code] = _EXACT.add(amounts.get(code, Decimal(0)), _decimal(row.get("billed_amount")) or Decimal(0))
    summaries = displayed.get("region_summaries")
    shown_regions = summaries if isinstance(summaries, dict) else {}
    for code in sorted({*shown_regions, *counts} - {"IOB"}):
        entry = shown_regions.get(code)
        entry = entry if isinstance(entry, dict) else {}
        shown_count = entry.get("key_count", 0)
        if _count(shown_count) != counts.get(code, 0):
            problems.append(f"region {code}: the page counts {q(shown_count)}, the evidence has {counts.get(code, 0)}")
        shown_amount = _decimal(entry.get("billed_amount", "0"))
        chain_amount = amounts.get(code, Decimal(0))
        if shown_amount is None or shown_amount != chain_amount:
            problems.append(
                f"region {code}: the page bills {_amount_text(entry.get('billed_amount', '0'))}, "
                f"the evidence has {money_text(chain_amount)}"
            )

    billed = [r for r in rows if r.get("type") == "record" and r.get("ledger") == "billed"]
    total, unkeyed = Decimal(0), Decimal(0)
    for row in billed:
        amount = _decimal(row.get("amount"))
        if amount is not None:
            total = _EXACT.add(total, amount)
            if row.get("key") is None:
                unkeyed = _EXACT.add(unkeyed, amount)
    # Completeness comes from the chain. A pack that does not record it is taken as complete: nothing in it can prove
    # that a ledger went unread, and an empty ledger is what a complete night with nothing in that ledger writes too.
    shown_complete, chain_complete = displayed.get("complete"), chain_completeness(rows)
    if chain_complete is not None:
        if q(shown_complete) != q(chain_complete):
            problems.append(f"complete: the page shows {q(shown_complete)}, the evidence has {q(chain_complete)}")
        incomplete = chain_complete is False
    else:
        incomplete = False
        if shown_complete is not True:
            problems.append(
                f"complete: the page shows {q(shown_complete)}, the evidence records no completeness, so the night is "
                "taken as complete"
            )
    if incomplete:
        # An incomplete run matches nothing and states no amount (Req 9.4): the page must show zero, whatever the
        # ledgers that were read hold.
        total, unkeyed = Decimal(0), Decimal(0)
    figures: list[tuple[str, object, Decimal]] = [
        ("billed total", displayed.get("billed_total"), total),
        ("unkeyed billed amount", displayed.get("billed_unkeyed"), unkeyed),
    ]
    view = displayed.get("view")
    if isinstance(view, dict):
        figures += [
            ("headline billed total", view.get("billed_total"), total),
            ("headline unkeyed amount", view.get("unkeyed_total"), unkeyed),
            ("headline keyed amount", view.get("keyed_total"), _EXACT.subtract(total, unkeyed)),
        ]
    for label, shown, expected in figures:
        number = _decimal(shown)
        if number is None or number != expected:
            problems.append(f"{label}: the page shows {_amount_text(shown)}, the evidence has {money_text(expected)}")
    if isinstance(view, dict):
        headline_findings = [r for r in chain_findings if r.get("region_code") not in _INFORMATIONAL]
        for label, field, expected_count in (
            ("headline finding count", "finding_count", len(headline_findings)),
            ("headline new count", "new_count", sum(1 for r in headline_findings if r.get("status") == "new")),
            (
                "headline persisting count",
                "persisting_count",
                sum(1 for r in headline_findings if r.get("status") == "persisting"),
            ),
        ):
            if _count(view.get(field)) != expected_count:
                problems.append(f"{label}: the page shows {q(view.get(field))}, the evidence has {expected_count}")
        problems.extend(_headline_problems(view, counts, amounts))
    return problems


#: An amount as the page prints it in prose: ``$0.7172``, ``âˆ’$3.10``, ``$1,234.50``.
_MONEY_TOKEN = re.compile("[\u2212-]?\\$[0-9][0-9,]*(?:\\.[0-9]+)?")


def _headline_problems(view: dict[str, Any], counts: dict[str, int], amounts: dict[str, Decimal]) -> list[str]:
    """Each number the headline text prints must be one of its own: a headline region's count, or its amount in the
    chain written exactly or rounded the one way the headline rounds (``headline_money_text``).

    Two checks. Every amount written as money must be one of those amounts as text. Every numeric literal, found by the
    explanation guard's own scanner (``explain.extract_numbers``), must be one of the numbers in those counts and texts,
    so ``0.7173 dollars`` is refused as surely as ``$0.7173``.
    """
    allowed: set[str] = set()
    allowed_numbers: set[Decimal] = set()
    for code in HEADLINE_ORDER:
        if code in counts:
            allowed_numbers.add(Decimal(counts[code]))
        if code in amounts:
            texts_of_amount = (money_text(amounts[code]), headline_money_text(amounts[code]))
            allowed.update(texts_of_amount)
            for text in texts_of_amount:
                allowed_numbers.update(extract_numbers(text))
    sentences = view.get("headline_sentences")
    texts = [s for s in sentences if isinstance(s, str)] if isinstance(sentences, list) else []
    if isinstance(view.get("headline"), str):
        texts.append(view["headline"])
    problems: list[str] = []
    if any(ch.isdecimal() and not "0" <= ch <= "9" for text in texts for ch in text):
        problems.append("headline: the page shows a digit that is not 0 to 9")
    tokens = dict.fromkeys(token for text in texts for token in _MONEY_TOKEN.findall(text))
    problems += [
        f"headline: the page shows {t}, which is no region's amount in the evidence" for t in tokens if t not in allowed
    ]
    refused: list[str] = []
    for literal in (lit for text in texts for lit in number_literals(text)):
        if Decimal(literal) not in allowed_numbers and literal not in refused:
            refused.append(literal)
    problems += [
        f"headline: the page shows the number {n}, which is not one of the headline's counts or amounts"
        for n in refused
    ]
    return problems


def _display_failure(problems: list[str]) -> str:
    shown = "; ".join(problems[:_MAX_PROBLEMS])
    more = len(problems) - _MAX_PROBLEMS
    return f"the page differs from the evidence: {shown}" + (f"; and {more} more" if more > 0 else "")


def _header_failure(rows: list[dict[str, object]], manifest: dict[str, Any], finding_rows: int) -> VerifyResult | None:
    """A failure of the header row, or ``None`` when there is none or it agrees with the manifest and the chain."""
    for i, row in enumerate(rows):
        if row.get("type") == "header" and i != 0:
            return VerifyResult(False, f"row {i}: a header row must be the first row", failed_row=i)
    if not rows or rows[0].get("type") != "header":
        return None
    header = rows[0]
    for field in HEADER_FIELDS:
        in_manifest, in_header = canonical_json(manifest.get(field)), canonical_json(header.get(field))
        if in_manifest != in_header:
            return VerifyResult(
                False, f"manifest {field} differs from the chain header (manifest {in_manifest}, header {in_header})"
            )
    if canonical_json(header.get("row_count")) != canonical_json(len(rows)):
        return VerifyResult(
            False, f"chain header says {canonical_json(header.get('row_count'))} rows, the chain has {len(rows)}"
        )
    if canonical_json(header.get("finding_count")) != canonical_json(finding_rows):
        return VerifyResult(
            False,
            f"chain header says {canonical_json(header.get('finding_count'))} findings, the chain has {finding_rows}",
        )
    if "complete" in header and not isinstance(header["complete"], bool):
        return VerifyResult(
            False,
            f"chain header says the night was complete {canonical_json(header['complete'])}, which is not true or false",
        )
    return None


def chain_completeness(rows: list[dict[str, object]]) -> bool | None:
    """Whether the night was complete, as the chain's header row records it; ``None`` when the chain does not say.

    Packs written before the header carried ``complete`` do not say, and are taken as complete. The manifest is not read
    here: in a pack without a header row, nothing binds the manifest to the chain.
    """
    if rows and rows[0].get("type") == "header":
        value = rows[0].get("complete")
        if isinstance(value, bool):
            return value
    return None


def verify_evidence_pack(pack_dir: Path, displayed: dict[str, Any] | None = None) -> VerifyResult:
    """Recompute the chain and manifest; report the first failure or confirm.

    For each row the stored ``row_hash`` is recomputed from its content and
    compared, the ``prev_hash`` chain is checked against the previous row's
    recomputed hash, the final hash is compared with the manifest, and each
    ledger hash is recomputed from the rows (Req 6.2-6.3). A header row, when the chain has one, must equal the
    manifest (Req 6.5). When *displayed* is given (the run as a page shows it), it must also agree with the chain
    (Req 6.6).
    """
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.exists():
        return VerifyResult(False, "manifest.json not found")
    manifest_raw: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))

    evidence_path = pack_dir / "evidence.jsonl"
    if not evidence_path.exists():
        return VerifyResult(False, "evidence.jsonl not found")

    rows: list[dict[str, object]] = []
    raw = evidence_path.read_bytes()
    lines = raw.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    for i, line_bytes in enumerate(lines):
        try:
            row = json.loads(line_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return VerifyResult(False, f"row {i}: not valid JSON", failed_row=i)
        if not isinstance(row, dict):
            return VerifyResult(False, f"row {i}: not a JSON object", failed_row=i)
        # Byte-exact: the stored line must be the canonical serialisation of its content (Req 6.3).
        if _canonical_json(row).encode("utf-8") != line_bytes:
            return VerifyResult(False, f"row {i}: bytes differ from the canonical form", failed_row=i)
        rows.append(row)

    chain_seed = str(manifest_raw.get("chain_seed", CHAIN_SEED))
    prev_recomputed = chain_seed

    for i, row in enumerate(rows):
        row_without_hash = {k: v for k, v in row.items() if k != "row_hash"}
        stored_prev = str(row.get("prev_hash", ""))
        recomputed = _sha(stored_prev + _canonical_json(row_without_hash))
        stored_hash = str(row.get("row_hash", ""))
        if recomputed != stored_hash:
            return VerifyResult(
                False,
                f"row {i}: hash mismatch (stored {stored_hash[:12]}, computed {recomputed[:12]})",
                failed_row=i,
            )
        expected_prev = chain_seed if i == 0 else prev_recomputed
        if stored_prev != expected_prev:
            return VerifyResult(False, f"row {i}: chain broken (prev_hash does not link to previous row)", failed_row=i)
        prev_recomputed = recomputed

    if prev_recomputed != str(manifest_raw.get("final_chain_hash", "")):
        return VerifyResult(
            False,
            f"final chain hash mismatch (manifest "
            f"{str(manifest_raw.get('final_chain_hash', ''))[:12]}, "
            f"computed {prev_recomputed[:12]})",
        )

    # Recompute each ledger hash from the rows. The manifest names exactly the three ledgers, and every record row
    # belongs to one of them: a verifier that looped only over the manifest's ledgers would pass a pack without one.
    for i, row in enumerate(rows):
        if row.get("type") == "record" and row.get("ledger") not in _LEDGERS:
            return VerifyResult(
                False,
                f"row {i}: record of ledger {canonical_json(row.get('ledger'))}, which is not intended, observed or "
                "billed",
                failed_row=i,
            )
    ledgers_manifest_raw = manifest_raw.get("ledgers", {})
    if not isinstance(ledgers_manifest_raw, dict):
        return VerifyResult(False, "manifest 'ledgers' is not an object")
    if set(ledgers_manifest_raw) != set(_LEDGERS):
        named = ", ".join(sorted(ledgers_manifest_raw)) or "none"
        return VerifyResult(False, f"manifest ledgers are billed, intended, observed: it names {named}")
    by_ledger: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        if row.get("type") != "record":
            continue
        ledger = str(row.get("ledger", ""))
        by_ledger.setdefault(ledger, []).append(row)

    for ledger_name, entry in ledgers_manifest_raw.items():
        if not isinstance(entry, dict):
            return VerifyResult(False, f"ledger '{ledger_name}' entry is not an object")
        ledger_rows = sorted(by_ledger.get(ledger_name, []), key=lambda r: str(r.get("row_id", "")))
        contents = [_content_from_row(r) for r in ledger_rows]
        recomputed_hash = _sha(_canonical_json(contents))
        expected_hash = str(entry.get("hash", ""))
        expected_count = int(entry.get("count", -1))
        if recomputed_hash != expected_hash:
            return VerifyResult(False, f"ledger '{ledger_name}': hash mismatch")
        if expected_count != len(ledger_rows):
            return VerifyResult(
                False,
                f"ledger '{ledger_name}': count mismatch ({expected_count} vs {len(ledger_rows)})",
            )

    finding_rows = sum(1 for row in rows if row.get("type") == "finding")
    if "finding_count" in manifest_raw and int(manifest_raw["finding_count"]) != finding_rows:
        return VerifyResult(False, "finding count differs from the manifest")

    header_failure = _header_failure(rows, manifest_raw, finding_rows)
    if header_failure is not None:
        return header_failure
    has_header = bool(rows) and rows[0].get("type") == "header"
    detail = f"verified {len(rows)} rows, {finding_rows} findings"
    detail += (
        ", header matches the manifest"
        if has_header
        else "; this pack carries no header row, so its run id and run time are not bound to the chain"
    )
    if displayed is not None:
        problems = compare_displayed(displayed, manifest_raw, rows, prev_recomputed)
        if problems:
            return VerifyResult(False, _display_failure(problems))
        detail += "; the page matches the evidence"

    return VerifyResult(
        True,
        detail,
        rows=len(rows),
        findings=finding_rows,
        final_hash=prev_recomputed,
        has_header=has_header,
    )
