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

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import Finding, Record, RunResult

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
    contents: list[dict[str, object]] = [
        {"type": "record", **_content_from_record(r)} for r in records
    ]
    contents.extend(_finding_row(f) for f in result.findings)
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
    }
    (pack_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    return final_chain_hash


@dataclass
class VerifyResult:
    """Outcome of verifying an evidence pack.

    ``failed_row`` is the 0-based index of the first row that fails, or ``None`` when the pack verifies or the failure
    is in the manifest as a whole. The browser verifier returns the same fields (ui-kit Req 6.4).
    """

    ok: bool
    detail: str
    failed_row: int | None = None
    rows: int = 0
    findings: int = 0
    final_hash: str | None = None


def verify_evidence_pack(pack_dir: Path) -> VerifyResult:
    """Recompute the chain and manifest; report the first failure or confirm.

    For each row the stored ``row_hash`` is recomputed from its content and
    compared, the ``prev_hash`` chain is checked against the previous row's
    recomputed hash, the final hash is compared with the manifest, and each
    ledger hash is recomputed from the rows (Req 6.2-6.3).
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
                f"row {i}: hash mismatch (stored {stored_hash[:12]}, "
                f"computed {recomputed[:12]})",
                failed_row=i,
            )
        expected_prev = chain_seed if i == 0 else prev_recomputed
        if stored_prev != expected_prev:
            return VerifyResult(
                False, f"row {i}: chain broken (prev_hash does not link to previous row)", failed_row=i
            )
        prev_recomputed = recomputed

    if prev_recomputed != str(manifest_raw.get("final_chain_hash", "")):
        return VerifyResult(
            False,
            f"final chain hash mismatch (manifest "
            f"{str(manifest_raw.get('final_chain_hash', ''))[:12]}, "
            f"computed {prev_recomputed[:12]})",
        )

    # Recompute each ledger hash from the rows.
    ledgers_manifest_raw = manifest_raw.get("ledgers", {})
    if not isinstance(ledgers_manifest_raw, dict):
        return VerifyResult(False, "manifest 'ledgers' is not an object")
    by_ledger: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        if row.get("type") != "record":
            continue
        ledger = str(row.get("ledger", ""))
        by_ledger.setdefault(ledger, []).append(row)

    for ledger_name, entry in ledgers_manifest_raw.items():
        if not isinstance(entry, dict):
            return VerifyResult(False, f"ledger '{ledger_name}' entry is not an object")
        ledger_rows = sorted(
            by_ledger.get(ledger_name, []), key=lambda r: str(r.get("row_id", ""))
        )
        contents = [_content_from_row(r) for r in ledger_rows]
        recomputed_hash = _sha(_canonical_json(contents))
        expected_hash = str(entry.get("hash", ""))
        expected_count = int(entry.get("count", -1))
        if recomputed_hash != expected_hash:
            return VerifyResult(False, f"ledger '{ledger_name}': hash mismatch")
        if expected_count != len(ledger_rows):
            return VerifyResult(
                False,
                f"ledger '{ledger_name}': count mismatch "
                f"({expected_count} vs {len(ledger_rows)})",
            )

    finding_rows = sum(1 for row in rows if row.get("type") == "finding")
    if "finding_count" in manifest_raw and int(manifest_raw["finding_count"]) != finding_rows:
        return VerifyResult(False, "finding count differs from the manifest")

    return VerifyResult(
        True,
        f"verified {len(rows)} rows, {finding_rows} findings",
        rows=len(rows),
        findings=finding_rows,
        final_hash=prev_recomputed,
    )
