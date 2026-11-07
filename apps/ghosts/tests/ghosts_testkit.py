"""Helpers shared by the Ghosts tests: the shipped control pointed at other data, and fixed run times."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

APP = Path(__file__).resolve().parents[1]
CONTROL = APP / "controls" / "staff-access.yaml"
FIXTURES = APP / "tests" / "fixtures"
DATA = APP / "data"
RUN_TIME = datetime(2026, 11, 4, 2, 0, tzinfo=UTC)
_PATH_OPTIONS = ("path", "assignments", "invoice", "roster")


def control_for(data_dir: Path, folder: Path, today: str = "2026-11-04", name: str = "control.yaml") -> Path:
    """Write the shipped Hollow Pines control into *folder*, reading its files from *data_dir* (absolute paths).

    Only the file locations and the run date change; the ledgers, normalisers, regions and words stay the shipped ones.
    """
    raw: dict[str, Any] = yaml.safe_load(CONTROL.read_text(encoding="utf-8"))

    def relocate(options: dict[str, Any]) -> None:
        for option in _PATH_OPTIONS:
            if option in options:
                options[option] = str(data_dir / str(options[option]).removeprefix("../data/"))

    for ledger in raw["ledgers"].values():
        for source in ledger["sources"]:
            relocate(source["options"])
            if "today" in source["options"]:
                source["options"]["today"] = today
    for enricher in raw.get("enrichers", []):
        relocate(enricher["options"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path
