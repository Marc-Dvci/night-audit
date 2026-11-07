"""Nights recorded before plain labels are shown in plain words, as presentation only (product rules: plain words first).

A run whose stored control carries no ``label`` for a region takes that region's plain label, and its headline
template, from its app's current control, and from the built-in plain words when the app has none. The Halloween name
stays as the small tag. Nothing stored changes, and every number the rebuilt headline prints is checked against the
evidence like any headline.
"""

from __future__ import annotations

import hashlib
import html
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from nightaudit.api import create_app, run_document
from nightaudit.control import DEFAULT_HEADLINES
from nightaudit.demo import export_run
from nightaudit.evidence import verify_evidence_pack, write_evidence_pack
from nightaudit.models import DEFAULT_REGION_LABELS, DEFAULT_REGION_NAMES, RunResult
from nightaudit.report import headline_sentences, report_html, run_view
from nightaudit.runner import load_run
from nightaudit.wording import BUILT_IN_WORDS, load_words, repo_app_words

ROOT = Path(__file__).resolve().parents[2]
#: The real lab night of 7 Nov, when a local copy of it exists (``runs/`` is not tracked).
LAB_NIGHT = ROOT / "runs" / "live" / "55e91b128f42ee31"

#: The lab night's headline in today's plain words of the Cloud account control: the figures are its own.
LAB_PLAIN = [
    "3 resources are running and on the bill with no approval: $0.7172 so far.",
    "2 resources exist with no approval and cost nothing.",
    "1 approved resource is gone.",
]


def _writer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("write_parity_fixture", ROOT / "scripts" / "write_parity_fixture.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WRITER = _writer()


@pytest.fixture()
def night() -> RunResult:
    night: RunResult = WRITER.lab_shaped_night()
    return night


def _vampires_labels() -> dict[str, str]:
    return load_words([WRITER.VAMPIRES_CONTROL])["vampires"].labels


def _stored(path: Path) -> dict[str, str]:
    return {
        p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in path.rglob("*")
        if p.is_file()
    }


def _save(result: RunResult, runs: Path) -> Path:
    folder = runs / result.run_id
    write_evidence_pack(result, folder / "evidence")
    (folder / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return folder


# --- The words ------------------------------------------------------------------------------------------------------


def test_a_night_stored_without_labels_reads_in_its_apps_current_plain_words(night: RunResult) -> None:
    view = run_view(night, WRITER.lab_words())
    assert view.headline_sentences == LAB_PLAIN
    assert view.headline == " ".join(LAB_PLAIN)
    assert view.region_labels == _vampires_labels()
    assert view.region_labels["OB"] == "Running and billed, never approved"
    assert not any(name in view.headline for name in DEFAULT_REGION_NAMES.values())


def test_a_night_of_an_app_with_no_current_control_reads_in_the_built_in_plain_words(night: RunResult) -> None:
    for words in (None, {}, {"ghosts": load_words([WRITER.VAMPIRES_CONTROL])["vampires"]}):
        view = run_view(night, words)
        assert view.region_labels == DEFAULT_REGION_LABELS
        assert view.headline_sentences == [
            "3 resources exist and are on the bill with no approval: $0.7172.",
            "2 resources exist with no approval and cost nothing.",
            "1 approved resource is gone and unbilled.",
        ]
    assert {c: (h.one, h.other) for c, h in BUILT_IN_WORDS.headlines.items()} == DEFAULT_HEADLINES


def test_only_the_regions_without_a_stored_label_take_the_current_words(night: RunResult) -> None:
    labelled = night.model_copy(update={"region_labels": {"OB": "Billed and nobody approved it"}})
    view = run_view(labelled, WRITER.lab_words())
    assert view.region_labels == {**_vampires_labels(), "OB": "Billed and nobody approved it"}
    # The labelled region keeps its stored template; the others are rebuilt.
    assert view.headline_sentences == [
        "3 Vampires are running and on the bill with no approval: $0.7172 so far.",
        *LAB_PLAIN[1:],
    ]


def test_a_night_stored_with_labels_keeps_every_stored_word(night: RunResult) -> None:
    labels = {code: f"Stored {code}" for code in DEFAULT_REGION_LABELS}
    stored = night.model_copy(update={"region_labels": labels})
    view = run_view(stored, WRITER.lab_words())
    assert view.region_labels == labels
    assert view.headline_sentences == [
        "3 Vampires are running and on the bill with no approval: $0.7172 so far.",
        "2 Poltergeists cost nothing.",
        "1 declared resource is gone.",
    ]


def test_the_halloween_name_stays_as_the_small_tag_in_the_morning_report(night: RunResult) -> None:
    report = report_html(night, words=WRITER.lab_words())
    assert html.escape(" ".join(LAB_PLAIN), quote=True) in report
    assert 'Running and billed, never approved <span class="tag">Vampire</span>' in report
    assert 'Exists, never approved, free <span class="tag">Poltergeist</span>' in report
    assert "Vampires are running" not in report


# --- Nothing stored changes -----------------------------------------------------------------------------------------


def test_the_page_holds_the_stored_run_unchanged_and_only_its_view_is_rebuilt(night: RunResult) -> None:
    document = run_document(night, words=WRITER.lab_words())
    view = document.pop("view")
    document.pop("downloads")
    assert document == json.loads(night.model_dump_json())
    assert document["region_labels"] == {} and document["ui"]["headlines"]["OB"]["other"].startswith("{count} Vampires")
    assert view["headline_sentences"] == LAB_PLAIN


@pytest.mark.integration
def test_the_api_the_static_demo_and_the_report_show_the_same_plain_words(night: RunResult, tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    folder = _save(night, runs)
    before = _stored(folder)
    words = WRITER.lab_words()
    http = TestClient(create_app(runs, words=words))
    served = http.get(f"/api/runs/{night.run_id}").json()
    latest = http.get("/api/latest").json()
    report = http.get(f"/api/runs/{night.run_id}/report.html").text
    export_run(runs, night.run_id, tmp_path / "static", (2026, 11, 7, 2, 0, 0), words=words)
    static = json.loads((tmp_path / "static" / "run.json").read_text(encoding="utf-8"))

    for document in (served, latest, static):
        assert document["view"]["headline_sentences"] == LAB_PLAIN
        assert document["view"]["region_labels"] == _vampires_labels()
    assert html.escape(" ".join(LAB_PLAIN), quote=True) in report
    assert html.escape(" ".join(LAB_PLAIN), quote=True) in (tmp_path / "static" / "report.html").read_text("utf-8")
    assert _stored(folder) == before, "showing a night writes nothing into it"
    assert verify_evidence_pack(folder / "evidence", served).ok
    assert verify_evidence_pack(tmp_path / "static", static).ok


def test_the_repository_reads_the_current_words_of_every_app() -> None:
    words = repo_app_words(ROOT)
    assert {"vampires", "ghosts", "own-build"} <= set(words)
    assert words["vampires"].labels == _vampires_labels()


# --- Every number shown is still checked -----------------------------------------------------------------------------


def test_the_rebuilt_headline_is_checked_against_the_evidence_like_any_headline() -> None:
    case: dict[str, Any] = json.loads(WRITER.build())["pack"]["relabelled"]
    verdicts = {d["name"]: d["verdict"] for d in case["displayed"]}
    assert verdicts.pop("a night stored without labels, served in plain words")["ok"]
    served = case["displayed"][0]["document"]
    assert served["view"]["headline_sentences"] == LAB_PLAIN
    assert set(verdicts) == {
        "its plain headline with the lead count changed",
        "its plain headline with the last count changed",
        "its plain headline with the amount rounded wrongly",
        "its plain headline with the amount written without a dollar sign",
    }
    for name, verdict in verdicts.items():
        assert not verdict["ok"], name
        assert "headline: the page shows" in verdict["detail"], name
    assert "the number 13" in verdicts["its plain headline with the lead count changed"]["detail"]
    assert "the number 4" in verdicts["its plain headline with the last count changed"]["detail"]
    assert "$0.7173" in verdicts["its plain headline with the amount rounded wrongly"]["detail"]


# --- The real lab night ----------------------------------------------------------------------------------------------


@pytest.mark.skipif(not (LAB_NIGHT / "result.json").is_file(), reason="no local copy of the lab night 55e91b128f42ee31")
def test_the_lab_night_of_7_nov_reads_in_plain_words_with_the_same_figures() -> None:
    before = _stored(LAB_NIGHT)
    result = load_run(LAB_NIGHT.parent, LAB_NIGHT.name)
    assert result.region_labels == {}
    words = repo_app_words(ROOT)
    assert headline_sentences(result, words) == LAB_PLAIN
    document = run_document(result, LAB_NIGHT, words)
    assert document["view"]["region_labels"] == _vampires_labels()
    assert verify_evidence_pack(LAB_NIGHT / "evidence", document).ok
    # The figures of the night: 3 running and billed, 2 present and free, 1 gone, $0.7172 so far.
    counts = {c: s.key_count for c, s in result.region_summaries.items()}
    assert (counts["OB"], counts["O"], counts["I"]) == (3, 2, 1)
    assert str(result.region_summaries["OB"].billed_amount) == "0.7172358"
    assert _stored(LAB_NIGHT) == before
