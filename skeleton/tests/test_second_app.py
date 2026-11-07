"""What the second app taught (Req 10): run time, notes, control context, unkeyed words, template slots, downloads,
decisions on the page, and a control that uses none of them running exactly as before."""

from __future__ import annotations

import hashlib
import json
import string
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from nightaudit.api import create_app, download_path, run_document
from nightaudit.cli import main as cli_main
from nightaudit.control import ControlConfig, RegionOverride
from nightaudit.decisions import DECISIONS_FILE, decision_row_hash, page_decisions
from nightaudit.demo import export_run, replace_folder
from nightaudit.evidence import canonical_json, verify_evidence_pack
from nightaudit.explain import evidence_numbers, extract_numbers, resolve_template
from nightaudit.models import DownloadUi, Finding, LedgerName, Record, RunResult
from nightaudit.report import report_html, run_numbers, run_view
from nightaudit.runner import load_control_file, run_control
from pydantic import ValidationError

RUN_TIME = datetime(2026, 11, 4, 2, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[2]

# Keys a and b are matched; c is a Vampire (observed and billed, 41.20); tax is a billed line with no key (0.62).
INTENDED = "row_id,id\ni1,a\ni2,b\n"
OBSERVED = "row_id,id,ts\no1,a,2026-09-01T00:00:00Z\no2,b,2026-09-01T00:00:00Z\no3,c,2026-09-01T00:00:00Z\n"
BILLED = "row_id,resource,amount\nb1,a,1.00\nb2,b,2.10\nb3,c,41.20\nb4,,0.62\n"


def control(folder: Path, extra: dict[str, Any] | None = None, sources: dict[str, Any] | None = None) -> Path:
    """A small control over three CSV ledgers, with *extra* top-level sections and optional ledger sources."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "intended.csv").write_text(INTENDED, "utf-8")
    (folder / "observed.csv").write_text(OBSERVED, "utf-8")
    (folder / "billed.csv").write_text(BILLED, "utf-8")
    ledgers: dict[str, Any] = {
        "intended": {"key_field": "id", "normalisers": ["strip"], "connector": {"type": "csv", "path": "intended.csv"}},
        "observed": {"key_field": "id", "normalisers": ["strip"], "connector": {"type": "csv", "path": "observed.csv"}},
        "billed": {
            "key_field": "resource",
            "normalisers": ["strip"],
            "connector": {"type": "csv", "path": "billed.csv"},
        },
    }
    for name, source in (sources or {}).items():
        ledgers[name]["sources"] = [source]
    raw: dict[str, Any] = {
        "id": "second-app",
        "title": "Second app",
        "alias_domains": {"old.example": "example"},
        "ledgers": ledgers,
        **(extra or {}),
    }
    path = folder / "control.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), "utf-8")
    return path


def say(*sentences: str) -> dict[str, Any]:
    return {"summarisers": [{"entry": "second_app_steps:say", "options": {"sentences": list(sentences)}}]}


def evidence_rows(runs: Path, result: RunResult) -> list[dict[str, Any]]:
    text = (runs / result.run_id / "evidence" / "evidence.jsonl").read_text("utf-8")
    return [json.loads(line) for line in text.splitlines()]


# --- Req 10.1: run time ---------------------------------------------------------------------------------------------


@pytest.mark.integration
def test_every_connector_is_given_the_run_time_before_it_fetches(tmp_path: Path) -> None:
    dated = {"type": "python", "entry": "second_app_steps:DatedRows"}
    path = control(tmp_path / "c", sources={"intended": dated, "observed": dated, "billed": dated})
    result = run_control(path, tmp_path / "runs", run_time=RUN_TIME)
    assert result.complete, result.ledger_errors
    assert result.regions["row-2026-11-04"] == "IOB"


@pytest.mark.integration
def test_a_connector_that_ignores_the_run_time_needs_no_change(tmp_path: Path) -> None:
    undated = {"type": "python", "entry": "second_app_steps:Undated"}
    path = control(tmp_path / "c", sources={"intended": undated})
    result = run_control(path, tmp_path / "runs", run_time=RUN_TIME)
    assert result.complete and result.regions["row-fixed"] == "I"


def test_nightaudit_run_at_moves_the_date_for_every_connector(tmp_path: Path) -> None:
    dated = {"type": "python", "entry": "second_app_steps:DatedRows"}
    path = control(tmp_path / "c", sources={"intended": dated, "observed": dated, "billed": dated})
    assert cli_main(["run", str(path), "--runs", str(tmp_path / "runs"), "--at", "2026-12-01T02:00:00Z"]) == 0
    (run_dir,) = [p for p in (tmp_path / "runs").iterdir() if (p / "result.json").exists()]
    result = RunResult.model_validate_json((run_dir / "result.json").read_text("utf-8"))
    assert set(result.regions) >= {"row-2026-12-01"}


# --- Req 10.2: notes ------------------------------------------------------------------------------------------------


@pytest.mark.integration
def test_a_summarisers_sentences_are_notes_in_the_evidence_the_page_and_the_report(tmp_path: Path) -> None:
    sentence = "Key c is billed 41.20 with no approval; 3 keys are observed."
    path = control(tmp_path / "c", say(sentence, "Every   other line\nmatches."))
    runs = tmp_path / "runs"
    result = run_control(path, runs, run_time=RUN_TIME)
    assert result.ledger_errors == {}
    assert [(n.text, n.numbers) for n in result.notes] == [
        (sentence, ["3", "41.20"]),
        ("Every other line matches.", []),
    ]
    notes = [r for r in evidence_rows(runs, result) if r["type"] == "note"]
    assert [(r["row_id"], r["text"], r["source"]) for r in notes] == [
        ("note:1", sentence, "second_app_steps:say"),
        ("note:2", "Every other line matches.", "second_app_steps:say"),
    ]
    assert verify_evidence_pack(runs / result.run_id / "evidence").ok
    assert run_document(result)["notes"][0]["text"] == sentence
    report = report_html(result)
    assert f'<p class="headline">{run_view(result).headline}</p><ul class="notes"><li>{sentence}</li>' in report
    assert {Decimal("41.20"), Decimal("3")} <= run_numbers(result)


@pytest.mark.integration
def test_a_note_that_cites_a_number_outside_the_evidence_is_refused_and_named(tmp_path: Path) -> None:
    path = control(tmp_path / "c", say("Key c is billed 41.20.", "Seven keys, 7 of them new."))
    result = run_control(path, tmp_path / "runs", run_time=RUN_TIME)
    assert result.notes == []
    assert result.ledger_errors == {
        "summariser:second_app_steps:say": "notes refused: 7 not in the run's evidence rows",
    }
    assert result.findings  # the run keeps its findings


@pytest.mark.integration
@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ("second_app_steps:fail", "RuntimeError: summariser failed"),
        ("second_app_steps:not_a_list", "TypeError: a summariser returns a list of sentences"),
        ("second_app_steps:missing", "AttributeError"),
    ],
)
def test_a_summariser_that_fails_adds_no_note_and_is_named(tmp_path: Path, entry: str, message: str) -> None:
    result = run_control(
        control(tmp_path / "c", {"summarisers": [{"entry": entry}]}), tmp_path / "runs", run_time=RUN_TIME
    )
    assert result.notes == [] and result.complete
    assert result.ledger_errors[f"summariser:{entry}"].startswith(message)


@pytest.mark.integration
def test_notes_are_a_short_list_of_short_sentences(tmp_path: Path) -> None:
    too_many = run_control(control(tmp_path / "a", say(*(["A note."] * 13))), tmp_path / "ra", run_time=RUN_TIME)
    too_long = run_control(control(tmp_path / "b", say("x" * 301)), tmp_path / "rb", run_time=RUN_TIME)
    for result in (too_many, too_long):
        assert result.notes == []
        assert result.ledger_errors["summariser:second_app_steps:say"].startswith("notes refused: at most 12 notes")


@pytest.mark.integration
def test_an_incomplete_run_has_no_notes(tmp_path: Path) -> None:
    path = control(tmp_path / "c", say("A note."))
    (tmp_path / "c" / "billed.csv").unlink()
    result = run_control(path, tmp_path / "runs", run_time=RUN_TIME)
    assert not result.complete and result.notes == []


words = st.text(alphabet=string.ascii_letters + " ", min_size=1, max_size=20)


@pytest.mark.integration
@pytest.mark.property
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(left=words, number=st.decimals(min_value=-1000, max_value=1000, places=2), right=words)
def test_property_a_note_is_kept_if_and_only_if_every_number_it_cites_is_evidence(
    tmp_path_factory: pytest.TempPathFactory, left: str, number: Decimal, right: str
) -> None:
    """P11 (Req 10.2): a summariser's sentence becomes a note exactly when its numbers are all in the evidence rows."""
    folder = tmp_path_factory.mktemp("p11")
    sentence = f"{left} {number} {right}"
    result = run_control(control(folder / "c", say(sentence)), folder / "runs", run_time=RUN_TIME)
    allowed = {n for r in result.snapshots for rec in r.records for n in _record_numbers(rec)}
    for finding in result.findings:
        allowed |= evidence_numbers(finding)
    cited = extract_numbers(" ".join(sentence.split()))
    if cited <= allowed:
        assert [n.text for n in result.notes] == [" ".join(sentence.split())]
        assert "summariser:second_app_steps:say" not in result.ledger_errors
    else:
        assert result.notes == []
        assert result.ledger_errors["summariser:second_app_steps:say"].startswith("notes refused:")


def _record_numbers(record: Record) -> set[Decimal]:
    nums = {Decimal(record.amount)} if record.amount is not None else set()
    for text in (record.row_id, record.raw_key, record.key or "", *record.attrs.values()):
        nums |= extract_numbers(text)
    if record.timestamp is not None:
        nums |= extract_numbers(record.timestamp.isoformat())
    return nums


# --- Req 10.3: control context --------------------------------------------------------------------------------------


@pytest.mark.integration
def test_an_enricher_that_takes_control_gets_the_folder_alias_domains_id_and_run_time(tmp_path: Path) -> None:
    extra = {
        "enrichers": [
            {"entry": "second_app_steps:where", "regions": ["OB"]},
            {"entry": "second_app_steps:old_style", "regions": ["OB"]},
        ]
    }
    result = run_control(control(tmp_path / "my-controls", extra), tmp_path / "runs", run_time=RUN_TIME)
    (c,) = [f for f in result.findings if f.key == "c"]
    assert c.context == {
        "folder": "my-controls",
        "aliases": "old.example>example",
        "control_id": "second-app",
        "run_date": "2026-11-04",
        "seen_by": "old_style",
    }


@pytest.mark.integration
def test_a_summariser_that_takes_control_gets_it_too(tmp_path: Path) -> None:
    extra = {"summarisers": [{"entry": "second_app_steps:count_billed", "options": {"amount": "41.20"}}]}
    result = run_control(control(tmp_path / "folder", extra), tmp_path / "runs", run_time=RUN_TIME)
    assert [n.text for n in result.notes] == ["Control second-app read its folder folder; amount 41.20."]


# --- Req 10.4: words for lines with no key --------------------------------------------------------------------------


@pytest.mark.integration
def test_the_lines_with_no_key_use_the_controls_words(tmp_path: Path) -> None:
    words = {
        "singular": "seat paid for nobody named",
        "plural": "seats paid for nobody named",
        "explanation": "The invoice counts more seats than there are assignments.",
    }
    result = run_control(control(tmp_path / "c", {"ui": {"unkeyed": words}}), tmp_path / "runs", run_time=RUN_TIME)
    line = run_view(result).lines[1]
    assert (line.label, line.note) == ("1 seat paid for nobody named", words["explanation"])
    report = report_html(result)
    assert "1 seat paid for nobody named" in report and "resource id" not in report


@pytest.mark.integration
def test_without_unkeyed_words_the_wording_is_the_one_used_before(tmp_path: Path) -> None:
    result = run_control(control(tmp_path / "c"), tmp_path / "runs", run_time=RUN_TIME)
    line = run_view(result).lines[1]
    assert line.label == "1 line with no resource id"
    assert line.note == "Tax, credits and support lines carry no resource id, so they are kept apart."


# --- Req 10.5: template slots ---------------------------------------------------------------------------------------


def _finding(context: dict[str, str] | None = None, attrs: dict[str, str] | None = None) -> Finding:
    record = Record(ledger=LedgerName.observed, source="s", row_id="o1", raw_key="k", key="k", attrs=attrs or {})
    return Finding(
        key="k",
        region_code="OB",
        name="Ghost",
        severity="high",
        meaning="Exists, unapproved.",
        informational=False,
        records=[record],
        context=context or {},
    )


def _with_template(template: str) -> ControlConfig:
    return ControlConfig(regions={"OB": RegionOverride(template=template)})


def test_context_and_attribute_slots_fill_a_template() -> None:
    finding = _finding({"left_on": "2026-09-12"}, {"system": "Directory"})
    text = resolve_template(finding, _with_template("Left on {context:left_on}. Active in {attr:system}."))
    assert text == "Left on 2026-09-12. Active in Directory."


def test_an_absent_value_is_empty_text_and_never_fails() -> None:
    text = resolve_template(_finding(), _with_template("Left on {context:left_on}; in {attr:system}; {nothing}."))
    assert text == "Left on ; in ; ."


def test_braces_in_a_value_stay_text() -> None:
    finding = _finding({"note": "{key} {context:x} {0}"})
    assert resolve_template(finding, _with_template("Says {context:note}")) == "Says {key} {context:x} {0}"


def test_a_template_that_cites_a_number_outside_the_evidence_falls_back_to_the_default() -> None:
    finding = _finding({"left_on": "2026-09-12"})
    default = resolve_template(finding, ControlConfig())
    assert resolve_template(finding, _with_template("Left {context:left_on}, 30 days ago.")) == default


slot = st.sampled_from(
    [
        "{context:a}",
        "{context:b}",
        "{attr:a}",
        "{attr:missing}",
        "{key}",
        "{billed_amount}",
        "{meaning}",
        "{name}",
        "{nights_persisted}",
        "{unknown}",
    ]
)
literal = st.text(alphabet=string.ascii_letters + " .,;:-", max_size=12)
values = st.dictionaries(st.sampled_from(["a", "b", "c"]), st.text(alphabet=string.printable, max_size=20), max_size=3)


@pytest.mark.property
@given(parts=st.lists(st.one_of(slot, literal), max_size=8), context=values, attrs=values)
def test_property_template_slots_never_fail_and_never_invent_a_number(
    parts: list[str], context: dict[str, str], attrs: dict[str, str]
) -> None:
    """P12 (Req 10.5): any template of words and slots renders without raising, citing only evidence numbers."""
    finding = _finding(context, attrs)
    text = resolve_template(finding, _with_template("".join(parts)))
    assert isinstance(text, str)
    assert extract_numbers(text) <= evidence_numbers(finding)


# --- Req 10.6: downloads --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "../result.json",
        "evidence/manifest.json",
        ".hidden.csv",
        "a/b.csv",
        "a\\b.csv",
        "review.exe",
        "review",
        "review.csv.",
        "C:review.csv",
        "%2e%2e.csv",
        "",
        "x" * 70 + ".csv",
        "review.CSV",
    ],
)
def test_a_download_name_outside_the_allow_list_is_refused(name: str) -> None:
    with pytest.raises(ValidationError):
        DownloadUi(label="Sheet", file=name)


def _served(tmp_path: Path) -> tuple[TestClient, RunResult, Path]:
    extra = {"ui": {"downloads": [{"label": "Sheet", "file": "sheet.csv"}, {"label": "Later", "file": "later.txt"}]}}
    runs = tmp_path / "runs"
    result = run_control(control(tmp_path / "c", extra), runs, run_time=RUN_TIME)
    (runs / result.run_id / "sheet.csv").write_bytes(b"person,decision\nc,\n")
    (runs / result.run_id / "unlisted.csv").write_bytes(b"secret\n")
    return TestClient(create_app(runs)), result, runs


@pytest.mark.integration
def test_a_listed_download_is_served_as_an_attachment_and_linked_only_when_it_exists(tmp_path: Path) -> None:
    http, result, runs = _served(tmp_path)
    response = http.get(f"/api/runs/{result.run_id}/files/sheet.csv")
    assert response.status_code == 200 and response.content == b"person,decision\nc,\n"
    assert response.headers["content-disposition"] == 'attachment; filename="sheet.csv"'
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert http.get(f"/api/runs/{result.run_id}").json()["downloads"] == [{"label": "Sheet", "file": "sheet.csv"}]
    assert http.get(f"/api/runs/{result.run_id}/files/later.txt").status_code == 404  # listed, not written yet


@pytest.mark.integration
@pytest.mark.parametrize(
    "name",
    [
        "unlisted.csv",
        "result.json",
        "..%2Fresult.json",
        "%2e%2e%2fresult.json",
        "evidence%2Fmanifest.json",
        "..%5Cresult.json",
    ],
)
def test_no_request_reads_a_file_the_control_does_not_list(tmp_path: Path, name: str) -> None:
    http, result, _ = _served(tmp_path)
    assert http.get(f"/api/runs/{result.run_id}/files/{name}").status_code == 404


@pytest.mark.integration
@pytest.mark.property
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=100)
@given(
    name=st.one_of(
        st.text(max_size=30),
        st.sampled_from(["sheet.csv", "unlisted.csv", "result.json", "../result.json", "evidence/manifest.json"]),
    )
)
def test_property_no_download_escapes_the_run_folder(tmp_path_factory: pytest.TempPathFactory, name: str) -> None:
    """P13 (Req 10.6): a file is returned only for a listed, allow-listed name, and it is that file's bytes."""
    folder = tmp_path_factory.getbasetemp() / "p13"
    if not (folder / "runs").exists():
        _served_into(folder)
    result_dir = next(p for p in (folder / "runs").iterdir() if (p / "result.json").exists())
    result = RunResult.model_validate_json((result_dir / "result.json").read_text("utf-8"))
    path = download_path(result_dir, result, name)
    if name == "sheet.csv":
        assert path is not None and path.read_bytes() == (result_dir / "sheet.csv").read_bytes()
    else:
        assert path is None


def _served_into(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    _served(folder)


@pytest.mark.integration
def test_the_static_demo_copies_the_downloads_beside_the_run(tmp_path: Path) -> None:
    _, result, runs = _served(tmp_path)
    export_run(runs, result.run_id, tmp_path / "out" / result.run_id, (2026, 11, 4, 2, 0, 0))
    out = tmp_path / "out" / result.run_id
    assert (out / "sheet.csv").read_bytes() == (runs / result.run_id / "sheet.csv").read_bytes()
    assert not (out / "unlisted.csv").exists() and not (out / "later.txt").exists()
    assert json.loads((out / "run.json").read_text("utf-8"))["downloads"] == [{"label": "Sheet", "file": "sheet.csv"}]


def test_a_demo_build_may_replace_only_its_own_folder(tmp_path: Path) -> None:
    root = tmp_path / "public" / "demo"
    (root / "other").mkdir(parents=True)
    (root / "other" / "runs.json").write_text("[]", "utf-8")
    for wrong in (root, root / "other", root / "other" / "deeper"):
        with pytest.raises(ValueError, match="may only write"):
            replace_folder(wrong, root, "mine")
    replace_folder(root / "mine", root, "mine")
    replace_folder(tmp_path / "scratch", root, "mine")
    assert (root / "other" / "runs.json").exists() and (root / "mine").is_dir()


# --- Req 10.7: decisions on the page --------------------------------------------------------------------------------


def _decide(runs: Path, result: RunResult, key: str = "c", code: str = "OB") -> Path:
    row: dict[str, Any] = {
        "index": 0,
        "prev_hash": result.evidence_chain_hash,
        "type": "decision",
        "run_id": result.run_id,
        "evidence_chain_hash": result.evidence_chain_hash,
        "key": key,
        "region_code": code,
        "decision": "revoke",
        "decision_date": "2026-11-05",
        "reviewer": "R. Reviewer",
    }
    row["row_hash"] = decision_row_hash(row)
    path = runs / result.run_id / "evidence" / DECISIONS_FILE
    path.write_bytes(canonical_json(row).encode("utf-8") + b"\n")
    return path


@pytest.mark.integration
def test_verified_decisions_are_shown_with_their_reviewer_and_date(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    result = run_control(control(tmp_path / "c"), runs, run_time=RUN_TIME)
    assert page_decisions(runs / result.run_id, result) is None
    _decide(runs, result)
    assert run_document(result, runs / result.run_id)["decisions"] == {
        "ok": True,
        "detail": "evidence verifies; 1 decisions verify",
        "rows": [
            {
                "key": "c",
                "region_code": "OB",
                "decision": "revoke",
                "decision_date": "2026-11-05",
                "reviewer": "R. Reviewer",
            }
        ],
    }


@pytest.mark.integration
def test_decisions_that_do_not_verify_are_not_shown(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    result = run_control(control(tmp_path / "c"), runs, run_time=RUN_TIME)
    path = _decide(runs, result)
    path.write_bytes(path.read_bytes().replace(b"revoke", b"keep!!"))
    shown = page_decisions(runs / result.run_id, result)
    assert shown is not None and shown["ok"] is False and shown["rows"] == []
    assert shown["detail"] == "decision 0: hash mismatch"
    _decide(runs, result, key="a", code="IOB")  # a is matched, not a finding
    shown = page_decisions(runs / result.run_id, result)
    assert shown is not None and shown["rows"] == [] and "did not report" in shown["detail"]


# --- A control that uses none of it ---------------------------------------------------------------------------------


def test_a_control_without_the_new_sections_keeps_its_run_ids() -> None:
    """The Vampires demo night 1 had run id 2a6b3e85b13673ed before Req 10 (commit ec92469), and keeps it."""
    control_file = load_control_file(ROOT / "apps" / "vampires" / "demo" / "night-1" / "control.yaml")
    digest = hashlib.sha256(f"{RUN_TIME.isoformat()}:{control_file.canonical_hash()}".encode()).hexdigest()[:16]
    assert digest == "2a6b3e85b13673ed"


@pytest.mark.integration
def test_a_run_without_notes_writes_no_note_row(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    result = run_control(control(tmp_path / "c"), runs, run_time=RUN_TIME)
    assert {r["type"] for r in evidence_rows(runs, result)} == {"header", "record", "finding"}
    assert "notes" in json.loads((runs / result.run_id / "result.json").read_text("utf-8"))
