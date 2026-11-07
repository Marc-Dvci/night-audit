"""The verifier names the first failing row, so the browser verifier can be compared with it (ui-kit Req 6.2, 6.4)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from hostile import CLOUD, RUN_TIME
from nightaudit.api import run_document
from nightaudit.cli import main as cli_main
from nightaudit.evidence import CHAIN_SEED, canonical_json, verify_evidence_pack, write_evidence_pack
from nightaudit.matcher import match
from nightaudit.models import LedgerName, LedgerSnapshot, Record, RunResult

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
    assert (result.rows, result.findings, result.final_hash) == (8, 2, final)
    assert result.has_header
    assert result.detail == "verified 8 rows, 2 findings, header matches the manifest"


def test_a_changed_byte_names_its_row(tmp_path: Path) -> None:
    pack, _ = _pack(tmp_path)
    lines = _lines(pack)
    changed = lines[4].replace(b'"raw_key":"c"', b'"raw_key":"x"')
    assert changed != lines[4]
    lines[4] = changed
    _write(pack, lines)
    result = verify_evidence_pack(pack)
    assert not result.ok and result.failed_row == 4
    assert result.detail.startswith("row 4: hash mismatch")


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


# --- The header row binds the pack to its run (Req 6.5) ---------------------------------------------------------------


def _set_manifest(pack: Path, **changes: object) -> None:
    manifest = json.loads((pack / "manifest.json").read_text("utf-8"))
    manifest.update(changes)
    (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _legacy(pack: Path) -> None:
    """Rewrite a pack the way it was written before the header row: same rows, no header, a chain from the seed."""
    rows = [json.loads(line) for line in _lines(pack)][1:]
    prev, out = CHAIN_SEED, []
    for index, row in enumerate(rows):
        row.pop("row_hash")
        row.update(index=index, prev_hash=prev)
        row["row_hash"] = hashlib.sha256((prev + canonical_json({k: v for k, v in row.items() if k != "row_hash"}))
                                         .encode()).hexdigest()
        prev = row["row_hash"]
        out.append(canonical_json(row).encode())
    _write(pack, out)
    _set_manifest(pack, final_chain_hash=prev, row_count=len(rows))


def test_the_first_row_of_a_pack_is_a_header_naming_the_run(tmp_path: Path) -> None:
    pack, _ = _pack(tmp_path)
    header = json.loads(_lines(pack)[0])
    manifest = json.loads((pack / "manifest.json").read_text("utf-8"))
    assert header["type"] == "header" and header["index"] == 0
    assert {k: header[k] for k in ("run_id", "run_time", "control_hash", "row_count", "finding_count")} == {
        k: manifest[k] for k in ("run_id", "run_time", "control_hash", "row_count", "finding_count")
    }
    assert manifest["row_count"] == len(_lines(pack))


def test_changing_the_run_id_in_the_manifest_fails_verification(tmp_path: Path) -> None:
    """Regression: the manifest's run id was not hashed, so a pack could be relabelled and still verify."""
    pack, _ = _pack(tmp_path)
    _set_manifest(pack, run_id="0123456789abcdef")
    result = verify_evidence_pack(pack)
    assert not result.ok
    assert result.detail.startswith("manifest run_id differs from the chain header")


@pytest.mark.parametrize(
    "field,value",
    [("run_time", "2026-01-01T00:00:00Z"), ("control_hash", "f" * 64), ("row_count", 99), ("finding_count", 0)],
)
def test_every_header_field_must_equal_the_manifest(tmp_path: Path, field: str, value: object) -> None:
    pack, _ = _pack(tmp_path)
    _set_manifest(pack, **{field: value})
    result = verify_evidence_pack(pack)
    assert not result.ok
    assert result.detail.startswith(f"manifest {field} differs from the chain header") or field == "finding_count"


def test_a_manifest_without_a_header_field_fails(tmp_path: Path) -> None:
    pack, _ = _pack(tmp_path)
    manifest = json.loads((pack / "manifest.json").read_text("utf-8"))
    del manifest["run_id"]
    (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert not verify_evidence_pack(pack).ok


def test_editing_the_header_breaks_the_chain_at_row_zero(tmp_path: Path) -> None:
    pack, _ = _pack(tmp_path)
    lines = _lines(pack)
    lines[0] = lines[0].replace(json.loads(lines[0])["run_id"].encode(), b"0123456789abcdef")
    _write(pack, lines)
    result = verify_evidence_pack(pack)
    assert not result.ok and result.failed_row == 0


def test_a_header_row_anywhere_but_first_fails(tmp_path: Path) -> None:
    pack, _ = _pack(tmp_path)
    lines = _lines(pack)
    row = json.loads(lines[2])
    row["type"] = "header"
    row.pop("row_hash")
    row["row_hash"] = hashlib.sha256((row["prev_hash"] + canonical_json(row)).encode()).hexdigest()
    lines[2] = canonical_json(row).encode()
    _write(pack, lines)
    result = verify_evidence_pack(pack)
    assert not result.ok  # the chain breaks at the next row before the header rule is reached


def test_a_pack_from_before_the_header_row_still_verifies_and_says_it_has_none(tmp_path: Path) -> None:
    """Live nights written before the header row exist; they must not turn red."""
    pack, _ = _pack(tmp_path)
    _legacy(pack)
    result = verify_evidence_pack(pack)
    assert result.ok and not result.has_header
    assert result.detail == (
        "verified 7 rows, 2 findings; this pack carries no header row, "
        "so its run id and run time are not bound to the chain"
    )


# --- The page against the chain (Req 6.6) ---------------------------------------------------------------------------


def _run(tmp: Path) -> tuple[Path, RunResult]:
    records = {
        LedgerName.intended: [Record(ledger=LedgerName.intended, source="i", row_id="i1", raw_key="a")],
        LedgerName.observed: [Record(ledger=LedgerName.observed, source="o", row_id=f"o{n}", raw_key=k, timestamp=OLD)
                              for n, k in enumerate(["a", "b", "c"])],
        LedgerName.billed: [Record(ledger=LedgerName.billed, source="b", row_id=f"b{n}", raw_key=k,
                                   amount=Decimal(amount))
                            for n, (k, amount) in enumerate([("a", "3.10"), ("b", "41.20"), ("", "-1.05")])],
    }
    result = match([LedgerSnapshot(name=n, source=n.value, records=r) for n, r in records.items()], CLOUD, RUN_TIME)
    write_evidence_pack(result, tmp / "evidence")
    (tmp / "result.json").write_text(result.model_dump_json(), encoding="utf-8")
    return tmp / "evidence", result


def _shown(result: RunResult) -> dict[str, Any]:
    return run_document(result)


def test_the_page_built_from_the_run_agrees_with_its_chain(tmp_path: Path) -> None:
    pack, result = _run(tmp_path)
    verdict = verify_evidence_pack(pack, _shown(result))
    assert verdict.ok, verdict.detail
    assert verdict.detail.endswith("; the page matches the evidence")


def test_a_finding_that_is_not_in_the_chain_fails_verification_and_is_named(tmp_path: Path) -> None:
    """Regression: the page could show a finding the chain did not hold, beside a passing "verified"."""
    pack, result = _run(tmp_path)
    shown = _shown(result)
    fake = json.loads(json.dumps(shown["findings"][0]))
    fake["key"] = "i-0fake"
    shown["findings"].append(fake)
    verdict = verify_evidence_pack(pack, shown)
    assert not verdict.ok
    assert 'finding "i-0fake" is shown but is not in the evidence' in verdict.detail


def _edit(shown: dict[str, Any], change: str) -> None:
    first = shown["findings"][0]
    if change == "region":
        first["region_code"] = "IO" if first["region_code"] != "IO" else "O"
    elif change == "status":
        first["status"] = "persisting"
    elif change == "billed amount":
        first["billed_amount"] = "0.01"
    elif change == "hidden finding":
        del shown["findings"][0]
    elif change == "doubled finding":
        shown["findings"].append(dict(first))
    elif change == "region count":
        shown["region_summaries"]["OB"]["key_count"] += 1
    elif change == "region amount":
        shown["region_summaries"]["OB"]["billed_amount"] = "1.00"
    elif change == "billed total":
        shown["billed_total"] = "0.01"
    elif change == "unkeyed amount":
        shown["billed_unkeyed"] = "0"
    elif change == "headline total":
        shown["view"]["billed_total"] = "0.01"
    elif change == "headline count":
        shown["view"]["finding_count"] += 1
    elif change == "run id":
        shown["run_id"] = "0123456789abcdef"
    elif change == "control hash":
        shown["control_hash"] = "0" * 64
    elif change == "chain hash":
        shown["evidence_chain_hash"] = "0" * 64
    else:
        raise AssertionError(change)


CHANGES = ["region", "status", "billed amount", "hidden finding", "doubled finding", "region count", "region amount",
           "billed total", "unkeyed amount", "headline total", "headline count", "run id", "control hash",
           "chain hash"]


@pytest.mark.parametrize("change", CHANGES)
def test_a_page_that_differs_from_the_chain_fails_verification(tmp_path: Path, change: str) -> None:
    pack, result = _run(tmp_path)
    assert {f.region_code for f in result.findings} >= {"OB", "O"}  # the edits below have something to edit
    shown = _shown(result)
    _edit(shown, change)
    verdict = verify_evidence_pack(pack, shown)
    assert not verdict.ok, change
    assert verdict.detail.startswith("the page differs from the evidence: ")
    assert verdict.failed_row is None


def test_the_chain_still_verifies_without_a_page_to_compare(tmp_path: Path) -> None:
    pack, _ = _run(tmp_path)
    assert verify_evidence_pack(pack).ok


def test_the_verify_command_compares_a_result_json_beside_the_pack(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pack, result = _run(tmp_path)
    assert cli_main(["verify", str(pack)]) == 0
    assert "the page matches the evidence" in capsys.readouterr().out
    shown = json.loads((tmp_path / "result.json").read_text("utf-8"))
    shown["findings"][0]["key"] = "i-0fake"
    (tmp_path / "result.json").write_text(json.dumps(shown), encoding="utf-8")
    assert cli_main(["verify", str(pack)]) == 1
    out = capsys.readouterr().out
    assert out.startswith("FAIL  the page differs from the evidence")
    assert 'finding "i-0fake" is shown but is not in the evidence' in out


def test_the_verify_command_says_when_there_is_no_page_to_compare(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pack, _ = _pack(tmp_path)
    assert cli_main(["verify", str(pack)]) == 0
    assert "was not compared" in capsys.readouterr().out
