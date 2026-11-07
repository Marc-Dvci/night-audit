"""The Hollow Pines control declares what Requirement 1.1 and 7.2 ask for, and the skeleton loads it unchanged."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from nightaudit.control import region_names, resolve_ui
from nightaudit.runner import load_control_file, run_control

CONTROLS = Path(__file__).resolve().parents[1] / "controls"
ALL = [CONTROLS / "staff-access.yaml", CONTROLS / "staff-access-github.yaml"]

EXPECTED_NAMES = {
    "OB": "Ghost",
    "O": "Poltergeist",
    "B": "Phantom seat",
    "I": "Unprovisioned joiner",
    "IB": "Wraith",
    "IO": "Unlicensed user",
    "IOB": "Living",
}


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_the_control_declares_the_people_rules(path: Path) -> None:
    control = load_control_file(path)
    assert control.app == "ghosts"
    assert control.grace_hours == 72
    assert control.alias_domains == {"hollowpines.org": "hollowpines.com"}
    assert {name: ledger.normalisers for name, ledger in control.ledgers.items()} == {
        "intended": ["email_canonical"],
        "observed": ["email_canonical"],
        "billed": ["email_canonical"],
    }
    assert region_names(control.to_config()) == EXPECTED_NAMES


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_the_page_speaks_about_people(path: Path) -> None:
    control = load_control_file(path)
    ui = resolve_ui(control)
    assert ui.title == "Ghosts"
    assert (ui.noun.singular, ui.noun.plural) == ("person", "people")
    assert {k: v.label for k, v in ui.ledgers.items()} == {
        "intended": "HR roster",
        "observed": "Accounts",
        "billed": "Paid seats",
    }
    assert [(c.label, c.from_) for c in ui.columns] == [
        ("Person", "key"),
        ("Region", "name"),
        ("Systems", "context:systems"),
        ("Seats", "context:seats"),
        ("Left on", "context:left_on"),
        ("Last sign-in", "context:last_sign_in_on"),
        ("Manager", "context:manager"),
    ]
    assert control.ui is not None and set(control.ui.headlines) == {"OB", "B", "IB", "I", "O"}


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_the_enricher_inherits_the_controls_folder_and_alias_table(path: Path) -> None:
    control = load_control_file(path)
    (enricher,) = control.enrichers
    assert enricher.entry == "ghosts.context:people_context"
    assert enricher.options == {"roster": "../data/hr_roster.csv"}  # no alias table repeated (skeleton Req 10.3)
    assert set(enricher.regions) == {"OB", "O", "B", "I", "IB", "IO"}
    assert [s.entry for s in control.summarisers] == ["ghosts.seats:seat_notes"]


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_the_roster_date_is_the_run_date_not_an_option(path: Path) -> None:
    (roster,) = load_control_file(path).ledgers["intended"].sources
    assert "today" not in roster.options


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_the_lines_with_no_key_and_the_downloads_are_in_the_companys_words(path: Path) -> None:
    ui = resolve_ui(load_control_file(path))
    assert (ui.unkeyed.singular, ui.unkeyed.plural) == ("seat paid for nobody named", "seats paid for nobody named")
    assert "resource" not in ui.unkeyed.explanation
    assert [(d.label, d.file) for d in ui.downloads] == [
        ("Review sheet (CSV)", "review.csv"),
        ("Review sheet (HTML)", "review.html"),
    ]


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_every_finding_region_has_a_template_with_no_accusation(path: Path) -> None:
    control = load_control_file(path)
    for code in ("OB", "O", "B", "I", "IB", "IO"):
        template = control.regions[code].template
        assert template and template.startswith("{context:hr_status} "), code
        assert not any(ch.isdigit() for ch in template), code  # numbers come from the evidence
        assert not {"malicious", "stole", "fraud", "abuse"} & set(template.lower().split()), code


def test_the_github_variant_only_adds_one_observed_source() -> None:
    base = load_control_file(ALL[0])
    variant = load_control_file(ALL[1])
    assert variant.ledgers["intended"] == base.ledgers["intended"]
    assert variant.ledgers["billed"] == base.ledgers["billed"]
    assert variant.ledgers["observed"].sources[:-1] == base.ledgers["observed"].sources
    assert variant.ledgers["observed"].sources[-1].entry == "ghosts.github:GitHubMembers"
    assert variant.regions == base.regions and variant.ui == base.ui


def test_the_last_sign_in_column_shows_the_date_only_and_the_evidence_keeps_the_timestamp(tmp_path: Path) -> None:
    """Regression: the column showed the raw timestamp, which wrapped. The full value stays in the finding's context.

    Runs the offline control; the GitHub one needs a token and an organisation (its column is checked above).
    """
    path = CONTROLS / "staff-access.yaml"
    result = run_control(path, tmp_path / "runs", run_time=datetime(2026, 11, 4, 2, 0, tzinfo=UTC))
    (column,) = [c for c in result.ui.columns if c.label == "Last sign-in"]
    source = column.from_.removeprefix("context:")
    shown = [(f.context[source], f.context["last_sign_in"]) for f in result.findings if f.context.get("last_sign_in")]
    assert shown, "the demo data has findings with a recorded sign-in"
    for cell, full in shown:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", cell), cell
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", full), full
        assert full.startswith(cell)
