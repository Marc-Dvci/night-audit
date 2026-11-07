"""The review campaign: export, import and verify (Req 5.1, 5.2)."""

from __future__ import annotations

import csv
import io
import json
import shutil
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import pytest
from ghosts.review import (
    COLUMNS,
    FORMULA_START,
    ReviewError,
    import_sheet,
    main,
    neutralise,
    restore,
    sheet_csv,
    sheet_html,
    verify_decisions,
)
from ghosts.run import run
from ghosts_testkit import FIXTURES, RUN_TIME, control_for
from hypothesis import given
from hypothesis import strategies as st
from nightaudit.models import Finding, LedgerName, Record, RunResult

CLOCK = lambda: datetime(2026, 11, 5, 9, 30, tzinfo=UTC)  # noqa: E731 - the injected clock edge
FINDINGS = {
    "c.wren@hollowpines.com": "B",
    "e.ashby@hollowpines.com": "IB",
    "f.lowe@hollowpines.com": "I",
    "svc-backup@hollowpines.com": "O",
}


@pytest.fixture(scope="module")
def pristine(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One run of the fixture company, never modified; tests copy it."""
    folder = tmp_path_factory.mktemp("review")
    result = run(control_for(FIXTURES, folder), folder / "runs", RUN_TIME)
    return folder / "runs" / result.run_id


@pytest.fixture
def run_dir(pristine: Path, tmp_path: Path) -> Path:
    target = tmp_path / pristine.name
    shutil.copytree(pristine, target)
    return target


def exported_rows(run_dir: Path) -> list[dict[str, str]]:
    assert main(["export", str(run_dir)]) == 0
    text = (run_dir / "review.csv").read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def write_sheet(path: Path, rows: list[dict[str, str]]) -> Path:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(COLUMNS), lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(buffer.getvalue(), encoding="utf-8", newline="")
    return path


def decide(rows: list[dict[str, str]], **decisions: str) -> list[dict[str, str]]:
    """Fill in decisions by local part, e.g. ``decide(rows, c_wren="revoke")``."""
    out = []
    for row in rows:
        row = dict(row)
        local = row["person"].split("@")[0].replace(".", "_").replace("-", "_")
        if local in decisions:
            row["decision"], row["decision_date"] = decisions[local], "2026-11-05"
        out.append(row)
    return out


# --- Export -----------------------------------------------------------------------------------------------------------


def test_the_sheet_has_one_line_per_finding_with_the_review_columns(run_dir: Path) -> None:
    rows = exported_rows(run_dir)
    assert {r["person"]: r["region_code"] for r in rows} == FINDINGS
    assert list(rows[0]) == list(COLUMNS)
    wren = next(r for r in rows if r["person"] == "c.wren@hollowpines.com")
    assert wren["region"] == "Phantom seat"
    assert wren["left_on"] == "2026-06-30"
    assert wren["seats"] == "Crypt Docs"
    assert wren["manager"] == "b.quill@hollowpines.com"
    assert (wren["decision"], wren["decision_date"]) == ("", "")
    ashby = next(r for r in rows if r["person"] == "e.ashby@hollowpines.com")
    assert ashby["left_on"] == "2026-11-05"  # a future leaving date is the leaving date the reviewer needs
    assert (run_dir / "review.html").exists()


def test_the_html_sheet_is_self_contained(run_dir: Path) -> None:
    exported_rows(run_dir)
    page = (run_dir / "review.html").read_text(encoding="utf-8")
    assert 'http-equiv="Content-Security-Policy"' in page
    assert "<script" not in page and "src=" not in page and "href=" not in page
    assert "c.wren@hollowpines.com" in page and "Phantom seat" in page


# --- Import -----------------------------------------------------------------------------------------------------------


def test_decisions_are_recorded_bound_to_the_runs_evidence_chain(run_dir: Path, tmp_path: Path) -> None:
    rows = decide(exported_rows(run_dir), c_wren="revoke", svc_backup="investigate")
    sheet = write_sheet(tmp_path / "done.csv", rows)
    written = import_sheet(run_dir, sheet, "Imogen Reviewer", clock=CLOCK)
    result = json.loads((run_dir / "result.json").read_text("utf-8"))
    assert [(r["key"], r["decision"]) for r in written] == [
        ("c.wren@hollowpines.com", "revoke"),
        ("svc-backup@hollowpines.com", "investigate"),
    ]
    assert written[0]["prev_hash"] == result["evidence_chain_hash"]
    assert written[1]["prev_hash"] == written[0]["row_hash"]
    assert {r["reviewer"] for r in written} == {"Imogen Reviewer"}
    assert {r["imported_at"] for r in written} == {"2026-11-05T09:30:00+00:00"}
    assert {r["decision_date"] for r in written} == {"2026-11-05"}
    lines = (run_dir / "evidence" / "decisions.jsonl").read_text("utf-8").splitlines()
    assert [json.loads(line)["row_hash"] for line in lines] == [r["row_hash"] for r in written]
    verdict = verify_decisions(run_dir)
    assert verdict.ok and verdict.count == 2


def test_a_second_import_continues_the_chain(run_dir: Path, tmp_path: Path) -> None:
    rows = exported_rows(run_dir)
    first = import_sheet(run_dir, write_sheet(tmp_path / "a.csv", decide(rows, f_lowe="keep")), "A", clock=CLOCK)
    second = import_sheet(run_dir, write_sheet(tmp_path / "b.csv", decide(rows, e_ashby="revoke")), "B", clock=CLOCK)
    assert second[0]["prev_hash"] == first[-1]["row_hash"] and second[0]["index"] == 1
    assert verify_decisions(run_dir).count == 2


def test_a_decision_on_a_key_the_run_did_not_report_is_refused(
    run_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = decide(exported_rows(run_dir), c_wren="revoke")
    outsider = {"person": "a.thornfield@hollowpines.com", "decision": "keep", "decision_date": "2026-11-05"}
    rows.append({**rows[0], **outsider})
    sheet = write_sheet(tmp_path / "done.csv", rows)
    code = main(["import", str(run_dir), str(sheet), "--reviewer", "Imogen Reviewer"], clock=CLOCK)
    err = capsys.readouterr().err
    assert code == 2
    assert "a.thornfield@hollowpines.com was not reported by run" in err
    assert not (run_dir / "evidence" / "decisions.jsonl").exists()  # nothing written, not even c.wren


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"region_code": "OB"}, "is B in run"),
        ({"run_id": "0000000000000000"}, "sheet of another run"),
        ({"evidence_chain_hash": "f" * 64}, "sheet of another run"),
        ({"decision": "delete"}, "decision must be one of keep, revoke, investigate"),
        ({"decision_date": "05/11/2026"}, "decision_date must be a date"),
    ],
    ids=["region", "run-id", "chain-hash", "decision", "date"],
)
def test_a_sheet_with_a_bad_line_is_refused_whole(
    run_dir: Path, tmp_path: Path, change: dict[str, str], message: str
) -> None:
    rows = decide(exported_rows(run_dir), c_wren="revoke", f_lowe="keep")
    rows = [{**r, **change} if r["person"] == "c.wren@hollowpines.com" else r for r in rows]
    with pytest.raises(ReviewError, match=message):
        import_sheet(run_dir, write_sheet(tmp_path / "bad.csv", rows), "R", clock=CLOCK)
    assert not (run_dir / "evidence" / "decisions.jsonl").exists()


def test_a_person_decided_twice_an_empty_sheet_and_no_reviewer_are_refused(run_dir: Path, tmp_path: Path) -> None:
    rows = decide(exported_rows(run_dir), c_wren="revoke")
    twice = write_sheet(tmp_path / "twice.csv", rows + [r for r in rows if r["decision"]])
    with pytest.raises(ReviewError, match="decided twice"):
        import_sheet(run_dir, twice, "R", clock=CLOCK)
    with pytest.raises(ReviewError, match="no decisions"):
        import_sheet(run_dir, write_sheet(tmp_path / "empty.csv", exported_rows(run_dir)), "R", clock=CLOCK)
    with pytest.raises(ReviewError, match="reviewer name is required"):
        import_sheet(run_dir, write_sheet(tmp_path / "ok.csv", rows), "  ", clock=CLOCK)


@pytest.mark.property
@given(person=st.emails() | st.text(min_size=1, max_size=60))
def test_property_decisions_only_on_reported_findings(pristine: Path, person: str) -> None:
    """G7 (Req 5.2): any key the run did not report is refused, and the decision chain is unchanged."""
    if person.strip() in FINDINGS:
        return
    decisions = pristine / "evidence" / "decisions.jsonl"
    before = decisions.read_bytes() if decisions.exists() else None
    row = {c: "" for c in COLUMNS}
    result = json.loads((pristine / "result.json").read_text("utf-8"))
    row.update(person=neutralise(person), region_code="O", decision="keep", decision_date="2026-11-05",
               run_id=result["run_id"], evidence_chain_hash=result["evidence_chain_hash"])
    sheet = pristine.parent / "property-sheet.csv"
    write_sheet(sheet, [row])
    with pytest.raises(ReviewError):
        import_sheet(pristine, sheet, "R", clock=CLOCK)
    after = decisions.read_bytes() if decisions.exists() else None
    assert after == before


# --- Verify -----------------------------------------------------------------------------------------------------------


def recorded(run_dir: Path, tmp_path: Path) -> Path:
    rows = decide(exported_rows(run_dir), c_wren="revoke", e_ashby="keep", svc_backup="investigate")
    import_sheet(run_dir, write_sheet(tmp_path / "done.csv", rows), "Imogen Reviewer", clock=CLOCK)
    return run_dir / "evidence" / "decisions.jsonl"


def test_changing_a_decision_is_detected(run_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = recorded(run_dir, tmp_path)
    path.write_bytes(path.read_bytes().replace(b'"decision":"revoke"', b'"decision":"keep"'))
    assert main(["verify", str(run_dir)]) == 1
    assert "FAIL  decision 0: hash mismatch" in capsys.readouterr().out


def test_dropping_a_decision_is_detected(run_dir: Path, tmp_path: Path) -> None:
    path = recorded(run_dir, tmp_path)
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(lines[0] + lines[2])
    verdict = verify_decisions(run_dir)
    assert not verdict.ok and verdict.failed_row == 1


def test_a_tampered_evidence_pack_fails_verify_and_refuses_import(run_dir: Path, tmp_path: Path) -> None:
    rows = decide(exported_rows(run_dir), c_wren="revoke")
    evidence = run_dir / "evidence" / "evidence.jsonl"
    evidence.write_bytes(evidence.read_bytes().replace(b"Crypt Docs", b"Crypt Dogs", 1))
    assert not verify_decisions(run_dir).ok
    with pytest.raises(ReviewError, match="does not verify"):
        import_sheet(run_dir, write_sheet(tmp_path / "done.csv", rows), "R", clock=CLOCK)


def test_the_cli_reports_ok(run_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    recorded(run_dir, tmp_path)
    assert main(["--runs", str(run_dir.parent), "verify", run_dir.name]) == 0
    assert "OK  evidence verifies; 3 decisions verify" in capsys.readouterr().out


@pytest.fixture(scope="module")
def decided(pristine: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A copy of the run with two decisions recorded, for the tamper property."""
    target = tmp_path_factory.mktemp("decided") / pristine.name
    shutil.copytree(pristine, target)
    rows = decide(list(csv.DictReader(io.StringIO(sheet_csv(_result(target))))), c_wren="revoke", f_lowe="keep")
    import_sheet(target, write_sheet(target.parent / "seed.csv", rows), "R", clock=CLOCK)
    return target


@pytest.mark.property
@given(data=st.data())
def test_property_decision_tampering_is_detected(decided: Path, data: st.DataObject) -> None:
    """G8 (Req 5.2): changing any single byte of decisions.jsonl makes verify fail."""
    path = decided / "evidence" / "decisions.jsonl"
    original = path.read_bytes()
    assert verify_decisions(decided).ok
    position = data.draw(st.integers(min_value=0, max_value=len(original) - 1))
    replacement = data.draw(st.integers(min_value=0, max_value=255).filter(lambda b: b != original[position]))
    try:
        path.write_bytes(original[:position] + bytes([replacement]) + original[position + 1:])
        assert not verify_decisions(decided).ok
    finally:
        path.write_bytes(original)


def _result(run_dir: Path) -> RunResult:
    return RunResult.model_validate_json((run_dir / "result.json").read_text("utf-8"))


# --- Values are text --------------------------------------------------------------------------------------------------

values = st.text(alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"), min_size=1,
                 max_size=60) | st.sampled_from(["<script>alert(1)</script>", '"><img src=x onerror=alert(1)>',
                                                 "=cmd|' /C calc'!A0", "+1-555", "@SUM(A1)", "'=already", "-x@y.z"])


def synthetic(person: str, name: str, manager: str) -> RunResult:
    record = Record(ledger=LedgerName.observed, source="s", row_id="r", raw_key=person, key=person)
    finding = Finding(key=person, region_code="O", name=name, severity="low", meaning="m", informational=False,
                      records=[record], context={"manager": manager, "systems": name, "seats": manager})
    return RunResult(run_id="0123456789abcdef", run_time=RUN_TIME, control_hash="c", complete=True,
                     control_title=name, findings=[finding], evidence_chain_hash="e" * 64)


class Markup(HTMLParser):
    """The tags of a page and its text, as a browser would split them."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, list[tuple[str, str | None]]]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, attrs))

    def handle_endtag(self, tag: str) -> None:
        self.tags.append(("/" + tag, []))

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def markup(page: str) -> Markup:
    parser = Markup()
    parser.feed(page)
    parser.close()
    return parser


@pytest.mark.property
@given(person=values, name=values, manager=values)
def test_property_the_review_sheet_shows_values_only_as_text(person: str, name: str, manager: str) -> None:
    """G9 (Req 5.1): hostile values change no tag of the HTML sheet; the CSV neutralises formulas and round-trips."""
    hostile = markup(sheet_html(synthetic(person, name, manager)))
    benign = markup(sheet_html(synthetic("p" * len(person), "n" * len(name), "m" * len(manager))))
    assert hostile.tags == benign.tags
    text = "".join(hostile.text)
    assert person in text and name in text and manager in text

    (row,) = list(csv.DictReader(io.StringIO(sheet_csv(synthetic(person, name, manager)), newline="")))
    for column in ("person", "region", "manager", "systems", "seats"):
        assert not row[column].startswith(FORMULA_START)
    assert (restore(row["person"]), restore(row["region"]), restore(row["manager"])) == (person, name, manager)
