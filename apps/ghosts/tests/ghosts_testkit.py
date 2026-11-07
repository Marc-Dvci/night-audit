"""Helpers shared by the Ghosts tests: the shipped control pointed at other data, and fixed run times."""

from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

import yaml
from nightaudit.connectors import Connector

APP = Path(__file__).resolve().parents[1]
CONTROL = APP / "controls" / "staff-access.yaml"
FIXTURES = APP / "tests" / "fixtures"
DATA = APP / "data"
RUN_TIME = datetime(2026, 11, 4, 2, 0, tzinfo=UTC)
_PATH_OPTIONS = ("path", "assignments", "invoice", "roster")


def _windows_text() -> Any:
    """The skeleton's ``windows_text`` test helper, loaded by path so this app's tests also run on their own."""
    path = APP.parents[1] / "skeleton" / "tests" / "windows_text.py"
    spec = importlib.util.spec_from_file_location("windows_text", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: A context manager inside which files and zip entries are written as Windows writes them.
as_windows = _windows_text().as_windows


def on[C: Connector](day: str, connector: C) -> C:
    """The connector as the runner hands it over: bound to 02:00 UTC on *day* (skeleton Req 10.1)."""
    connector.bind_run_time(datetime.combine(date.fromisoformat(day), time(2, 0), tzinfo=UTC))
    return connector


def control_for(data_dir: Path, folder: Path, name: str = "control.yaml") -> Path:
    """Write the shipped Hollow Pines control into *folder*, reading its files from *data_dir* (absolute paths).

    Only the file locations change; the ledgers, normalisers, regions and words stay the shipped ones. The run date is
    the run's time, as in production.
    """
    raw: dict[str, Any] = yaml.safe_load(CONTROL.read_text(encoding="utf-8"))

    def relocate(options: dict[str, Any]) -> None:
        for option in _PATH_OPTIONS:
            if option in options:
                options[option] = str(data_dir / str(options[option]).removeprefix("../data/"))

    for ledger in raw["ledgers"].values():
        for source in ledger["sources"]:
            relocate(source["options"])
    for step in [*raw.get("enrichers", []), *raw.get("summarisers", [])]:
        relocate(step.setdefault("options", {}))
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path
