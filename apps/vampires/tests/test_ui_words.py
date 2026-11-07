"""The Vampires controls ship their words (ui-kit Req 1.4, 8.2)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from nightaudit.control import region_labels, resolve_ui
from nightaudit.models import DEFAULT_REGION_NAMES
from nightaudit.runner import load_control_file

APP = Path(__file__).resolve().parents[1]
DEMO_CONTROLS = sorted((APP / "demo").glob("night-*/control.yaml"))
ALL_CONTROLS = [APP / "controls" / "aws-account.yaml", *DEMO_CONTROLS]
#: The plain label a reader sees first for each region; the Halloween name is only a tag beside it.
LABELS = {
    "OB": "Running and billed, never approved",
    "O": "Exists, never approved, free",
    "B": "Billed, nothing to see",
    "I": "Approved, but gone",
    "IB": "Approved and billed, not seen",
    "IO": "Approved and present, not billed yet",
    "IOB": "Matched",
}


@pytest.mark.parametrize("path", ALL_CONTROLS, ids=lambda p: p.parent.name + "/" + p.name)
def test_each_vampires_control_declares_its_words(path: Path) -> None:
    control = load_control_file(path)
    assert control.ui is not None
    ui = resolve_ui(control)
    assert ui.title == "Cloud account"
    assert (ui.noun.singular, ui.noun.plural) == ("resource", "resources")
    assert set(control.ui.headlines) == {"OB", "B", "IB", "I", "O"}
    assert set(control.ui.ledgers) == {"intended", "observed", "billed"}
    assert region_labels(control.to_config()) == LABELS
    for headline in control.ui.headlines.values():
        for text in (headline.one, headline.other):
            assert not any(name in text for name in DEFAULT_REGION_NAMES.values()), text


def test_the_demo_nights_share_one_vocabulary() -> None:
    assert len(DEMO_CONTROLS) == 3
    vocabularies = {load_control_file(p).ui.model_dump_json() for p in DEMO_CONTROLS}  # type: ignore[union-attr]
    assert len(vocabularies) == 1


@pytest.mark.parametrize("path", DEMO_CONTROLS, ids=lambda p: p.parent.name)
def test_demo_attribute_columns_name_real_attributes(path: Path) -> None:
    ui = resolve_ui(load_control_file(path))
    headers: set[str] = set()
    for name in ("intended", "observed", "billed"):
        with (path.parent / f"{name}.csv").open(encoding="utf-8", newline="") as handle:
            headers.update(next(csv.reader(handle)))
    for column in ui.columns:
        if column.from_.startswith("attr:"):
            assert column.from_.split(":", 1)[1] in headers
        assert not column.from_.startswith("context:"), "the demo has no CloudTrail context"
