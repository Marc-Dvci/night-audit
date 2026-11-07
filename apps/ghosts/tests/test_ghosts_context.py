"""The people_context enricher puts the HR facts into each finding's evidence (Req 2.2, 5.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ghosts.context import people_context
from ghosts_testkit import APP, DATA, FIXTURES, RUN_TIME, control_for
from nightaudit.evidence import verify_evidence_pack
from nightaudit.models import Finding, LedgerName, Record
from nightaudit.runner import run_control
from nightaudit.steps import ControlContext


@pytest.mark.integration
def test_a_leavers_leaving_date_reaches_the_findings_evidence_row(tmp_path: Path) -> None:
    result = run_control(control_for(FIXTURES, tmp_path), tmp_path / "runs", run_time=RUN_TIME)
    by_key = {f.key: f for f in result.findings}
    wren = by_key["c.wren@hollowpines.com"]
    assert wren.region_code == "B"  # left, account disabled, Crypt Docs seat still assigned
    assert wren.context["left_on"] == "2026-06-30"
    assert wren.context["manager"] == "b.quill@hollowpines.com"
    assert wren.context["seats"] == "Crypt Docs"

    pack = tmp_path / "runs" / result.run_id / "evidence"
    assert verify_evidence_pack(pack).ok
    rows = [json.loads(line) for line in (pack / "evidence.jsonl").read_text("utf-8").splitlines()]
    (row,) = [r for r in rows if r.get("type") == "finding" and r["key"] == "c.wren@hollowpines.com"]
    assert row["context"]["left_on"] == "2026-06-30"


@pytest.mark.integration
def test_each_finding_gets_the_columns_the_page_shows(tmp_path: Path) -> None:
    result = run_control(control_for(FIXTURES, tmp_path), tmp_path / "runs", run_time=RUN_TIME)
    regions = {f.key: f.region_code for f in result.findings}
    assert regions == {
        "c.wren@hollowpines.com": "B",
        "e.ashby@hollowpines.com": "IB",
        "f.lowe@hollowpines.com": "I",
        "svc-backup@hollowpines.com": "O",
    }
    by_key = {f.key: f.context for f in result.findings}
    assert by_key["e.ashby@hollowpines.com"]["leaving_on"] == "2026-11-05"
    assert by_key["e.ashby@hollowpines.com"]["seats"] == "Belfry CRM, Crypt Docs"
    assert "left_on" not in by_key["e.ashby@hollowpines.com"]
    assert by_key["svc-backup@hollowpines.com"] == {
        "systems": "Hollow Pines directory",
        "hr_roster": "no record",
        "hr_status": "No HR record.",
        "last_sign_in_on": "not recorded",
    }
    assert by_key["f.lowe@hollowpines.com"]["person"] == "Finn Lowe"
    assert result.ledger_errors == {}


def test_systems_are_joined_and_the_latest_sign_in_wins() -> None:
    def observed(row: str, system: str, signed_in: str) -> Record:
        return Record(
            ledger=LedgerName.observed,
            source="s",
            row_id=row,
            raw_key="k",
            key="k",
            attrs={"system": system, "last_sign_in": signed_in},
        )

    finding = Finding(
        key="k",
        region_code="O",
        name="Poltergeist",
        severity="low",
        meaning="m",
        informational=False,
        records=[
            observed("1", "Hollow Pines directory", "2026-10-30T09:00:00Z"),
            observed("2", "GitHub hollow-pines-demo", "2026-11-01T07:00:00+00:00"),
        ],
    )
    context = people_context([finding], {"roster": str(FIXTURES / "hr_roster.csv")})["k"]
    assert context["systems"] == "GitHub hollow-pines-demo, Hollow Pines directory"
    assert context["last_sign_in"] == "2026-11-01T07:00:00+00:00"


def test_a_relative_roster_path_resolves_against_the_controls_folder() -> None:
    finding = Finding(
        key="f.lowe@hollowpines.com", region_code="I", name="n", severity="s", meaning="m", informational=False
    )
    control = ControlContext(folder=APP / "controls")
    context = people_context([finding], {"roster": "../tests/fixtures/hr_roster.csv"}, control=control)
    assert context["f.lowe@hollowpines.com"]["person"] == "Finn Lowe"


def test_the_controls_alias_domains_map_roster_emails(tmp_path: Path) -> None:
    roster = tmp_path / "roster.csv"
    roster.write_text(
        "email,given_name,family_name,manager_email\nB.Quill@HollowPines.org,Bram,Quill,a@x\n", encoding="utf-8"
    )
    finding = Finding(
        key="b.quill@hollowpines.com", region_code="O", name="n", severity="s", meaning="m", informational=False
    )
    control = ControlContext(folder=tmp_path, alias_domains={"hollowpines.org": "hollowpines.com"})
    aliased = people_context([finding], {"roster": "roster.csv"}, control=control)
    plain = people_context([finding], {"roster": str(roster)})
    assert aliased["b.quill@hollowpines.com"]["person"] == "Bram Quill"
    assert plain["b.quill@hollowpines.com"] == {"hr_roster": "no record", "hr_status": "No HR record."}


@pytest.mark.integration
def test_the_explanation_states_the_condition_in_words(tmp_path: Path) -> None:
    result = run_control(control_for(DATA, tmp_path), tmp_path / "runs", run_time=RUN_TIME)
    by_key = {f.key: f for f in result.findings}
    assert by_key["j.marsh@hollowpines.com"].explanation == (
        "Left on 2026-09-12. Account still active, last sign-in 2026-10-30. Seats in Belfry CRM and Crypt Docs."
    )
    assert by_key["noor.haddad@hollowpines.com"].explanation == (
        "On the HR roster since 2026-11-02. No active account and no paid seat yet."
    )
    reporting = by_key["svc-reporting@hollowpines.com"].explanation
    assert reporting is not None and reporting.startswith("No HR record. Account active in ")
    for finding in result.findings:
        assert finding.explanation and "{" not in finding.explanation
