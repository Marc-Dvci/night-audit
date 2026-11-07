"""The control supplies the words (ui-kit Req 1)."""

from __future__ import annotations

import hashlib
import json
import string
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from nightaudit.control import ControlFile, region_labels, resolve_ui
from nightaudit.models import DEFAULT_REGION_LABELS, DEFAULT_REGION_NAMES, RunResult
from nightaudit.runner import run_control
from pydantic import ValidationError

LEDGERS: dict[str, Any] = {
    name: {"key_field": "id", "normalisers": ["strip", "lower"], "connector": {"type": "csv", "path": f"{name}.csv"}}
    for name in ("intended", "observed", "billed")
}

FULL_UI: dict[str, Any] = {
    "title": "Vampires",
    "tagline": "Every night, the account is checked.",
    "noun": {"singular": "resource", "plural": "resources"},
    "ledgers": {"billed": {"label": "Billed", "source": "Cost and Usage Report 2.0 line items."}},
    "columns": [{"label": "Resource", "from": "key"}, {"label": "Kind", "from": "attr:kind"}],
    "headlines": {
        "OB": {
            "one": "{count} Vampire is on the bill: {amount}.",
            "other": "{count} Vampires are on the bill: {amount}.",
        },
        "O": "{count} Poltergeist {noun} cost nothing.",
    },
}


def _control(ui: dict[str, Any] | None = None, **extra: Any) -> ControlFile:
    data: dict[str, Any] = {"id": "c", "title": "Test control", "ledgers": LEDGERS, **extra}
    if ui is not None:
        data["ui"] = ui
    return ControlFile.model_validate(data)


def test_a_full_ui_section_loads_and_resolves() -> None:
    ui = resolve_ui(_control(FULL_UI))
    assert ui.title == "Vampires"
    assert ui.noun.plural == "resources"
    assert [(c.label, c.from_) for c in ui.columns] == [("Resource", "key"), ("Kind", "attr:kind")]
    assert ui.headlines["OB"].one == "{count} Vampire is on the bill: {amount}."
    assert ui.headlines["O"].one == ui.headlines["O"].other == "{count} Poltergeist {noun} cost nothing."
    # A ledger the section leaves out keeps its default words.
    assert ui.ledgers["billed"].source == "Cost and Usage Report 2.0 line items."
    assert ui.ledgers["intended"].label == "Intended"


def test_a_control_without_ui_gets_neutral_defaults() -> None:
    ui = resolve_ui(_control())
    assert ui.title == "Test control"
    assert ui.tagline
    assert (ui.noun.singular, ui.noun.plural) == ("item", "items")
    assert set(ui.ledgers) == {"intended", "observed", "billed"}
    assert [c.from_ for c in ui.columns] == ["key", "status", "amount"]
    assert set(ui.headlines) == {"OB", "B", "IB", "I", "O"}


def test_default_headlines_speak_in_plain_words_not_region_names() -> None:
    """A reader never needs a region's Halloween name to read the headline (product rules)."""
    ui = resolve_ui(_control(regions={"OB": {"name": "Ghost"}}))
    for code, headline in ui.headlines.items():
        for text in (headline.one, headline.other):
            assert "Ghost" not in text and DEFAULT_REGION_NAMES[code] not in text, text
            assert "{noun}" in text
    assert ui.headlines["OB"].one.startswith("{count} {noun} exists")
    assert ui.headlines["OB"].other.startswith("{count} {noun} exist ")


def test_a_region_name_with_braces_cannot_add_a_slot() -> None:
    ui = resolve_ui(_control(regions={"OB": {"name": "{amount}", "label": "{owner}"}}))
    for text in (ui.headlines["OB"].one, ui.headlines["OB"].other):
        fields = [name for _, name, _, _ in string.Formatter().parse(text) if name is not None]
        assert sorted(fields) == ["amount", "count", "noun"]


def test_a_region_label_enters_the_control_hash_only_when_it_is_set() -> None:
    plain = _control(regions={"OB": {"name": "Vampire"}})
    labelled = _control(regions={"OB": {"name": "Vampire", "label": "Running and billed, never approved"}})
    data = plain.model_dump(mode="json")
    data.pop("ui")
    data.pop("summarisers")
    data["regions"]["OB"].pop("label")
    before_labels = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert plain.canonical_hash() == before_labels
    assert labelled.canonical_hash() != plain.canonical_hash()


def test_region_labels_come_from_the_control_then_its_own_names_then_the_defaults() -> None:
    config = _control(
        regions={"OB": {"name": "Vampire", "label": "Billed, never approved"}, "O": {"name": "Hand-written"}}
    ).to_config()
    labels = region_labels(config)
    assert labels["OB"] == "Billed, never approved"
    assert labels["O"] == "Hand-written"  # a control's own plain name is its label
    assert labels["B"] == DEFAULT_REGION_LABELS["B"]
    assert region_labels(_control(regions={"I": {"name": "Skeleton"}}).to_config())["I"] == DEFAULT_REGION_LABELS["I"]


@pytest.mark.parametrize(
    "ui",
    [
        {"columns": [{"label": "X", "from": "owner"}]},
        {"columns": [{"label": "X", "from": "attr:"}]},
        {"headlines": {"OB": "{count} with {owner}"}},
        {"headlines": {"OB": "no count here {amount}"}},
        {"headlines": {"OB": "{count} Vampires, up 3 since yesterday"}},
        {"headlines": {"IOB": "{count} matched"}},
        {"ledgers": {"approved": {"label": "A", "source": "B"}}},
        {"subtitle": "not a field"},
    ],
)
def test_invalid_ui_sections_are_rejected(ui: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _control(ui)


def test_the_ui_section_is_part_of_the_control_hash() -> None:
    assert _control(FULL_UI).canonical_hash() != _control({**FULL_UI, "tagline": "Other words."}).canonical_hash()


def test_a_control_without_ui_keeps_its_previous_hash() -> None:
    control = _control()
    data = control.model_dump(mode="json")
    assert data.pop("ui") is None
    assert data.pop("summarisers") == []  # added by skeleton Req 10; left out of the hash while empty
    before_ui_kit = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert control.canonical_hash() == before_ui_kit


@pytest.mark.integration
def test_the_run_carries_the_resolved_ui(tmp_path: Path) -> None:
    for name in ("intended", "observed", "billed"):
        (tmp_path / f"{name}.csv").write_text("row_id,id,amount\nr1,a,1.00\n", encoding="utf-8")
    (tmp_path / "control.yaml").write_text(
        yaml.safe_dump({"id": "c", "ledgers": LEDGERS, "ui": FULL_UI}), encoding="utf-8"
    )
    result = run_control(tmp_path / "control.yaml", tmp_path / "runs", run_time=datetime(2026, 11, 4, tzinfo=UTC))
    assert result.ui.title == "Vampires"
    saved = RunResult.model_validate_json((tmp_path / "runs" / result.run_id / "result.json").read_text("utf-8"))
    assert saved.ui == result.ui
    assert '"from":"key"' in saved.model_dump_json()


def test_a_run_saved_before_the_ui_kit_still_loads() -> None:
    old = RunResult(run_id="0" * 16, run_time=datetime(2026, 11, 4, tzinfo=UTC), control_hash="h", complete=True)
    data = old.model_dump(mode="json")
    data.pop("ui")
    assert RunResult.model_validate(data).ui.title == "Night Audit"
