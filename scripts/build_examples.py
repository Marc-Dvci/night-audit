"""Copy one finished Vampires demo night into ``examples/vampires-night/``, byte for byte.

The night is the third recorded night of the Vampires demo (6 Nov 2026, 02:00 UTC). The copy is:

* ``report.html``: the morning report,
* ``evidence.jsonl`` and ``manifest.json``: the evidence pack,
* ``run.json``: the run as the page shows it, which ``nightaudit verify`` compares with the pack,
* ``ledgers/intended.csv``, ``observed.csv`` and ``billed.csv``: the three ledger inputs of that night.

Run ``uv run python scripts/build_demos.py`` first if the demo changed, then ``uv run python scripts/build_examples.py``.
``skeleton/tests/test_examples.py`` fails when the copy differs from the committed demo.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "skeleton" / "web" / "public" / "demo" / "vampires"
INPUTS = ROOT / "apps" / "vampires" / "demo" / "night-3"
TARGET = ROOT / "examples" / "vampires-night"
LEDGERS = ("intended.csv", "observed.csv", "billed.csv")
RUN_FILES = ("report.html", "evidence.jsonl", "manifest.json", "run.json")


def night_run_id() -> str:
    """The run id of the newest demo night (``runs.json`` lists them newest first)."""
    runs = json.loads((DEMO / "runs.json").read_text(encoding="utf-8"))
    return str(runs[0]["run_id"])


def copies() -> list[tuple[Path, Path]]:
    """Each (source, destination) pair, in the order they are written."""
    run = DEMO / night_run_id()
    pairs = [(run / name, TARGET / name) for name in RUN_FILES]
    pairs += [(INPUTS / name, TARGET / "ledgers" / name) for name in LEDGERS]
    return pairs


def main() -> int:
    for source, destination in copies():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        print(f"{destination.relative_to(ROOT).as_posix()}  <-  {source.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
