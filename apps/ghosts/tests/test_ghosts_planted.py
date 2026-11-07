"""Acceptance: the Hollow Pines run finds exactly what planted.yaml says, and nothing else."""

from __future__ import annotations

from pathlib import Path

from ghosts.acceptance import evaluate, load_planted, run_time_of, table
from ghosts.run import run
from ghosts_testkit import APP, CONTROL
from nightaudit.evidence import verify_evidence_pack
from nightaudit.models import LedgerName


def test_the_run_finds_exactly_the_planted_findings(tmp_path: Path) -> None:
    planted = load_planted()
    result, verdict = evaluate(CONTROL, tmp_path, planted)
    assert verdict.ok, "\n" + table(verdict)
    found = {f.key: f.region_code for f in result.findings if not f.informational}
    assert found == {p["key"]: p["region"] for p in planted["planted"]}
    assert verify_evidence_pack(tmp_path / result.run_id / "evidence").ok


def test_the_planted_findings_carry_the_evidence_their_stories_name(tmp_path: Path) -> None:
    result, _ = evaluate(CONTROL, tmp_path, load_planted())
    context = {f.key: f.context for f in result.findings}
    assert context["j.marsh@hollowpines.com"]["left_on"] == "2026-09-12"
    assert context["j.marsh@hollowpines.com"]["last_sign_in"] == "2026-10-30T19:42:00Z"
    assert context["j.marsh@hollowpines.com"]["seats"] == "Belfry CRM, Crypt Docs"
    assert context["p.lindqvist@hollowpines.com"]["left_on"] == "2026-06-30"
    assert context["p.lindqvist@hollowpines.com"]["employment_type"] == "contractor"
    assert context["p.lindqvist@hollowpines.com"]["seats"] == "Lantern Chat"
    assert context["r.voss@hollowpines.com"]["left_on"] == "2026-08-01"
    assert context["r.voss@hollowpines.com"]["seats"] == "Ossuary Design"
    (voss,) = [f for f in result.findings if f.key == "r.voss@hollowpines.com"]
    assert {r.raw_key for r in voss.records if r.ledger == LedgerName.observed} == {"R.Voss+old@hollowpines.org"}
    assert context["svc-reporting@hollowpines.com"]["hr_roster"] == "no record"
    assert context["temp.contractor@hollowpines.com"]["seats"] == "Belfry CRM"
    assert "systems" not in context["temp.contractor@hollowpines.com"]
    assert context["noor.haddad@hollowpines.com"]["person"] == "Noor Haddad"
    assert context["e.castell@hollowpines.com"]["seats"] == "Crypt Docs"


def test_the_unnamed_lantern_chat_seats_are_unkeyed_billed_rows(tmp_path: Path) -> None:
    result, _ = evaluate(CONTROL, tmp_path, load_planted())
    unkeyed = [u for u in result.unkeyed if u.ledger == LedgerName.billed]
    assert [u.row_id for u in unkeyed] == [f"lantern-chat:unnamed-{n}" for n in (1, 2, 3)]
    assert sum(u.amount or 0 for u in unkeyed) == result.billed_unkeyed == 24
    assert [n.text for n in result.notes] == [
        "Lantern Chat invoices 3 more seats than it assigns (178 invoiced, 175 assigned).",
        "Belfry CRM, Crypt Docs and Ossuary Design invoice exactly the seats they assign.",
    ]
    assert not (tmp_path / result.run_id / "seats.json").exists()


def test_the_planted_file_parses_as_written() -> None:
    planted = load_planted()
    (noor,) = [p for p in planted["planted"] if p["key"] == "noor.haddad@hollowpines.com"]
    assert noor["story"].startswith("Starts 2026-11-02 per HR.")
    assert noor["story"].endswith("so the joiner is reported.")
    assert planted["run_date"] == "2026-11-04" and run_time_of(planted).isoformat() == "2026-11-04T02:00:00+00:00"


def test_the_github_variant_without_a_token_is_incomplete_and_makes_no_request(tmp_path: Path) -> None:
    result = run(APP / "controls" / "staff-access-github.yaml", tmp_path, run_time_of(load_planted()))
    assert not result.complete and result.findings == []
    assert result.missing_ledgers == ["observed"]
    assert "not a GitHub organisation name" in result.ledger_errors["observed"]
