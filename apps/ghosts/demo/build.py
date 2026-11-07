"""Run Hollow Pines on two nights and export them as static files for the no-login demo (Req 7.2).

* Night of 2026-11-04: the planted company. Its review sheet is a download, and no decision is recorded yet.
* Night of 2026-11-05: the same data a day later, so every finding persists. An IT manager has decided three findings
  on the review sheet, and the decisions are imported through ``ghosts.review`` with a fixed clock, so the page shows
  each one with its reviewer and date.

Each night's folder holds the files the skeleton's ``nightaudit.demo.export_run`` writes, including ``review.csv`` and
``review.html`` (the control's downloads) and, on the second night, ``decisions.jsonl``.

The target is ``skeleton/web/public/demo/ghosts/``; nothing else is written there. Every person and decision is
synthetic.

Rebuild every demo: ``uv run python scripts/build_demos.py``. This app only: ``uv run python apps/ghosts/demo/build.py``
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from pathlib import Path

from ghosts.review import COLUMNS, import_sheet, load_result, neutralise, review_rows
from ghosts.run import run
from nightaudit.demo import export_run, replace_folder, write_runs_json

HERE = Path(__file__).resolve().parent
APP_DIR = HERE.parent
ROOT = HERE.parents[2]
APP = "ghosts"
CONTROL = APP_DIR / "controls" / "staff-access.yaml"
RUNS = ROOT / "runs" / "ghosts-demo"
DEMO_ROOT = ROOT / "skeleton" / "web" / "public" / "demo"
TARGET = DEMO_ROOT / APP
NIGHTS = [datetime(2026, 11, 4, 2, 0, tzinfo=UTC), datetime(2026, 11, 5, 2, 0, tzinfo=UTC)]
APP_ENTRIES = [{"name": "ghosts-demo", "title": "Ghosts demo company", "mode": "demo", "base": f"demo/{APP}/"}]
#: A fixed zip timestamp, so a rebuild with the same inputs writes the same bytes.
ZIP_TIME = (2026, 11, 5, 2, 0, 0)
RUN_FILES = ("run.json", "report.html", "evidence.jsonl", "manifest.json", "evidence.zip", "review.csv", "review.html")
#: The synthetic reviewer and the three decisions recorded against the second night.
REVIEWER = "Dana Okafor, IT manager"
DECIDED_ON = "2026-11-05"
IMPORTED_AT = datetime(2026, 11, 5, 15, 30, tzinfo=UTC)
DECISIONS = {
    "j.marsh@hollowpines.com": "revoke",
    "p.lindqvist@hollowpines.com": "revoke",
    "svc-reporting@hollowpines.com": "investigate",
}


def decided_sheet(run_dir: Path) -> bytes:
    """The run's review sheet with the three decisions filled in, as the reviewer would return it."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(COLUMNS), lineterminator="\r\n")
    writer.writeheader()
    for row in review_rows(load_result(run_dir)):
        if row["person"] in DECISIONS:
            row = {**row, "decision": DECISIONS[row["person"]], "decision_date": DECIDED_ON}
        writer.writerow({k: neutralise(v) for k, v in row.items()})
    return buffer.getvalue().encode("utf-8")


def build(target: Path = TARGET, runs: Path = RUNS) -> list[str]:
    """Run both nights into *runs*, record the decisions, export into *target*; return the run ids, oldest first."""
    replace_folder(runs, DEMO_ROOT, APP)
    replace_folder(target, DEMO_ROOT, APP)
    run_ids: list[str] = []
    for when in NIGHTS:
        result = run(CONTROL, runs, when)
        findings = [f for f in result.findings if not f.informational]
        print(f"ghosts {when.date()}: run {result.run_id}, {len(findings)} findings, "
              f"{len(result.findings) - len(findings)} informational, pending {result.pending_keys}")
        run_ids.append(result.run_id)
    second = runs / run_ids[-1]
    sheet = runs / "decided-review.csv"
    sheet.write_bytes(decided_sheet(second))
    rows = import_sheet(second, sheet, REVIEWER, clock=lambda: IMPORTED_AT)
    print(f"ghosts: {len(rows)} decisions recorded by {REVIEWER}")
    for run_id in run_ids:
        export_run(runs, run_id, target / run_id, ZIP_TIME)
    write_runs_json(runs, run_ids, target)
    print(f"ghosts demo written to {target}")
    return run_ids


def main() -> int:
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
