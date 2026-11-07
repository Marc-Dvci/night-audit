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
        LedgerName.observed: [
            Record(ledger=LedgerName.observed, source="o", row_id=f"o{n}", raw_key=k, timestamp=OLD)
            for n, k in enumerate(["a", "b", "c"])
        ],
        LedgerName.billed: [
            Record(ledger=LedgerName.billed, source="b", row_id="b1", raw_key="a", amount=Decimal("3.10"))
        ],
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
        row["row_hash"] = hashlib.sha256(
            (prev + canonical_json({k: v for k, v in row.items() if k != "row_hash"})).encode()
        ).hexdigest()
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
    [
        ("run_time", "2026-01-01T00:00:00Z"),
        ("control_hash", "f" * 64),
        ("row_count", 99),
        ("finding_count", 0),
        ("complete", False),
    ],
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
        LedgerName.observed: [
            Record(ledger=LedgerName.observed, source="o", row_id=f"o{n}", raw_key=k, timestamp=OLD)
            for n, k in enumerate(["a", "b", "c"])
        ],
        LedgerName.billed: [
            Record(ledger=LedgerName.billed, source="b", row_id=f"b{n}", raw_key=k, amount=Decimal(amount))
            for n, (k, amount) in enumerate([("a", "3.10"), ("b", "41.20"), ("", "-1.05")])
        ],
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


CHANGES = [
    "region",
    "status",
    "billed amount",
    "hidden finding",
    "doubled finding",
    "region count",
    "region amount",
    "billed total",
    "unkeyed amount",
    "headline total",
    "headline count",
    "run id",
    "control hash",
    "chain hash",
]


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


@pytest.mark.integration
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


@pytest.mark.integration
def test_the_verify_command_says_when_there_is_no_page_to_compare(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pack, _ = _pack(tmp_path)
    assert cli_main(["verify", str(pack)]) == 0
    assert "was not compared" in capsys.readouterr().out


# --- Completeness is bound to the chain (Req 6.5, 9.4) ----------------------------------------------------------------


def _incomplete_run(tmp: Path) -> tuple[Path, RunResult]:
    """A night whose observed ledger could not be read, while the billed ledger was: its chain holds billed rows."""
    snapshots = [
        LedgerSnapshot(
            name=LedgerName.intended,
            source="i",
            records=[Record(ledger=LedgerName.intended, source="i", row_id="i1", raw_key="a")],
        ),
        LedgerSnapshot(name=LedgerName.observed, source="o", missing=True),
        LedgerSnapshot(
            name=LedgerName.billed,
            source="b",
            records=[Record(ledger=LedgerName.billed, source="b", row_id="b1", raw_key="a", amount=Decimal("41.20"))],
        ),
    ]
    result = match(snapshots, CLOUD, RUN_TIME)
    assert not result.complete and not result.findings
    write_evidence_pack(result, tmp / "evidence")
    return tmp / "evidence", result


def _rechain(pack: Path, change: Any) -> None:
    """Apply *change* to every parsed row, then rehash the chain from the seed and update the manifest's final hash."""
    rows = [json.loads(line) for line in _lines(pack)]
    prev, out = CHAIN_SEED, []
    for row in rows:
        change(row)
        row.pop("row_hash")
        row["prev_hash"] = prev
        row["row_hash"] = hashlib.sha256((prev + canonical_json(row)).encode()).hexdigest()
        prev = row["row_hash"]
        out.append(canonical_json(row).encode())
    _write(pack, out)
    _set_manifest(pack, final_chain_hash=prev)


def _as_written_before_completeness(pack: Path) -> None:
    """Rewrite a pack the way it was written before the chain recorded completeness: no ``complete`` anywhere."""
    _rechain(pack, lambda row: row.pop("complete", None))
    manifest = json.loads((pack / "manifest.json").read_text("utf-8"))
    del manifest["complete"]
    (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _hide_the_bill(shown: dict[str, Any]) -> None:
    """The page edited to say the night was incomplete and billed nothing, its findings still on it."""
    shown["complete"] = False
    shown["billed_total"] = shown["billed_unkeyed"] = "0"
    for field in ("billed_total", "unkeyed_total", "keyed_total"):
        shown["view"][field] = "0"


def test_the_header_and_the_manifest_record_whether_the_night_was_complete(tmp_path: Path) -> None:
    complete, _ = _run(tmp_path / "complete")
    incomplete, _ = _incomplete_run(tmp_path / "incomplete")
    for pack, expected in ((complete, True), (incomplete, False)):
        header = json.loads(_lines(pack)[0])
        manifest = json.loads((pack / "manifest.json").read_text("utf-8"))
        assert header["complete"] is expected and manifest["complete"] is expected


def test_regression_a_page_that_says_incomplete_to_hide_the_bill_fails_verification(tmp_path: Path) -> None:
    """Bug: the verifier took completeness from the page. A complete night's page edited to ``complete: false`` and a
    billed total of 0, its findings still shown, verified while it hid $43.25 of bill."""
    pack, result = _run(tmp_path)
    shown = _shown(result)
    _hide_the_bill(shown)
    verdict = verify_evidence_pack(pack, shown)
    assert not verdict.ok
    assert "complete: the page shows false, the evidence has true" in verdict.detail


def test_a_page_that_says_complete_beside_an_incomplete_chain_fails_verification(tmp_path: Path) -> None:
    pack, result = _incomplete_run(tmp_path)
    shown = _shown(result)
    assert verify_evidence_pack(pack, shown).ok
    shown["complete"] = True
    shown["billed_total"] = "41.20"
    verdict = verify_evidence_pack(pack, shown)
    assert not verdict.ok
    assert "complete: the page shows true, the evidence has false" in verdict.detail


def test_changing_the_completeness_in_the_manifest_fails_verification(tmp_path: Path) -> None:
    pack, _ = _run(tmp_path)
    _set_manifest(pack, complete=False)
    verdict = verify_evidence_pack(pack)
    assert not verdict.ok
    assert verdict.detail.startswith("manifest complete differs from the chain header")


def test_a_completeness_that_is_not_true_or_false_fails_verification(tmp_path: Path) -> None:
    pack, _ = _run(tmp_path)
    _rechain(pack, lambda row: row.update(complete="no") if row["type"] == "header" else None)
    _set_manifest(pack, complete="no")
    verdict = verify_evidence_pack(pack)
    assert not verdict.ok
    assert verdict.detail == 'chain header says the night was complete "no", which is not true or false'


TAKEN_AS_COMPLETE = (
    "complete: the page shows false, the evidence records no completeness, so the night is taken as complete"
)


def _old_shape(pack: Path, header: bool) -> None:
    _as_written_before_completeness(pack)
    if not header:
        _legacy(pack)


@pytest.mark.parametrize("header", [True, False], ids=["with-header", "before-the-header"])
def test_a_complete_pack_written_before_completeness_was_recorded_still_verifies_against_its_page(
    tmp_path: Path, header: bool
) -> None:
    """Such a pack exists: the lab night, a complete night with a header row."""
    pack, run = _run(tmp_path)
    _old_shape(pack, header)
    shown = _shown(run)
    shown["evidence_chain_hash"] = verify_evidence_pack(pack).final_hash
    verdict = verify_evidence_pack(pack, shown)
    assert verdict.ok, verdict.detail


@pytest.mark.parametrize("header", [True, False], ids=["with-header", "before-the-header"])
def test_a_pack_that_records_no_completeness_is_taken_as_complete_so_an_incomplete_page_fails(
    tmp_path: Path, header: bool
) -> None:
    """Nothing in such a pack can prove the night was incomplete, so it is held to a complete night's figures. An
    incomplete night written that way (the Crew night ``41178d37bd0da182``) fails and must be run again."""
    pack, run = _incomplete_run(tmp_path)
    _old_shape(pack, header)
    shown = _shown(run)
    shown["evidence_chain_hash"] = verify_evidence_pack(pack).final_hash
    verdict = verify_evidence_pack(pack, shown)
    assert not verdict.ok
    assert TAKEN_AS_COMPLETE in verdict.detail
    assert "billed total: the page shows $0.00, the evidence has $41.20" in verdict.detail


@pytest.mark.parametrize("header", [True, False], ids=["with-header", "before-the-header"])
def test_a_pack_written_before_completeness_was_recorded_cannot_hide_its_bill_either(
    tmp_path: Path, header: bool
) -> None:
    pack, result = _run(tmp_path)
    _old_shape(pack, header)
    shown = _shown(result)
    shown["evidence_chain_hash"] = verify_evidence_pack(pack).final_hash
    _hide_the_bill(shown)
    verdict = verify_evidence_pack(pack, shown)
    assert not verdict.ok
    assert TAKEN_AS_COMPLETE in verdict.detail


def _unkeyed_bill_only(tmp: Path) -> tuple[Path, RunResult]:
    """A complete night with empty intended and observed ledgers and one unkeyed billed row of 41.20: no finding."""
    snapshots = [
        LedgerSnapshot(name=LedgerName.intended, source="i", records=[]),
        LedgerSnapshot(name=LedgerName.observed, source="o", records=[]),
        LedgerSnapshot(
            name=LedgerName.billed,
            source="b",
            records=[Record(ledger=LedgerName.billed, source="b", row_id="b1", raw_key="", amount=Decimal("41.20"))],
        ),
    ]
    result = match(snapshots, CLOUD, RUN_TIME)
    assert result.complete and not result.findings and result.billed_unkeyed == Decimal("41.20")
    write_evidence_pack(result, tmp / "evidence")
    return tmp / "evidence", result


@pytest.mark.parametrize("header", [True, False], ids=["with-header", "before-the-header"])
def test_regression_an_old_pack_cannot_hide_an_unkeyed_bill_behind_a_page_that_says_incomplete(
    tmp_path: Path, header: bool
) -> None:
    """Bug: a pack without completeness was taken as incomplete when it held no finding and a ledger of no rows. A
    complete night with only an unkeyed bill of $41.20, rewritten to the old shape, verified beside a page that said
    ``complete: false`` with every total 0."""
    pack, result = _unkeyed_bill_only(tmp_path)
    _old_shape(pack, header)
    shown = _shown(result)
    shown["evidence_chain_hash"] = verify_evidence_pack(pack).final_hash
    assert verify_evidence_pack(pack, shown).ok
    _hide_the_bill(shown)
    verdict = verify_evidence_pack(pack, shown)
    assert not verdict.ok
    assert TAKEN_AS_COMPLETE in verdict.detail
    assert "unkeyed billed amount: the page shows $0.00, the evidence has $41.20" in verdict.detail


# --- The manifest names exactly the three ledgers (Req 6.3) ---------------------------------------------------------


def test_regression_a_manifest_that_omits_a_ledger_fails_verification(tmp_path: Path) -> None:
    """Bug: both verifiers checked only the ledgers the manifest named, so a manifest without ``billed`` verified."""
    pack, _ = _run(tmp_path)
    manifest = json.loads((pack / "manifest.json").read_text("utf-8"))
    del manifest["ledgers"]["billed"]
    (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    verdict = verify_evidence_pack(pack)
    assert not verdict.ok
    assert verdict.detail == "manifest ledgers are billed, intended, observed: it names intended, observed"


def test_a_manifest_that_names_a_fourth_ledger_fails_verification(tmp_path: Path) -> None:
    pack, _ = _run(tmp_path)
    manifest = json.loads((pack / "manifest.json").read_text("utf-8"))
    manifest["ledgers"]["extra"] = manifest["ledgers"]["billed"]
    (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    verdict = verify_evidence_pack(pack)
    assert not verdict.ok
    assert verdict.detail.startswith("manifest ledgers are billed, intended, observed: it names billed, extra,")


def test_a_record_row_of_another_ledger_fails_verification_at_its_row(tmp_path: Path) -> None:
    pack, _ = _run(tmp_path)
    moved = {"done": False}

    def move(row: dict[str, Any]) -> None:
        if row["type"] == "record" and row["ledger"] == "billed" and not moved["done"]:
            row["ledger"] = "elsewhere"
            moved["done"] = True

    _rechain(pack, move)
    rows = [json.loads(line) for line in _lines(pack)]
    at = next(i for i, r in enumerate(rows) if r.get("ledger") == "elsewhere")
    verdict = verify_evidence_pack(pack)
    assert not verdict.ok
    assert verdict.failed_row == at
    assert verdict.detail == f'row {at}: record of ledger "elsewhere", which is not intended, observed or billed'


# --- The headline's rounded amount (ui-kit Req 2.2) -------------------------------------------------------------------


def _vampire_night(tmp: Path) -> tuple[Path, RunResult]:
    """One Vampire billed $0.7172358001, the lab night's figure, so the headline rounds it to $0.7172."""
    snapshots = [
        LedgerSnapshot(name=LedgerName.intended, source="i", records=[]),
        LedgerSnapshot(
            name=LedgerName.observed,
            source="o",
            records=[Record(ledger=LedgerName.observed, source="o", row_id="o1", raw_key="i-0vamp", timestamp=OLD)],
        ),
        LedgerSnapshot(
            name=LedgerName.billed,
            source="b",
            records=[
                Record(
                    ledger=LedgerName.billed, source="b", row_id="b1", raw_key="i-0vamp", amount=Decimal("0.7172358001")
                )
            ],
        ),
    ]
    result = match(snapshots, CLOUD, RUN_TIME)
    write_evidence_pack(result, tmp / "evidence")
    return tmp / "evidence", result


def test_a_headline_that_shows_its_amount_rounded_to_four_figures_agrees_with_the_chain(tmp_path: Path) -> None:
    pack, result = _vampire_night(tmp_path)
    shown = _shown(result)
    assert "$0.7172" in shown["view"]["headline"] and "$0.7172358001" not in shown["view"]["headline"]
    verdict = verify_evidence_pack(pack, shown)
    assert verdict.ok, verdict.detail
    shown["view"]["headline_sentences"] = [
        s.replace("$0.7172", "$0.7172358001") for s in shown["view"]["headline_sentences"]
    ]
    assert verify_evidence_pack(pack, shown).ok  # the exact amount is true too


def test_regression_a_headline_that_rounds_its_amount_wrongly_fails_verification(tmp_path: Path) -> None:
    """Bug: the page's headline text was not compared with the chain, so it could print any amount."""
    pack, result = _vampire_night(tmp_path)
    shown = _shown(result)
    for field in ("headline_sentences",):
        shown["view"][field] = [s.replace("$0.7172", "$0.7173") for s in shown["view"][field]]
    shown["view"]["headline"] = shown["view"]["headline"].replace("$0.7172", "$0.7173")
    verdict = verify_evidence_pack(pack, shown)
    assert not verdict.ok
    assert "headline: the page shows $0.7173, which is no region's amount in the evidence" in verdict.detail


def _set_headline(shown: dict[str, Any], old: str, new: str) -> None:
    view = shown["view"]
    view["headline_sentences"] = [s.replace(old, new) for s in view["headline_sentences"]]
    view["headline"] = view["headline"].replace(old, new)


@pytest.mark.parametrize(
    ("old", "new", "number"),
    [
        ("$0.7172", "0.7173 dollars", "0.7173"),
        ("$0.7172", "USD 0.7173", "0.7173"),
        ("1 Vampire", "2 Vampire", "2"),
        (": $0.7172.", ": $0.7172, for 3 nights.", "3"),
        ("$0.7172", "$0.7172 (0.7172358001 exactly)", ""),
    ],
    ids=["amount-in-words", "amount-after-a-code", "count", "extra-number", "exact-amount-beside-the-rounded-one"],
)
def test_regression_every_number_in_the_headline_must_be_its_own_count_or_amount(
    tmp_path: Path, old: str, new: str, number: str
) -> None:
    """Bug: the headline check read only amounts written ``$0.7172``, so ``0.7173 dollars`` verified. Every numeric
    literal is now scanned with the explanation guard's scanner (``explain.extract_numbers``)."""
    pack, result = _vampire_night(tmp_path)
    shown = _shown(result)
    assert old in shown["view"]["headline"], shown["view"]["headline"]
    _set_headline(shown, old, new)
    verdict = verify_evidence_pack(pack, shown)
    if not number:
        assert verdict.ok, verdict.detail
        return
    assert not verdict.ok
    assert f"headline: the page shows the number {number}, which is not one of the headline's counts or amounts" in (
        verdict.detail
    )


def test_a_headline_with_a_digit_that_is_not_ascii_fails_verification(tmp_path: Path) -> None:
    """``\u0661`` (ARABIC-INDIC DIGIT ONE) reads as 1 to Python's scanner and as no digit to the browser's, so the two
    could disagree; both refuse it instead."""
    pack, result = _vampire_night(tmp_path)
    shown = _shown(result)
    _set_headline(shown, "1 Vampire", "\u0661 Vampire")
    verdict = verify_evidence_pack(pack, shown)
    assert not verdict.ok
    assert "headline: the page shows a digit that is not 0 to 9" in verdict.detail


@pytest.mark.parametrize("where", ["finding", "region", "billed total", "headline billed total"])
def test_a_page_that_rounds_any_amount_but_the_headline_fails_verification(tmp_path: Path, where: str) -> None:
    pack, result = _vampire_night(tmp_path)
    shown = _shown(result)
    if where == "finding":
        shown["findings"][0]["billed_amount"] = "0.7172"
    elif where == "region":
        shown["region_summaries"]["OB"]["billed_amount"] = "0.7172"
    elif where == "billed total":
        shown["billed_total"] = "0.7172"
    else:
        shown["view"]["billed_total"] = "0.7172"
    verdict = verify_evidence_pack(pack, shown)
    assert not verdict.ok
    assert "the evidence has $0.7172358001" in verdict.detail
