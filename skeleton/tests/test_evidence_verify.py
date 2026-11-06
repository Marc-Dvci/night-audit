"""The verifier names the first failing row, so the browser verifier can be compared with it (ui-kit Req 6.2, 6.4)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from hostile import CLOUD, RUN_TIME
from nightaudit.evidence import CHAIN_SEED, canonical_json, verify_evidence_pack, write_evidence_pack
from nightaudit.matcher import match
from nightaudit.models import LedgerName, LedgerSnapshot, Record

OLD = datetime(2026, 9, 1, tzinfo=UTC)


def _pack(tmp: Path) -> tuple[Path, str]:
    records = {
        LedgerName.intended: [Record(ledger=LedgerName.intended, source="i", row_id="i1", raw_key="a")],
        LedgerName.observed: [Record(ledger=LedgerName.observed, source="o", row_id=f"o{n}", raw_key=k, timestamp=OLD)
                              for n, k in enumerate(["a", "b", "c"])],
        LedgerName.billed: [Record(ledger=LedgerName.billed, source="b", row_id="b1", raw_key="a",
                                   amount=Decimal("3.10"))],
    }
    result = match([LedgerSnapshot(name=n, source=n.value, records=r) for n, r in records.items()], CLOUD, RUN_TIME)
    final = write_evidence_pack(result, tmp)
    return tmp, final


def _lines(pack: Path) -> list[bytes]:
    return (pack / "evidence.jsonl").read_bytes().split(b"\n")[:-1]


def _write(pack: Path, lines: list[bytes]) -> None:
    (pack / "evidence.jsonl").write_bytes(b"\n".join(lines) + b"\n")


def test_a_good_pack_reports_rows_findings_and_final_hash(tmp_path: Path) -> None:
    pack, final = _pack(tmp_path)
    result = verify_evidence_pack(pack)
    assert result.ok and result.failed_row is None
    assert (result.rows, result.findings, result.final_hash) == (7, 2, final)
    assert result.detail == "verified 7 rows, 2 findings"


def test_a_changed_byte_names_its_row(tmp_path: Path) -> None:
    pack, _ = _pack(tmp_path)
    lines = _lines(pack)
    changed = lines[3].replace(b'"raw_key":"c"', b'"raw_key":"x"')
    assert changed != lines[3]
    lines[3] = changed
    _write(pack, lines)
    result = verify_evidence_pack(pack)
    assert not result.ok and result.failed_row == 3
    assert result.detail.startswith("row 3: hash mismatch")


def test_a_rehashed_row_breaks_the_link_to_the_next_row(tmp_path: Path) -> None:
    pack, _ = _pack(tmp_path)
    lines = _lines(pack)
    row = json.loads(lines[2])
    row["raw_key"] = "z"
    row.pop("row_hash")
    row["row_hash"] = hashlib.sha256((row["prev_hash"] + canonical_json(row)).encode()).hexdigest()
    lines[2] = canonical_json(row).encode()
    _write(pack, lines)
    result = verify_evidence_pack(pack)
    assert result.failed_row == 3
    assert "chain broken" in result.detail


def test_a_manifest_level_failure_names_no_row(tmp_path: Path) -> None:
    pack, _ = _pack(tmp_path)
    manifest = json.loads((pack / "manifest.json").read_text("utf-8"))
    manifest["final_chain_hash"] = CHAIN_SEED
    (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = verify_evidence_pack(pack)
    assert not result.ok and result.failed_row is None
