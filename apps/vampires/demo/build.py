"""Run the three demo nights and export them as static files for the no-login demo.

Writes ``runs/demo`` (the API's runs folder) and ``skeleton/web/public/demo/vampires/``:

* ``runs.json``: the run summaries, newest first,
* ``<run id>/run.json``: the run as the page reads it (the result plus its ``view``),
* ``<run id>/evidence.jsonl`` and ``manifest.json``: the evidence pack, for "Verify this night" (Req 6.5),
* ``<run id>/report.html``: the morning report, marked as a recorded run (Req 7.2, 8.3),
* ``<run id>/evidence.zip``: the pack as one download.

It writes nothing else: ``apps.json`` and the other apps' demos belong to ``scripts/build_demos.py``.

Rebuild every demo: ``uv run python scripts/build_demos.py``.
This app only: ``uv run python apps/vampires/demo/build.py``
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nightaudit.demo import export_run, replace_folder, write_runs_json
from nightaudit.runner import run_control

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
APP = "vampires"
RUNS = ROOT / "runs" / "demo"
DEMO_ROOT = ROOT / "skeleton" / "web" / "public" / "demo"
TARGET = DEMO_ROOT / APP
NIGHTS = [
    ("night-1", datetime(2026, 11, 4, 2, 0, tzinfo=UTC)),
    ("night-2", datetime(2026, 11, 5, 2, 0, tzinfo=UTC)),
    ("night-3", datetime(2026, 11, 6, 2, 0, tzinfo=UTC)),
]
#: This app's entries in ``apps.json``: the live API and this recorded demo. The live entry comes first.
APP_ENTRIES = [
    {"name": "vampires", "title": "Vampires", "mode": "live", "base": "api/"},
    {"name": "vampires-demo", "title": "Vampires demo account", "mode": "demo", "base": f"demo/{APP}/"},
]
#: A fixed zip timestamp, so a rebuild with the same inputs writes the same bytes.
ZIP_TIME = (2026, 11, 6, 2, 0, 0)


def build(target: Path = TARGET, runs: Path = RUNS) -> list[str]:
    """Run the three nights into *runs*, export them into *target*, and return the run ids, oldest first."""
    replace_folder(runs, DEMO_ROOT, APP)
    replace_folder(target, DEMO_ROOT, APP)
    run_ids = []
    for folder, when in NIGHTS:
        result = run_control(HERE / folder / "control.yaml", runs, run_time=when)
        run_ids.append(result.run_id)
        print(f"vampires {folder}: run {result.run_id}, {len(result.findings)} findings, pending {result.pending_keys}")
    for run_id in run_ids:
        export_run(runs, run_id, target / run_id, ZIP_TIME)
    write_runs_json(runs, run_ids, target)
    print(f"vampires demo written to {target}")
    return run_ids


def main() -> int:
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
