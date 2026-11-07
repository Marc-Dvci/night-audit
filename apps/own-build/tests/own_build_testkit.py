"""Helpers shared by the own-build tests: the shipped control pointed at other data, tiny repositories, fixed run time."""

from __future__ import annotations

import csv
import importlib.util
import io
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from nightaudit.models import RunResult
from nightaudit.runner import run_control
from own_build.paths import spec_paths

APP = Path(__file__).resolve().parents[1]
CONTROL = APP / "controls" / "own-build.yaml"
CASEBOOK = APP / "casebook" / "cases.yaml"
FIXTURES = APP / "tests" / "fixtures"
DATA = APP / "data"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
#: The first 02:00 UTC after the recorded snapshot; the committed demo night.
RUN_TIME = datetime(2026, 11, 8, 2, 0, tzinfo=UTC)
_PATH_OPTIONS = ("path", "files", "sessions")


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


def control_for(data_dir: Path, folder: Path, name: str = "control.yaml") -> Path:
    """Write the shipped own-build control into *folder*, reading its files from *data_dir* (absolute paths).

    Only the file locations change; the ledgers, normalisers, regions and words stay the shipped ones.
    """
    raw: dict[str, Any] = yaml.safe_load(CONTROL.read_text(encoding="utf-8"))

    def relocate(options: dict[str, Any]) -> None:
        for option in _PATH_OPTIONS:
            if option in options:
                options[option] = str(data_dir / str(options[option]).removeprefix("../data/"))

    for ledger in raw["ledgers"].values():
        for source in ledger["sources"]:
            relocate(source["options"])
    for step in raw.get("summarisers", []):
        relocate(step.setdefault("options", {}))
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


def _csv(header: list[str], rows: list[list[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def write_repository(folder: Path, specs: dict[str, str], tracked: list[str], kiro: list[dict[str, str]]) -> Path:
    """Write the four recorded files of a tiny repository into *folder* and return it.

    *specs* maps ``<spec>/<document>`` to markdown; the promises are read out of it with the real parser. Every Kiro
    session named by a row gets a sessions row whose credits are the sum of its shares (blank when all are blank).
    """
    folder.mkdir(parents=True, exist_ok=True)
    started = "2026-11-07T00:00:00.000Z"
    promises = sorted({(file, *key.split("/", 1)) for key, text in specs.items() for file in spec_paths(text)})
    (folder / "spec-files.csv").write_text(
        _csv(["file", "spec", "doc", "commit"], [[f, s, d, COMMIT] for f, s, d in promises]), encoding="utf-8"
    )
    (folder / "tracked-files.csv").write_text(
        _csv(["file", "commit"], [[p, COMMIT] for p in sorted(tracked)]), encoding="utf-8"
    )
    (folder / "kiro-files.csv").write_text(
        _csv(
            ["file", "session", "credit_share", "started"],
            [[r["file"], r["session"], r.get("credit_share", ""), started] for r in kiro],
        ),
        encoding="utf-8",
    )
    sessions: dict[str, list[str]] = {}
    for row in kiro:
        sessions.setdefault(row["session"], []).append(row.get("credit_share", ""))
    session_rows = []
    for session, shares in sorted(sessions.items()):
        given = [s for s in shares if s]
        credits = format(sum((Decimal(s) for s in given), Decimal(0)), "f") if given else ""
        session_rows.append([session, started, "claude-sonnet-5.5", str(len(shares)), credits])
    (folder / "kiro-sessions.csv").write_text(
        _csv(["session", "started", "model", "files_touched", "credits"], session_rows), encoding="utf-8"
    )
    return folder


def run_in(data_dir: Path, work: Path, at: datetime = RUN_TIME) -> RunResult:
    """Run the shipped control over *data_dir*, writing under *work*."""
    return run_control(control_for(data_dir, work / "control"), work / "runs", run_time=at)
